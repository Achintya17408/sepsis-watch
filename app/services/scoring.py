"""
Background scoring service.

Implements the core sepsis risk assessment pipeline:
  1. Fetch latest vitals + labs from DB
  2. Compute SOFA score (pure functions)
  3. Run LSTM inference if a checkpoint is registered (falls back to SOFA heuristic)
  4. Deduplication check — suppress alerts fired within the last 30 min
  5. Persist SepsisAlert
  6. Generate LangGraph clinical summary (best-effort)
  7. Route notifications to on-call doctors via Twilio

Called from:
  - API background task (POST /vitals, POST /labs) — via run_scoring_for_patient()
  - Celery periodic worker                          — via _score_patient() directly
"""
import logging
import uuid as _uuid_mod
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import AsyncSessionLocal
from app.models.patient import (
    AlertNotification,
    LabResult,
    Patient,
    SepsisAlert,
    VitalReading,
)
from app.services.alert_router import get_on_call_doctors
from app.services.notifier import format_alert_message, send_whatsapp
from app.services.sofa import compute_sofa, sofa_to_score_and_level

log = logging.getLogger(__name__)

# Any unacknowledged alert younger than this is considered a duplicate
ALERT_DEDUP_MINUTES: int = 30


def _score_to_level(risk: float) -> str:
    if risk >= 0.90:
        return "CRITICAL"
    if risk >= 0.75:
        return "HIGH"
    if risk >= 0.50:
        return "MEDIUM"
    return "LOW"


# ── Public entry point (called by FastAPI BackgroundTasks) ───────────────────

async def run_scoring_for_patient(patient_id: str) -> None:
    """
    Create a fresh DB session and run the full scoring pipeline.
    Designed to be called as a FastAPI background task — fire-and-forget.
    """
    async with AsyncSessionLocal() as db:
        try:
            await _score_patient(patient_id, db)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            log.error("Scoring pipeline error for patient %s: %s", patient_id, exc, exc_info=True)


# ── Core scoring logic ───────────────────────────────────────────────────────

async def _score_patient(
    patient_id: str, db: AsyncSession
) -> Optional[SepsisAlert]:
    """
    Full scoring pipeline for one patient.
    Returns the created SepsisAlert, or None if no alert was warranted.
    """
    # Validate + parse patient ID
    try:
        pid = _uuid_mod.UUID(patient_id)
    except ValueError:
        log.warning("Invalid patient UUID: %s", patient_id)
        return None

    # ── Step 1: Patient exists? ───────────────────────────────────────────────
    patient: Optional[Patient] = await db.get(Patient, pid)
    if not patient:
        log.debug("Patient %s not found — skip scoring", patient_id)
        return None

    # ── Step 2: Latest vital reading ─────────────────────────────────────────
    v_res = await db.execute(
        select(VitalReading)
        .where(VitalReading.patient_id == pid)
        .order_by(VitalReading.recorded_at.desc())
        .limit(1)
    )
    latest_vital: Optional[VitalReading] = v_res.scalar_one_or_none()

    if latest_vital is None:
        log.debug("No vitals found for patient %s — skip scoring", patient_id)
        return None

    # ── Step 3: Latest lab draw within 48h ───────────────────────────────────
    lab_cutoff = datetime.utcnow() - timedelta(hours=48)
    l_res = await db.execute(
        select(LabResult)
        .where(
            LabResult.patient_id == pid,
            LabResult.collected_at >= lab_cutoff,
        )
        .order_by(LabResult.collected_at.desc())
        .limit(1)
    )
    latest_lab: Optional[LabResult] = l_res.scalar_one_or_none()

    # ── Step 4: SOFA computation ─────────────────────────────────────────────
    vitals_dict = {
        "mean_arterial_bp": latest_vital.mean_arterial_bp,
        "gcs_total": latest_vital.gcs_total,
    }
    labs_dict: dict = {}
    if latest_lab:
        labs_dict = {
            "pao2_fio2_ratio": latest_lab.pao2_fio2_ratio,
            "platelets": latest_lab.platelets,
            "bilirubin_total": latest_lab.bilirubin_total,
            "creatinine": latest_lab.creatinine,
        }

    sofa = compute_sofa(vitals_dict, labs_dict)
    sofa_score, _ = sofa_to_score_and_level(sofa)

    # ── Step 5: LSTM inference — combined with SOFA (take the higher risk) ───
    # The LSTM captures 24-hour trends; SOFA captures the current snapshot.
    # We always take the MAX so that neither model can mask the other's signal.
    # A high SOFA will never be overridden by a conservative LSTM, and a rising
    # LSTM trend will not be masked by a temporarily normal SOFA.
    risk_score: float = sofa_score  # baseline
    try:
        from ml.sepsis.inference import get_risk_score  # lazy import — optional dep

        lstm_result = await get_risk_score(str(pid), db)
        if lstm_result is not None:
            risk_score = max(sofa_score, lstm_result)
            log.debug(
                "Patient %s: SOFA=%.2f LSTM=%.2f → combined=%.2f",
                patient_id, sofa_score, lstm_result, risk_score,
            )
    except Exception as exc:
        log.debug("LSTM inference unavailable (%s) — using SOFA heuristic only", exc)

    # ── Step 6: Threshold — LOW starts at 0.25 ───────────────────────────────
    if risk_score < 0.25:
        return None

    alert_level = _score_to_level(risk_score)

    # ── Step 7: Deduplication ────────────────────────────────────────────────
    dedup_cutoff = datetime.utcnow() - timedelta(minutes=ALERT_DEDUP_MINUTES)
    dup_res = await db.execute(
        select(SepsisAlert).where(
            SepsisAlert.patient_id == pid,
            SepsisAlert.acknowledged == False,
            SepsisAlert.triggered_at >= dedup_cutoff,
        ).limit(1)
    )
    if dup_res.scalar_one_or_none() is not None:
        log.debug(
            "Duplicate alert suppressed for patient %s — unacknowledged alert within %d min",
            patient_id,
            ALERT_DEDUP_MINUTES,
        )
        return None

    # ── Step 8: Persist SepsisAlert ──────────────────────────────────────────
    alert = SepsisAlert(
        patient_id=pid,
        risk_score=risk_score,
        alert_level=alert_level,
    )
    db.add(alert)
    await db.flush()
    await db.refresh(alert)

    log.info(
        "SepsisAlert %s created — patient=%s level=%s risk=%.3f SOFA=%d",
        alert.id,
        patient_id,
        alert_level,
        risk_score,
        sofa,
    )

    # ── Step 9: LangGraph clinical summary (best-effort) ─────────────────────
    try:
        from app.agents.clinical_summary import generate_clinical_summary  # lazy

        summary = await generate_clinical_summary(
            patient=patient,
            latest_vital=latest_vital,
            latest_lab=latest_lab,
            sofa_score=sofa,
            risk_score=risk_score,
            alert_level=alert_level,
            db=db,
        )
        if summary:
            alert.clinical_summary = summary
    except Exception as exc:
        log.warning("Clinical summary generation failed for alert %s: %s", alert.id, exc)

    # ── Step 10: Route notifications ─────────────────────────────────────────
    try:
        doctors = await get_on_call_doctors(patient.ward or "All", db)
        message_body = format_alert_message(patient, alert, sofa)

        for doctor in doctors:
            if not doctor.phone_whatsapp:
                continue
            sid, error = send_whatsapp(doctor.phone_whatsapp, message_body)
            notif = AlertNotification(
                alert_id=alert.id,
                doctor_id=doctor.id,
                channel="WHATSAPP",
                destination_number=doctor.phone_whatsapp,
                delivery_status="SENT" if sid else "FAILED",
                twilio_message_sid=sid,
                failure_reason=error,
                sent_at=datetime.utcnow() if sid else None,
                message_preview=message_body[:500],
            )
            db.add(notif)
    except Exception as exc:
        log.error("Notification routing failed for alert %s: %s", alert.id, exc)

    return alert
