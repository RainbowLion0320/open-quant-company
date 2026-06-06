"""
Contracts for data/cron_logger.py.

Tests monkeypatch _LOG_DIR to tmp_path for isolation.
"""
import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _patch_log_dir(tmp_path, monkeypatch):
    """Redirect cron logger to a temp directory."""
    import data.ops.cron_logger as mod
    log_dir = tmp_path / "cron_log"
    log_dir.mkdir()
    monkeypatch.setattr(mod, "_LOG_DIR", log_dir)
    return log_dir


class TestLogCronSuccess:

    def test_writes_jsonl_row_with_status_ok(self, _patch_log_dir):
        import data.ops.cron_logger as mod
        mod.log_cron_success("test_script", extra_key="value")
        log_file = _patch_log_dir / "test_script.jsonl"
        assert log_file.exists()
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["script"] == "test_script"
        assert entry["status"] == "ok"
        assert entry["extra_key"] == "value"
        assert "ts" in entry


class TestLogCronError:

    def test_truncates_error_to_500_chars(self, _patch_log_dir):
        import data.ops.cron_logger as mod
        long_error = "E" * 1000
        mod.log_cron_error("test_script", error=long_error)
        log_file = _patch_log_dir / "test_script.jsonl"
        entry = json.loads(log_file.read_text().strip().splitlines()[0])
        assert len(entry["error"]) == 500

    def test_truncates_traceback_to_2000_chars(self, _patch_log_dir):
        import data.ops.cron_logger as mod
        long_tb = "T" * 3000
        mod.log_cron_error("test_script", error="err", tb=long_tb)
        log_file = _patch_log_dir / "test_script.jsonl"
        entry = json.loads(log_file.read_text().strip().splitlines()[0])
        assert len(entry["traceback"]) == 2000


class TestRotateIfNeeded:

    def test_keeps_last_n_lines(self, _patch_log_dir):
        import data.ops.cron_logger as mod
        test_file = _patch_log_dir / "rotate_test.jsonl"
        # Write 10 lines
        test_file.write_text("\n".join(f'{{"i":{i}}}' for i in range(10)) + "\n")
        mod._rotate_if_needed(test_file, max_lines=3)
        lines = test_file.read_text().strip().splitlines()
        assert len(lines) == 3
        # Should keep the last 3 lines
        assert json.loads(lines[0])["i"] == 7
        assert json.loads(lines[2])["i"] == 9

    def test_preserves_trailing_newline(self, _patch_log_dir):
        import data.ops.cron_logger as mod
        test_file = _patch_log_dir / "trailing_test.jsonl"
        test_file.write_text("\n".join(f'{{"i":{i}}}' for i in range(10)) + "\n")
        mod._rotate_if_needed(test_file, max_lines=3)
        content = test_file.read_text()
        assert content.endswith("\n")


class TestCronRun:

    def test_logs_success_on_normal_exit(self, _patch_log_dir):
        import data.ops.cron_logger as mod
        with mod.cron_run("success_script"):
            pass  # normal exit
        log_file = _patch_log_dir / "success_script.jsonl"
        entry = json.loads(log_file.read_text().strip().splitlines()[0])
        assert entry["status"] == "ok"
        assert "elapsed_s" in entry

    def test_logs_error_and_re_raises(self, _patch_log_dir):
        import data.ops.cron_logger as mod
        with pytest.raises(ValueError, match="boom"):
            with mod.cron_run("fail_script"):
                raise ValueError("boom")
        log_file = _patch_log_dir / "fail_script.jsonl"
        entry = json.loads(log_file.read_text().strip().splitlines()[0])
        assert entry["status"] == "error"
        assert "boom" in entry["error"]
        assert "ValueError" in entry["traceback"]
