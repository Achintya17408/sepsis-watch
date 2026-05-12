"""
Register a trained SepsisLSTM checkpoint in the ml_model_versions table.

Run this after ml/sepsis/train.py to activate the LSTM inference path.
Once registered, scoring.py will use the LSTM instead of the SOFA heuristic.

Usage:
    python scripts/register_model.py

Options:
    --checkpoint   Path to .pt file  (default: ml/checkpoints/sepsis_lstm_v1.pt)
    --model-name   Name to register  (default: sepsis_lstm)
    --description  Free-text note    (default: auto-generated)
    --no-activate  Register but leave is_active=False
"""
import argparse
import asyncio
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update
from dotenv import load_dotenv

load_dotenv()

from app.db.base import AsyncSessionLocal  # noqa: E402
from app.models.patient import MlModelVersion  # noqa: E402


async def register(
    checkpoint: str,
    model_name: str,
    notes: str,
    activate: bool,
) -> None:
    path = Path(checkpoint)
    if not path.exists():
        print(f"ERROR: checkpoint not found at '{path.resolve()}'")
        print("Run 'python -m ml.sepsis.train' first.")
        sys.exit(1)

    size_mb = path.stat().st_size / 1_048_576
    version_tag = f"v1.{datetime.utcnow().strftime('%Y%m%d%H%M')}"

    async with AsyncSessionLocal() as db:
        # Deactivate any existing active version of this model
        if activate:
            await db.execute(
                update(MlModelVersion)
                .where(
                    MlModelVersion.model_name == model_name,
                    MlModelVersion.is_active == True,
                )
                .values(is_active=False)
            )
            print(f"Deactivated any existing active '{model_name}' versions.")

        version = MlModelVersion(
            id=uuid.uuid4(),
            model_name=model_name,
            version_tag=version_tag,
            framework="pytorch",
            architecture="BiLSTM+TemporalAttention",
            artifact_path=str(path.resolve()),
            notes=notes or f"Trained {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC | {size_mb:.1f} MB",
            is_active=activate,
            created_at=datetime.utcnow(),
            trained_at=datetime.utcnow(),
            decision_threshold=0.5,
        )
        db.add(version)
        await db.commit()
        await db.refresh(version)

    status = "ACTIVE" if activate else "INACTIVE"
    print(f"\n✓ Registered '{model_name}' checkpoint [{status}]")
    print(f"  ID          : {version.id}")
    print(f"  Version tag : {version.version_tag}")
    print(f"  Path        : {version.artifact_path}")
    print(f"  Size        : {size_mb:.1f} MB")
    print(f"  Notes       : {version.notes}")

    if activate:
        print("\nThe scoring pipeline will now use LSTM inference instead of SOFA heuristic.")
        print("Restart uvicorn and the Celery worker if they are running.")
    else:
        print(f"\nActivate later with: UPDATE ml_model_versions SET is_active=true WHERE id='{version.id}';")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Register a SepsisLSTM checkpoint")
    parser.add_argument(
        "--checkpoint", default="ml/checkpoints/sepsis_lstm_v1.pt",
        help="Path to the trained .pt file",
    )
    parser.add_argument(
        "--model-name", default="sepsis_lstm",
        help="Model name (must match what inference.py queries for)",
    )
    parser.add_argument("--notes", default="", help="Optional notes")
    parser.add_argument(
        "--no-activate", action="store_true",
        help="Register without setting is_active=True",
    )
    args = parser.parse_args()

    asyncio.run(register(
        checkpoint=args.checkpoint,
        model_name=args.model_name,
        notes=args.notes,
        activate=not args.no_activate,
    ))
