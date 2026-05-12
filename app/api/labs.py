from typing import List
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models.patient import LabResult, Patient
from app.schemas.lab import LabCreate, LabResponse
from app.services.scoring import run_scoring_for_patient

router = APIRouter(prefix="/labs", tags=["Labs"])


@router.post("/", response_model=LabResponse, status_code=201)
async def ingest_lab(
    payload: LabCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest a laboratory result panel.
    Triggers a background scoring pass — new lab values (especially lactate,
    creatinine, bilirubin) substantially affect SOFA and LSTM input features.
    """
    patient = await db.get(Patient, payload.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    lab = LabResult(**payload.model_dump(exclude_none=False))
    db.add(lab)
    await db.flush()
    await db.refresh(lab)

    background_tasks.add_task(run_scoring_for_patient, str(payload.patient_id))

    return lab


@router.get("/{patient_id}", response_model=List[LabResponse])
async def list_labs(
    patient_id: UUID,
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Return the most recent N lab results for a patient (newest first)."""
    patient = await db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    result = await db.execute(
        select(LabResult)
        .where(LabResult.patient_id == patient_id)
        .order_by(LabResult.collected_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
