"""Strategy center payload builders and command helpers."""

from __future__ import annotations

from web.api.errors import DataNotFoundError, InvalidParameterError, StrategyRunError


def strategy_list_payload() -> dict:
    from data.storage.results_db import list_strategies as db_list
    from data.strategy.catalog import ALLOWED_STATUSES, get_enabled_strategies

    strategies = db_list()
    registry = get_enabled_strategies()
    for strategy in registry:
        status = strategy.get("status", "candidate")
        strategy["status_rank"] = list(ALLOWED_STATUSES).index(status) if status in ALLOWED_STATUSES else 0
    return {
        "strategies": strategies,
        "registry": registry,
        "total": len(strategies),
        "statuses": list(ALLOWED_STATUSES),
    }


def strategy_status_payload() -> dict:
    from data.strategy.catalog import ALLOWED_STATUSES, get_enabled_strategies, status_label

    registry = get_enabled_strategies()
    return {
        "strategies": [
            {
                "name": strategy["name"],
                "label": strategy["label"],
                "status": strategy.get("status", "candidate"),
                "status_label": status_label(strategy.get("status", "candidate")),
                "color": strategy["color"],
            }
            for strategy in registry
        ],
        "statuses": list(ALLOWED_STATUSES),
        "status_labels": {status: status_label(status) for status in ALLOWED_STATUSES},
        "status": "ok",
    }


def strategy_governance_payload() -> dict:
    from data.strategy.catalog import list_strategy_names
    from research.strategy_governance import governance_summary

    return {**governance_summary(list_strategy_names()), "status": "ok"}


def strategy_catalog_payload() -> dict:
    from research.strategy_catalog import catalog_items

    items = [item.__dict__ for item in catalog_items()]
    return {"items": items, "total": len(items)}


def strategy_data_coverage_payload() -> dict:
    from research.strategy_data_coverage import build_strategy_data_coverage

    return build_strategy_data_coverage()


def strategy_evaluation_payload() -> dict:
    from research.strategy_evaluation import required_baselines

    return {
        "baselines": required_baselines(),
        "status": "research_required",
        "note": "Candidate strategies require OOS, walk-forward, cost and regime evidence before promotion.",
    }


async def start_strategy_run(strategy: str, limit: int, params: dict | None, mode: str) -> str:
    from data.strategy.catalog import list_strategy_names
    from web.api.jobs import run_strategy_async

    valid = set(list_strategy_names()) | {"all"}
    if strategy not in valid:
        raise StrategyRunError(strategy, f"Invalid strategy. Choose from: {', '.join(sorted(valid))}")
    if mode not in {"production", "research"}:
        raise StrategyRunError(strategy, f"Invalid strategy run scope: {mode}")
    return await run_strategy_async(strategy, limit, params, mode=mode)


def strategy_evidence_list_payload() -> dict:
    from research.strategy_evaluation import list_evidence_artifacts

    items = list_evidence_artifacts()
    return {"items": items, "total": len(items)}


def strategy_evidence_detail_payload(strategy: str) -> dict:
    from research.strategy_evaluation import load_evidence_artifact

    return load_evidence_artifact(strategy)


def strategy_signals_payload(name: str, sort: str = "score", order: str = "desc") -> dict:
    from data.storage.results_db import load_strategy_signals
    from data.strategy.catalog import list_strategy_names

    valid = set(list_strategy_names())
    if name not in valid:
        raise InvalidParameterError("strategy", name, f"Choose from: {', '.join(sorted(valid))}")

    signals = load_strategy_signals(name, sort=sort, order=order)
    if not signals:
        raise DataNotFoundError("strategy", name)
    return {
        "strategy": name,
        "total": len(signals),
        "buys": sum(1 for signal in signals if signal.get("signal") == "buy"),
        "signals": signals,
    }
