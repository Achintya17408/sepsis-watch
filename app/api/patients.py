from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models.patient import LabResult, Patient, SepsisAlert, VitalReading
from app.schemas.patient import (
    PatientCreate,
    PatientResponse,
    PatientRiskResponse,
    PatientUpdate,
)
from app.services.scoring import run_scoring_for_patient
from app.services.sofa import compute_qsofa, compute_sofa

router = APIRouter(prefix="/patients", tags=["Patients"])


@router.post("/", response_model=PatientResponse, status_code=201)
async def create_patient(
    payload: PatientCreate,
    db: AsyncSession = Depends(get_db),
):
    patient = Patient(**payload.model_dump())
    db.add(patient)
    await db.flush()
    await db.refresh(patient)
    return patient


@router.get("/", response_model=List[PatientResponse])
async def list_patients(
    ward: Optional[str] = Query(None, description="Filter by ward (e.g. MICU, SICU, CCU)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    q = select(Patient)
    if ward:
        q = q.where(Patient.ward == ward)
    q = q.order_by(Patient.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(patient_id: UUID, db: AsyncSession = Depends(get_db)):
    patient = await db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.patch("/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: UUID,
    payload: PatientUpdate,
    db: AsyncSession = Depends(get_db),
):
    patient = await db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(patient, field, value)
    await db.flush()
    await db.refresh(patient)
    return patient


@router.get("/{patient_id}/risk", response_model=PatientRiskResponse)
async def get_patient_risk(
    patient_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Return the latest sepsis risk score, SOFA, and qSOFA for a given patient.
    Triggers a fresh scoring pass in the background after returning the cached result.
    """
    patient = await db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Latest triggered alert (for cached risk + level)
    a_res = await db.execute(
        select(SepsisAlert)
        .where(SepsisAlert.patient_id == patient_id)
        .order_by(SepsisAlert.triggered_at.desc())
        .limit(1)
    )
    latest_alert: Optional[SepsisAlert] = a_res.scalar_one_or_none()

    # Latest vital for SOFA cardiovascular + CNS + qSOFA
    v_res = await db.execute(
        select(VitalReading)
        .where(VitalReading.patient_id == patient_id)
        .order_by(VitalReading.recorded_at.desc())
        .limit(1)
    )
    latest_vital: Optional[VitalReading] = v_res.scalar_one_or_none()

    # Latest lab within 48h for SOFA respiratory/coagulation/hepatic/renal
    lab_cutoff = datetime.utcnow() - timedelta(hours=48)
    l_res = await db.execute(
        select(LabResult)
        .where(
            LabResult.patient_id == patient_id,
            LabResult.collected_at >= lab_cutoff,
        )
        .order_by(LabResult.collected_at.desc())
        .limit(1)
    )
    latest_lab: Optional[LabResult] = l_res.scalar_one_or_none()

    sofa: Optional[int] = None
    qsofa: Optional[int] = None

    if latest_vital or latest_lab:
        vitals_dict = (
            {"mean_arterial_bp": latest_vital.mean_arterial_bp, "gcs_total": latest_vital.gcs_total}
            if latest_vital
            else {}
        )
        labs_dict = (
            {
                "pao2_fio2_ratio": latest_lab.pao2_fio2_ratio,
                "platelets": latest_lab.platelets,
                "bilirubin_total": latest_lab.bilirubin_total,
                "creatinine": latest_lab.creatinine,
            }
            if latest_lab
            else {}
        )
        sofa = compute_sofa(vitals_dict, labs_dict)

    if latest_vital:
        qsofa = compute_qsofa(
            latest_vital.respiratory_rate,
            latest_vital.systolic_bp,
            latest_vital.gcs_total,
        )

    return PatientRiskResponse(
        patient_id=patient.id,
        patient_name=patient.name,
        ward=patient.ward,
        latest_risk_score=latest_alert.risk_score if latest_alert else None,
        latest_alert_level=latest_alert.alert_level if latest_alert else None,
        sofa_score=sofa,
        qsofa_score=qsofa,
        last_assessed_at=latest_alert.triggered_at if latest_alert else None,
    )


@router.post("/{patient_id}/score", status_code=202)
async def trigger_scoring(
    patient_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger a scoring pass for a patient (async — returns 202 immediately)."""
    patient = await db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    background_tasks.add_task(run_scoring_for_patient, str(patient_id))
    return {"status": "scoring_queued", "patient_id": str(patient_id)}
