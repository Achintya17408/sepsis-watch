from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone


class VitalCreate(BaseModel):
    patient_id: UUID
    recorded_at: datetime
    heart_rate: Optional[float] = Field(None, ge=0.0, le=300.0)
    systolic_bp: Optional[float] = Field(None, ge=20.0, le=300.0)
    diastolic_bp: Optional[float] = Field(None, ge=0.0, le=250.0)
    mean_arterial_bp: Optional[float] = Field(None, ge=10.0, le=250.0)
    spo2: Optional[float] = Field(None, ge=50.0, le=100.0)
    respiratory_rate: Optional[float] = Field(None, ge=0.0, le=70.0)
    temperature_c: Optional[float] = Field(None, ge=25.0, le=45.0)
    gcs_total: Optional[int] = Field(None, ge=3, le=15)

    @field_validator("recorded_at", mode="after")
    @classmethod
    def strip_timezone(cls, v: datetime) -> datetime:
        """Normalize to naive UTC datetime — the DB column is timezone-naive."""
        if v.tzinfo is not None:
            return v.astimezone(timezone.utc).replace(tzinfo=None)
        return v


class VitalResponse(BaseModel):
    id: UUID
    patient_id: UUID
    recorded_at: datetime
    heart_rate: Optional[float] = None
    systolic_bp: Optional[float] = None
    diastolic_bp: Optional[float] = None
    mean_arterial_bp: Optional[float] = None
    spo2: Optional[float] = None
    respiratory_rate: Optional[float] = None
    temperature_c: Optional[float] = None
    gcs_total: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)
