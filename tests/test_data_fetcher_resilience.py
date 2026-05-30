"""
Contracts for data/fetcher.py retry and throttle mechanisms.

Tests use monkeypatching to avoid real network calls and deterministic timing.
"""
import time
import pytest


class TestRetryWithBackoff:
    """retry_with_backoff decorator contract tests."""

    def test_failing_twice_then_succeeding_calls_three_times(self, monkeypatch):
        """Function failing twice then succeeding is called exactly 3 times."""
        import data.fetcher as mod

        # Remove jitter for deterministic delays
        monkeypatch.setattr(mod.random, "uniform", lambda a, b: 0.0)

        sleep_calls = []
        monkeypatch.setattr(mod.time, "sleep", lambda d: sleep_calls.append(d))

        call_count = {"n": 0}

        @mod.retry_with_backoff(max_retries=2, base_delay=1.0, backoff_factor=2.0, jitter=False)
        def flaky():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise ConnectionError("transient")
            return "ok"

        result = flaky()
        assert result == "ok"
        assert call_count["n"] == 3

    def test_sleep_delays_are_exponential(self, monkeypatch):
        """Sleep delays follow base_delay * backoff_factor^attempt."""
        import data.fetcher as mod

        monkeypatch.setattr(mod.random, "uniform", lambda a, b: 0.0)

        sleep_calls = []
        monkeypatch.setattr(mod.time, "sleep", lambda d: sleep_calls.append(d))

        call_count = {"n": 0}

        @mod.retry_with_backoff(max_retries=2, base_delay=1.0, backoff_factor=2.0, jitter=False)
        def flaky():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise ConnectionError("transient")
            return "ok"

        flaky()
        # attempt 0: delay = 1.0 * 2^0 = 1.0
        # attempt 1: delay = 1.0 * 2^1 = 2.0
        assert len(sleep_calls) == 2
        assert sleep_calls[0] == pytest.approx(1.0)
        assert sleep_calls[1] == pytest.approx(2.0)

    def test_failing_three_times_raises(self, monkeypatch):
        """Function failing max_retries+1 times raises the final error."""
        import data.fetcher as mod

        monkeypatch.setattr(mod.random, "uniform", lambda a, b: 0.0)
        monkeypatch.setattr(mod.time, "sleep", lambda d: None)

        @mod.retry_with_backoff(max_retries=2, base_delay=1.0, backoff_factor=2.0, jitter=False)
        def always_fail():
            raise ConnectionError("permanent")

        with pytest.raises(ConnectionError, match="permanent"):
            always_fail()


class TestThrottle:
    """_throttle() contract tests."""

    def test_first_call_does_not_sleep_when_old(self, monkeypatch):
        """First call does not sleep when _last_request_time is old."""
        import data.fetcher as mod

        mod._last_request_time = 0.0
        slept = []
        monkeypatch.setattr(mod.time, "sleep", lambda d: slept.append(d))
        monkeypatch.setattr(mod.time, "monotonic", lambda: 1000.0)
        monkeypatch.setattr(mod.random, "uniform", lambda a, b: 0.0)

        mod._throttle()
        assert slept == []

    def test_second_call_sleeps_for_remaining_interval(self, monkeypatch):
        """Second call sleeps for remaining interval when elapsed < MIN_INTERVAL."""
        import data.fetcher as mod

        mod._last_request_time = 0.0
        slept = []
        monkeypatch.setattr(mod.time, "sleep", lambda d: slept.append(d))
        monkeypatch.setattr(mod.random, "uniform", lambda a, b: 0.0)

        # First call at t=100
        monkeypatch.setattr(mod.time, "monotonic", lambda: 100.0)
        mod._throttle()

        # Second call at t=101 (1s elapsed, need 2s more)
        monkeypatch.setattr(mod.time, "monotonic", lambda: 101.0)
        mod._throttle()

        assert len(slept) == 1
        assert slept[0] == pytest.approx(2.0)

        # Cleanup
        mod._last_request_time = 0.0
