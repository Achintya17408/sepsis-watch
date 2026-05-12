from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models.patient import Doctor
from app.schemas.doctor import DoctorCreate, DoctorResponse, DoctorUpdate, OnCallUpdate

router = APIRouter(prefix="/doctors", tags=["Doctors"])


@router.post("/", response_model=DoctorResponse, status_code=201)
async def create_doctor(
    payload: DoctorCreate,
    db: AsyncSession = Depends(get_db),
):
    """Register a new clinician in the alert routing registry."""
    doctor = Doctor(**payload.model_dump())
    db.add(doctor)
    await db.flush()
    await db.refresh(doctor)
    return doctor


@router.get("/", response_model=List[DoctorResponse])
async def list_doctors(
    ward: Optional[str] = Query(None),
    on_call_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    q = select(Doctor).where(Doctor.is_active == True)
    if ward:
        q = q.where(Doctor.ward_assignment == ward)
    if on_call_only:
        q = q.where(Doctor.is_on_call == True)
    q = q.order_by(Doctor.name.asc())
    result = await db.execute(q)
    return list(result.scalars().all())


@router.get("/{doctor_id}", response_model=DoctorResponse)
async def get_doctor(doctor_id: UUID, db: AsyncSession = Depends(get_db)):
    doctor = await db.get(Doctor, doctor_id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return doctor


@router.patch("/{doctor_id}", response_model=DoctorResponse)
async def update_doctor(
    doctor_id: UUID,
    payload: DoctorUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Partial update a doctor's profile — name, role, phone, ward, active status, on-call.
    Only the fields included in the request body are changed.
    """
    doctor = await db.get(Doctor, doctor_id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(doctor, field, value)
    doctor.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(doctor)
    return doctor


@router.patch("/{doctor_id}/oncall", response_model=DoctorResponse)
async def update_oncall(
    doctor_id: UUID,
    payload: OnCallUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update a doctor's on-call status.
    Called by scheduling systems or manually by ward admin at shift change.
    """
    doctor = await db.get(Doctor, doctor_id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    doctor.is_on_call = payload.is_on_call
    if payload.on_call_start:
        doctor.on_call_start = payload.on_call_start
    if payload.on_call_end:
        doctor.on_call_end = payload.on_call_end
    doctor.updated_at = datetime.utcnow()

    await db.flush()
    await db.refresh(doctor)
    return doctor
