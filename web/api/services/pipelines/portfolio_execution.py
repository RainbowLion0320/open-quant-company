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
            "signal_validation",
            "Signal Validation",
            "Drop disabled strategies, missing files, and invalid symbols",
            kind="decision",
            metrics=[metric("Checks", "enabled, exists, universe")],
            inputs=["Buy/sell signals"],
            outputs=["Validated signals", "Rejected signals"],
        ),
        node(
            "regime_snapshot",
            "Regime Snapshot",
            "Load confirmed market regime and adaptive params",
            metrics=[metric("Source", "orchestrator.detect()")],
            inputs=["Validated signals"],
            outputs=["Market regime", "Adaptive risk params"],
        ),
        node(
            "risk_overlay",
            "Risk Overlay",
            "Market regime risk adjustment",
            metrics=[metric("Source", "orchestrator.detect()")],
            inputs=["Validated signals", "Market regime", "Adaptive risk params"],
            outputs=["Risk-adjusted signals"],
        ),
        node(
            "allocation",
            "Asset Allocation",
            "Multi-asset weight distribution",
            metrics=[metric("Assets", "stock, ETF, bond, futures")],
            inputs=["Risk-adjusted signals"],
            outputs=["Candidate target weights"],
        ),
        node(
            "rebalance_gate",
            "Rebalance Needed?",
            "Compare target weights with current holdings",
            kind="decision",
            metrics=[metric("Trigger", "date, drift, signal")],
            inputs=["Candidate target weights", "Current positions"],
            outputs=["Target weights", "No-op path"],
        ),
        node(
            "risk",
            "Risk Limits",
            "Position limits, concentration, drawdown",
            metrics=[metric("Checks", "single-name cap, total exposure, stop-loss")],
            inputs=["Target weights"],
            outputs=["Approved orders", "Risk rejections"],
        ),
        node(
            "order_intents",
            "Order Intents",
            "Translate target deltas into buy/sell intents",
            metrics=[metric("Intent", "buy/sell/skip")],
            inputs=["Approved orders"],
            outputs=["Order intents"],
        ),
        node(
            "fill_model",
            "Fill Model",
            "Apply price, slippage, fee, and lot-size assumptions",
            metrics=[metric("Model", "paper fill")],
            inputs=["Order intents"],
            outputs=["Simulated fills", "Rejected fills"],
        ),
        node(
            "paper",
            "Paper Order Simulation",
            "Simulated execution with costs",
            metrics=[metric("Mode", "paper")],
            inputs=["Simulated fills"],
            outputs=["Filled orders", "Cash impact"],
        ),
        node(
            "ledger_update",
            "Ledger Update",
            "Apply fills to positions and cash ledger",
            metrics=[metric("Ledger", "positions + cash")],
            inputs=["Filled orders", "Cash impact"],
            outputs=["Updated ledger"],
        ),
        node(
            "persist",
            "Persistence & Audit",
            "Ledger + run record",
            metrics=[metric("Store", "var/store/ledger/")],
            inputs=["Updated ledger"],
            outputs=["Run ledger", "Audit trail"],
        ),
    ]
    edges = [
        edge("signals", "signal_validation"),
        edge("signal_validation", "regime_snapshot"),
        edge("regime_snapshot", "risk_overlay"),
        edge("risk_overlay", "allocation"),
        edge("allocation", "rebalance_gate"),
        edge("rebalance_gate", "risk", label="yes", condition="rebalance needed"),
        edge("rebalance_gate", "persist", label="no-op", condition="no rebalance", active=False),
        edge("risk", "order_intents"),
        edge("order_intents", "fill_model"),
        edge("fill_model", "paper"),
        edge("paper", "ledger_update"),
        edge("ledger_update", "persist"),
    ]
    return {
        "pipeline_key": "portfolio_execution",
        "updated": updated_timestamp(),
        "summary": {"mode": "paper"},
        "nodes": nodes,
        "edges": edges,
        "warnings": [],
    }
