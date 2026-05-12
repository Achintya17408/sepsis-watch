"""
Feature extraction for SepsisLSTM inference.

Queries vital_readings and lab_results tables for a given patient,
bins the readings into SEQUENCE_HOURS hourly slots, forward-fills
missing values, and zero-imputes any remaining gaps.

Output shape: (SEQUENCE_HOURS=24, NUM_FEATURES=14)  dtype=float32

Column order (must be identical to what the model was trained with):
  [0]  heart_rate
  [1]  systolic_bp
  [2]  diastolic_bp
  [3]  mean_arterial_bp
  [4]  spo2
  [5]  respiratory_rate
  [6]  temperature_c
  [7]  gcs_total
  [8]  wbc
  [9]  creatinine
  [10] bilirubin_total
  [11] platelets
  [12] lactate
  [13] pao2_fio2_ratio
"""
import uuid as _uuid_mod
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import LabResult, VitalReading

FEATURE_COLS = [
    # Vitals (8)
    "heart_rate",
    "systolic_bp",
    "diastolic_bp",
    "mean_arterial_bp",
    "spo2",
    "respiratory_rate",
    "temperature_c",
    "gcs_total",
    # Labs (6)
    "wbc",
    "creatinine",
    "bilirubin_total",
    "platelets",
    "lactate",
    "pao2_fio2_ratio",
]

SEQUENCE_HOURS: int = 24   # look-back window length
MIN_VITAL_READINGS: int = 3  # minimum readings required; return None if fewer


async def build_feature_tensor(
    patient_id: str,
    db: AsyncSession,
    reference_time: Optional[datetime] = None,
) -> Optional[np.ndarray]:
    """
    Build a (SEQUENCE_HOURS, NUM_FEATURES) float32 array for the given patient.

    reference_time controls the anchor of the 24-hour window:
    - None (default / inference mode): anchor = datetime.utcnow(), and only
      readings within the last SEQUENCE_HOURS are fetched.
    - explicit datetime (training mode): anchor = that time, ALL readings for
      the patient are fetched and binned relative to the anchor. Readings older
      than SEQUENCE_HOURS before the anchor fall into slot 0 (oldest bucket).
      This correctly handles MIMIC-III's date-shifted historical timestamps.

    Returns None if the patient has fewer than MIN_VITAL_READINGS vital
    recordings in the look-back window (insufficient data for LSTM).
    """
    try:
        pid = _uuid_mod.UUID(patient_id)
    except ValueError:
        return None

    training_mode = reference_time is not None
    now = reference_time if training_mode else datetime.utcnow()

    # ── Query vitals ─────────────────────────────────────────────────────────
    if training_mode:
        # Historical mode: fetch ALL vitals; bin relative to reference_time
        v_result = await db.execute(
            select(VitalReading)
            .where(VitalReading.patient_id == pid)
            .order_by(VitalReading.recorded_at.asc())
        )
    else:
        cutoff = now - timedelta(hours=SEQUENCE_HOURS)
        v_result = await db.execute(
            select(VitalReading)
            .where(VitalReading.patient_id == pid, VitalReading.recorded_at >= cutoff)
            .order_by(VitalReading.recorded_at.asc())
        )
    vital_rows = v_result.scalars().all()

    if len(vital_rows) < MIN_VITAL_READINGS:
        return None

    # ── Query labs ───────────────────────────────────────────────────────────
    if training_mode:
        l_result = await db.execute(
            select(LabResult)
            .where(LabResult.patient_id == pid)
            .order_by(LabResult.collected_at.asc())
        )
    else:
        cutoff = now - timedelta(hours=SEQUENCE_HOURS)
        l_result = await db.execute(
            select(LabResult)
            .where(LabResult.patient_id == pid, LabResult.collected_at >= cutoff)
            .order_by(LabResult.collected_at.asc())
        )
    lab_rows = l_result.scalars().all()

    # ── Build (SEQUENCE_HOURS × NUM_FEATURES) matrix initialised with NaN ───
    n_features = len(FEATURE_COLS)
    matrix = np.full((SEQUENCE_HOURS, n_features), np.nan, dtype=np.float32)

    def _time_to_slot(ts: datetime) -> int:
        """Convert a timestamp to a 0-based time slot index (0=oldest, 23=newest)."""
        age_h = (now - ts).total_seconds() / 3600.0
        # Clamp to [0, SEQUENCE_HOURS-1] — handles both future timestamps (negative
        # age_h, e.g. MIMIC date-shifted patients) and very old readings.
        slot = int(max(0.0, min(float(age_h), float(SEQUENCE_HOURS - 1))))
        return SEQUENCE_HOURS - 1 - slot  # ascending: 0=oldest bucket

    for row in vital_rows:
        _fill_vital(matrix, _time_to_slot(row.recorded_at), row)

    for row in lab_rows:
        _fill_lab(matrix, _time_to_slot(row.collected_at), row)

    # ── Forward-fill then zero-impute ────────────────────────────────────────
    for col in range(n_features):
        last = np.nan
        for t in range(SEQUENCE_HOURS):
            if not np.isnan(matrix[t, col]):
                last = matrix[t, col]
            elif not np.isnan(last):
                matrix[t, col] = last

    np.nan_to_num(matrix, nan=0.0, copy=False)
    return matrix  # (24, 14)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _set(matrix: np.ndarray, t: int, col: str, val: Optional[float]) -> None:
    if val is not None:
        matrix[t, FEATURE_COLS.index(col)] = float(val)


def _fill_vital(matrix: np.ndarray, t: int, row: VitalReading) -> None:
    _set(matrix, t, "heart_rate", row.heart_rate)
    _set(matrix, t, "systolic_bp", row.systolic_bp)
    _set(matrix, t, "diastolic_bp", row.diastolic_bp)
    _set(matrix, t, "mean_arterial_bp", row.mean_arterial_bp)
    _set(matrix, t, "spo2", row.spo2)
    _set(matrix, t, "respiratory_rate", row.respiratory_rate)
    _set(matrix, t, "temperature_c", row.temperature_c)
    if row.gcs_total is not None:
        _set(matrix, t, "gcs_total", float(row.gcs_total))


def _fill_lab(matrix: np.ndarray, t: int, row: LabResult) -> None:
    _set(matrix, t, "wbc", row.wbc)
    _set(matrix, t, "creatinine", row.creatinine)
    _set(matrix, t, "bilirubin_total", row.bilirubin_total)
    _set(matrix, t, "platelets", row.platelets)
    _set(matrix, t, "lactate", row.lactate)
    _set(matrix, t, "pao2_fio2_ratio", row.pao2_fio2_ratio)
