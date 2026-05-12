"""
SOFA (Sequential Organ Failure Assessment) score computation.
All functions are **pure** — no I/O, no DB, no imports beyond stdlib.

Sepsis-3 definition (Singer et al., JAMA 2016):
  Sepsis    = life-threatening organ dysfunction caused by dysregulated host response to infection.
              Operationally: SOFA ≥ 2 points above baseline in a patient with suspected infection.
  Sep-shock = subset of sepsis with circulatory & cellular/metabolic abnormalities.

SOFA total range: 0–24  (6 organ systems × 0–4 points each).

References:
  Vincent JL et al. (1996) The SOFA score. Intensive Care Med.
  Singer M et al. (2016) The Third International Consensus Definitions for Sepsis. JAMA.
"""
from typing import Optional


# ── Individual organ-system sub-scores ──────────────────────────────────────

def sofa_respiratory(pao2_fio2_ratio: Optional[float]) -> int:
    """
    PaO₂/FiO₂ ratio (mmHg).  Normal ≥ 400.

    Score 0: ≥ 400 mmHg
    Score 1: 300–399
    Score 2: 200–299
    Score 3: 100–199  (requires mechanical ventilation in full Sepsis-3 definition)
    Score 4: < 100    (requires mechanical ventilation in full Sepsis-3 definition)

    Note: without ventilation data scores 3 & 4 are approximated from the ratio alone.
    """
    if pao2_fio2_ratio is None:
        return 0
    if pao2_fio2_ratio >= 400:
        return 0
    if pao2_fio2_ratio >= 300:
        return 1
    if pao2_fio2_ratio >= 200:
        return 2
    if pao2_fio2_ratio >= 100:
        return 3
    return 4


def sofa_coagulation(platelets: Optional[float]) -> int:
    """
    Platelet count (×10³/µL).  Normal ≥ 150.

    Score 0: ≥ 150
    Score 1: 100–149
    Score 2: 50–99
    Score 3: 20–49
    Score 4: < 20
    """
    if platelets is None:
        return 0
    if platelets >= 150:
        return 0
    if platelets >= 100:
        return 1
    if platelets >= 50:
        return 2
    if platelets >= 20:
        return 3
    return 4


def sofa_liver(bilirubin_total: Optional[float]) -> int:
    """
    Total bilirubin (mg/dL).  Normal < 1.2.

    Score 0: < 1.2
    Score 1: 1.2–1.9
    Score 2: 2.0–5.9
    Score 3: 6.0–11.9
    Score 4: ≥ 12.0
    """
    if bilirubin_total is None:
        return 0
    if bilirubin_total < 1.2:
        return 0
    if bilirubin_total < 2.0:
        return 1
    if bilirubin_total < 6.0:
        return 2
    if bilirubin_total < 12.0:
        return 3
    return 4


def sofa_cardiovascular(mean_arterial_bp: Optional[float]) -> int:
    """
    MAP (mmHg) — simplified version without vasopressor dose data.

    Full Sepsis-3 scoring considers type and dose of vasopressors (dopamine,
    noradrenaline, epinephrine, vasopressin). Without that data:
      Score 0: MAP ≥ 70 mmHg
      Score 1: MAP < 70 mmHg (hypotension; vasopressor need cannot be quantified)

    This is a conservative under-estimate; actual cardiovascular SOFA may be higher
    if vasopressors are in use.
    """
    if mean_arterial_bp is None:
        return 0
    return 0 if mean_arterial_bp >= 70.0 else 1


def sofa_cns(gcs_total: Optional[int]) -> int:
    """
    Glasgow Coma Scale total score (3–15).  15 = fully alert.

    Score 0: GCS 15
    Score 1: GCS 13–14
    Score 2: GCS 10–12
    Score 3: GCS 6–9
    Score 4: GCS < 6
    """
    if gcs_total is None:
        return 0
    if gcs_total == 15:
        return 0
    if gcs_total >= 13:
        return 1
    if gcs_total >= 10:
        return 2
    if gcs_total >= 6:
        return 3
    return 4


def sofa_renal(creatinine: Optional[float]) -> int:
    """
    Serum creatinine (mg/dL).  Normal < 1.2.

    Score 0: < 1.2
    Score 1: 1.2–1.9
    Score 2: 2.0–3.4
    Score 3: 3.5–4.9
    Score 4: ≥ 5.0

    Note: full scoring also considers urine output (< 0.5 mL/kg/h = score 3,
    < 0.2 mL/kg/h = score 4). Without urine output data this under-estimates
    renal score in oliguric/anuric patients.
    """
    if creatinine is None:
        return 0
    if creatinine < 1.2:
        return 0
    if creatinine < 2.0:
        return 1
    if creatinine < 3.5:
        return 2
    if creatinine < 5.0:
        return 3
    return 4


# ── Composite score ──────────────────────────────────────────────────────────

def compute_sofa(vitals: dict, labs: dict) -> int:
    """
    Compute total SOFA score (0–24).

    Expected keys (all optional — missing values score 0 conservatively):
      vitals: mean_arterial_bp (float, mmHg)
              gcs_total        (int, 3–15)
      labs:   pao2_fio2_ratio  (float, mmHg)
              platelets        (float, ×10³/µL)
              bilirubin_total  (float, mg/dL)
              creatinine       (float, mg/dL)
    """
    return (
        sofa_respiratory(labs.get("pao2_fio2_ratio"))
        + sofa_coagulation(labs.get("platelets"))
        + sofa_liver(labs.get("bilirubin_total"))
        + sofa_cardiovascular(vitals.get("mean_arterial_bp"))
        + sofa_cns(vitals.get("gcs_total"))
        + sofa_renal(labs.get("creatinine"))
    )


def sofa_to_score_and_level(sofa: int) -> tuple:
    """
    Map SOFA total to a (risk_score: float, alert_level: str) tuple.
    Used as the fallback risk estimator when the LSTM checkpoint is unavailable.

    Calibration (conservative; LSTM will be more precise when trained):
      SOFA 0–1  → 0.10  (no clinical concern — monitoring only)
      SOFA 2–4  → 0.35  LOW     (possible sepsis onset; Sepsis-3 threshold SOFA ≥ 2)
      SOFA 5–7  → 0.58  MEDIUM  (probable sepsis; significant organ dysfunction)
      SOFA 8–11 → 0.78  HIGH    (serious organ dysfunction; high mortality ~40–50%)
      SOFA 12+  → 0.93  CRITICAL (severe dysfunction; SOFA ≥12 carries ~60–80% mortality)
    """
    if sofa <= 1:
        return 0.10, "LOW"
    if sofa <= 4:
        return 0.35, "LOW"
    if sofa <= 7:
        return 0.58, "MEDIUM"
    if sofa <= 11:
        return 0.78, "HIGH"
    return 0.93, "CRITICAL"


# ── qSOFA bedside screener ───────────────────────────────────────────────────

def compute_qsofa(
    respiratory_rate: Optional[float],
    systolic_bp: Optional[float],
    gcs_total: Optional[int],
) -> int:
    """
    Quick SOFA (qSOFA) — 3-item point-of-care screening tool.
    Range 0–3.  Score ≥ 2 warrants full SOFA assessment and infection work-up.

    Components:
      +1 if respiratory rate ≥ 22 breaths/min
      +1 if systolic BP ≤ 100 mmHg
      +1 if altered mentation (GCS < 15)
    """
    score = 0
    if respiratory_rate is not None and respiratory_rate >= 22.0:
        score += 1
    if systolic_bp is not None and systolic_bp <= 100.0:
        score += 1
    if gcs_total is not None and gcs_total < 15:
        score += 1
    return score
