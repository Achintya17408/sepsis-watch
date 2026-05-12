"""
Twilio delivery-status webhook endpoint.

Configure in your Twilio Console:
  Messaging → WhatsApp Sandbox → Status Callback URL
  → https://your-domain.com/webhooks/twilio/status

Twilio POST-encodes these form fields on each status change:
  MessageSid, MessageStatus, To, From, ErrorCode (on failure)

Valid MessageStatus values:
  queued → sent → delivered → read (WhatsApp only)
  failed | undelivered | canceled
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models.patient import AlertNotification

log = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/twilio/status")
async def twilio_delivery_status(
    MessageSid: str = Form(...),
    MessageStatus: str = Form(...),
    ErrorCode: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Update AlertNotification delivery lifecycle from Twilio status callbacks.
    Returns HTTP 200 + JSON regardless — Twilio retries on non-200, we don't want that loop.
    """
    result = await db.execute(
        select(AlertNotification)
        .where(AlertNotification.twilio_message_sid == MessageSid)
        .limit(1)
    )
    notif: AlertNotification | None = result.scalar_one_or_none()

    if not notif:
        log.warning("Twilio webhook: no AlertNotification found for SID %s", MessageSid)
        return {"status": "ok", "note": "sid_not_found"}

    now = datetime.utcnow()
    status_upper = MessageStatus.upper()
    notif.delivery_status = status_upper

    if status_upper == "DELIVERED":
        notif.delivered_at = now
    elif status_upper == "READ":
        notif.read_at = now
        if not notif.delivered_at:
            notif.delivered_at = now
    elif status_upper in {"FAILED", "UNDELIVERED"}:
        notif.failure_reason = f"ErrorCode={ErrorCode}" if ErrorCode else "delivery_failed"

    log.info(
        "Twilio status update: SID=%s status=%s notification_id=%s",
        MessageSid,
        MessageStatus,
        notif.id,
    )
    return {"status": "ok"}
