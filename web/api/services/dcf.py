"""DCF valuation service for stock routes."""

from __future__ import annotations

from web.api.errors import InvalidParameterError
from web.api.models import DCFParams, DCFResult


def compute_dcf_result(code: str, params: DCFParams | None) -> DCFResult:
    from data.market.price_service import get_stock_prices
    from data.market.price_types import PriceUseCase

    if params is None:
        raise InvalidParameterError("params", "missing", "DCFParams body required")

    current_price = 0.0
    try:
        kdf = get_stock_prices(code, use_case=PriceUseCase.VALUATION)
        if kdf is not None and len(kdf) > 0:
            current_price = float(kdf.sort_values("date").iloc[-1]["close"])
    except Exception:
        pass

    shares = params.shares
    if shares <= 0:
        try:
            kdf = get_stock_prices(code, use_case=PriceUseCase.VALUATION)
            if kdf is not None and "outstanding_share" in kdf.columns:
                shares = float(kdf["outstanding_share"].iloc[-1]) / 1e8
        except Exception:
            shares = 1.0

    fcf = params.fcf
    growth = params.growth_rate
    terminal_growth = params.terminal_growth
    discount = params.discount_rate

    if growth >= discount:
        growth = discount * 0.9
    if terminal_growth >= discount:
        terminal_growth = discount * 0.5

    stage1_pv = 0
    fcf_t = fcf
    for year in range(1, 6):
        fcf_t *= (1 + growth)
        stage1_pv += fcf_t / ((1 + discount) ** year)

    terminal_fcf = fcf_t * (1 + terminal_growth)
    terminal_value = terminal_fcf / (discount - terminal_growth)
    stage2_pv = terminal_value / ((1 + discount) ** 5)

    intrinsic_value_per_share = (stage1_pv + stage2_pv) / shares
    safety_margin_pct = (
        ((intrinsic_value_per_share - current_price) / intrinsic_value_per_share) * 100
        if intrinsic_value_per_share > 0
        else 0
    )

    if safety_margin_pct >= 30:
        verdict = "underpriced"
    elif safety_margin_pct >= 0:
        verdict = "fair"
    elif safety_margin_pct >= -10:
        verdict = "slightly_overpriced"
    else:
        verdict = "overpriced"

    return DCFResult(
        intrinsic_value=round(intrinsic_value_per_share, 2),
        current_price=round(current_price, 2),
        safety_margin=round(safety_margin_pct, 1),
        verdict=verdict,
    )
