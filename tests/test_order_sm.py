"""Contract tests for OrderStateMachine — valid/invalid transitions, event sourcing."""

import pytest
from broker.order_sm import (
    OrderState, OrderStateMachine, StateTransition, InvalidTransition,
)


class TestOrderStateMachine:
    def test_initial_state_is_pending(self):
        sm = OrderStateMachine("ORD_001")
        assert sm.current_state == OrderState.PENDING
        assert sm.is_active
        assert not sm.is_terminal

    def test_pending_to_filled(self):
        sm = OrderStateMachine("ORD_001")
        t = sm.transition(OrderState.FILLED, reason="全部成交")
        assert sm.current_state == OrderState.FILLED
        assert sm.is_terminal
        assert len(sm.history) == 1
        assert t.from_state == OrderState.PENDING
        assert t.to_state == OrderState.FILLED

    def test_pending_to_partial_filled(self):
        sm = OrderStateMachine("ORD_001")
        sm.transition(OrderState.PARTIAL_FILLED, reason="300/500 filled")
        assert sm.current_state == OrderState.PARTIAL_FILLED
        assert sm.is_active
        assert not sm.is_terminal

    def test_partial_to_partial_again(self):
        sm = OrderStateMachine("ORD_001")
        sm.transition(OrderState.PARTIAL_FILLED, reason="300/500")
        sm.transition(OrderState.PARTIAL_FILLED, reason="100 more, 400/500")
        assert sm.current_state == OrderState.PARTIAL_FILLED
        assert len(sm.history) == 2

    def test_partial_to_filled(self):
        sm = OrderStateMachine("ORD_001")
        sm.transition(OrderState.PARTIAL_FILLED, reason="300/500")
        sm.transition(OrderState.FILLED, reason="remaining 200")
        assert sm.current_state == OrderState.FILLED
        assert sm.is_terminal

    def test_pending_to_rejected(self):
        sm = OrderStateMachine("ORD_001")
        sm.transition(OrderState.REJECTED, reason="风控拒绝")
        assert sm.current_state == OrderState.REJECTED
        assert sm.is_terminal

    def test_pending_to_cancelled(self):
        sm = OrderStateMachine("ORD_001")
        sm.transition(OrderState.CANCELLED, reason="用户撤单")
        assert sm.current_state == OrderState.CANCELLED
        assert sm.is_terminal
        assert sm.can_be_cancelled is False  # already terminal

    def test_partial_to_cancelled(self):
        sm = OrderStateMachine("ORD_001")
        sm.transition(OrderState.PARTIAL_FILLED, reason="100/500")
        sm.transition(OrderState.CANCELLED, reason="用户撤单")
        assert sm.current_state == OrderState.CANCELLED

    def test_pending_to_expired(self):
        sm = OrderStateMachine("ORD_001")
        sm.transition(OrderState.EXPIRED, reason="收盘未成交")
        assert sm.current_state == OrderState.EXPIRED
        assert sm.is_terminal

    def test_partial_to_expired(self):
        sm = OrderStateMachine("ORD_001")
        sm.transition(OrderState.PARTIAL_FILLED, reason="100/500")
        sm.transition(OrderState.EXPIRED, reason="收盘, 400股过期")
        assert sm.current_state == OrderState.EXPIRED

    # ── Invalid transitions ──

    def test_filled_cannot_transition(self):
        sm = OrderStateMachine("ORD_001")
        sm.transition(OrderState.FILLED)
        with pytest.raises(InvalidTransition):
            sm.transition(OrderState.CANCELLED)

    def test_rejected_cannot_transition(self):
        sm = OrderStateMachine("ORD_001")
        sm.transition(OrderState.REJECTED)
        with pytest.raises(InvalidTransition):
            sm.transition(OrderState.FILLED)

    def test_cancelled_cannot_transition(self):
        sm = OrderStateMachine("ORD_001")
        sm.transition(OrderState.CANCELLED)
        with pytest.raises(InvalidTransition):
            sm.transition(OrderState.PARTIAL_FILLED)

    def test_expired_cannot_transition(self):
        sm = OrderStateMachine("ORD_001")
        sm.transition(OrderState.EXPIRED)
        with pytest.raises(InvalidTransition):
            sm.transition(OrderState.FILLED)

    def test_pending_cannot_jump_to_self(self):
        sm = OrderStateMachine("ORD_001")
        with pytest.raises(InvalidTransition):
            sm.transition(OrderState.PENDING)

    def test_filled_cannot_go_to_expired(self):
        sm = OrderStateMachine("ORD_001")
        sm.transition(OrderState.FILLED)
        with pytest.raises(InvalidTransition):
            sm.transition(OrderState.EXPIRED)

    # ── Event sourcing ──

    def test_drain_events_returns_and_clears(self):
        sm = OrderStateMachine("ORD_001")
        sm.transition(OrderState.PARTIAL_FILLED, reason="100/500")
        sm.transition(OrderState.FILLED, reason="400/500")

        events = sm.drain_events()
        assert len(events) == 2
        assert events[0].to_state == OrderState.PARTIAL_FILLED
        assert events[1].to_state == OrderState.FILLED

        # Should be empty after drain
        assert len(sm.pending_events) == 0

    def test_transition_event_type_mapping(self):
        sm = OrderStateMachine("ORD_001")
        t = sm.transition(OrderState.PARTIAL_FILLED, reason="partial")
        assert t.event_type == "order_partial_filled"

    def test_can_be_cancelled(self):
        sm = OrderStateMachine("ORD_001")
        assert sm.can_be_cancelled is True
        sm.transition(OrderState.PARTIAL_FILLED)
        assert sm.can_be_cancelled is True
        sm.transition(OrderState.FILLED)
        assert sm.can_be_cancelled is False

    def test_can_be_filled(self):
        sm = OrderStateMachine("ORD_001")
        assert sm.can_be_filled is True
        sm.transition(OrderState.REJECTED)
        assert sm.can_be_filled is False

    # ── Serialization ──

    def test_to_dict_and_from_dict_roundtrip(self):
        sm = OrderStateMachine("ORD_001")
        sm.transition(OrderState.PARTIAL_FILLED, reason="100/500",
                      metadata={"filled": 100})
        sm.transition(OrderState.FILLED, reason="剩余400",
                      metadata={"filled": 400})

        data = sm.to_dict()
        restored = OrderStateMachine.from_dict(data)

        assert restored.order_id == "ORD_001"
        assert restored.current_state == OrderState.FILLED
        assert len(restored.history) == 2
        assert restored.history[0].reason == "100/500"
        assert restored.history[0].metadata["filled"] == 100

    def test_transition_metadata(self):
        sm = OrderStateMachine("ORD_001")
        t = sm.transition(OrderState.FILLED, reason="done",
                          metadata={"fill_price": 12.50, "shares": 100})
        assert t.metadata["fill_price"] == 12.50
        assert t.metadata["shares"] == 100
