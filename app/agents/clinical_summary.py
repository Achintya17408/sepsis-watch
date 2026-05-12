"""
LangGraph clinical summary agent.

Transforms structured ICU data (vitals, labs, SOFA score, comorbidities)
into an evidence-based clinical narrative.

Graph: prepare_context → call_llm → END

The graph is compiled once at module import and shared across all calls.

LLM priority order (set env vars to activate each path)
---------------------------------------------------------
1. Groq   (free cloud API, 14 400 req/day) — set GROQ_API_KEY.
   Default model: llama3-8b-8192  (override with GROQ_MODEL).
   Sign up free: https://console.groq.com
2. Anthropic Claude 3 Haiku       — set ANTHROPIC_API_KEY.
   Override model with ANTHROPIC_MODEL (default: claude-3-haiku-20240307).
3. Ollama (local only, free)       — set OLLAMA_MODEL (e.g. llama3).
   OLLAMA_HOST defaults to http://localhost:11434.
   ⚠  Will not work on cloud deployments — use Groq or Anthropic there.
4. Rule-based fallback             — always active; no key required.
"""
import logging
import os
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Comorbidity, LabResult, Patient, VitalReading

log = logging.getLogger(__name__)

# ── LangGraph state schema ───────────────────────────────────────────────────


class SummaryState(TypedDict):
    patient_name: str
    patient_age: Optional[int]
    ward: Optional[str]
    alert_level: str
    risk_score: float
    sofa_score: int
    vitals: Dict[str, Any]
    labs: Dict[str, Any]
    comorbidities: List[str]
    # Intermediate / output fields
    prompt: str
    summary: Optional[str]


# ── Node 1: compose the LLM prompt ──────────────────────────────────────────


def _prepare_context_node(state: SummaryState) -> SummaryState:
    """Pure transformation — formats clinical data into the prompt string."""
    v = state["vitals"]
    la = state["labs"]

    def _fmt(val: Any, unit: str = "", precision: int = 1) -> str:
        if val is None:
            return "N/A"
        try:
            return f"{float(val):.{precision}f}{unit}"
        except (TypeError, ValueError):
            return str(val)

    vitals_text = (
        f"  Heart Rate        : {_fmt(v.get('heart_rate'), ' bpm', 0)}\n"
        f"  Blood Pressure    : {_fmt(v.get('systolic_bp'), '', 0)}"
        f"/{_fmt(v.get('diastolic_bp'), ' mmHg', 0)}"
        f"  (MAP {_fmt(v.get('mean_arterial_bp'), ' mmHg', 0)})\n"
        f"  SpO₂              : {_fmt(v.get('spo2'), '%', 1)}\n"
        f"  Temperature       : {_fmt(v.get('temperature_c'), ' °C', 1)}\n"
        f"  Respiratory Rate  : {_fmt(v.get('respiratory_rate'), ' breaths/min', 0)}\n"
        f"  GCS               : {_fmt(v.get('gcs_total'), '/15', 0)}"
    )

    labs_text = (
        f"  Lactate           : {_fmt(la.get('lactate'), ' mmol/L')}  [normal <2.0]\n"
        f"  WBC               : {_fmt(la.get('wbc'), ' ×10³/µL')}  [normal 4.5–11]\n"
        f"  Creatinine        : {_fmt(la.get('creatinine'), ' mg/dL')}  [normal <1.2]\n"
        f"  Bilirubin (Total) : {_fmt(la.get('bilirubin_total'), ' mg/dL')}  [normal <1.2]\n"
        f"  Platelets         : {_fmt(la.get('platelets'), ' ×10³/µL')}  [normal 150–400]\n"
        f"  PaO₂/FiO₂        : {_fmt(la.get('pao2_fio2_ratio'), ' mmHg')}  [normal >400]\n"
        f"  INR               : {_fmt(la.get('inr'), '')}  [normal 0.8–1.2]"
    )

    comorbidities_text = (
        ", ".join(state["comorbidities"]) if state["comorbidities"] else "None documented"
    )

    prompt = f"""\
You are a clinical decision support AI embedded in an ICU sepsis early warning system.
A sepsis alert has been triggered. Write a concise, evidence-based clinical briefing
for the on-call physician receiving this notification.

━━━ PATIENT OVERVIEW ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Name    : {state['patient_name']}
Age     : {state['patient_age'] or 'Unknown'}
Ward    : {state['ward'] or 'Unknown'}
Alert   : {state['alert_level']}  |  Risk Score: {state['risk_score']:.0%}  |  SOFA: {state['sofa_score']}/24

━━━ LATEST VITALS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{vitals_text}

━━━ LATEST LABS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{labs_text}

━━━ KNOWN COMORBIDITIES ━━━━━━━━━━━━━━━━━━━━━━━━
{comorbidities_text}

INSTRUCTIONS:
Write exactly 3–4 sentences. Stop writing after the 4th sentence.
1. State the primary clinical concern and the severity of this sepsis alert.
2. Identify the two or three most abnormal findings supporting the alert.
3. Recommend immediate bedside or lab actions the physician should consider.

Constraints:
- Do NOT specify drug names or dosages.
- Do NOT invent data, patient names, or vital values beyond what is provided above.
- Do NOT repeat this prompt or write a second patient scenario.
- Write in a neutral, precise clinical register.
- Output only the briefing text — no headers, no bullet points, no repetition.
"""

    return {**state, "prompt": prompt}


# ── Node 2: call an LLM (Ollama → Anthropic → rule-based fallback) ──────────


def _call_llm_node(state: SummaryState) -> SummaryState:
    """
    Generate the clinical summary via the first available LLM path.

    Priority: Groq → Anthropic → Ollama → rule-based fallback.
    Each path is tried in order; errors fall through to the next.
    """
    prompt = state["prompt"]

    # ── Path 1: Groq (free cloud API — recommended for deployment) ────────
    groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_api_key:
        try:
            import groq as _groq  # lazy import

            groq_model = os.getenv("GROQ_MODEL", "llama3-8b-8192").strip()
            client_groq = _groq.Groq(api_key=groq_api_key)
            response_g = client_groq.chat.completions.create(
                model=groq_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=350,
                temperature=0.2,
            )
            text_g = response_g.choices[0].message.content.strip()
            log.info("Clinical summary via Groq/%s (%d chars)", groq_model, len(text_g))
            return {**state, "summary": text_g}
        except ImportError:
            log.error("groq package not installed — run: pip install groq")
        except Exception as exc:
            log.error("Groq error: %s — falling through to Anthropic", exc)

    # ── Path 2: Anthropic Claude ──────────────────────────────────────────
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if anthropic_key:
        try:
            import anthropic as _anthropic  # lazy import

            anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307").strip()
            client_anthropic = _anthropic.Anthropic(api_key=anthropic_key)
            response_a = client_anthropic.messages.create(
                model=anthropic_model,
                max_tokens=350,
                messages=[{"role": "user", "content": prompt}],
            )
            text_a = response_a.content[0].text.strip()
            log.info("Clinical summary via Anthropic/%s (%d chars)", anthropic_model, len(text_a))
            return {**state, "summary": text_a}
        except Exception as exc:
            log.error("Anthropic error: %s — falling through to Ollama", exc)

    # ── Path 3: Ollama (local only — not available on cloud) ─────────────
    ollama_model = os.getenv("OLLAMA_MODEL", "").strip()
    if ollama_model:
        try:
            import ollama as _ollama  # lazy import — not a hard dependency

            host = os.getenv("OLLAMA_HOST", "http://localhost:11434").strip()
            client_ollama = _ollama.Client(host=host)

            v = state["vitals"]
            la = state["labs"]
            comorbidities_text = (
                ", ".join(state["comorbidities"]) if state["comorbidities"] else "None documented"
            )

            def _fv(val: Any, unit: str = "") -> str:
                return f"{val}{unit}" if val is not None else "N/A"

            user_msg = (
                f"Patient: {state['patient_name']} | Alert: {state['alert_level']} | "
                f"Risk: {state['risk_score']:.0%} | SOFA: {state['sofa_score']}/24\n"
                f"Vitals — HR: {_fv(v.get('heart_rate'), ' bpm')}, "
                f"BP: {_fv(v.get('systolic_bp'))}/{_fv(v.get('diastolic_bp'))} mmHg, "
                f"SpO2: {_fv(v.get('spo2'), '%')}, Temp: {_fv(v.get('temperature_c'), '°C')}, "
                f"RR: {_fv(v.get('respiratory_rate'), ' /min')}, GCS: {_fv(v.get('gcs_total'), '/15')}\n"
                f"Labs — Creatinine: {_fv(la.get('creatinine'), ' mg/dL')}, "
                f"Lactate: {_fv(la.get('lactate'), ' mmol/L')}, "
                f"WBC: {_fv(la.get('wbc'), ' ×10³/µL')}, "
                f"Platelets: {_fv(la.get('platelets'), ' ×10³/µL')}\n"
                f"Comorbidities: {comorbidities_text}\n\n"
                "Write a 3-sentence clinical briefing for the on-call physician. "
                "Output only the 3 sentences, no headers."
            )
            response_o = client_ollama.chat(
                model=ollama_model,
                messages=[
                    {"role": "system", "content": (
                        "You are a clinical decision support AI for an ICU. "
                        "Write concise 3-sentence briefings using only the facts given. "
                        "Never invent data. Output only plain prose sentences."
                    )},
                    {"role": "user", "content": user_msg},
                ],
                options={"num_predict": 250, "temperature": 0.2},
            )
            text_o: str = response_o["message"]["content"].strip()
            sentences = [s.strip() for s in text_o.replace("\n", " ").split(".") if s.strip()]
            text_o = ". ".join(sentences[:4]).rstrip(".") + "." if sentences else text_o
            log.info("Clinical summary via Ollama/%s (%d chars)", ollama_model, len(text_o))
            return {**state, "summary": text_o}

        except ImportError:
            log.error("ollama package not installed — run: pip install ollama")
        except Exception as exc:
            log.error("Ollama/%s error: %s — falling through to rule-based", ollama_model, exc)

    if not groq_api_key and not anthropic_key and not ollama_model:
        log.warning("No LLM configured (GROQ_API_KEY / ANTHROPIC_API_KEY / OLLAMA_MODEL) — using rule-based summary")

    # ── Path 4: Rule-based fallback ───────────────────────────────────────
    v = state["vitals"]
    la = state["labs"]
    abnormal: list[str] = []
    if v.get("heart_rate") and v["heart_rate"] > 100:
        abnormal.append(f"tachycardia {v['heart_rate']:.0f} bpm")
    if v.get("mean_arterial_bp") and v["mean_arterial_bp"] < 65:
        abnormal.append(f"MAP {v['mean_arterial_bp']:.0f} mmHg")
    if v.get("spo2") and v["spo2"] < 94:
        abnormal.append(f"SpO₂ {v['spo2']:.0f}%")
    if v.get("temperature_c") and v["temperature_c"] > 38.3:
        abnormal.append(f"fever {v['temperature_c']:.1f}°C")
    if v.get("respiratory_rate") and v["respiratory_rate"] > 22:
        abnormal.append(f"RR {v['respiratory_rate']:.0f}/min")
    if v.get("gcs_total") and v["gcs_total"] < 13:
        abnormal.append(f"GCS {v['gcs_total']:.0f}/15")
    if la.get("creatinine") and la["creatinine"] > 1.2:
        abnormal.append(f"Cr {la['creatinine']:.1f} mg/dL")
    if la.get("lactate") and la["lactate"] >= 2.0:
        abnormal.append(f"Lactate {la['lactate']:.1f} mmol/L")

    abnormal_text = (
        f"Key findings: {', '.join(abnormal[:4])}." if abnormal else "Multiple parameters abnormal."
    )
    comorbidities_text = (
        f"Known comorbidities: {', '.join(state['comorbidities'][:3])}."
        if state["comorbidities"] else ""
    )
    fallback = (
        f"{state['alert_level']} sepsis alert for {state['patient_name']} — "
        f"SOFA {state['sofa_score']}/24, risk score {state['risk_score']:.0%}. "
        f"{abnormal_text} "
        f"{comorbidities_text} "
        "Immediate bedside review and labs recommended."
    ).strip()
    return {**state, "summary": fallback}


# ── Compile the graph once at module load ────────────────────────────────────


def _build_graph() -> Any:
    g: StateGraph = StateGraph(SummaryState)
    g.add_node("prepare_context", _prepare_context_node)
    g.add_node("call_llm", _call_llm_node)
    g.add_edge("prepare_context", "call_llm")
    g.add_edge("call_llm", END)
    g.set_entry_point("prepare_context")
    return g.compile()


_GRAPH = _build_graph()


# ── Public entry point ───────────────────────────────────────────────────────


async def generate_clinical_summary(
    patient: Patient,
    latest_vital: Optional[VitalReading],
    latest_lab: Optional[LabResult],
    sofa_score: int,
    risk_score: float,
    alert_level: str,
    db: AsyncSession,
) -> Optional[str]:
    """
    Fetch comorbidities, build state, run the LangGraph pipeline.
    Returns the generated clinical summary string, or None on unexpected failure.
    """
    # Fetch top 5 chronic comorbidities (ordered by MIMIC seq_num = clinical priority)
    comorbidities: List[str] = []
    try:
        c_res = await db.execute(
            select(Comorbidity.condition_name)
            .where(Comorbidity.patient_id == patient.id, Comorbidity.is_chronic == True)
            .order_by(Comorbidity.seq_num.asc().nulls_last())
            .limit(5)
        )
        comorbidities = [row[0] for row in c_res.fetchall()]
    except Exception as exc:
        log.warning("Could not fetch comorbidities for summary: %s", exc)

    vitals_dict: Dict[str, Any] = {}
    if latest_vital:
        vitals_dict = {
            "heart_rate": latest_vital.heart_rate,
            "systolic_bp": latest_vital.systolic_bp,
            "diastolic_bp": latest_vital.diastolic_bp,
            "mean_arterial_bp": latest_vital.mean_arterial_bp,
            "spo2": latest_vital.spo2,
            "respiratory_rate": latest_vital.respiratory_rate,
            "temperature_c": latest_vital.temperature_c,
            "gcs_total": latest_vital.gcs_total,
        }

    labs_dict: Dict[str, Any] = {}
    if latest_lab:
        labs_dict = {
            "wbc": latest_lab.wbc,
            "lactate": latest_lab.lactate,
            "creatinine": latest_lab.creatinine,
            "bilirubin_total": latest_lab.bilirubin_total,
            "platelets": latest_lab.platelets,
            "pao2_fio2_ratio": latest_lab.pao2_fio2_ratio,
            "inr": latest_lab.inr,
        }

    initial_state: SummaryState = {
        "patient_name": patient.name,
        "patient_age": patient.age,
        "ward": patient.ward,
        "alert_level": alert_level,
        "risk_score": risk_score,
        "sofa_score": sofa_score,
        "vitals": vitals_dict,
        "labs": labs_dict,
        "comorbidities": comorbidities,
        "prompt": "",
        "summary": None,
    }

    try:
        result: SummaryState = _GRAPH.invoke(initial_state)
        return result.get("summary")
    except Exception as exc:
        log.error("LangGraph pipeline failed: %s", exc, exc_info=True)
        return None
