"""Signal history payload builders for API routes."""

from __future__ import annotations

from datetime import datetime, timedelta


def signal_changes_payload(days: int = 7) -> dict:
    from data.storage.results_db import load_strategy_signals, list_strategies

    all_signals = []
    for strategy in list_strategies():
        name = strategy["name"]
        signals = load_strategy_signals(name, sort="score", order="desc")
        last_computed = strategy.get("last_computed", "")
        for signal in signals:
            if signal.get("signal") != "buy":
                continue
            all_signals.append({
                "date": last_computed[:10] if last_computed else "",
                "strategy": name,
                "symbol": signal["symbol"],
                "name": signal.get("name", ""),
                "from_signal": "hold",
                "to_signal": "buy",
                "score": signal.get("score", 0),
            })

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    recent = [signal for signal in all_signals if signal["date"] >= cutoff or not signal["date"]]
    return {
        "changes": sorted(recent, key=lambda item: item.get("score", 0) or 0, reverse=True),
        "total": len(recent),
        "window_days": days,
        "note": "Shows current buy signals within the window. Full change tracking requires historical snapshots.",
    }
