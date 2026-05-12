"""
Unit tests for SOFA score computation.

All functions under test are pure — no I/O, no mocking required.
Tests cover:
  - Each of the 6 organ-system sub-scores across all boundary values
  - Total compute_sofa() with full, partial, and empty inputs
  - sofa_to_score_and_level() mapping
  - compute_qsofa() boundary conditions
"""
import pytest

from app.services.sofa import (
    compute_qsofa,
    compute_sofa,
    sofa_cardiovascular,
    sofa_cns,
    sofa_coagulation,
    sofa_liver,
    sofa_renal,
    sofa_respiratory,
    sofa_to_score_and_level,
)


# ── Tests: sofa_respiratory ───────────────────────────────────────────────────

class TestSofaRespiratory:
    def test_normal(self):
        assert sofa_respiratory(450.0) == 0

    def test_boundary_400(self):
        assert sofa_respiratory(400.0) == 0

    def test_score_1(self):
        assert sofa_respiratory(350.0) == 1

    def test_boundary_300(self):
        assert sofa_respiratory(300.0) == 1

    def test_score_2(self):
        assert sofa_respiratory(250.0) == 2

    def test_score_3(self):
        assert sofa_respiratory(150.0) == 3

    def test_score_4(self):
        assert sofa_respiratory(80.0) == 4

    def test_none_returns_zero(self):
        assert sofa_respiratory(None) == 0


# ── Tests: sofa_coagulation ───────────────────────────────────────────────────

class TestSofaCoagulation:
    def test_normal(self):
        assert sofa_coagulation(200.0) == 0

    def test_boundary_150(self):
        assert sofa_coagulation(150.0) == 0

    def test_score_1(self):
        assert sofa_coagulation(120.0) == 1

    def test_boundary_100(self):
        assert sofa_coagulation(100.0) == 1

    def test_score_2(self):
        assert sofa_coagulation(70.0) == 2

    def test_score_3(self):
        assert sofa_coagulation(30.0) == 3

    def test_score_4(self):
        assert sofa_coagulation(10.0) == 4

    def test_none_returns_zero(self):
        assert sofa_coagulation(None) == 0


# ── Tests: sofa_liver ────────────────────────────────────────────────────────

class TestSofaLiver:
    def test_normal(self):
        assert sofa_liver(0.8) == 0

    def test_boundary_1_2(self):
        assert sofa_liver(1.2) == 1        # ≥ 1.2 → score ≥ 1

    def test_score_1(self):
        assert sofa_liver(1.5) == 1

    def test_score_2(self):
        assert sofa_liver(3.0) == 2

    def test_score_3(self):
        assert sofa_liver(8.0) == 3

    def test_score_4(self):
        assert sofa_liver(15.0) == 4

    def test_none_returns_zero(self):
        assert sofa_liver(None) == 0


# ── Tests: sofa_cardiovascular ───────────────────────────────────────────────

class TestSofaCardiovascular:
    def test_normal_map(self):
        assert sofa_cardiovascular(80.0) == 0

    def test_boundary_70(self):
        assert sofa_cardiovascular(70.0) == 0   # MAP exactly 70 → no hypotension

    def test_hypotension(self):
        assert sofa_cardiovascular(65.0) == 1

    def test_severe_hypotension(self):
        assert sofa_cardiovascular(40.0) == 1

    def test_none_returns_zero(self):
        assert sofa_cardiovascular(None) == 0


# ── Tests: sofa_cns ───────────────────────────────────────────────────────────

class TestSofaCns:
    def test_gcs_15_normal(self):
        assert sofa_cns(15) == 0

    def test_gcs_14(self):
        assert sofa_cns(14) == 1

    def test_gcs_13(self):
        assert sofa_cns(13) == 1

    def test_gcs_12(self):
        assert sofa_cns(12) == 2

    def test_gcs_10(self):
        assert sofa_cns(10) == 2

    def test_gcs_9(self):
        assert sofa_cns(9) == 3

    def test_gcs_6(self):
        assert sofa_cns(6) == 3

    def test_gcs_5(self):
        assert sofa_cns(5) == 4

    def test_gcs_3_minimum(self):
        assert sofa_cns(3) == 4

    def test_none_returns_zero(self):
        assert sofa_cns(None) == 0


# ── Tests: sofa_renal ────────────────────────────────────────────────────────

class TestSofaRenal:
    def test_normal(self):
        assert sofa_renal(0.9) == 0

    def test_boundary_1_2(self):
        assert sofa_renal(1.2) == 1

    def test_score_1(self):
        assert sofa_renal(1.5) == 1

    def test_score_2(self):
        assert sofa_renal(2.5) == 2

    def test_score_3(self):
        assert sofa_renal(4.0) == 3

    def test_score_4(self):
        assert sofa_renal(6.0) == 4

    def test_none_returns_zero(self):
        assert sofa_renal(None) == 0


# ── Tests: compute_sofa ───────────────────────────────────────────────────────

class TestComputeSofa:
    def test_all_normal_returns_zero(self):
        vitals = {"mean_arterial_bp": 85.0, "gcs_total": 15}
        labs = {
            "pao2_fio2_ratio": 420.0,
            "platelets": 200.0,
            "bilirubin_total": 0.8,
            "creatinine": 0.9,
        }
        assert compute_sofa(vitals, labs) == 0

    def test_septic_shock_pattern(self):
        """Classic septic shock: low MAP, low platelets, elevated creatinine."""
        vitals = {"mean_arterial_bp": 55.0, "gcs_total": 10}
        labs = {
            "pao2_fio2_ratio": 180.0,
            "platelets": 45.0,
            "bilirubin_total": 4.0,
            "creatinine": 3.8,
        }
        score = compute_sofa(vitals, labs)
        # Resp=3, Coag=3, Liver=2, Cardio=1, CNS=2, Renal=3 → total 14
        assert score == 14

    def test_empty_dicts_returns_zero(self):
        assert compute_sofa({}, {}) == 0

    def test_partial_data(self):
        """Only creatinine and platelets available — others should score 0."""
        vitals = {}
        labs = {"platelets": 80.0, "creatinine": 2.5}
        # Resp=0, Coag=2, Liver=0, Cardio=0, CNS=0, Renal=2 → 4
        assert compute_sofa(vitals, labs) == 4


# ── Tests: sofa_to_score_and_level ───────────────────────────────────────────

class TestSofaToLevel:
    @pytest.mark.parametrize("sofa,expected_level", [
        (0, "LOW"),
        (1, "LOW"),
        (2, "LOW"),
        (4, "LOW"),
        (5, "MEDIUM"),
        (7, "MEDIUM"),
        (8, "HIGH"),
        (11, "HIGH"),
        (12, "CRITICAL"),
        (20, "CRITICAL"),
    ])
    def test_alert_levels(self, sofa, expected_level):
        _, level = sofa_to_score_and_level(sofa)
        assert level == expected_level

    def test_risk_scores_increase_monotonically(self):
        scores = [sofa_to_score_and_level(s)[0] for s in [0, 2, 5, 8, 12]]
        assert scores == sorted(scores), "Risk scores should increase with SOFA"


# ── Tests: compute_qsofa ─────────────────────────────────────────────────────

class TestComputeQsofa:
    def test_all_normal_zero(self):
        assert compute_qsofa(18.0, 120.0, 15) == 0

    def test_all_abnormal_three(self):
        assert compute_qsofa(25.0, 95.0, 13) == 3

    def test_only_rr_elevated(self):
        assert compute_qsofa(22.0, 120.0, 15) == 1

    def test_boundary_rr_21(self):
        assert compute_qsofa(21.0, 120.0, 15) == 0   # < 22 → no point

    def test_boundary_rr_22(self):
        assert compute_qsofa(22.0, 120.0, 15) == 1   # == 22 → 1 point

    def test_sbp_at_threshold(self):
        assert compute_qsofa(18.0, 100.0, 15) == 1   # ≤ 100 → 1 point

    def test_sbp_above_threshold(self):
        assert compute_qsofa(18.0, 101.0, 15) == 0

    def test_none_fields_score_zero(self):
        assert compute_qsofa(None, None, None) == 0

    def test_partial_none(self):
        # Only RR available and abnormal
        assert compute_qsofa(25.0, None, None) == 1
