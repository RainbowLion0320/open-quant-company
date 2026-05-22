"""Contract tests for BackfillLedger — lifecycle, queries, retry."""

import pytest
from data.backfill import BackfillLedger, BackfillEntry


@pytest.fixture
def ledger():
    """Fresh ledger for each test, cleaned after."""
    l = BackfillLedger()
    l.clear()
    yield l
    l.clear()


class TestBackfillLifecycle:
    def test_start_returns_run_id(self, ledger):
        run_id = ledger.start("ohlcv_daily")
        assert run_id.startswith("bf_")
        assert len(run_id) == 15  # bf_ + 12 hex

    def test_start_creates_running_entry(self, ledger):
        run_id = ledger.start("ohlcv_daily", date_start="20240101", date_end="20240522")
        running = ledger.running()
        assert len(running) == 1
        assert running[0].dimension == "ohlcv_daily"
        assert running[0].status == "running"
        assert running[0].triggered_by == "manual"

    def test_complete_updates_status(self, ledger):
        run_id = ledger.start("ohlcv_daily")
        ledger.complete(run_id, rows_fetched=5000)

        last = ledger.last_run("ohlcv_daily")
        assert last is not None
        assert last.status == "done"
        assert last.rows_fetched == 5000
        assert last.completed_at != ""

    def test_fail_updates_status(self, ledger):
        run_id = ledger.start("stock_holders")
        ledger.fail(run_id, error="Network timeout")

        last = ledger.last_run("stock_holders")
        assert last is not None
        assert last.status == "failed"
        assert "Network timeout" in last.error

    def test_error_truncated_to_500_chars(self, ledger):
        run_id = ledger.start("test_dim")
        long_error = "x" * 600
        ledger.fail(run_id, error=long_error)
        last = ledger.last_run("test_dim")
        assert len(last.error) <= 500


class TestBackfillQueries:
    def test_last_run_returns_most_recent(self, ledger):
        ledger.start("ohlcv_daily", date_start="20240101")
        ledger.start("ohlcv_daily", date_start="20240102")
        last = ledger.last_run("ohlcv_daily")
        assert last.date_start == "20240102"

    def test_last_run_nonexistent_dimension(self, ledger):
        last = ledger.last_run("nonexistent")
        assert last is None

    def test_last_successful_filters_by_done(self, ledger):
        rid1 = ledger.start("test_dim")
        ledger.complete(rid1)
        rid2 = ledger.start("test_dim")
        ledger.fail(rid2, error="fail")

        last_ok = ledger.last_successful("test_dim")
        assert last_ok is not None
        assert last_ok.status == "done"
        assert last_ok.run_id == rid1

    def test_last_successful_none_when_no_success(self, ledger):
        ledger.start("test_dim")
        last = ledger.last_successful("test_dim")
        assert last is None  # still running, not done

    def test_history_with_dimension_filter(self, ledger):
        ledger.start("dim_a")
        ledger.start("dim_b")
        ledger.start("dim_a")

        hist = ledger.history(dimension="dim_a")
        assert len(hist) == 2
        assert all(e.dimension == "dim_a" for e in hist)

    def test_history_with_status_filter(self, ledger):
        rid1 = ledger.start("test_dim")
        ledger.complete(rid1)
        rid2 = ledger.start("test_dim")
        ledger.fail(rid2, error="fail")

        done = ledger.history(dimension="test_dim", status="done")
        assert len(done) == 1
        assert done[0].status == "done"

    def test_history_limit(self, ledger):
        for _ in range(5):
            ledger.start("test_dim")

        hist = ledger.history(dimension="test_dim", limit=3)
        assert len(hist) == 3

    def test_history_empty_ledger(self, ledger):
        hist = ledger.history()
        assert hist == []

    def test_running_filters_active(self, ledger):
        ledger.start("dim_a")
        run_id = ledger.start("dim_b")
        ledger.complete(run_id)
        ledger.start("dim_c")

        active = ledger.running()
        assert len(active) == 2
        dims = {e.dimension for e in active}
        assert "dim_a" in dims
        assert "dim_c" in dims
        assert "dim_b" not in dims


class TestBackfillRetry:
    def test_needs_retry_returns_failed_under_max(self, ledger):
        rid = ledger.start("test_dim")
        ledger.fail(rid, error="timeout")
        needs = ledger.needs_retry("test_dim", max_retries=3)
        assert len(needs) == 1
        assert needs[0].retry_count == 0

    def test_needs_retry_excludes_exceeded_max(self, ledger):
        # Simulate an entry with retry_count=3
        rid = ledger.start("test_dim", triggered_by="auto")
        # Manually bump retry_count
        df = ledger._all()
        mask = df["run_id"] == rid
        df.loc[mask, "retry_count"] = 3
        df.loc[mask, "status"] = "failed"
        ledger._write_all(df)

        needs = ledger.needs_retry("test_dim", max_retries=3)
        assert len(needs) == 0

    def test_needs_retry_empty_ledger(self, ledger):
        needs = ledger.needs_retry()
        assert needs == []

    def test_retry_increments_count(self, ledger):
        rid = ledger.start("test_dim")
        ledger.fail(rid, error="first fail")

        new_id = ledger.retry("test_dim")
        assert new_id.startswith("bf_")
        assert new_id != rid

        # The new entry should have retry_count=1
        last = ledger.last_run("test_dim")
        assert last is not None
        assert last.retry_count == 1
        assert last.triggered_by == "auto"


class TestBackfillSummary:
    def test_summary_empty_ledger(self, ledger):
        s = ledger.summary()
        assert s["total_runs"] == 0
        assert s["done"] == 0
        assert s["failed"] == 0

    def test_summary_with_entries(self, ledger):
        rid1 = ledger.start("dim_a")
        ledger.complete(rid1)
        rid2 = ledger.start("dim_b")
        ledger.fail(rid2, error="fail")
        ledger.start("dim_a")

        s = ledger.summary()
        assert s["total_runs"] == 3
        assert s["done"] == 1
        assert s["failed"] == 1
        assert s["running"] == 1
        assert s["dimensions_repaired"] == 2

    def test_summary_last_run_at(self, ledger):
        ledger.start("test_dim")
        s = ledger.summary()
        assert s["last_run_at"] is not None


class TestBackfillEntry:
    def test_to_row_and_from_row_roundtrip(self):
        entry = BackfillEntry(
            run_id="bf_test123456",
            dimension="ohlcv_daily",
            status="done",
            date_start="20240101",
            date_end="20240522",
            rows_fetched=5000,
            rows_before=4800,
            error="",
            retry_count=0,
            started_at="2024-05-22T10:00:00",
            completed_at="2024-05-22T10:05:00",
            duration_seconds=300.0,
            triggered_by="manual",
        )
        row = entry.to_row()
        restored = BackfillEntry.from_row(row)
        assert restored.run_id == entry.run_id
        assert restored.dimension == entry.dimension
        assert restored.status == entry.status
        assert restored.rows_fetched == 5000
        assert restored.triggered_by == "manual"
