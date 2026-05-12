from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class PatientCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    age: Optional[int] = Field(None, ge=0, le=130)
    ward: Optional[str] = Field(None, max_length=50)
    hospital_id: Optional[str] = Field(None, max_length=100)
    mimic_subject_id: Optional[int] = Field(None, ge=0)


class PatientUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    age: Optional[int] = Field(None, ge=0, le=130)
    ward: Optional[str] = Field(None, max_length=50)
    hospital_id: Optional[str] = Field(None, max_length=100)


class PatientResponse(BaseModel):
    id: UUID
    name: str
    age: Optional[int] = None
    ward: Optional[str] = None
    hospital_id: Optional[str] = None
    mimic_subject_id: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PatientRiskResponse(BaseModel):
    patient_id: UUID
    patient_name: str
    ward: Optional[str] = None
    latest_risk_score: Optional[float] = None
    latest_alert_level: Optional[str] = None
    sofa_score: Optional[int] = None
    qsofa_score: Optional[int] = None
    last_assessed_at: Optional[datetime] = None
