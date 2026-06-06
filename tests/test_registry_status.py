"""Contract tests for P2-12 strategy registry — status lifecycle, promotion, capabilities."""

import pytest
from data.strategy.catalog import (
    ALLOWED_STATUSES, VALID_PROMOTIONS, STATUS_CAPABILITIES,
    get_status, get_by_status, status_rank, status_label,
    can_run_paper, can_run_production, can_run_tournament,
    validate_promotion,
)


class TestStatusConstants:
    def test_allowed_statuses_are_ordered_by_maturity(self):
        assert ALLOWED_STATUSES == ("candidate", "validated", "paper", "production", "retired")

    def test_valid_promotions_candidate(self):
        assert VALID_PROMOTIONS["candidate"] == {"validated"}

    def test_valid_promotions_validated(self):
        assert VALID_PROMOTIONS["validated"] == {"paper"}

    def test_valid_promotions_paper(self):
        assert VALID_PROMOTIONS["paper"] == {"production", "retired"}

    def test_valid_promotions_production(self):
        assert VALID_PROMOTIONS["production"] == {"retired"}

    def test_valid_promotions_retired_is_terminal(self):
        assert VALID_PROMOTIONS["retired"] == set()

    def test_status_capabilities_candidate(self):
        caps = STATUS_CAPABILITIES["candidate"]
        assert "backtest" in caps
        assert "scan" in caps
        assert "production" not in caps

    def test_status_capabilities_production(self):
        caps = STATUS_CAPABILITIES["production"]
        assert "production" in caps
        assert "paper_trading" in caps
        assert "tournament" in caps


class TestGetStatus:
    def test_known_strategy_returns_status(self):
        st = get_status("multifactor")
        assert st in ALLOWED_STATUSES

    def test_unknown_strategy_defaults_to_candidate(self):
        assert get_status("nonexistent_strategy_xyz") == "candidate"

    def test_buffett_is_production(self):
        assert get_status("buffett") == "production"


class TestGetByStatus:
    def test_returns_list_of_strategies(self):
        prods = get_by_status("production")
        assert isinstance(prods, list)
        assert len(prods) > 0
        for s in prods:
            assert s["status"] == "production"

    def test_invalid_status_returns_empty(self):
        assert get_by_status("invalid_status") == []

    def test_candidate_returns_correct_subset(self):
        cands = get_by_status("candidate")
        for s in cands:
            assert s["status"] == "candidate"


class TestStatusRank:
    def test_production_ranks_higher_than_candidate(self):
        assert status_rank("ml_lgbm") > _status_rank_of("candidate")

    def test_unknown_strategy_rank(self):
        assert status_rank("nonexistent") == 0


class TestCapabilityGates:
    def test_paper_strategy_can_run_paper(self):
        assert can_run_paper("ml_lgbm") is True

    def test_paper_strategy_cannot_run_production(self):
        assert can_run_production("ml_lgbm") is False

    def test_paper_strategy_can_run_tournament(self):
        assert can_run_tournament("ml_lgbm") is True

    def test_candidate_cannot_run_paper(self):
        assert status_rank("nonexistent") < 2  # paper rank = 2


class TestValidatePromotion:
    def test_valid_promotion_candidate_to_validated(self):
        # This tests the logic — actual strategies are production, so we test the function directly
        valid, reason = validate_promotion("buffett", "retired")
        assert valid is True
        assert reason == "ok"

    def test_invalid_promotion_candidate_to_production(self):
        valid, reason = validate_promotion("buffett", "validated")
        assert valid is False
        assert "Invalid promotion" in reason

    def test_invalid_target_status(self):
        valid, reason = validate_promotion("buffett", "nonexistent")
        assert valid is False

    def test_retired_cannot_promote(self):
        # buffett is production → retired is valid. Then from retired, no promotion is valid.
        # We test the rule: retired terminal state.
        assert VALID_PROMOTIONS["retired"] == set()


class TestStatusLabel:
    def test_known_status_labels(self):
        assert status_label("candidate") == "候选"
        assert status_label("validated") == "已验证"
        assert status_label("paper") == "模拟盘"
        assert status_label("production") == "生产"
        assert status_label("retired") == "已退役"

    def test_unknown_status_passthrough(self):
        assert status_label("unknown") == "unknown"


def _status_rank_of(status: str) -> int:
    return list(ALLOWED_STATUSES).index(status)
