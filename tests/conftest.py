"""
Shared pytest fixtures for the sepsis-watch test suite.

Strategy:
- Pure-function tests (SOFA, LSTM model) need no mocking.
- API route tests use FastAPI's dependency_overrides to substitute
  get_db with an AsyncMock session, bypassing the real database.
- External services (Twilio, Anthropic) are patched at the function level
  in individual test modules.
"""
import uuid
from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db.base import get_db
from app.main import app


# ── DB session mock factory ──────────────────────────────────────────────────

_REFRESH_DEFAULT_CREATED_AT = datetime(2026, 1, 1, 8, 0, 0)


async def _simulate_db_refresh(obj) -> None:
    """
    Simulate what SQLAlchemy does during a real db.refresh(): populate any
    server-generated columns (primary key UUID, created_at) that are still
    None because the real INSERT never happened.
    """
    if getattr(obj, "id", None) is None:
        obj.id = uuid.uuid4()
    if getattr(obj, "created_at", None) is None:
        obj.created_at = _REFRESH_DEFAULT_CREATED_AT


def make_db_session() -> AsyncMock:
    """
    Build a minimal async mock of an SQLAlchemy AsyncSession.
    Tests configure .execute.return_value to return desired query results.
    """
    session = AsyncMock()

    # Default query result chain: execute → result → scalar_one_or_none → None
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    result.scalars.return_value.all.return_value = []
    result.fetchall.return_value = []
    session.execute = AsyncMock(return_value=result)

    # Default get (single-object lookup) → None
    session.get = AsyncMock(return_value=None)

    # Mutations — no-ops by default
    session.add = MagicMock()
    session.flush = AsyncMock()
    # refresh populates server-generated defaults so response serialization works
    session.refresh = AsyncMock(side_effect=_simulate_db_refresh)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    return session


# ── FastAPI test client with mocked DB ───────────────────────────────────────


@pytest.fixture()
def mock_db() -> AsyncMock:
    return make_db_session()


@pytest.fixture()
def client(mock_db: AsyncMock):
    """TestClient with the DB dependency injected as a mock."""

    async def _override_get_db() -> AsyncGenerator:
        yield mock_db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c, mock_db
    app.dependency_overrides.clear()


# ── Domain object factories ───────────────────────────────────────────────────


def make_patient(**kwargs) -> MagicMock:
    p = MagicMock()
    p.id = kwargs.get("id", uuid.uuid4())
    p.name = kwargs.get("name", "Test Patient")
    p.age = kwargs.get("age", 55)
    p.ward = kwargs.get("ward", "MICU")
    p.hospital_id = kwargs.get("hospital_id", None)
    p.mimic_subject_id = kwargs.get("mimic_subject_id", None)
    p.created_at = kwargs.get("created_at", datetime(2026, 1, 1, 8, 0, 0))
    return p


def make_vital(**kwargs) -> MagicMock:
    v = MagicMock()
    v.id = kwargs.get("id", uuid.uuid4())
    v.patient_id = kwargs.get("patient_id", uuid.uuid4())
    v.recorded_at = kwargs.get("recorded_at", datetime(2026, 1, 1, 9, 0, 0))
    v.heart_rate = kwargs.get("heart_rate", 110.0)
    v.systolic_bp = kwargs.get("systolic_bp", 88.0)
    v.diastolic_bp = kwargs.get("diastolic_bp", 55.0)
    v.mean_arterial_bp = kwargs.get("mean_arterial_bp", 66.0)
    v.spo2 = kwargs.get("spo2", 93.0)
    v.respiratory_rate = kwargs.get("respiratory_rate", 24.0)
    v.temperature_c = kwargs.get("temperature_c", 38.9)
    v.gcs_total = kwargs.get("gcs_total", 13)
    return v


def make_alert(**kwargs) -> MagicMock:
    a = MagicMock()
    a.id = kwargs.get("id", uuid.uuid4())
    a.patient_id = kwargs.get("patient_id", uuid.uuid4())
    a.admission_id = kwargs.get("admission_id", None)
    a.model_version_id = kwargs.get("model_version_id", None)
    a.risk_score = kwargs.get("risk_score", 0.72)
    a.alert_level = kwargs.get("alert_level", "HIGH")
    a.triggered_at = kwargs.get("triggered_at", datetime(2026, 1, 1, 9, 5, 0))
    a.acknowledged = kwargs.get("acknowledged", False)
    a.acknowledged_by = kwargs.get("acknowledged_by", None)
    a.acknowledged_at = kwargs.get("acknowledged_at", None)
    a.clinical_summary = kwargs.get("clinical_summary", "Patient presents with elevated lactate and low MAP.")
    return a
