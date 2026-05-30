"""
Execution observability contracts.

Tests the execution dry-run CLI command and verifies it returns
structured JSON without mutating broker state.
"""
import pytest


class TestExecutionDryRun:

    def test_dry_run_returns_valid_json(self):
        """Execution dry-run returns a valid JSON structure."""
        from astrolabe_cli.commands.execution import dry_run
        result = dry_run()
        data = result.render_json()
        import json
        parsed = json.loads(data)
        assert parsed["ok"] is True
        assert "data" in parsed

    def test_dry_run_has_required_fields(self):
        """Dry-run output contains all required fields."""
        from astrolabe_cli.commands.execution import dry_run
        result = dry_run()
        assert result.ok is True
        d = result.data
        assert "ok" in d
        assert "signals_loaded" in d
        assert "orders_proposed" in d
        assert "orders_rejected" in d
        assert "risk_rejections" in d
        assert "cash_after" in d
        assert "warnings" in d

    def test_dry_run_does_not_mutate_state(self):
        """Dry-run does not change broker state."""
        from astrolabe_cli.commands.execution import dry_run
        # Run twice - should get same result
        r1 = dry_run()
        r2 = dry_run()
        assert r1.data["signals_loaded"] == r2.data["signals_loaded"]
        assert r1.data["cash_after"] == r2.data["cash_after"]

    def test_dry_run_exit_code_zero(self):
        """Dry-run exits with code 0."""
        from astrolabe_cli.commands.execution import dry_run
        result = dry_run()
        assert result.ok is True
