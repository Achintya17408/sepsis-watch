from sqlalchemy import Column, String, Float, DateTime, Integer, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base
import uuid
from datetime import datetime


class Patient(Base):
    __tablename__ = "patients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mimic_subject_id = Column(Integer, unique=True, nullable=True)  # links to MIMIC-III
    hospital_id = Column(String, nullable=True)                      # hospital MRN (Indian hospital)
    name = Column(String, nullable=False)
    age = Column(Integer)
    ward = Column(String)                                            # ICU / CCU / General
    created_at = Column(DateTime, default=datetime.utcnow)


class VitalReading(Base):
    """
    Time-series vitals table converted to a TimescaleDB hypertable.

    TimescaleDB requires the partition column (recorded_at) to be part of any
    unique index including the primary key. We use a composite PK (id, recorded_at)
    to satisfy this constraint while still having a unique row identifier.
    """
    __tablename__ = "vital_readings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    recorded_at = Column(DateTime, nullable=False, primary_key=True)  # composite PK + time dimension
    heart_rate = Column(Float)
    systolic_bp = Column(Float)
    diastolic_bp = Column(Float)
    spo2 = Column(Float)
    temperature_c = Column(Float)                                    # Celsius (Indian standard)
    respiratory_rate = Column(Float)


class SepsisAlert(Base):
    __tablename__ = "sepsis_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    risk_score = Column(Float, nullable=False)              # 0.0–1.0 from LSTM model
    alert_level = Column(String)                            # LOW / MEDIUM / HIGH / CRITICAL
    triggered_at = Column(DateTime, default=datetime.utcnow)
    acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(String, nullable=True)        # doctor name / ID
    clinical_summary = Column(String, nullable=True)       # agent-generated clinical text
