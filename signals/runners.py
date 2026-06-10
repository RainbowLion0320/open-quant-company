"""Production strategy runner functions.

This module is intentionally import-safe. CLI-only environment setup, socket
timeouts and notification side effects belong in scripts/compute_signals.py.
"""
from __future__ import annotations

import sys

from core.settings import get_section
from signals.scoring import estimate_buffett_score, favored_sectors_for_regime, score_cybernetic_from_factors
from signals.selection import apply_ranked_buys
from signals.technical import technical_factors_from_frame


def _get_latest_price(symbol: str) -> float:
    """Return latest cached/refreshed close price, or 0 when unavailable."""
    try:
        from data.market.price_service import get_latest_price
        from data.market.price_types import PriceUseCase

        return get_latest_price(symbol, use_case=PriceUseCase.VALUATION)
    except Exception:
        return 0.0


def compute_buffett(limit: int = 0) -> list[dict]:
    """Run the Buffett full scan and return signal source rows."""
    from data.market.financials import get_buffett_inputs
    from data.market.symbols import CIRCLE_STOCKS, SYMBOL_INDUSTRY, SYMBOL_NAME
    from signals.buffett import buffett_filter as bf

    symbols = list(CIRCLE_STOCKS)
    if limit and limit < len(symbols):
        symbols = symbols[:limit]

    results = []
    total = len(symbols)
    passed = 0

    for i, sym in enumerate(symbols):
        try:
            ind = SYMBOL_INDUSTRY.get(sym, "待分类")
            price = _get_latest_price(sym)
            inputs = get_buffett_inputs(sym, current_price=price, industry=ind)
            if not inputs or not inputs.get("roe_history"):
                continue

            r = bf(symbol=sym, name=SYMBOL_NAME.get(sym, sym), **inputs)
            verdict = r.verdict.value if hasattr(r.verdict, "value") else str(r.verdict)
            passed_flag = "✅" in verdict or "通过" in verdict

            results.append(
                {
                    "symbol": r.symbol,
                    "name": r.name,
                    "industry": r.industry,
                    "sector": r.sector,
                    "verdict": verdict,
                    "score": r.score,
                    "roe": round(r.avg_roe_5y * 100, 1),
                    "gross_margin": round(r.avg_gross_margin_5y * 100, 1) if r.avg_gross_margin_5y > 0 else None,
                    "net_margin": round(r.avg_net_margin_5y * 100, 1) if r.avg_net_margin_5y > 0 else None,
                    "de": round(r.debt_equity_ratio, 1),
                    "safety_margin": round(r.safety_margin_pct * 100, 1),
                    "dcf_value": round(r.dcf_value, 1),
                    "current_price": round(price, 2),
                }
            )

            if passed_flag:
                passed += 1

        except Exception:
            pass

        if (i + 1) % 100 == 0:
            print(f"  Buffett [{i+1}/{total}] {passed} passed ...", flush=True, file=sys.stderr)

    print(f"  Buffett done: {len(results)} scanned, {passed} passed", flush=True, file=sys.stderr)
    return results


def compute_multifactor(limit: int = 0) -> list[dict]:
    """Run the production multifactor scorer."""
    from cybernetics.orchestrator import QuantOrchestrator
    from data.market.financials import get_buffett_inputs
    from data.market.symbols import CIRCLE_STOCKS, SYMBOL_INDUSTRY, SYMBOL_NAME
    from signals.buffett import buffett_filter as bf
    from signals.multifactor import MultiFactorScorer

    orch = QuantOrchestrator()
    try:
        snapshot = orch.detect()
        regime = snapshot.regime.value if hasattr(snapshot.regime, "value") else str(snapshot.regime)
        regime_probs = getattr(snapshot, "regime_probs", {})
    except Exception:
        regime = "sideways"
        regime_probs = {}

    scorer = MultiFactorScorer(regime=regime, regime_probs=regime_probs)
    symbols = list(CIRCLE_STOCKS)
    if limit and limit < len(symbols):
        symbols = symbols[:limit]

    results = []
    total = len(symbols)

    for i, sym in enumerate(symbols):
        try:
            name = SYMBOL_NAME.get(sym, sym)
            ind = SYMBOL_INDUSTRY.get(sym, "待分类")

            price = _get_latest_price(sym)
            inputs = get_buffett_inputs(sym, current_price=price, industry=ind)
            if not inputs:
                continue
            br = bf(symbol=sym, name=name, **inputs)

            tech = _get_technical_factors(sym)
            factors = {
                "buffett_score": br.score if br.score > 0 else estimate_buffett_score(inputs),
                "safety_margin": br.safety_margin_pct,
                "roe_5y": (
                    sum(inputs.get("roe_history", [0])[-5:])
                    / max(1, len(inputs.get("roe_history", [0])[-5:]))
                )
                if inputs.get("roe_history")
                else 0,
                "roe_trend": _roe_trend(inputs.get("roe_history", [])),
                "momentum_1m": tech["momentum_1m"],
                "momentum_3m": tech["momentum_3m"],
                "momentum_3m_skip_1m": tech["momentum_3m_skip_1m"],
                "momentum_6m_skip_1m": tech["momentum_6m_skip_1m"],
                "trend_strength": tech["trend_strength"],
                "volatility": tech["volatility"],
                "sector": inputs.get("sector", ""),
                "symbol": sym,
            }

            components = scorer.score_components(factors)
            score = components["total"]

            results.append(
                {
                    "symbol": sym,
                    "name": name,
                    "industry": ind,
                    "score": round(score, 1),
                    "signal": "hold",
                    "detail": {
                        "regime": regime,
                        "quality": components["quality"],
                        "valuation": components["valuation"],
                        "technical": components["technical"],
                        "market": components["market"],
                        "industry": components.get("industry", 50.0),
                        "momentum_3m_skip_1m": round(tech.get("momentum_3m_skip_1m", 0), 4),
                        "momentum_6m_skip_1m": round(tech.get("momentum_6m_skip_1m", 0), 4),
                        "trend_strength": round(tech.get("trend_strength", 0), 4),
                    },
                }
            )

        except Exception:
            pass

        if (i + 1) % 100 == 0:
            buys = sum(1 for r in results if r["signal"] == "buy")
            print(f"  Multifactor [{i+1}/{total}] {buys} buys ...", flush=True, file=sys.stderr)

    results = apply_ranked_buys(results, "multifactor", default_min_score=MFC_BUY_THRESHOLD())
    buys = sum(1 for r in results if r["signal"] == "buy")
    print(f"  Multifactor done: {len(results)} scored, {buys} buys (regime={regime})", flush=True, file=sys.stderr)
    return results


def MFC_BUY_THRESHOLD() -> float:
    try:
        return float(get_section("signals.multifactor.buy_threshold", 52))
    except Exception:
        return 52.0


def _roe_trend(history: list) -> str:
    if len(history) < 3:
        return "flat"
    recent = history[-3:]
    if recent[-1] > recent[0] * 1.05:
        return "up"
    if recent[-1] < recent[0] * 0.95:
        return "down"
    return "flat"


def _get_technical_factors(symbol: str) -> dict:
    """Compute momentum, trend and volatility from local market data."""
    fallback = {
        "momentum_1m": 0,
        "momentum_3m": 0,
        "momentum_3m_skip_1m": 0,
        "momentum_6m_skip_1m": 0,
        "trend_strength": 0,
        "volatility": 0.30,
    }
    try:
        from data.market.price_service import get_stock_prices
        from data.market.price_types import PriceUseCase

        df = get_stock_prices(symbol, use_case=PriceUseCase.SIGNAL)
        if df is None or len(df) < 63:
            return fallback
        df = df.sort_values("date") if "date" in df.columns else df
        return technical_factors_from_frame(df)
    except Exception:
        return fallback


def compute_cybernetic(limit: int = 0) -> list[dict]:
    """Run cybernetic sector rotation signals from the current market regime."""
    from cybernetics.orchestrator import QuantOrchestrator
    from data.market.symbols import CIRCLE_STOCKS, FALLBACK_SECTOR, SYMBOL_INDUSTRY, SYMBOL_NAME, SYMBOL_SECTOR

    orch = QuantOrchestrator()
    try:
        snapshot = orch.detect()
        regime = snapshot.regime.value if hasattr(snapshot.regime, "value") else str(snapshot.regime)
        regime_probs = getattr(snapshot, "regime_probs", {})
        params = orch.get_params()
    except Exception:
        regime = "sideways"
        regime_probs = {}
        params = {"position_pct": 0.15, "max_positions": 5, "stop_loss": -0.05}

    favored = favored_sectors_for_regime(regime)

    symbols = list(CIRCLE_STOCKS)
    if limit and limit < len(symbols):
        symbols = symbols[:limit]

    results = []
    for sym in symbols:
        ind = SYMBOL_INDUSTRY.get(sym, "待分类")
        sec = SYMBOL_SECTOR.get(sym, FALLBACK_SECTOR)
        name = SYMBOL_NAME.get(sym, sym)

        tech = _get_technical_factors(sym)
        score = score_cybernetic_from_factors(ind, regime, tech, regime_probs=regime_probs)

        results.append(
            {
                "symbol": sym,
                "name": name,
                "industry": ind,
                "sector": sec,
                "score": round(score, 1),
                "signal": "hold",
                "detail": {
                    "regime": regime,
                    "favored_sectors": favored,
                    "position_pct": params.get("position_size", params.get("position_pct", 0.15)),
                    "max_positions": params.get("max_positions", 5),
                    "trend_strength": round(tech.get("trend_strength", 0), 4),
                    "momentum_3m_skip_1m": round(tech.get("momentum_3m_skip_1m", 0), 4),
                    "volatility": round(tech.get("volatility", 0), 4),
                },
            }
        )

    min_score = float(params.get("confidence_threshold", 0.60)) * 100
    max_buys = max(10, int(params.get("max_positions", 5)) * 4)
    results = apply_ranked_buys(
        results,
        "cybernetic",
        default_min_score=min_score,
        default_max_buys=max_buys,
    )
    buys = sum(1 for r in results if r["signal"] == "buy")
    print(f"  Cybernetic done: {len(results)} signals, {buys} buys (regime={regime})", flush=True, file=sys.stderr)
    return results
