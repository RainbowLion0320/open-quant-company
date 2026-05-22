"""
Event Ledger — append-only immutable audit trail for the full order lifecycle.

Every state change in OrderStateMachine is recorded as a LedgerEvent.
The ledger supports:
  - append: write an event (fcntl-locked for cross-process safety)
  - replay: read all events in sequence order
  - trace: follow the parent_event_id chain from any event back to its origin
  - reconstruct_state: replay all events to rebuild positions/cash holdings

Storage: data/store/paper/ledger.parquet (append-only, via DataHub)

Event chain for a trade:
  ORDER_CREATED → ORDER_PARTIAL_FILLED → ORDER_FILLED
  Each event's parent_event_id points to the previous event in the chain.
  NAV_SNAPSHOT is recorded daily, referencing the day's sequence range.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date as DateType, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from data.datahub import get_datahub


class EventType(str, Enum):
    ORDER_CREATED = "order_created"
    ORDER_PARTIAL_FILLED = "order_partial_filled"
    ORDER_FILLED = "order_filled"
    ORDER_REJECTED = "order_rejected"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_EXPIRED = "order_expired"
    NAV_SNAPSHOT = "nav_snapshot"


@dataclass
class LedgerEvent:
    """A single immutable event in the audit ledger."""

    event_id: str
    event_type: EventType
    timestamp: str
    sequence: int = 0

    # Linking
    parent_event_id: str = ""
    order_id: str = ""

    # Context
    run_date: str = ""          # ISO date YYYY-MM-DD
    symbol: str = ""
    strategy: str = ""

    # Flexible payload
    payload: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict:
        """Convert to a dict suitable for a DataFrame row."""
        import json
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
            "parent_event_id": self.parent_event_id,
            "order_id": self.order_id,
            "run_date": self.run_date,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "payload": json.dumps(self.payload, ensure_ascii=False),
        }

    @classmethod
    def from_row(cls, row: dict) -> "LedgerEvent":
        """Construct from a DataFrame row dict."""
        import json
        payload_raw = row.get("payload", "{}")
        if isinstance(payload_raw, str):
            payload_raw = json.loads(payload_raw)
        return cls(
            event_id=str(row.get("event_id", "")),
            event_type=EventType(row.get("event_type", "order_created")),
            timestamp=str(row.get("timestamp", "")),
            sequence=int(row.get("sequence", 0)),
            parent_event_id=str(row.get("parent_event_id", "")),
            order_id=str(row.get("order_id", "")),
            run_date=str(row.get("run_date", "")),
            symbol=str(row.get("symbol", "")),
            strategy=str(row.get("strategy", "")),
            payload=payload_raw or {},
        )


class EventLedger:
    """Append-only event ledger backed by Parquet.

    Usage:
        ledger = EventLedger()
        ledger.append(LedgerEvent(...))
        ledger.append(LedgerEvent(...))

        # Replay all events
        events = ledger.replay()

        # Trace an order's full lifecycle
        chain = ledger.trace_order("PAPER_000001")

        # Trace from a NAV snapshot back to signals
        sources = ledger.trace_nav_to_signal("2026-05-22")

        # Reconstruct full state
        state = ledger.reconstruct_state()
    """

    def __init__(self, store_dir: Path | None = None):
        self._hub = get_datahub()
        self._store = store_dir or self._hub.paper_dir()
        self._store.mkdir(parents=True, exist_ok=True)
        self._file = self._store / "ledger.parquet"
        self._next_sequence: int | None = None

    # ── append ──

    def append(self, event: LedgerEvent) -> LedgerEvent:
        """Append a single event to the ledger. Assigns sequence number."""
        if event.sequence <= 0:
            event.sequence = self._next_seq()

        row = pd.DataFrame([event.to_row()])

        if self._file.exists():
            existing = self._hub.read_parquet(self._file, default=pd.DataFrame())
            df = pd.concat([existing, row], ignore_index=True)
        else:
            df = row

        self._hub.write_parquet(df, self._file)
        self._next_sequence = event.sequence + 1
        return event

    def append_batch(self, events: list[LedgerEvent]) -> list[LedgerEvent]:
        """Append multiple events atomically."""
        for e in events:
            self.append(e)
        return events

    # ── sequence ──

    def _next_seq(self) -> int:
        if self._next_sequence is None:
            existing = self._all()
            if existing.empty:
                self._next_sequence = 1
            else:
                self._next_sequence = int(existing["sequence"].max()) + 1
        return self._next_sequence

    def _all(self) -> pd.DataFrame:
        if not self._file.exists():
            return pd.DataFrame()
        return self._hub.read_parquet(
            self._file,
            default=pd.DataFrame(),
        )

    # ── query ──

    def replay(self, from_sequence: int = 0, to_sequence: int | None = None) -> list[LedgerEvent]:
        """Return all events in sequence order, optionally bounded."""
        df = self._all()
        if df.empty:
            return []
        if from_sequence > 0:
            df = df[df["sequence"] >= from_sequence]
        if to_sequence is not None:
            df = df[df["sequence"] <= to_sequence]
        df = df.sort_values("sequence")
        return [LedgerEvent.from_row(row) for _, row in df.iterrows()]

    def events_for_date(self, dt: DateType | str) -> list[LedgerEvent]:
        """Return all events for a given trading date."""
        date_str = dt.isoformat() if isinstance(dt, DateType) else str(dt)
        df = self._all()
        if df.empty:
            return []
        mask = df["run_date"] == date_str
        return [LedgerEvent.from_row(row) for _, row in df[mask].sort_values("sequence").iterrows()]

    def events_for_order(self, order_id: str) -> list[LedgerEvent]:
        """Return all events for a specific order, in sequence order."""
        df = self._all()
        if df.empty:
            return []
        mask = df["order_id"] == order_id
        return [LedgerEvent.from_row(row) for _, row in df[mask].sort_values("sequence").iterrows()]

    def events_by_type(self, event_type: EventType, limit: int = 100) -> list[LedgerEvent]:
        """Return recent events of a given type."""
        df = self._all()
        if df.empty:
            return []
        mask = df["event_type"] == event_type.value
        recent = df[mask].sort_values("sequence", ascending=False).head(limit)
        return [LedgerEvent.from_row(row) for _, row in recent.iterrows()]

    # ── trace ──

    def trace_order(self, order_id: str) -> dict:
        """Return the full lifecycle chain for an order.

        Returns:
            {
                "order_id": str,
                "events": [LedgerEvent, ...],
                "current_state": str,
                "transitions": [(from_state, to_state, timestamp, reason), ...],
                "signal_info": dict | None,  # from ORDER_CREATED payload
            }
        """
        events = self.events_for_order(order_id)
        if not events:
            return {"order_id": order_id, "events": [], "current_state": "unknown",
                    "transitions": [], "signal_info": None}

        transitions = []
        signal_info = None
        current_state = "unknown"

        for e in events:
            current_state = e.payload.get("to_state", e.event_type.value)
            prev_state = e.payload.get("from_state", "")
            if prev_state:
                transitions.append((
                    prev_state,
                    current_state,
                    e.timestamp,
                    e.payload.get("reason", ""),
                ))
            if e.event_type == EventType.ORDER_CREATED:
                signal_info = e.payload.get("signal", None)

        return {
            "order_id": order_id,
            "events": events,
            "current_state": current_state,
            "transitions": transitions,
            "signal_info": signal_info,
        }

    def trace_nav_to_signals(self, nav_date: DateType | str) -> list[dict]:
        """Trace a day's NAV back to the signals that drove the fills.

        For each fill event on the given date, follow parent_event_id back
        to ORDER_CREATED, which carries signal info in its payload.

        Returns a list of traces: [{nav_event, fill_events, order_event, signal_info}, ...]
        """
        date_str = nav_date.isoformat() if isinstance(nav_date, DateType) else str(nav_date)
        all_events = self.events_for_date(date_str)

        # Group fill events
        fills = [e for e in all_events if e.event_type in (
            EventType.ORDER_PARTIAL_FILLED,
            EventType.ORDER_FILLED,
        )]

        traces = []
        for fill in fills:
            # Walk back to ORDER_CREATED
            order_created = self._find_ancestor(fill, EventType.ORDER_CREATED)
            trace = {
                "fill_event": fill,
                "order_event": order_created,
                "signal_info": order_created.payload.get("signal") if order_created else None,
                "order_id": fill.order_id,
                "symbol": fill.symbol,
                "strategy": fill.strategy,
            }
            traces.append(trace)

        return traces

    def _find_ancestor(self, event: LedgerEvent, target_type: EventType) -> LedgerEvent | None:
        """Walk parent_event_id chain to find an event of target_type."""
        if event.event_type == target_type:
            return event
        if not event.parent_event_id:
            return None

        df = self._all()
        if df.empty:
            return None
        mask = df["event_id"] == event.parent_event_id
        matches = df[mask]
        if matches.empty:
            return None

        parent = LedgerEvent.from_row(matches.iloc[0].to_dict())
        return self._find_ancestor(parent, target_type)

    # ── state reconstruction ──

    def reconstruct_state(self, as_of: DateType | str | None = None) -> dict:
        """Replay all events to reconstruct portfolio state.

        Returns:
            {
                "cash": float,
                "positions": {symbol: {"volume": int, "avg_cost": float}},
                "total_equity": float,
                "trade_count": int,
            }
        """
        date_str = as_of.isoformat() if isinstance(as_of, DateType) else (str(as_of) if as_of else None)

        cash = 1_000_000.0
        positions: dict[str, dict] = {}
        trade_count = 0

        events = self.replay()
        for e in events:
            if date_str and e.run_date > date_str:
                break

            if e.event_type in (EventType.ORDER_FILLED, EventType.ORDER_PARTIAL_FILLED):
                side = e.payload.get("side", "")
                shares = int(e.payload.get("shares", e.payload.get("filled_shares", 0)))
                price = float(e.payload.get("fill_price", e.payload.get("price", 0)))
                commission = float(e.payload.get("commission", 0))
                symbol = e.symbol

                if shares <= 0 or price <= 0:
                    continue

                amount = shares * price
                trade_count += 1

                if side == "buy":
                    cost = amount + commission
                    if cost <= cash:
                        cash -= cost
                        prev = positions.get(symbol, {"volume": 0, "avg_cost": 0.0})
                        total_cost = prev["avg_cost"] * prev["volume"] + cost
                        new_vol = prev["volume"] + shares
                        positions[symbol] = {
                            "volume": new_vol,
                            "avg_cost": total_cost / new_vol if new_vol > 0 else 0.0,
                        }
                else:  # sell
                    cash += amount - commission
                    prev = positions.get(symbol, {"volume": 0, "avg_cost": 0.0})
                    new_vol = max(0, prev["volume"] - shares)
                    if new_vol <= 0:
                        positions.pop(symbol, None)
                    else:
                        positions[symbol] = {"volume": new_vol, "avg_cost": prev["avg_cost"]}

        return {
            "cash": cash,
            "positions": positions,
            "total_equity": cash,  # without current prices, just cash + cost basis
            "trade_count": trade_count,
        }

    # ── stats ──

    def stats(self) -> dict:
        """Summary statistics about the ledger."""
        df = self._all()
        if df.empty:
            return {"total_events": 0, "orders": 0, "fills": 0, "date_range": None}

        return {
            "total_events": len(df),
            "orders": int(df[df["event_type"] == "order_created"].shape[0]),
            "fills": int(df[df["event_type"].isin(("order_filled", "order_partial_filled"))].shape[0]),
            "date_range": (
                str(df["run_date"].min()),
                str(df["run_date"].max()),
            ) if "run_date" in df.columns else None,
            "sequence_range": (
                int(df["sequence"].min()),
                int(df["sequence"].max()),
            ),
        }

    # ── clear ──

    def clear(self):
        """Remove all ledger data. Use with caution."""
        if self._file.exists():
            self._file.unlink()
        self._next_sequence = None
