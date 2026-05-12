"""
SepsisLSTM — Bidirectional LSTM + temporal attention for sepsis risk scoring.

Architecture:
  Input  : (batch, seq_len=24, input_dim=14)  — hourly vitals+labs tensor
  BiLSTM : 2 layers, hidden_dim=128 per direction → output (batch, seq, 256)
  Attention: learned soft-attention over seq dimension → context (batch, 256)
  Head   : FC(256→64) → ReLU → Dropout → FC(64→1) → Sigmoid
  Output : (batch,)  — risk score in [0.0, 1.0]

Feature columns (14, order must match FEATURE_COLS in ml/sepsis/features.py):
  0  heart_rate         bpm
  1  systolic_bp        mmHg
  2  diastolic_bp       mmHg
  3  mean_arterial_bp   mmHg       (SOFA cardiovascular)
  4  spo2               %
  5  respiratory_rate   breaths/min
  6  temperature_c      °C
  7  gcs_total          3–15       (SOFA neurological)
  8  wbc                ×10³/µL
  9  creatinine         mg/dL      (SOFA renal)
  10 bilirubin_total    mg/dL      (SOFA hepatic)
  11 platelets          ×10³/µL   (SOFA coagulation)
  12 lactate            mmol/L     (septic shock marker)
  13 pao2_fio2_ratio    mmHg       (SOFA respiratory)

Training:
  Run ml/sepsis/train.py (not included in this release) using MIMIC-III CSVs
  loaded by scripts/load_mimic.py.  Labels come from Sepsis-3 onset annotations
  in the angus2001 / simplified-SOFA-2 consensus dataset.

Checkpoint format:
  torch.save(model.state_dict(), "ml/checkpoints/sepsis_lstm_v1.pt")
  Register the path in the ml_model_versions table with is_active=True.
"""
import torch
import torch.nn as nn


class TemporalAttention(nn.Module):
    """
    Additive (Bahdanau-style) attention over the time dimension of LSTM outputs.

    Learns a scalar score for each timestep, then produces a weighted context
    vector via softmax-normalised sum.  This lets the model focus on the most
    clinically abnormal time windows rather than just the final hidden state.
    """

    def __init__(self, hidden_dim: int) -> None:
        super().__init__()
        # Maps each hidden state to a scalar importance score
        self.score_layer = nn.Linear(hidden_dim, 1, bias=False)

    def forward(
        self, lstm_out: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            lstm_out : (batch, seq_len, hidden_dim)
        Returns:
            context  : (batch, hidden_dim)  — attention-weighted sum
            weights  : (batch, seq_len)     — attention distribution (sums to 1)
        """
        # (batch, seq_len, hidden) → (batch, seq_len, 1) → (batch, seq_len)
        logits = self.score_layer(lstm_out).squeeze(-1)
        weights = torch.softmax(logits, dim=1)           # (batch, seq_len)
        context = (lstm_out * weights.unsqueeze(-1)).sum(dim=1)  # (batch, hidden)
        return context, weights


class SepsisLSTM(nn.Module):
    """
    Bidirectional LSTM + temporal attention for sepsis risk scoring.

    The BiLSTM captures:
      - Forward direction : deteriorating trend (HR rising, MAP falling, …)
      - Backward direction: recovery/stabilisation patterns

    Class constants mirror the defaults used during MIMIC-III pre-training
    so the architecture can be recreated identically for inference.
    """

    NUM_FEATURES: int = 14   # must match len(FEATURE_COLS) in features.py
    HIDDEN_DIM: int = 128
    NUM_LAYERS: int = 2
    DROPOUT: float = 0.3

    def __init__(
        self,
        input_dim: int = NUM_FEATURES,
        hidden_dim: int = HIDDEN_DIM,
        num_layers: int = NUM_LAYERS,
        dropout: float = DROPOUT,
    ) -> None:
        super().__init__()
        self.hidden_dim = hidden_dim

        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        # Bidirectional → output feature size is hidden_dim × 2
        bi_hidden = hidden_dim * 2

        self.attention = TemporalAttention(bi_hidden)

        self.classifier = nn.Sequential(
            nn.Linear(bi_hidden, 64),
            nn.ReLU(),
            nn.Dropout(p=dropout),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x : (batch, seq_len, input_dim)  float32 tensor.
                NaN values must be zero-imputed before passing (see features.py).
        Returns:
            risk : (batch,)  float32  — sepsis risk score in [0.0, 1.0]
        """
        lstm_out, _ = self.lstm(x)           # (batch, seq_len, hidden*2)
        context, _ = self.attention(lstm_out)    # (batch, hidden*2)
        risk = self.classifier(context).squeeze(-1)  # (batch,)
        return risk
