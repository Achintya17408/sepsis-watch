"""
Twilio WhatsApp / SMS notification service.

Sends sepsis alerts as WhatsApp messages via the Twilio Messaging API.
All functions are synchronous (Twilio REST SDK is sync) and are safe to
call from async code via normal function calls — they perform a single
HTTPS request each and complete quickly.
"""
import logging
import os
from typing import Optional, Tuple

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.models.patient import Patient, SepsisAlert

log = logging.getLogger(__name__)


def send_whatsapp(to_number: str, body: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Send a WhatsApp message via Twilio.

    Args:
        to_number: Recipient in E.164 format, e.g. "+919876543210".
        body:      Message text (max ~1600 chars for WhatsApp).

    Returns:
        (message_sid, error_message)
        On success: (sid, None)
        On failure: (None, error_description)
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_WHATSAPP_FROM")

    if not all([account_sid, auth_token, from_number]):
        log.warning("Twilio credentials not fully configured — WhatsApp notification skipped")
        return None, "TWILIO_NOT_CONFIGURED"

    try:
        client = Client(account_sid, auth_token)
        # from_number may already include the "whatsapp:" prefix (from .env)
        from_wa = from_number if from_number.startswith("whatsapp:") else f"whatsapp:{from_number}"
        to_wa = to_number if to_number.startswith("whatsapp:") else f"whatsapp:{to_number}"
        msg = client.messages.create(
            from_=from_wa,
            to=to_wa,
            body=body,
        )
        log.info("WhatsApp sent to %s — Twilio SID: %s status: %s", to_number, msg.sid, msg.status)
        return msg.sid, None

    except TwilioRestException as exc:
        log.error(
            "Twilio error sending WhatsApp to %s — code: %s msg: %s",
            to_number,
            exc.code,
            exc.msg,
        )
        return None, f"Twilio {exc.code}: {exc.msg}"

    except Exception as exc:
        log.error("Unexpected error sending WhatsApp to %s: %s", to_number, exc)
        return None, str(exc)


def format_alert_message(patient: Patient, alert: SepsisAlert, sofa_score: int) -> str:
    """
    Build the WhatsApp message body for a sepsis alert.

    Keeps the message concise to be readable on a phone screen.
    Clinical summary is truncated at 400 chars to stay within WhatsApp limits.
    """
    lines = [
        f"🚨 *SEPSIS WATCH — {alert.alert_level or 'ALERT'}*",
        f"Patient : {patient.name}",
        f"Ward    : {patient.ward or 'Unknown'} | Age: {patient.age or '?'}",
        f"Risk    : {alert.risk_score:.0%} | SOFA: {sofa_score}/24",
        f"Time    : {alert.triggered_at.strftime('%d %b %Y %H:%M')} UTC",
        "",
    ]
    if alert.clinical_summary:
        summary = alert.clinical_summary[:400]
        if len(alert.clinical_summary) > 400:
            summary += "…"
        lines += ["*Clinical Summary:*", summary, ""]

    lines.append(
        "⚠️ _Decision support only. All treatment decisions remain with the attending physician._"
    )
    return "\n".join(lines)
