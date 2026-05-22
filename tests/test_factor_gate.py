"""Contract tests for P2-12 LLM factor candidate pool gate."""

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Real expression.py path that promote_candidate_factor writes to
_EXPR_PATH = Path(__file__).resolve().parent.parent / "signals" / "expression.py"


# ── Helpers to create test FactorCandidate instances ──

class FakeFactorCandidate:
    def __init__(self, name, formula, ic=0.05, icir=0.3, oos_ic=0.04, passed_oos=True):
        self.name = name
        self.formula = formula
        self.ic = ic
        self.icir = icir
        self.oos_ic = oos_ic
        self.passed_oos = passed_oos


@pytest.fixture
def temp_pool_path():
    """Create a temporary candidate_factors.yaml for isolated testing."""
    fd, path = tempfile.mkstemp(suffix=".yaml", prefix="candidate_factors_")
    os.close(fd)
    yield Path(path)
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


@pytest.fixture
def clean_pool(temp_pool_path):
    """Patch CANDIDATE_POOL_PATH to use a temp file, and clean it."""
    with patch("scripts.factor_hypothesis.CANDIDATE_POOL_PATH", temp_pool_path):
        if temp_pool_path.exists():
            temp_pool_path.unlink()
        yield temp_pool_path
        if temp_pool_path.exists():
            temp_pool_path.unlink()


@pytest.fixture
def safe_expr():
    """Backup and restore the real expression.py around promote tests."""
    backup = _EXPR_PATH.read_text()
    yield
    _EXPR_PATH.write_text(backup)


# ── Tests ──

class TestSaveToCandidatePool:
    def test_saves_new_factors(self, clean_pool):
        from scripts.factor_hypothesis import save_to_candidate_pool

        factors = [
            FakeFactorCandidate("alpha_momentum_20d", "ts_mean(returns, 20) / ts_std(returns, 20)"),
        ]
        result = save_to_candidate_pool(factors)
        assert result is True
        assert clean_pool.exists()

    def test_pool_contains_saved_factor(self, clean_pool):
        from scripts.factor_hypothesis import save_to_candidate_pool, list_candidate_factors

        factors = [FakeFactorCandidate("test_factor_1", "rank(close)")]
        save_to_candidate_pool(factors)

        pool = list_candidate_factors()
        assert "test_factor_1" in pool
        assert pool["test_factor_1"]["formula"] == "rank(close)"
        assert pool["test_factor_1"]["status"] == "candidate"

    def test_duplicate_factor_not_overwritten(self, clean_pool):
        from scripts.factor_hypothesis import save_to_candidate_pool, list_candidate_factors

        f1 = [FakeFactorCandidate("dup_factor", "ts_mean(close, 10)", ic=0.05)]
        f2 = [FakeFactorCandidate("dup_factor", "ts_mean(close, 20)", ic=0.03)]

        save_to_candidate_pool(f1)
        save_to_candidate_pool(f2)

        pool = list_candidate_factors()
        assert pool["dup_factor"]["formula"] == "ts_mean(close, 10)"

    def test_saves_multiple_factors(self, clean_pool):
        from scripts.factor_hypothesis import save_to_candidate_pool, list_candidate_factors

        factors = [
            FakeFactorCandidate(f"factor_{i}", f"formula_{i}", ic=0.02 + i * 0.01)
            for i in range(5)
        ]
        save_to_candidate_pool(factors)
        pool = list_candidate_factors()
        assert len(pool) == 5


class TestListCandidateFactors:
    def test_empty_pool_returns_empty_dict(self, clean_pool):
        from scripts.factor_hypothesis import list_candidate_factors
        assert list_candidate_factors() == {}

    def test_filter_by_status(self, clean_pool):
        from scripts.factor_hypothesis import save_to_candidate_pool, list_candidate_factors

        save_to_candidate_pool([FakeFactorCandidate("f_cand", "close")])
        candidates = list_candidate_factors(status="candidate")
        assert "f_cand" in candidates
        assert candidates["f_cand"]["status"] == "candidate"

    def test_filter_by_promoted_returns_empty_when_none(self, clean_pool):
        from scripts.factor_hypothesis import save_to_candidate_pool, list_candidate_factors

        save_to_candidate_pool([FakeFactorCandidate("f_only", "close")])
        promoted = list_candidate_factors(status="promoted")
        assert promoted == {}


class TestPromoteCandidateFactor:
    def test_promote_nonexistent_factor_returns_false(self, clean_pool, safe_expr):
        from scripts.factor_hypothesis import promote_candidate_factor
        assert promote_candidate_factor("nonexistent_factor") is False

    def test_promote_updates_status(self, clean_pool, safe_expr):
        from scripts.factor_hypothesis import save_to_candidate_pool, promote_candidate_factor, list_candidate_factors

        save_to_candidate_pool([FakeFactorCandidate("promo_test", "ts_rank(volume, 5)")])

        result = promote_candidate_factor("promo_test")
        assert result is True

        pool = list_candidate_factors()
        assert pool["promo_test"]["status"] == "promoted"

    def test_promote_already_promoted_returns_false(self, clean_pool, safe_expr):
        from scripts.factor_hypothesis import (
            save_to_candidate_pool, promote_candidate_factor,
            list_candidate_factors,
        )

        save_to_candidate_pool([FakeFactorCandidate("double_promo", "close/open")])
        assert promote_candidate_factor("double_promo") is True
        assert promote_candidate_factor("double_promo") is False

    def test_promote_writes_to_expression_file(self, clean_pool, safe_expr):
        """Promote should inject factor DSL into expression.py."""
        from scripts.factor_hypothesis import save_to_candidate_pool, promote_candidate_factor

        save_to_candidate_pool([FakeFactorCandidate("expr_test", "rank(close)")])

        result = promote_candidate_factor("expr_test")
        assert result is True

        content = _EXPR_PATH.read_text()
        assert '"expr_test"' in content


class TestAutoRegisterDeprecated:
    def test_auto_register_redirects_to_pool(self, clean_pool):
        from scripts.factor_hypothesis import auto_register_factors, list_candidate_factors

        factors = [FakeFactorCandidate("deprecated_test", "ts_mean(close, 5)")]
        result = auto_register_factors(factors)
        assert result is True

        pool = list_candidate_factors()
        assert "deprecated_test" in pool


class TestFormulaToDSL:
    def test_converts_close_t(self):
        from scripts.factor_hypothesis import _formula_to_dsl
        result = _formula_to_dsl("close_t", "test_factor")
        assert "Ref('close')" in result

    def test_converts_open_t(self):
        from scripts.factor_hypothesis import _formula_to_dsl
        result = _formula_to_dsl("open_t", "test_factor")
        assert "Ref('open')" in result
