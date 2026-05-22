"""Contract tests for fill and slippage models."""

import pytest
from broker.fill_models import (
    SlippageModel, FillModel,
    NoSlippage, FixedBpsSlippage, VolBasedSlippage,
    ImmediateFill, ProbabilisticFill, LimitUpDownAwareFill,
    CompositeFill, MatchResult,
)


class TestNoSlippage:
    def test_returns_same_price(self):
        model = NoSlippage()
        assert model.apply(12.50, "buy", 100) == 12.50
        assert model.apply(12.50, "sell", 100) == 12.50

    def test_zero_price(self):
        model = NoSlippage()
        assert model.apply(0, "buy", 100) == 0


class TestFixedBpsSlippage:
    def test_buy_slippage_positive(self):
        model = FixedBpsSlippage(bps=5.0)
        result = model.apply(100.0, "buy", 1000)
        # 5 bps = 0.05%, so 100 * 1.0005 = 100.05
        assert result == pytest.approx(100.05, abs=0.01)

    def test_sell_slippage_negative(self):
        model = FixedBpsSlippage(bps=5.0)
        result = model.apply(100.0, "sell", 1000)
        assert result == pytest.approx(99.95, abs=0.01)

    def test_custom_bps(self):
        model = FixedBpsSlippage(bps=10.0)
        result_buy = model.apply(100.0, "buy", 1000)
        assert result_buy == pytest.approx(100.10, abs=0.01)

    def test_zero_bps(self):
        model = FixedBpsSlippage(bps=0)
        assert model.apply(100.0, "buy", 1000) == 100.0


class TestVolBasedSlippage:
    def test_low_vol(self):
        model = VolBasedSlippage(base_bps=5.0)
        result = model.apply(100.0, "buy", 1000, {"annualized_vol": 0.10})
        # bps = 5 * (0.10/0.20) = 2.5 → factor = 1.00025
        assert result == pytest.approx(100.025, abs=0.01)

    def test_high_vol_capped(self):
        model = VolBasedSlippage(base_bps=5.0, max_bps=50.0)
        result = model.apply(100.0, "buy", 1000, {"annualized_vol": 1.0})
        # bps = min(5 * 1.0/0.20, 50) = min(25, 50) = 25
        assert result == pytest.approx(100.25, abs=0.01)

    def test_default_vol_when_no_ctx(self):
        model = VolBasedSlippage(base_bps=5.0)
        result = model.apply(100.0, "buy", 1000, None)
        # Uses default 0.20 vol
        assert result > 100.0  # buy, so positive slippage

    def test_vol_floor(self):
        model = VolBasedSlippage(base_bps=5.0, vol_floor=0.05)
        result = model.apply(100.0, "buy", 1000, {"annualized_vol": 0.01})
        # Uses floor 0.05, not 0.01
        # bps = 5 * 0.05/0.20 = 1.25
        assert result == pytest.approx(100.0125, abs=0.01)


class TestImmediateFill:
    def test_fills_all(self):
        model = ImmediateFill()
        result = model.evaluate(500, "buy", 12.50)
        assert result.status == "filled"
        assert result.filled_shares == 500
        assert result.fill_price == 12.50

    def test_with_slippage(self):
        model = ImmediateFill(slippage=FixedBpsSlippage(bps=10))
        result = model.evaluate(500, "buy", 100.0)
        assert result.status == "filled"
        assert result.fill_price > 100.0


class TestProbabilisticFill:
    def test_fills_with_seed(self):
        import random
        random.seed(42)
        model = ProbabilisticFill(fill_prob=0.5, partial_pct=0.5)

        fill_count = 0
        partial_count = 0
        for _ in range(100):
            result = model.evaluate(100, "buy", 10.0)
            if result.status == "filled" and result.filled_shares == 100:
                fill_count += 1
            elif result.status == "partial_filled":
                partial_count += 1

        # With prob=0.5, both should happen
        assert fill_count > 0
        assert partial_count > 0

    def test_always_fills_when_prob_is_1(self):
        model = ProbabilisticFill(fill_prob=1.0)
        result = model.evaluate(100, "buy", 10.0)
        assert result.status == "filled"
        assert result.filled_shares == 100


class TestLimitUpDownAwareFill:
    def test_normal_fill(self):
        model = LimitUpDownAwareFill()
        ctx = {"prev_close": 10.0}
        result = model.evaluate(500, "buy", 10.50, symbol="000001", ctx=ctx)
        assert result.status == "filled"
        assert result.filled_shares == 500

    def test_limit_up_blocks_buy(self):
        model = LimitUpDownAwareFill()
        # prev_close=10.0, limit_up=11.0
        ctx = {"prev_close": 10.0}
        result = model.evaluate(500, "buy", 11.00, symbol="000001", ctx=ctx)
        assert result.status == "rejected"
        assert result.filled_shares == 0
        assert "涨停" in result.reason

    def test_limit_down_blocks_sell(self):
        model = LimitUpDownAwareFill()
        ctx = {"prev_close": 10.0}
        result = model.evaluate(500, "sell", 9.00, symbol="000001", ctx=ctx)
        assert result.status == "rejected"
        assert result.filled_shares == 0
        assert "跌停" in result.reason

    def test_suspended_blocks(self):
        model = LimitUpDownAwareFill()
        ctx = {"suspended": True, "prev_close": 10.0}
        result = model.evaluate(500, "buy", 10.50, symbol="000001", ctx=ctx)
        assert result.status == "rejected"
        assert "停牌" in result.reason

    def test_custom_limit_pct(self):
        model = LimitUpDownAwareFill(limit_pct=0.20)  # 科创板 20%
        ctx = {"prev_close": 10.0}
        # 10.50 < 12.00 (20% up), so buy should work
        result = model.evaluate(500, "buy", 10.50, symbol="000001", ctx=ctx)
        assert result.status == "filled"

    def test_explicit_limit_up(self):
        model = LimitUpDownAwareFill()
        ctx = {"limit_up": 11.0, "limit_down": 9.0}
        result = model.evaluate(500, "buy", 11.0, symbol="000001", ctx=ctx)
        assert result.status == "rejected"

    def test_sell_at_market_within_limits(self):
        model = LimitUpDownAwareFill()
        ctx = {"prev_close": 10.0}
        result = model.evaluate(500, "sell", 10.2, symbol="000001", ctx=ctx)
        assert result.status == "filled"


class TestCompositeFill:
    def test_first_model_rejects_stops_chain(self):
        # Limit up check first, then immediate fill
        composite = CompositeFill([
            LimitUpDownAwareFill(),
            ImmediateFill(),
        ])
        ctx = {"prev_close": 10.0}
        result = composite.evaluate(500, "buy", 11.0, symbol="000001", ctx=ctx)
        assert result.status == "rejected"
        assert "涨停" in result.reason

    def test_all_pass_fills(self):
        composite = CompositeFill([
            LimitUpDownAwareFill(),
            ImmediateFill(),
        ])
        ctx = {"prev_close": 10.0}
        result = composite.evaluate(500, "buy", 10.5, symbol="000001", ctx=ctx)
        assert result.status == "filled"
        assert result.filled_shares == 500


class TestMatchResult:
    def test_defaults(self):
        r = MatchResult(filled_shares=100, fill_price=12.50, status="filled")
        assert r.filled_shares == 100
        assert r.fill_price == 12.50
        assert r.commission == 0.0
        assert r.slippage_bps == 0.0

    def test_with_commission(self):
        r = MatchResult(filled_shares=100, fill_price=12.50, status="filled",
                        commission=1.01)
        assert r.commission == 1.01
