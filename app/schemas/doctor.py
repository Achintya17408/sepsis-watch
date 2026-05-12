import re
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime

VALID_ROLES = {"DOCTOR", "NURSE", "ADMIN", "RESIDENT", "FELLOW", "INTENSIVIST"}
_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


class DoctorCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    role: str
    employee_id: Optional[str] = Field(None, max_length=50)
    specialization: Optional[str] = Field(None, max_length=100)
    phone_whatsapp: Optional[str] = None
    phone_backup: Optional[str] = None
    email: Optional[str] = Field(None, max_length=200)
    ward_assignment: Optional[str] = Field(None, max_length=50)

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        v = v.upper().strip()
        if v not in VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(VALID_ROLES)}")
        return v

    @field_validator("phone_whatsapp", "phone_backup")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not _E164_RE.match(v):
            raise ValueError(
                "Phone must be E.164 format — e.g. +919876543210 (country code + number)"
            )
        return v


class DoctorResponse(BaseModel):
    id: UUID
    name: str
    role: str
    employee_id: Optional[str] = None
    specialization: Optional[str] = None
    phone_whatsapp: Optional[str] = None
    ward_assignment: Optional[str] = None
    is_on_call: bool
    is_active: bool
    on_call_start: Optional[datetime] = None
    on_call_end: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OnCallUpdate(BaseModel):
    is_on_call: bool
    on_call_start: Optional[datetime] = None
    on_call_end: Optional[datetime] = None


class DoctorUpdate(BaseModel):
    """Partial update — all fields optional. PATCH /doctors/{id}."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    role: Optional[str] = None
    employee_id: Optional[str] = Field(None, max_length=50)
    specialization: Optional[str] = Field(None, max_length=100)
    phone_whatsapp: Optional[str] = None
    phone_backup: Optional[str] = None
    email: Optional[str] = Field(None, max_length=200)
    ward_assignment: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None
    is_on_call: Optional[bool] = None
    on_call_start: Optional[datetime] = None
    on_call_end: Optional[datetime] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.upper().strip()
        if v not in VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(VALID_ROLES)}")
        return v

    @field_validator("phone_whatsapp", "phone_backup")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not _E164_RE.match(v):
            raise ValueError(
                "Phone must be E.164 format — e.g. +919876543210 (country code + number)"
            )
        return v
