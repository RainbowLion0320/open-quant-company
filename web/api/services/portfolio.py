"""Portfolio route service helpers."""

from __future__ import annotations


def apply_latest_execution_price(broker, code: str) -> None:
    """Populate the broker quote cache for a market order when fresh data is available."""
    try:
        from data.market.price_service import get_stock_prices
        from data.market.price_types import PriceUseCase

        df = get_stock_prices(code, use_case=PriceUseCase.EXECUTION)
        if df is not None and len(df) > 0:
            current = float(df.sort_values("date").iloc[-1]["close"])
            broker.set_prices({code: current})
    except Exception:
        return
