"""
Unit tests for the SepsisLSTM model (PyTorch — no DB needed).

Tests verify:
- Model instantiation with default and custom hyperparameters
- Forward pass output shape and range
- TemporalAttention output properties
- Model determinism (same input → same output in eval mode)
- Gradient flow in training mode

These tests are automatically skipped if PyTorch is not installed in the
current environment (e.g. during lightweight CI without the ML dependencies).
"""
import pytest

torch = pytest.importorskip("torch", reason="PyTorch not installed; skipping model tests")

from ml.sepsis.model import SepsisLSTM, TemporalAttention  # noqa: E402


class TestTemporalAttention:
    def test_output_shapes(self):
        batch, seq, hidden = 4, 24, 256
        attn = TemporalAttention(hidden_dim=hidden)
        x = torch.randn(batch, seq, hidden)
        context, weights = attn(x)
        assert context.shape == (batch, hidden)
        assert weights.shape == (batch, seq)

    def test_weights_sum_to_one(self):
        attn = TemporalAttention(hidden_dim=64)
        x = torch.randn(3, 10, 64)
        _, weights = attn(x)
        sums = weights.sum(dim=1)
        assert torch.allclose(sums, torch.ones(3), atol=1e-5)

    def test_weights_non_negative(self):
        attn = TemporalAttention(hidden_dim=32)
        x = torch.randn(2, 15, 32)
        _, weights = attn(x)
        assert (weights >= 0).all()


class TestSepsisLSTM:
    def test_default_instantiation(self):
        model = SepsisLSTM()
        assert model.hidden_dim == SepsisLSTM.HIDDEN_DIM

    def test_custom_hyperparams(self):
        model = SepsisLSTM(input_dim=10, hidden_dim=32, num_layers=1, dropout=0.0)
        # Forward pass with matching input
        x = torch.randn(2, 24, 10)
        out = model(x)
        assert out.shape == (2,)

    def test_output_shape_single_sample(self):
        model = SepsisLSTM()
        model.eval()
        x = torch.randn(1, 24, SepsisLSTM.NUM_FEATURES)
        with torch.no_grad():
            risk = model(x)
        assert risk.shape == (1,)

    def test_output_shape_batch(self):
        model = SepsisLSTM()
        model.eval()
        x = torch.randn(8, 24, SepsisLSTM.NUM_FEATURES)
        with torch.no_grad():
            risk = model(x)
        assert risk.shape == (8,)

    def test_output_range(self):
        """Risk scores must be in [0, 1] (Sigmoid output)."""
        model = SepsisLSTM()
        model.eval()
        with torch.no_grad():
            for _ in range(10):
                x = torch.randn(4, 24, SepsisLSTM.NUM_FEATURES)
                risk = model(x)
                assert (risk >= 0.0).all(), "Risk scores must be non-negative"
                assert (risk <= 1.0).all(), "Risk scores must be <= 1.0"

    def test_determinism_in_eval_mode(self):
        """Same tensor input → same output when model is in eval mode."""
        model = SepsisLSTM()
        model.eval()
        x = torch.randn(2, 24, SepsisLSTM.NUM_FEATURES)
        with torch.no_grad():
            out1 = model(x)
            out2 = model(x)
        assert torch.allclose(out1, out2)

    def test_different_inputs_different_outputs(self):
        model = SepsisLSTM()
        model.eval()
        x1 = torch.ones(1, 24, SepsisLSTM.NUM_FEATURES)
        x2 = torch.zeros(1, 24, SepsisLSTM.NUM_FEATURES)
        with torch.no_grad():
            r1 = model(x1).item()
            r2 = model(x2).item()
        assert r1 != r2

    def test_gradient_flow_in_train_mode(self):
        """Gradients must flow back to model parameters during training."""
        model = SepsisLSTM()
        model.train()
        x = torch.randn(2, 24, SepsisLSTM.NUM_FEATURES, requires_grad=False)
        labels = torch.tensor([1.0, 0.0])
        risk = model(x)
        loss = torch.nn.functional.binary_cross_entropy(risk, labels)
        loss.backward()
        # Check at least one parameter has a gradient
        grads = [p.grad for p in model.parameters() if p.grad is not None]
        assert len(grads) > 0, "No gradients found — backward pass failed"

    def test_zero_input_runs_without_error(self):
        model = SepsisLSTM()
        model.eval()
        x = torch.zeros(1, 24, SepsisLSTM.NUM_FEATURES)
        with torch.no_grad():
            risk = model(x)
        assert 0.0 <= risk.item() <= 1.0
