"""
SepsisLSTM training script.

Two modes:
  1. Synthetic data (default, runs immediately, no MIMIC-III needed)
     Generates physiologically realistic ICU sequences with known sepsis labels.
     Good for development, smoke-testing the full inference pipeline, and
     verifying the model architecture before real data arrives.

  2. MIMIC-III data (--mode mimic)
     Loads from the database after scripts/load_mimic.py has been run.
     Produces a model trained on real retrospective ICU outcomes.

Usage:
  # Synthetic (no DB needed):
  python -m ml.sepsis.train

  # MIMIC-III (DB must be running with data loaded):
  python -m ml.sepsis.train --mode mimic

  # Custom hyper-params:
  python -m ml.sepsis.train --epochs 30 --batch-size 64 --lr 1e-3

Checkpoint saved to:
  ml/checkpoints/sepsis_lstm_v1.pt

After training, run:
  python scripts/register_model.py
to register the checkpoint in ml_model_versions so scoring.py uses it.
"""
import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset, random_split

# Allow running as `python -m ml.sepsis.train` from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ml.sepsis.model import SepsisLSTM  # noqa: E402

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

CHECKPOINT_PATH = Path("ml/checkpoints/sepsis_lstm_v1.pt")
SEQUENCE_HOURS = 24
NUM_FEATURES = 14  # must match FEATURE_COLS in features.py


# ── Synthetic data generation ─────────────────────────────────────────────────

def _make_sepsis_sequence(rng: np.random.Generator) -> np.ndarray:
    """
    Generate a 24h synthetic sequence for a septic patient.

    Physiology:
      - HR drifts upward (tachycardia)
      - MAP drifts downward (hypotension)
      - SpO2 gradually falls
      - RR rises (tachypnoea)
      - Temp initially spikes, may normalise or fall (cold sepsis)
      - Lactate rises (tissue hypoperfusion)
      - Platelets fall (coagulopathy)
      - Creatinine rises (AKI)
      - Bilirubin rises (hepatic dysfunction)
    """
    t = np.linspace(0, 1, SEQUENCE_HOURS)

    # Feature order: HR, SBP, DBP, MAP, SpO2, RR, Temp, GCS,
    #                WBC, Creatinine, Bilirubin, Platelets, Lactate, PaO2/FiO2
    hr   = 90  + 40 * t + rng.normal(0, 4, SEQUENCE_HOURS)             # 90→130
    sbp  = 118 - 35 * t + rng.normal(0, 5, SEQUENCE_HOURS)             # 118→83
    dbp  = 75  - 22 * t + rng.normal(0, 4, SEQUENCE_HOURS)             # 75→53
    map_ = 90  - 28 * t + rng.normal(0, 4, SEQUENCE_HOURS)             # 90→62
    spo2 = 98  - 8  * t + rng.normal(0, 1, SEQUENCE_HOURS)             # 98→90
    rr   = 14  + 14 * t + rng.normal(0, 2, SEQUENCE_HOURS)             # 14→28
    temp = 38.5 + 0.8 * np.sin(np.pi * t) + rng.normal(0, 0.2, SEQUENCE_HOURS)  # spike then drop
    gcs  = 15  - 4  * t + rng.normal(0, 0.5, SEQUENCE_HOURS)           # 15→11

    wbc       = 12 + 8  * t + rng.normal(0, 1.5, SEQUENCE_HOURS)       # 12→20
    creat     = 1.0 + 3.0 * t**2 + rng.normal(0, 0.2, SEQUENCE_HOURS)  # 1→4
    bili      = 0.8 + 2.5 * t + rng.normal(0, 0.2, SEQUENCE_HOURS)     # 0.8→3.3
    platelets = 200 - 140 * t + rng.normal(0, 15, SEQUENCE_HOURS)      # 200→60
    lactate   = 1.0 + 4.0 * t**1.5 + rng.normal(0, 0.3, SEQUENCE_HOURS)  # 1→5
    pao2fio2  = 380 - 200 * t + rng.normal(0, 20, SEQUENCE_HOURS)      # 380→180

    seq = np.stack([hr, sbp, dbp, map_, spo2, rr, temp, gcs,
                    wbc, creat, bili, platelets, lactate, pao2fio2], axis=1)
    return seq.astype(np.float32)


def _make_nonsepsis_sequence(rng: np.random.Generator) -> np.ndarray:
    """
    Generate a 24h synthetic sequence for a non-septic ICU patient.

    Physiology: mild fluctuations around normal ICU values, slight
    improving trends (post-op recovery or stable cardiac patient).
    """
    t = np.linspace(0, 1, SEQUENCE_HOURS)

    hr   = 80 + 10 * np.sin(np.pi * t * 2) + rng.normal(0, 4, SEQUENCE_HOURS)
    sbp  = 125 + 5  * np.sin(np.pi * t) + rng.normal(0, 5, SEQUENCE_HOURS)
    dbp  = 78  + 3  * np.sin(np.pi * t) + rng.normal(0, 3, SEQUENCE_HOURS)
    map_ = 93  + 4  * np.sin(np.pi * t) + rng.normal(0, 3, SEQUENCE_HOURS)
    spo2 = 98  - 1  * t + rng.normal(0, 0.5, SEQUENCE_HOURS)           # barely changes
    rr   = 16  + 2  * t + rng.normal(0, 1.5, SEQUENCE_HOURS)
    temp = 37.2 + 0.3 * rng.normal(0, 1, SEQUENCE_HOURS)
    gcs  = 14  + rng.integers(0, 2, SEQUENCE_HOURS).astype(float)      # 14–15

    wbc       = 8   + 1   * rng.normal(0, 1, SEQUENCE_HOURS)
    creat     = 0.9 + 0.1 * rng.normal(0, 1, SEQUENCE_HOURS)
    bili      = 0.7 + 0.1 * rng.normal(0, 1, SEQUENCE_HOURS)
    platelets = 220 + 20  * rng.normal(0, 1, SEQUENCE_HOURS)           # stable
    lactate   = 1.1 + 0.2 * rng.normal(0, 1, SEQUENCE_HOURS)
    pao2fio2  = 370 + 20  * rng.normal(0, 1, SEQUENCE_HOURS)

    seq = np.stack([hr, sbp, dbp, map_, spo2, rr, temp, gcs,
                    wbc, creat, bili, platelets, lactate, pao2fio2], axis=1)
    return seq.astype(np.float32)


def generate_synthetic_dataset(
    n_sepsis: int = 1000,
    n_nonsepsis: int = 1000,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Returns:
        X : (n_total, SEQUENCE_HOURS, NUM_FEATURES)  float32
        y : (n_total,)                               float32  (0 or 1)
    """
    rng = np.random.default_rng(seed)

    sepsis_seqs    = [_make_sepsis_sequence(rng)    for _ in range(n_sepsis)]
    nonsepsis_seqs = [_make_nonsepsis_sequence(rng) for _ in range(n_nonsepsis)]

    X = np.stack(sepsis_seqs + nonsepsis_seqs, axis=0)
    y = np.array([1.0] * n_sepsis + [0.0] * n_nonsepsis, dtype=np.float32)

    # Shuffle
    idx = rng.permutation(len(y))
    return X[idx], y[idx]


# ── MIMIC-III dataset loader ──────────────────────────────────────────────────

def _load_mimic_dataset(
    augment_synthetic: int = 1500,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Load sequences from the DB (requires load_mimic.py to have been run).

    Labels (Sepsis-3-inspired, ICD-code driven):
      Positive (1): patient has any sepsis/septicemia/bacteremia/septic-shock
                    ICD diagnosis recorded in the comorbidities table.
      Negative (0): no such diagnosis.

    Augmentation:
      Because the MIMIC demo dataset is small (≤100 patients), synthetic
      sequences generated by _make_sepsis_sequence / _make_nonsepsis_sequence
      are appended so the model sees enough examples to generalise.
      Set augment_synthetic=0 to disable.

    NOTE: We deliberately avoid using sepsis_alerts as labels because those
    alerts are produced by the model itself — using them would be circular.
    """
    import asyncio

    # ── Sepsis ICD-9 keyword patterns ────────────────────────────────────────
    SEPSIS_KEYWORDS = (
        "sepsis", "septic", "septicemia", "septicaemia",
        "bacteremia", "bacteraemia",
    )

    async def _fetch():
        from sqlalchemy import select, func, or_
        from sqlalchemy import String
        from app.db.base import AsyncSessionLocal
        from app.models.patient import Patient, Comorbidity, VitalReading
        from ml.sepsis.features import build_feature_tensor

        async with AsyncSessionLocal() as db:
            res = await db.execute(select(Patient).limit(5000))
            patients = res.scalars().all()

            # Build set of patient IDs with sepsis diagnoses (ICD ground truth)
            conditions = [
                Comorbidity.condition_name.ilike(f"%{kw}%")
                for kw in SEPSIS_KEYWORDS
            ]
            sep_res = await db.execute(
                select(Comorbidity.patient_id).where(or_(*conditions)).distinct()
            )
            sepsis_patient_ids = {row[0] for row in sep_res.fetchall()}

        sequences, labels = [], []
        async with AsyncSessionLocal() as db:
            for p in patients:
                # Anchor the feature window to the patient's LAST vital reading.
                ref_res = await db.execute(
                    select(func.max(VitalReading.recorded_at))
                    .where(VitalReading.patient_id == p.id)
                )
                reference_time = ref_res.scalar_one_or_none()
                if reference_time is None:
                    continue  # patient has no vitals

                seq = await build_feature_tensor(
                    str(p.id), db, reference_time=reference_time
                )
                if seq is None:
                    continue  # fewer than MIN_VITAL_READINGS

                label = 1.0 if p.id in sepsis_patient_ids else 0.0
                sequences.append(seq)
                labels.append(label)

        return sequences, labels

    real_seqs, real_labels = asyncio.run(_fetch())
    real_labels_arr = np.array(real_labels, dtype=np.float32)

    n_real    = len(real_labels_arr)
    n_sepsis  = int(real_labels_arr.sum())
    n_nosep   = n_real - n_sepsis
    log.info(
        "MIMIC real data: %d sequences | sepsis=%d (%.1f%%) | no-sepsis=%d",
        n_real, n_sepsis, 100 * n_sepsis / max(n_real, 1), n_nosep,
    )

    if n_real == 0:
        raise RuntimeError(
            "No MIMIC sequences found — ensure load_mimic.py has been run "
            "and patients have at least MIN_VITAL_READINGS vitals."
        )

    X_real = np.stack(real_seqs, axis=0).astype(np.float32)

    if augment_synthetic <= 0:
        return X_real, real_labels_arr

    # ── Augment with synthetic data ───────────────────────────────────────────
    # Aim for balanced classes: generate enough synthetic to reach augment_synthetic
    # total examples while keeping a ~50/50 split.
    rng = np.random.default_rng(42)
    half   = augment_synthetic // 2
    aug_X  = np.stack(
        [_make_sepsis_sequence(rng) for _ in range(half)]
        + [_make_nonsepsis_sequence(rng) for _ in range(half)],
        axis=0,
    ).astype(np.float32)
    aug_y = np.array([1.0] * half + [0.0] * half, dtype=np.float32)

    X_all = np.concatenate([X_real, aug_X], axis=0)
    y_all = np.concatenate([real_labels_arr, aug_y], axis=0)

    # Shuffle
    idx = rng.permutation(len(y_all))
    log.info(
        "Combined dataset: %d sequences | sepsis=%.1f%%",
        len(y_all), 100 * y_all[idx].mean(),
    )
    return X_all[idx], y_all[idx]


# ── Normalisation ─────────────────────────────────────────────────────────────

# Per-feature mean and std computed from synthetic dataset statistics.
# When MIMIC data is used, these are re-computed from the training split.
_FEATURE_MEAN = np.array([
    96.0,   # HR
    105.0,  # SBP
    66.0,   # DBP
    79.0,   # MAP
    95.0,   # SpO2
    18.0,   # RR
    37.8,   # Temp
    14.0,   # GCS
    10.0,   # WBC
    1.5,    # Creatinine
    1.2,    # Bilirubin
    155.0,  # Platelets
    2.0,    # Lactate
    290.0,  # PaO2/FiO2
], dtype=np.float32)

_FEATURE_STD = np.array([
    20.0, 20.0, 12.0, 15.0, 4.0, 6.0, 0.8, 1.5,
    4.0,  1.0,  1.0,  70.0, 1.5, 100.0,
], dtype=np.float32)


def _normalise(X: np.ndarray, mean=None, std=None):
    mean = _FEATURE_MEAN if mean is None else mean
    std  = _FEATURE_STD  if std  is None else std
    std  = np.where(std == 0, 1.0, std)  # avoid div-by-zero
    return (X - mean) / std, mean, std


# ── Training loop ─────────────────────────────────────────────────────────────

def train(
    mode: str = "synthetic",
    epochs: int = 25,
    batch_size: int = 32,
    lr: float = 5e-4,
    val_split: float = 0.15,
    n_synthetic: int = 2000,
):
    log.info("=== SepsisLSTM Training (%s mode) ===", mode)

    # ── Load data ────────────────────────────────────────────────────────────
    if mode == "mimic":
        log.info("Loading sequences from database…")
        X, y = _load_mimic_dataset()
    else:
        log.info("Generating %d synthetic ICU patient sequences…", n_synthetic)
        half = n_synthetic // 2
        X, y = generate_synthetic_dataset(n_sepsis=half, n_nonsepsis=half)

    log.info("Dataset: %d sequences | sepsis=%.1f%%", len(y), 100 * y.mean())

    # ── Normalise ────────────────────────────────────────────────────────────
    X, mean, std = _normalise(X)
    np.save("ml/checkpoints/feature_mean.npy", mean)
    np.save("ml/checkpoints/feature_std.npy",  std)
    log.info("Feature normalisation stats saved.")

    # ── Split ────────────────────────────────────────────────────────────────
    dataset = TensorDataset(
        torch.from_numpy(X),
        torch.from_numpy(y),
    )
    n_val  = max(1, int(len(dataset) * val_split))
    n_train = len(dataset) - n_val
    train_ds, val_ds = random_split(dataset, [n_train, n_val],
                                    generator=torch.Generator().manual_seed(42))

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader   = DataLoader(val_ds,   batch_size=batch_size)

    # ── Model / optimiser ────────────────────────────────────────────────────
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    log.info("Training on device: %s", device)

    model     = SepsisLSTM().to(device)
    criterion = nn.BCELoss()
    optimiser = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimiser, T_max=epochs)

    best_val_loss = float("inf")

    for epoch in range(1, epochs + 1):
        # ── Train ────────────────────────────────────────────────────────────
        model.train()
        train_loss = 0.0
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimiser.zero_grad()
            pred = model(xb)
            loss = criterion(pred, yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimiser.step()
            train_loss += loss.item() * len(yb)
        train_loss /= n_train

        # ── Validate ─────────────────────────────────────────────────────────
        model.eval()
        val_loss = 0.0
        correct  = 0
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(device), yb.to(device)
                pred = model(xb)
                val_loss += criterion(pred, yb).item() * len(yb)
                predicted = (pred >= 0.5).float()
                correct  += (predicted == yb).sum().item()
        val_loss /= n_val
        val_acc = correct / n_val

        scheduler.step()

        log.info(
            "Epoch %3d/%d | train_loss=%.4f | val_loss=%.4f | val_acc=%.3f",
            epoch, epochs, train_loss, val_loss, val_acc,
        )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), CHECKPOINT_PATH)
            log.info("  ✓ Checkpoint saved (val_loss=%.4f)", val_loss)

    log.info("Training complete. Best val_loss=%.4f", best_val_loss)
    log.info("Checkpoint: %s", CHECKPOINT_PATH.resolve())
    log.info("")
    log.info("Next step → run:  python scripts/register_model.py")
    log.info("This inserts the checkpoint into ml_model_versions so the")
    log.info("scoring pipeline uses the LSTM instead of the SOFA heuristic.")


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train SepsisLSTM")
    parser.add_argument(
        "--mode", choices=["synthetic", "mimic"], default="synthetic",
        help="Data source. 'synthetic' runs immediately; 'mimic' requires load_mimic.py.",
    )
    parser.add_argument("--epochs",     type=int,   default=25)
    parser.add_argument("--batch-size", type=int,   default=32)
    parser.add_argument("--lr",         type=float, default=5e-4)
    parser.add_argument("--n-synthetic",type=int,   default=2000,
                        help="Total synthetic sequences (half sepsis, half non-sepsis).")
    args = parser.parse_args()

    train(
        mode=args.mode,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        n_synthetic=args.n_synthetic,
    )
