"""Contract tests for EventLedger — append, replay, trace, reconstruct."""

import tempfile
from datetime import date
from pathlib import Path

import pytest

from broker.ledger import EventLedger, LedgerEvent, EventType


@pytest.fixture
def ledger():
    """Create a ledger backed by a temporary directory."""
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "paper"
        store.mkdir(parents=True, exist_ok=True)
        ledger = EventLedger(store_dir=store)
        yield ledger
        # Clean up
        if ledger._file.exists():
            ledger._file.unlink()


class TestLedgerAppend:
    def test_append_single_event(self, ledger):
        e = LedgerEvent(
            event_id="evt_001",
            event_type=EventType.ORDER_CREATED,
            timestamp="2026-05-22T15:00:00",
            order_id="PAPER_000001",
            run_date="2026-05-22",
            symbol="000001",
            payload={"side": "buy", "shares": 100},
        )
        result = ledger.append(e)
        assert result.sequence >= 1
        assert ledger._file.exists()

    def test_append_assigns_sequence(self, ledger):
        e1 = LedgerEvent(event_id="e1", event_type=EventType.ORDER_CREATED,
                         timestamp="2026-05-22T10:00:00", order_id="O1", run_date="2026-05-22")
        e2 = LedgerEvent(event_id="e2", event_type=EventType.ORDER_FILLED,
                         timestamp="2026-05-22T10:01:00", order_id="O1", run_date="2026-05-22")

        r1 = ledger.append(e1)
        r2 = ledger.append(e2)
        assert r2.sequence == r1.sequence + 1

    def test_append_batch(self, ledger):
        events = [
            LedgerEvent(event_id=f"e{i}", event_type=EventType.ORDER_CREATED,
                        timestamp=f"2026-05-22T10:0{i}:00", order_id=f"O{i}",
                        run_date="2026-05-22")
            for i in range(5)
        ]
        result = ledger.append_batch(events)
        assert len(result) == 5
        assert all(e.sequence > 0 for e in result)


class TestLedgerReplay:
    def test_replay_empty(self, ledger):
        events = ledger.replay()
        assert events == []

    def test_replay_returns_sorted(self, ledger):
        e1 = LedgerEvent(event_id="e1", event_type=EventType.ORDER_CREATED,
                         timestamp="2026-05-22T10:00:00", order_id="O1",
                         run_date="2026-05-22", sequence=1)
        e2 = LedgerEvent(event_id="e2", event_type=EventType.ORDER_FILLED,
                         timestamp="2026-05-22T10:01:00", order_id="O1",
                         run_date="2026-05-22", sequence=2)
        ledger.append(e1)
        ledger.append(e2)

        events = ledger.replay()
        assert len(events) == 2
        assert events[0].sequence < events[1].sequence

    def test_replay_from_sequence(self, ledger):
        for i in range(10):
            ledger.append(LedgerEvent(
                event_id=f"e{i}", event_type=EventType.ORDER_CREATED,
                timestamp=f"2026-05-22T10:{i:02d}:00", order_id=f"O{i}",
                run_date="2026-05-22",
            ))
        events = ledger.replay(from_sequence=5)
        assert len(events) >= 5


class TestLedgerQuery:
    def test_events_for_date(self, ledger):
        ledger.append(LedgerEvent(
            event_id="e1", event_type=EventType.ORDER_CREATED,
            timestamp="2026-05-21T10:00:00", order_id="O1", run_date="2026-05-21",
        ))
        ledger.append(LedgerEvent(
            event_id="e2", event_type=EventType.ORDER_CREATED,
            timestamp="2026-05-22T10:00:00", order_id="O2", run_date="2026-05-22",
        ))
        ledger.append(LedgerEvent(
            event_id="e3", event_type=EventType.ORDER_FILLED,
            timestamp="2026-05-22T10:01:00", order_id="O2", run_date="2026-05-22",
        ))

        day1 = ledger.events_for_date("2026-05-21")
        assert len(day1) == 1

        day2 = ledger.events_for_date(date(2026, 5, 22))
        assert len(day2) == 2

    def test_events_for_order(self, ledger):
        ledger.append(LedgerEvent(
            event_id="e1", event_type=EventType.ORDER_CREATED,
            timestamp="2026-05-22T10:00:00", order_id="ORD_A", run_date="2026-05-22",
        ))
        ledger.append(LedgerEvent(
            event_id="e2", event_type=EventType.ORDER_CREATED,
            timestamp="2026-05-22T10:01:00", order_id="ORD_B", run_date="2026-05-22",
        ))
        ledger.append(LedgerEvent(
            event_id="e3", event_type=EventType.ORDER_FILLED,
            timestamp="2026-05-22T10:02:00", order_id="ORD_A", run_date="2026-05-22",
        ))

        ord_a = ledger.events_for_order("ORD_A")
        assert len(ord_a) == 2

        ord_b = ledger.events_for_order("ORD_B")
        assert len(ord_b) == 1

    def test_events_by_type(self, ledger):
        for i in range(5):
            ledger.append(LedgerEvent(
                event_id=f"e{i}", event_type=EventType.ORDER_CREATED,
                timestamp=f"2026-05-22T10:0{i}:00", order_id=f"O{i}",
                run_date="2026-05-22",
            ))
        ledger.append(LedgerEvent(
            event_id="ef", event_type=EventType.ORDER_FILLED,
            timestamp="2026-05-22T10:06:00", order_id="O0",
            run_date="2026-05-22",
        ))

        created = ledger.events_by_type(EventType.ORDER_CREATED, limit=100)
        assert len(created) == 5

        filled = ledger.events_by_type(EventType.ORDER_FILLED, limit=100)
        assert len(filled) == 1


class TestLedgerTrace:
    def test_trace_order_full_lifecycle(self, ledger):
        # ORDER_CREATED
        create = LedgerEvent(
            event_id="evt_create", event_type=EventType.ORDER_CREATED,
            timestamp="2026-05-22T10:00:00", order_id="ORD_001",
            run_date="2026-05-22", symbol="000001",
            payload={
                "side": "buy",
                "requested_shares": 500,
                "signal": {"strategy": "multifactor", "score": 85},
                "from_state": "pending",
                "to_state": "pending",
            },
        )
        ledger.append(create)

        # PARTIAL_FILLED
        partial = LedgerEvent(
            event_id="evt_partial", event_type=EventType.ORDER_PARTIAL_FILLED,
            timestamp="2026-05-22T10:00:01", order_id="ORD_001",
            parent_event_id="evt_create",
            run_date="2026-05-22", symbol="000001",
            payload={
                "from_state": "pending",
                "to_state": "partial_filled",
                "filled_shares": 300,
                "fill_price": 12.50,
                "side": "buy",
            },
        )
        ledger.append(partial)

        # FILLED
        filled = LedgerEvent(
            event_id="evt_filled", event_type=EventType.ORDER_FILLED,
            timestamp="2026-05-22T10:00:02", order_id="ORD_001",
            parent_event_id="evt_partial",
            run_date="2026-05-22", symbol="000001",
            payload={
                "from_state": "partial_filled",
                "to_state": "filled",
                "filled_shares": 200,
                "fill_price": 12.52,
                "side": "buy",
            },
        )
        ledger.append(filled)

        trace = ledger.trace_order("ORD_001")
        assert trace["current_state"] == "filled"
        assert len(trace["events"]) == 3
        assert len(trace["transitions"]) == 3
        assert trace["signal_info"] == {"strategy": "multifactor", "score": 85}

    def test_trace_order_not_found(self, ledger):
        trace = ledger.trace_order("NONEXISTENT")
        assert trace["current_state"] == "unknown"
        assert trace["events"] == []

    def test_trace_nav_to_signals(self, ledger):
        # Create an order with signal info
        ledger.append(LedgerEvent(
            event_id="evt_create", event_type=EventType.ORDER_CREATED,
            timestamp="2026-05-22T10:00:00", order_id="ORD_001",
            run_date="2026-05-22", symbol="000001", strategy="multifactor",
            payload={
                "side": "buy",
                "signal": {"strategy": "multifactor", "score": 85},
            },
        ))
        ledger.append(LedgerEvent(
            event_id="evt_fill", event_type=EventType.ORDER_FILLED,
            timestamp="2026-05-22T10:00:01", order_id="ORD_001",
            parent_event_id="evt_create",
            run_date="2026-05-22", symbol="000001", strategy="multifactor",
            payload={
                "filled_shares": 500,
                "fill_price": 12.50,
            },
        ))

        traces = ledger.trace_nav_to_signals("2026-05-22")
        assert len(traces) > 0
        assert traces[0]["signal_info"] == {"strategy": "multifactor", "score": 85}
        assert traces[0]["symbol"] == "000001"

    def test_paper_broker_generated_events_are_parent_linked(self, ledger):
        from broker import PaperBroker

        broker = PaperBroker(initial_cash=100000, enable_risk=False, ledger=ledger)
        broker.set_prices({"000001": 10.0})
        order_id = broker.submit_order("000001", price=10.0, volume=100, side="buy")

        events = ledger.events_for_order(order_id)
        assert [e.event_type for e in events] == [EventType.ORDER_CREATED, EventType.ORDER_FILLED]
        assert events[1].parent_event_id == events[0].event_id


class TestLedgerReconstruct:
    def test_reconstruct_empty(self, ledger):
        state = ledger.reconstruct_state()
        assert state["cash"] == 1_000_000.0
        assert state["positions"] == {}
        assert state["trade_count"] == 0

    def test_reconstruct_buy_and_sell(self, ledger):
        # Buy 500 shares at 10.00
        ledger.append(LedgerEvent(
            event_id="e1", event_type=EventType.ORDER_FILLED,
            timestamp="2026-05-22T10:00:00", order_id="O1",
            run_date="2026-05-22", symbol="000001",
            payload={
                "side": "buy", "shares": 500, "fill_price": 10.0,
                "commission": 4.05,
            },
        ))
        # Sell 200 shares at 11.00
        ledger.append(LedgerEvent(
            event_id="e2", event_type=EventType.ORDER_FILLED,
            timestamp="2026-05-22T10:01:00", order_id="O2",
            run_date="2026-05-22", symbol="000001",
            payload={
                "side": "sell", "shares": 200, "fill_price": 11.0,
                "commission": 4.07,
            },
        ))

        state = ledger.reconstruct_state()
        assert state["trade_count"] == 2
        assert state["positions"]["000001"]["volume"] == 300  # 500 - 200

        # Cash check: start 1M, buy 500*10+4.05 = 5004.05, sell 200*11-4.07 = 2195.93
        expected_cash = 1_000_000 - 5004.05 + 2195.93
        assert abs(state["cash"] - expected_cash) < 0.01

    def test_reconstruct_as_of_date(self, ledger):
        ledger.append(LedgerEvent(
            event_id="e1", event_type=EventType.ORDER_FILLED,
            timestamp="2026-05-21T10:00:00", order_id="O1",
            run_date="2026-05-21", symbol="000001",
            payload={"side": "buy", "shares": 100, "fill_price": 10.0, "commission": 0.81},
        ))
        ledger.append(LedgerEvent(
            event_id="e2", event_type=EventType.ORDER_FILLED,
            timestamp="2026-05-22T10:00:00", order_id="O2",
            run_date="2026-05-22", symbol="000002",
            payload={"side": "buy", "shares": 200, "fill_price": 20.0, "commission": 3.24},
        ))

        # As of day 1: only first trade
        state_day1 = ledger.reconstruct_state(as_of="2026-05-21")
        assert state_day1["trade_count"] == 1
        assert "000001" in state_day1["positions"]
        assert "000002" not in state_day1["positions"]

        # As of day 2: both trades
        state_day2 = ledger.reconstruct_state(as_of="2026-05-22")
        assert state_day2["trade_count"] == 2

    def test_reconstruct_sell_reduces_position(self, ledger):
        ledger.append(LedgerEvent(
            event_id="e1", event_type=EventType.ORDER_FILLED,
            timestamp="2026-05-22T10:00:00", order_id="O1",
            run_date="2026-05-22", symbol="000001",
            payload={"side": "buy", "shares": 500, "fill_price": 10.0, "commission": 4.05},
        ))
        ledger.append(LedgerEvent(
            event_id="e2", event_type=EventType.ORDER_FILLED,
            timestamp="2026-05-22T10:01:00", order_id="O2",
            run_date="2026-05-22", symbol="000001",
            payload={"side": "sell", "shares": 500, "fill_price": 12.0, "commission": 4.31},
        ))

        state = ledger.reconstruct_state()
        assert "000001" not in state["positions"]  # fully sold


class TestLedgerStats:
    def test_stats_empty(self, ledger):
        stats = ledger.stats()
        assert stats["total_events"] == 0

    def test_stats_with_events(self, ledger):
        ledger.append(LedgerEvent(
            event_id="e1", event_type=EventType.ORDER_CREATED,
            timestamp="2026-05-22T10:00:00", order_id="O1", run_date="2026-05-22",
        ))
        ledger.append(LedgerEvent(
            event_id="e2", event_type=EventType.ORDER_FILLED,
            timestamp="2026-05-22T10:01:00", order_id="O1", run_date="2026-05-22",
        ))

        stats = ledger.stats()
        assert stats["total_events"] == 2
        assert stats["orders"] == 1
        assert stats["fills"] == 1
