"""Portfolio Execution pipeline payload builder."""

from __future__ import annotations

from web.api.services.pipelines.common import edge, metric, node, updated_timestamp


def build_portfolio_execution_pipeline() -> dict[str, object]:
    """Build Portfolio Execution pipeline payload."""
    nodes = [
        node(
            "signals",
            "Signals",
            "Strategy signal aggregation",
            metrics=[metric("Source", "compute_signals.py")],
            inputs=["Strategy signals"],
            outputs=["Buy/sell signals"],
        ),
        node(
            "regime",
            "Regime Overlay",
            "Market regime risk adjustment",
            metrics=[metric("Source", "orchestrator.detect()")],
            inputs=["Buy/sell signals", "Market regime"],
            outputs=["Risk-adjusted signals"],
        ),
        node(
            "allocation",
            "Asset Allocation",
            "Multi-asset weight distribution",
            metrics=[metric("Assets", "stock, ETF, bond, futures")],
            inputs=["Risk-adjusted signals"],
            outputs=["Target weights"],
        ),
        node(
            "risk",
            "Risk Checks",
            "Position limits, concentration, drawdown",
            metrics=[metric("Checks", "single-name cap, total exposure, stop-loss")],
            inputs=["Target weights"],
            outputs=["Approved orders", "Risk rejections"],
        ),
        node(
            "paper",
            "Paper Order Simulation",
            "Simulated execution with costs",
            metrics=[metric("Mode", "paper")],
            inputs=["Approved orders"],
            outputs=["Filled orders", "Cash impact"],
        ),
        node(
            "persist",
            "Persistence & Audit",
            "Ledger + run record",
            metrics=[metric("Store", "data/store/ledger/")],
            inputs=["Filled orders", "Cash impact"],
            outputs=["Run ledger", "Audit trail"],
        ),
    ]
    edges = [
        edge("signals", "regime"),
        edge("regime", "allocation"),
        edge("allocation", "risk"),
        edge("risk", "paper"),
        edge("paper", "persist"),
    ]
    return {
        "pipeline_key": "portfolio_execution",
        "updated": updated_timestamp(),
        "summary": {"mode": "paper"},
        "nodes": nodes,
        "edges": edges,
        "warnings": [],
    }
