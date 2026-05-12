"""
Celery application + periodic scoring task.

Start the worker (processes task queue):
    celery -A app.worker worker --loglevel=info

Start the beat scheduler (fires periodic tasks):
    celery -A app.worker beat --loglevel=info

Or combine both in one process (dev only — not recommended for production):
    celery -A app.worker worker --beat --loglevel=info
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta

from celery import Celery

log = logging.getLogger(__name__)

celery_app = Celery(
    "sepsis_watch",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,   # one task at a time per worker process
    task_acks_late=True,            # acknowledge only after the task completes
    broker_connection_retry_on_startup=True,
    beat_schedule={
        # Runs every 15 minutes — scores all patients with active ICU admissions
        "score-active-icu-patients": {
            "task": "app.worker.score_all_active_patients",
            "schedule": 900.0,
        }
    },
)


# ── Periodic task: score all active ICU patients ─────────────────────────────


@celery_app.task(
    name="app.worker.score_all_active_patients",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def score_all_active_patients(self):  # type: ignore[override]
    """
    Every 15 minutes: iterate patients with active ICU admissions and run
    SOFA + LSTM scoring.  Fires SepsisAlerts where warranted.
    """
    try:
        asyncio.run(_run_batch_scoring())
    except Exception as exc:
        log.error("Batch scoring task failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


async def _run_batch_scoring() -> None:
    from sqlalchemy import select

    from app.db.base import AsyncSessionLocal
    from app.models.patient import IcuAdmission
    from app.services.scoring import _score_patient

    log.info("Periodic batch scoring started")

    # Find patient IDs with admissions that are still open or closed within last 12h
    # (a patient discharged <12h ago might still trigger an alert we want to capture)
    cutoff = datetime.utcnow() - timedelta(hours=12)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(IcuAdmission.patient_id)
            .where(
                (IcuAdmission.icu_discharged_at.is_(None))
                | (IcuAdmission.icu_discharged_at >= cutoff)
            )
            .distinct()
        )
        patient_ids = [str(row[0]) for row in result.fetchall()]

    log.info("Batch scoring: %d active ICU patient(s)", len(patient_ids))

    async with AsyncSessionLocal() as db:
        for pid in patient_ids:
            try:
                await _score_patient(pid, db)
                await db.commit()
            except Exception as exc:
                await db.rollback()
                log.error("Scoring failed for patient %s: %s", pid, exc, exc_info=True)

    log.info("Batch scoring complete")


# ── On-demand task: score a single patient ───────────────────────────────────


@celery_app.task(name="app.worker.score_single_patient")
def score_single_patient(patient_id: str) -> None:
    """
    On-demand scoring for one patient.
    Can be enqueued from anywhere: celery_app.send_task('app.worker.score_single_patient', args=[pid])
    """
    try:
        asyncio.run(_run_single_scoring(patient_id))
    except Exception as exc:
        log.error("On-demand scoring failed for patient %s: %s", patient_id, exc, exc_info=True)


async def _run_single_scoring(patient_id: str) -> None:
    from app.db.base import AsyncSessionLocal
    from app.services.scoring import _score_patient

    async with AsyncSessionLocal() as db:
        try:
            await _score_patient(patient_id, db)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            raise
