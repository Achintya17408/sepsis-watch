from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models.patient import SepsisAlert
from app.schemas.alert import AcknowledgeRequest, AlertListResponse, AlertResponse

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("/", response_model=AlertListResponse)
async def list_alerts(
    unacknowledged_only: bool = Query(
        True, description="If true, return only unacknowledged alerts"
    ),
    ward: Optional[str] = Query(None, description="Filter alerts by patient ward (join required)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    List sepsis alerts.

    Default behaviour: unacknowledged alerts only, newest first — this is the
    live dashboard view for ICU staff.
    """
    q = select(SepsisAlert)
    if unacknowledged_only:
        q = q.where(SepsisAlert.acknowledged == False)
    q = q.order_by(SepsisAlert.triggered_at.desc())

    # Count — build independently to avoid ORDER BY in subquery
    count_q = select(func.count(SepsisAlert.id))
    if unacknowledged_only:
        count_q = count_q.where(SepsisAlert.acknowledged == False)
    total_res = await db.execute(count_q)
    total: int = total_res.scalar_one()

    # Page
    result = await db.execute(q.offset(offset).limit(limit))
    alerts = list(result.scalars().all())

    return AlertListResponse(total=total, alerts=alerts)  # type: ignore[arg-type]


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: UUID, db: AsyncSession = Depends(get_db)):
    alert = await db.get(SepsisAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.patch("/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: UUID,
    payload: AcknowledgeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Mark an alert as acknowledged by a clinician.
    This removes the alert from the active dashboard and stops escalation.
    """
    alert = await db.get(SepsisAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.acknowledged:
        raise HTTPException(status_code=409, detail="Alert already acknowledged")

    alert.acknowledged = True
    alert.acknowledged_by = payload.acknowledged_by
    alert.acknowledged_at = datetime.utcnow()

    await db.flush()
    await db.refresh(alert)
    return alert
