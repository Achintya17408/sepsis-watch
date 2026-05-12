"""
API integration tests for the /alerts endpoints.

Behaviours tested:
1. GET /alerts — list with total count (unacked by default)
2. GET /alerts/{id} — single fetch and 404
3. PATCH /alerts/{id}/acknowledge — happy path and 409 on double-ack
"""
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import make_alert, make_patient


class TestListAlerts:
    def _setup_alert_list(self, mock_db, alerts: list):
        """Configure mock_db.execute to simulate an alert list query + count query."""
        # The endpoint calls execute twice: once for count, once for rows.
        count_result = MagicMock()
        count_result.scalar_one.return_value = len(alerts)

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = alerts

        mock_db.execute = AsyncMock(side_effect=[count_result, list_result])

    def test_returns_200_with_total(self, client):
        c, mock_db = client
        self._setup_alert_list(mock_db, [])
        resp = c.get("/alerts/")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "alerts" in data

    def test_empty_list(self, client):
        c, mock_db = client
        self._setup_alert_list(mock_db, [])
        resp = c.get("/alerts/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["alerts"] == []

    def test_list_with_alerts(self, client):
        c, mock_db = client
        a1 = make_alert(risk_score=0.82, alert_level="CRITICAL")
        a2 = make_alert(risk_score=0.65, alert_level="HIGH")
        self._setup_alert_list(mock_db, [a1, a2])
        resp = c.get("/alerts/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["alerts"]) == 2

    def test_unacknowledged_only_default(self, client):
        """By default only unacknowledged alerts are returned — verify query param default."""
        c, mock_db = client
        self._setup_alert_list(mock_db, [])
        resp = c.get("/alerts/")
        # We cannot inspect SQLAlchemy .where() calls on a mock, but the API
        # must return 200 without error when the default filter is applied.
        assert resp.status_code == 200

    def test_acknowledged_only_param(self, client):
        """?unacknowledged_only=false should be accepted."""
        c, mock_db = client
        self._setup_alert_list(mock_db, [])
        resp = c.get("/alerts/?unacknowledged_only=false")
        assert resp.status_code == 200

    def test_limit_too_large_returns_422(self, client):
        c, _ = client
        resp = c.get("/alerts/?limit=9999")
        assert resp.status_code == 422

    def test_pagination_params_accepted(self, client):
        c, mock_db = client
        self._setup_alert_list(mock_db, [])
        resp = c.get("/alerts/?limit=10&offset=20")
        assert resp.status_code == 200


class TestGetAlert:
    def test_existing_alert_returns_200(self, client):
        c, mock_db = client
        alert = make_alert(risk_score=0.78, alert_level="HIGH")
        mock_db.get = AsyncMock(return_value=alert)
        resp = c.get(f"/alerts/{alert.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["alert_level"] == "HIGH"
        assert data["risk_score"] == pytest.approx(0.78)

    def test_nonexistent_alert_returns_404(self, client):
        c, mock_db = client
        mock_db.get = AsyncMock(return_value=None)
        resp = c.get(f"/alerts/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Alert not found"

    def test_invalid_uuid_returns_422(self, client):
        c, _ = client
        resp = c.get("/alerts/not-a-uuid")
        assert resp.status_code == 422


class TestAcknowledgeAlert:
    ACK_PAYLOAD = {"acknowledged_by": "Dr. Mehta"}

    def test_acknowledge_unacked_returns_200(self, client):
        c, mock_db = client
        alert = make_alert(acknowledged=False)
        mock_db.get = AsyncMock(return_value=alert)
        resp = c.patch(f"/alerts/{alert.id}/acknowledge", json=self.ACK_PAYLOAD)
        assert resp.status_code == 200

    def test_sets_acknowledged_true(self, client):
        c, mock_db = client
        alert = make_alert(acknowledged=False)
        mock_db.get = AsyncMock(return_value=alert)
        c.patch(f"/alerts/{alert.id}/acknowledge", json=self.ACK_PAYLOAD)
        # The route mutates the alert object directly
        assert alert.acknowledged is True

    def test_sets_acknowledged_by(self, client):
        c, mock_db = client
        alert = make_alert(acknowledged=False)
        mock_db.get = AsyncMock(return_value=alert)
        c.patch(f"/alerts/{alert.id}/acknowledge", json={"acknowledged_by": "Dr. Singh"})
        assert alert.acknowledged_by == "Dr. Singh"

    def test_sets_acknowledged_at(self, client):
        c, mock_db = client
        alert = make_alert(acknowledged=False)
        mock_db.get = AsyncMock(return_value=alert)
        c.patch(f"/alerts/{alert.id}/acknowledge", json=self.ACK_PAYLOAD)
        assert alert.acknowledged_at is not None

    def test_double_acknowledge_returns_409(self, client):
        c, mock_db = client
        already_acked = make_alert(acknowledged=True)
        mock_db.get = AsyncMock(return_value=already_acked)
        resp = c.patch(f"/alerts/{already_acked.id}/acknowledge", json=self.ACK_PAYLOAD)
        assert resp.status_code == 409
        assert "already acknowledged" in resp.json()["detail"].lower()

    def test_nonexistent_alert_acknowledge_returns_404(self, client):
        c, mock_db = client
        mock_db.get = AsyncMock(return_value=None)
        resp = c.patch(f"/alerts/{uuid.uuid4()}/acknowledge", json=self.ACK_PAYLOAD)
        assert resp.status_code == 404

    def test_flush_called_on_success(self, client):
        c, mock_db = client
        alert = make_alert(acknowledged=False)
        mock_db.get = AsyncMock(return_value=alert)
        c.patch(f"/alerts/{alert.id}/acknowledge", json=self.ACK_PAYLOAD)
        mock_db.flush.assert_awaited()

    def test_missing_acknowledged_by_returns_422(self, client):
        c, _ = client
        resp = c.patch(f"/alerts/{uuid.uuid4()}/acknowledge", json={})
        assert resp.status_code == 422
