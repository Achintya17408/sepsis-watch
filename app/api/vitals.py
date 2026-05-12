from typing import List
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models.patient import Patient, VitalReading
from app.schemas.vital import VitalCreate, VitalResponse
from app.services.scoring import run_scoring_for_patient

router = APIRouter(prefix="/vitals", tags=["Vitals"])


@router.post("/", response_model=VitalResponse, status_code=201)
async def ingest_vital(
    payload: VitalCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest a new vital signs reading.
    Immediately returns 201 with the saved record.
    Triggers a background scoring pass so alert latency is low.
    """
    # Verify patient exists
    patient = await db.get(Patient, payload.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    vital = VitalReading(**payload.model_dump())
    db.add(vital)
    await db.flush()
    await db.refresh(vital)

    # Non-blocking scoring trigger
    background_tasks.add_task(run_scoring_for_patient, str(payload.patient_id))

    return vital


@router.get("/{patient_id}", response_model=List[VitalResponse])
async def list_vitals(
    patient_id: UUID,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """Return the most recent N vital readings for a patient (newest first)."""
    patient = await db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    result = await db.execute(
        select(VitalReading)
        .where(VitalReading.patient_id == patient_id)
        .order_by(VitalReading.recorded_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
