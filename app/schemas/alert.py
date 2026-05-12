from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from uuid import UUID
from datetime import datetime


class AlertResponse(BaseModel):
    id: UUID
    patient_id: UUID
    admission_id: Optional[UUID] = None
    model_version_id: Optional[UUID] = None
    risk_score: float
    alert_level: Optional[str] = None
    triggered_at: datetime
    acknowledged: bool
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    clinical_summary: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AcknowledgeRequest(BaseModel):
    acknowledged_by: str = Field(..., min_length=1, max_length=200)


class AlertListResponse(BaseModel):
    total: int
    alerts: List[AlertResponse]
