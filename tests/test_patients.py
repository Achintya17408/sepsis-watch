"""
API integration tests for the /patients endpoints.

All DB I/O is intercepted via the `client` fixture (conftest.py).
Real SQLAlchemy Patient objects are instantiated (they use Python-side
uuid.uuid4 and datetime.utcnow defaults), so no special mock setup is
needed for responses that go through db.flush / db.refresh.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import make_patient


VALID_PAYLOAD = {
    "name": "Priya Sharma",
    "age": 62,
    "ward": "MICU",
    "hospital_id": "AIIMS-2024-0001",
}


class TestCreatePatient:
    def test_success_returns_201(self, client):
        c, mock_db = client
        resp = c.post("/patients/", json=VALID_PAYLOAD)
        assert resp.status_code == 201

    def test_response_contains_id_and_name(self, client):
        c, mock_db = client
        resp = c.post("/patients/", json=VALID_PAYLOAD)
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["name"] == "Priya Sharma"
        assert data["age"] == 62
        assert data["ward"] == "MICU"

    def test_response_contains_created_at(self, client):
        c, mock_db = client
        resp = c.post("/patients/", json=VALID_PAYLOAD)
        assert "created_at" in resp.json()

    def test_db_add_and_flush_called(self, client):
        c, mock_db = client
        c.post("/patients/", json=VALID_PAYLOAD)
        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()

    def test_missing_name_returns_422(self, client):
        c, _ = client
        resp = c.post("/patients/", json={"age": 40, "ward": "MICU"})
        assert resp.status_code == 422

    def test_age_out_of_range_returns_422(self, client):
        c, _ = client
        resp = c.post("/patients/", json={"name": "X", "age": 200})
        assert resp.status_code == 422

    def test_empty_name_returns_422(self, client):
        c, _ = client
        resp = c.post("/patients/", json={"name": "", "age": 30})
        assert resp.status_code == 422

    def test_minimal_payload_name_only(self, client):
        c, _ = client
        resp = c.post("/patients/", json={"name": "Minimal Patient"})
        assert resp.status_code == 201

    def test_extra_fields_ignored(self, client):
        c, _ = client
        payload = {**VALID_PAYLOAD, "nonexistent_field": "ignored"}
        resp = c.post("/patients/", json=payload)
        # Extra fields must not raise 422; they're silently dropped
        assert resp.status_code == 201


class TestGetPatient:
    def test_existing_patient_returns_200(self, client):
        c, mock_db = client
        patient = make_patient(name="Arjun Das", ward="CCU")
        mock_db.get = AsyncMock(return_value=patient)
        resp = c.get(f"/patients/{patient.id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Arjun Das"

    def test_nonexistent_patient_returns_404(self, client):
        c, mock_db = client
        mock_db.get = AsyncMock(return_value=None)
        resp = c.get(f"/patients/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Patient not found"

    def test_invalid_uuid_returns_422(self, client):
        c, _ = client
        resp = c.get("/patients/not-a-uuid")
        assert resp.status_code == 422


class TestListPatients:
    def test_empty_list_returns_200(self, client):
        c, mock_db = client
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result_mock)
        resp = c.get("/patients/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_patients(self, client):
        c, mock_db = client
        p1 = make_patient(name="Patient One", ward="MICU")
        p2 = make_patient(name="Patient Two", ward="SICU")
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [p1, p2]
        mock_db.execute = AsyncMock(return_value=result_mock)
        resp = c.get("/patients/")
        assert resp.status_code == 200
        names = [r["name"] for r in resp.json()]
        assert "Patient One" in names
        assert "Patient Two" in names

    def test_limit_param_accepted(self, client):
        c, mock_db = client
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result_mock)
        resp = c.get("/patients/?limit=10&offset=0")
        assert resp.status_code == 200

    def test_limit_too_large_returns_422(self, client):
        c, _ = client
        resp = c.get("/patients/?limit=9999")
        assert resp.status_code == 422


class TestUpdatePatient:
    def test_patch_ward_success(self, client):
        c, mock_db = client
        patient = make_patient(ward="MICU")
        mock_db.get = AsyncMock(return_value=patient)
        resp = c.patch(f"/patients/{patient.id}", json={"ward": "SICU"})
        assert resp.status_code == 200

    def test_patch_nonexistent_returns_404(self, client):
        c, mock_db = client
        mock_db.get = AsyncMock(return_value=None)
        resp = c.patch(f"/patients/{uuid.uuid4()}", json={"ward": "SICU"})
        assert resp.status_code == 404

    def test_patch_age_out_of_range_returns_422(self, client):
        c, _ = client
        resp = c.patch(f"/patients/{uuid.uuid4()}", json={"age": -5})
        assert resp.status_code == 422


class TestGetPatientRisk:
    def test_nonexistent_patient_returns_404(self, client):
        c, mock_db = client
        mock_db.get = AsyncMock(return_value=None)
        resp = c.get(f"/patients/{uuid.uuid4()}/risk")
        assert resp.status_code == 404

    def test_existing_patient_with_no_vitals(self, client):
        c, mock_db = client
        patient = make_patient()
        # First call: get patient; subsequent: execute queries return empty
        mock_db.get = AsyncMock(return_value=patient)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result_mock)
        resp = c.get(f"/patients/{patient.id}/risk")
        assert resp.status_code == 200
        data = resp.json()
        assert "patient_id" in data
        assert "sofa_score" in data

    def test_score_trigger_returns_202(self, client):
        """POST /patients/{id}/score should accept (202) and trigger background task."""
        c, mock_db = client
        patient = make_patient()
        mock_db.get = AsyncMock(return_value=patient)
        with patch("app.api.patients.run_scoring_for_patient"):
            resp = c.post(f"/patients/{patient.id}/score")
        assert resp.status_code == 202
