from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone


class LabCreate(BaseModel):
    patient_id: UUID
    collected_at: datetime
    admission_id: Optional[UUID] = None

    @field_validator("collected_at", mode="after")
    @classmethod
    def strip_timezone(cls, v: datetime) -> datetime:
        """Normalize to naive UTC datetime — the DB column is timezone-naive."""
        if v.tzinfo is not None:
            return v.astimezone(timezone.utc).replace(tzinfo=None)
        return v
    # CBC
    wbc: Optional[float] = Field(None, ge=0.0, le=500.0)
    hemoglobin: Optional[float] = Field(None, ge=0.0, le=30.0)
    hematocrit: Optional[float] = Field(None, ge=0.0, le=100.0)
    platelets: Optional[float] = Field(None, ge=0.0, le=3000.0)
    # BMP
    sodium: Optional[float] = Field(None, ge=80.0, le=200.0)
    potassium: Optional[float] = Field(None, ge=1.0, le=15.0)
    chloride: Optional[float] = Field(None, ge=50.0, le=180.0)
    bicarbonate: Optional[float] = Field(None, ge=0.0, le=60.0)
    bun: Optional[float] = Field(None, ge=0.0, le=500.0)
    creatinine: Optional[float] = Field(None, ge=0.0, le=50.0)
    glucose: Optional[float] = Field(None, ge=0.0, le=2000.0)
    # LFTs
    bilirubin_total: Optional[float] = Field(None, ge=0.0, le=100.0)
    bilirubin_direct: Optional[float] = Field(None, ge=0.0, le=100.0)
    ast: Optional[float] = Field(None, ge=0.0, le=10000.0)
    alt: Optional[float] = Field(None, ge=0.0, le=10000.0)
    alkaline_phosphatase: Optional[float] = Field(None, ge=0.0, le=5000.0)
    albumin: Optional[float] = Field(None, ge=0.0, le=10.0)
    # Coagulation
    inr: Optional[float] = Field(None, ge=0.0, le=30.0)
    prothrombin_time: Optional[float] = Field(None, ge=0.0, le=200.0)
    aptt: Optional[float] = Field(None, ge=0.0, le=250.0)
    # ABG
    ph: Optional[float] = Field(None, ge=6.5, le=8.0)
    pao2: Optional[float] = Field(None, ge=0.0, le=700.0)
    paco2: Optional[float] = Field(None, ge=0.0, le=200.0)
    fio2: Optional[float] = Field(None, ge=0.0, le=1.0)
    pao2_fio2_ratio: Optional[float] = Field(None, ge=0.0, le=700.0)
    base_excess: Optional[float] = Field(None, ge=-30.0, le=30.0)
    # Sepsis markers
    lactate: Optional[float] = Field(None, ge=0.0, le=50.0)
    procalcitonin: Optional[float] = Field(None, ge=0.0, le=1000.0)
    crp: Optional[float] = Field(None, ge=0.0, le=1000.0)
    # Urinalysis
    urine_wbc: Optional[float] = Field(None, ge=0.0, le=1000.0)
    urine_nitrites: Optional[str] = None
    source: str = "live"


class LabResponse(BaseModel):
    id: UUID
    patient_id: UUID
    collected_at: datetime
    wbc: Optional[float] = None
    hemoglobin: Optional[float] = None
    hematocrit: Optional[float] = None
    platelets: Optional[float] = None
    sodium: Optional[float] = None
    potassium: Optional[float] = None
    creatinine: Optional[float] = None
    glucose: Optional[float] = None
    bilirubin_total: Optional[float] = None
    inr: Optional[float] = None
    ph: Optional[float] = None
    pao2: Optional[float] = None
    paco2: Optional[float] = None
    fio2: Optional[float] = None
    pao2_fio2_ratio: Optional[float] = None
    lactate: Optional[float] = None
    procalcitonin: Optional[float] = None
    crp: Optional[float] = None
    source: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
