"""
Order state machine — enforces valid lifecycle transitions with event sourcing.

States:  PENDING → PARTIAL_FILLED → FILLED | REJECTED | CANCELLED | EXPIRED

Every state transition is recorded as an immutable event. The ledger consumes these
events to build the audit trail. The state machine itself only enforces valid
transitions — it does not persist events (that's the ledger's job).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class OrderState(str, Enum):
    PENDING = "pending"
    PARTIAL_FILLED = "partial_filled"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


# Valid transitions from each state
_TRANSITIONS: dict[OrderState, set[OrderState]] = {
    OrderState.PENDING: {
        OrderState.PARTIAL_FILLED,
        OrderState.FILLED,
        OrderState.REJECTED,
        OrderState.CANCELLED,
        OrderState.EXPIRED,
    },
    OrderState.PARTIAL_FILLED: {
        OrderState.PARTIAL_FILLED,
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.EXPIRED,
    },
    OrderState.FILLED: set(),
    OrderState.REJECTED: set(),
    OrderState.CANCELLED: set(),
    OrderState.EXPIRED: set(),
}

_TERMINAL_STATES: set[OrderState] = {
    OrderState.FILLED,
    OrderState.REJECTED,
    OrderState.CANCELLED,
    OrderState.EXPIRED,
}


class InvalidTransition(ValueError):
    """Raised when a state transition is not allowed."""


@dataclass
class StateTransition:
    """A single state change in an order's lifecycle."""

    timestamp: str
    from_state: OrderState
    to_state: OrderState
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def event_type(self) -> str:
        """Map the transition to a ledger event type string."""
        match self.to_state:
            case OrderState.PARTIAL_FILLED:
                return "order_partial_filled"
            case OrderState.FILLED:
                return "order_filled"
            case OrderState.REJECTED:
                return "order_rejected"
            case OrderState.CANCELLED:
                return "order_cancelled"
            case OrderState.EXPIRED:
                return "order_expired"
            case _:
                return "order_created"


class OrderStateMachine:
    """Manages the lifecycle of a single order with strict transition validation.

    Usage:
        sm = OrderStateMachine("ORD_001")
        sm.transition(OrderState.PARTIAL_FILLED, reason="100/500 filled")
        sm.transition(OrderState.FILLED, reason="remaining 400 filled")
        assert sm.is_terminal

    Events are collected via `drain_events()` — the ledger calls this after each
    transition to persist the events.
    """

    def __init__(
        self,
        order_id: str,
        initial_state: OrderState = OrderState.PENDING,
        created_at: str | None = None,
    ):
        self.order_id = order_id
        self.current_state = initial_state
        self.created_at = created_at or datetime.now().isoformat()
        self._history: list[StateTransition] = []
        self._events: list[StateTransition] = []

    # ── state queries ──

    @property
    def is_terminal(self) -> bool:
        return self.current_state in _TERMINAL_STATES

    @property
    def is_active(self) -> bool:
        return not self.is_terminal

    @property
    def can_be_cancelled(self) -> bool:
        return self.current_state in (OrderState.PENDING, OrderState.PARTIAL_FILLED)

    @property
    def can_be_filled(self) -> bool:
        return self.current_state in (OrderState.PENDING, OrderState.PARTIAL_FILLED)

    @property
    def history(self) -> list[StateTransition]:
        return list(self._history)

    # ── transitions ──

    def transition(
        self,
        to_state: OrderState,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> StateTransition:
        """Attempt a state transition. Raises InvalidTransition if not allowed."""
        if self.is_terminal:
            raise InvalidTransition(
                f"Order {self.order_id} is in terminal state '{self.current_state.value}' "
                f"— cannot transition to '{to_state.value}'"
            )

        allowed = _TRANSITIONS.get(self.current_state, set())
        if to_state not in allowed:
            raise InvalidTransition(
                f"Order {self.order_id}: invalid transition "
                f"'{self.current_state.value}' → '{to_state.value}'"
            )

        t = StateTransition(
            timestamp=datetime.now().isoformat(),
            from_state=self.current_state,
            to_state=to_state,
            reason=reason,
            metadata=metadata or {},
        )
        self._history.append(t)
        self._events.append(t)
        self.current_state = to_state
        return t

    # ── event sourcing interface ──

    def drain_events(self) -> list[StateTransition]:
        """Return and clear pending events. Called by the ledger after persistence."""
        events = self._events
        self._events = []
        return events

    @property
    def pending_events(self) -> list[StateTransition]:
        return list(self._events)

    # ── serialization ──

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "current_state": self.current_state.value,
            "created_at": self.created_at,
            "history": [
                {
                    "timestamp": h.timestamp,
                    "from_state": h.from_state.value,
                    "to_state": h.to_state.value,
                    "reason": h.reason,
                    "metadata": h.metadata,
                }
                for h in self._history
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OrderStateMachine":
        sm = cls(
            order_id=data["order_id"],
            initial_state=OrderState(data.get("current_state", "pending")),
            created_at=data.get("created_at", ""),
        )
        for h in data.get("history", []):
            sm._history.append(StateTransition(
                timestamp=h["timestamp"],
                from_state=OrderState(h["from_state"]),
                to_state=OrderState(h["to_state"]),
                reason=h.get("reason", ""),
                metadata=h.get("metadata", {}),
            ))
        sm.current_state = OrderState(data.get("current_state", "pending"))
        return sm

    def __repr__(self) -> str:
        return (f"<OrderStateMachine id={self.order_id} "
                f"state={self.current_state.value} "
                f"transitions={len(self._history)}>")
