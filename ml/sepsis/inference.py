"""
SepsisLSTM inference engine.

Loads the active model checkpoint from the ml_model_versions registry,
builds the feature tensor from the last 24h of patient data, and runs
a forward pass.

Falls back to None (caller uses SOFA heuristic) when:
  - No active sepsis_lstm entry in ml_model_versions
  - Checkpoint file absent from disk
  - Patient has < 3 vital readings in the look-back window
  - Any unexpected PyTorch error

Model is cached in-process after first load to avoid repeated disk I/O.
"""
import logging
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import torch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import MlModelVersion
from ml.sepsis.features import SEQUENCE_HOURS, build_feature_tensor
from ml.sepsis.model import SepsisLSTM

log = logging.getLogger(__name__)

# Module-level cache: checkpoint_path_str → SepsisLSTM instance
_model_cache: Dict[str, SepsisLSTM] = {}


async def get_risk_score(patient_id: str, db: AsyncSession) -> Optional[float]:
    """
    Run LSTM inference for a patient.

    Returns:
        float in [0.0, 1.0] — sepsis risk score, or
        None  — if inference is not possible (caller uses SOFA heuristic).
    """
    # ── Find active model version ────────────────────────────────────────────
    mv_res = await db.execute(
        select(MlModelVersion).where(
            MlModelVersion.model_name == "sepsis_lstm",
            MlModelVersion.is_active == True,
        ).limit(1)
    )
    model_version: Optional[MlModelVersion] = mv_res.scalar_one_or_none()

    if not model_version or not model_version.artifact_path:
        log.debug("No active sepsis_lstm model registered — LSTM inference skipped")
        return None

    checkpoint_path = Path(model_version.artifact_path)
    if not checkpoint_path.exists():
        log.warning(
            "Model checkpoint not found at '%s' — LSTM inference skipped", checkpoint_path
        )
        return None

    # ── Build feature tensor ─────────────────────────────────────────────────
    feature_matrix = await build_feature_tensor(patient_id, db)
    if feature_matrix is None:
        log.debug(
            "Insufficient data for LSTM inference (patient=%s, need >=%d vital readings "
            "in last %dh)",
            patient_id,
            3,
            SEQUENCE_HOURS,
        )
        return None

    # ── Load model (cached after first call) ─────────────────────────────────
    model = _load_model(str(checkpoint_path))
    if model is None:
        return None

    # ── Forward pass ─────────────────────────────────────────────────────────
    try:
        x = torch.tensor(feature_matrix, dtype=torch.float32).unsqueeze(0)  # (1, 24, 14)
        with torch.no_grad():
            risk: float = model(x).item()
        return float(np.clip(risk, 0.0, 1.0))
    except Exception as exc:
        log.error("LSTM forward pass failed for patient %s: %s", patient_id, exc, exc_info=True)
        return None


def _load_model(checkpoint_path: str) -> Optional[SepsisLSTM]:
    """
    Load SepsisLSTM from a PyTorch state-dict checkpoint.
    Caches the loaded model by path to avoid repeated disk reads.
    """
    if checkpoint_path in _model_cache:
        return _model_cache[checkpoint_path]

    try:
        model = SepsisLSTM()
        state_dict = torch.load(
            checkpoint_path,
            map_location=torch.device("cpu"),
            weights_only=True,  # safe loading — do not unpickle arbitrary objects
        )
        model.load_state_dict(state_dict)
        model.eval()
        _model_cache[checkpoint_path] = model
        log.info("SepsisLSTM loaded and cached from '%s'", checkpoint_path)
        return model
    except Exception as exc:
        log.error("Failed to load LSTM checkpoint from '%s': %s", checkpoint_path, exc)
        return None
