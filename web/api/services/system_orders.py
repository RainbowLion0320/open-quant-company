"""System order lifecycle payload builders."""

from __future__ import annotations

from web.api.errors import DataNotFoundError


def order_lifecycle_payload(date: str = "", symbol: str = "", status: str = "", limit: int = 50) -> dict:
    from broker.ledger import EventLedger

    ledger = EventLedger()
    all_events = ledger.replay()
    if not all_events:
        return {"orders": [], "total": 0, "status": "ok"}

    orders: dict[str, dict] = {}
    for event in all_events:
        if date and event.run_date != date:
            continue
        if symbol and event.symbol != symbol:
            continue

        order_id = event.order_id
        orders.setdefault(
            order_id,
            {
                "order_id": order_id,
                "symbol": event.symbol,
                "strategy": event.strategy,
                "run_date": event.run_date,
                "events": [],
                "current_state": "unknown",
                "transitions": [],
            },
        )
        item = orders[order_id]
        item["events"].append(
            {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "timestamp": event.timestamp,
                "sequence": event.sequence,
                "payload": event.payload,
            }
        )
        from_state = event.payload.get("from_state", "")
        to_state = event.payload.get("to_state", event.event_type.value)
        if from_state and to_state:
            item["transitions"].append(
                {
                    "timestamp": event.timestamp,
                    "from_state": from_state,
                    "to_state": to_state,
                    "reason": event.payload.get("reason", ""),
                }
            )
        item["current_state"] = to_state

    result = list(orders.values())
    if status:
        result = [order for order in result if order["current_state"] == status]
    result.sort(key=lambda order: order.get("run_date", ""), reverse=True)
    result = result[:limit]
    return {"orders": result, "total": len(result), "status": "ok"}


def order_trace_payload(order_id: str) -> dict:
    from broker.ledger import EventLedger, EventType

    ledger = EventLedger()
    trace = ledger.trace_order(order_id)
    if not trace["events"]:
        raise DataNotFoundError("order", order_id)

    order_events = trace["events"]
    run_date = order_events[0].run_date if order_events else ""
    related_nav = [
        {"event_id": event.event_id, "timestamp": event.timestamp, "payload": event.payload}
        for event in ledger.events_by_type(EventType.NAV_SNAPSHOT, limit=200)
        if event.run_date == run_date
    ]

    return {
        "order_id": order_id,
        "current_state": trace["current_state"],
        "transitions": trace["transitions"],
        "signal_info": trace["signal_info"],
        "events": [
            {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "timestamp": event.timestamp,
                "sequence": event.sequence,
                "parent_event_id": event.parent_event_id,
                "symbol": event.symbol,
                "strategy": event.strategy,
                "payload": event.payload,
            }
            for event in order_events
        ],
        "related_nav": related_nav,
        "status": "ok",
    }
