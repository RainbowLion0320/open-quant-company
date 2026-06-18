"""Contract tests for ConfigAuditLedger — record, query, summary."""

import pytest
from data.ops.audit import ConfigAuditLedger, ConfigAuditEntry


@pytest.fixture
def ledger():
    l = ConfigAuditLedger()
    l.clear()
    yield l
    l.clear()


class TestConfigAuditRecord:
    def test_record_returns_change_id(self, ledger):
        cid = ledger.record(section="risk_control", method="PATCH",
                            old_data={"max_pct": 0.25}, new_data={"max_pct": 0.30})
        assert cid.startswith("cfg_")
        assert len(cid) == 16  # cfg_ + 12 hex

    def test_record_detects_changed_keys(self, ledger):
        ledger.record(
            section="risk_control",
            old_data={"a": 1, "b": 2},
            new_data={"a": 1, "b": 3},
        )
        last = ledger.last_change()
        assert last is not None
        assert "b" in last.changed_keys
        assert "a" not in last.changed_keys

    def test_record_detects_added_keys(self, ledger):
        ledger.record(
            section="trading",
            old_data={"a": 1},
            new_data={"a": 1, "c": 42},
        )
        last = ledger.last_change()
        assert "c" in last.changed_keys

    def test_record_detects_removed_keys(self, ledger):
        ledger.record(
            section="trading",
            old_data={"a": 1, "b": 2},
            new_data={"a": 1},
        )
        last = ledger.last_change()
        assert "b" in last.changed_keys

    def test_record_captures_metadata(self, ledger):
        ledger.record(
            section="strategies",
            method="PUT",
            source_ip="192.168.1.1",
            user_agent="test-agent",
        )
        last = ledger.last_change()
        assert last.method == "PUT"
        assert last.source_ip == "192.168.1.1"
        assert last.user_agent == "test-agent"


class TestConfigAuditQueries:
    def test_history_returns_all(self, ledger):
        ledger.record(section="a", new_data={"x": 1})
        ledger.record(section="b", new_data={"y": 2})
        hist = ledger.history()
        assert len(hist) == 2

    def test_history_filtered_by_section(self, ledger):
        ledger.record(section="risk_control", new_data={"x": 1})
        ledger.record(section="trading", new_data={"y": 2})
        ledger.record(section="risk_control", new_data={"z": 3})

        hist = ledger.history(section="risk_control")
        assert len(hist) == 2
        assert all(e.section == "risk_control" for e in hist)

    def test_history_limit(self, ledger):
        for i in range(5):
            ledger.record(section=f"s{i}", new_data={"x": i})

        hist = ledger.history(limit=3)
        assert len(hist) == 3

    def test_history_empty_ledger(self, ledger):
        hist = ledger.history()
        assert hist == []

    def test_last_change_per_section(self, ledger):
        ledger.record(section="a", new_data={"v": 1})
        ledger.record(section="a", new_data={"v": 2})

        last = ledger.last_change(section="a")
        assert last is not None
        assert last.new_keys == ["v"]

    def test_last_change_nonexistent_section(self, ledger):
        last = ledger.last_change(section="nonexistent")
        assert last is None

    def test_summary_empty(self, ledger):
        s = ledger.summary()
        assert s["total_changes"] == 0

    def test_summary_with_entries(self, ledger):
        ledger.record(section="a", new_data={"x": 1})
        ledger.record(section="b", new_data={"y": 2})
        ledger.record(section="a", new_data={"z": 3})

        s = ledger.summary()
        assert s["total_changes"] == 3
        assert "a" in s["sections_touched"]
        assert "b" in s["sections_touched"]
        assert s["last_change_at"] is not None


class TestConfigAuditEntry:
    def test_to_row_and_from_row_roundtrip(self):
        entry = ConfigAuditEntry(
            change_id="cfg_test123456",
            timestamp="2024-05-22T10:00:00",
            section="risk_control",
            method="PATCH",
            old_keys=["max_pct", "enabled"],
            new_keys=["max_pct", "enabled"],
            changed_keys=["max_pct"],
            source_ip="127.0.0.1",
            user_agent="test/1.0",
        )
        row = entry.to_row()
        restored = ConfigAuditEntry.from_row(row)
        assert restored.change_id == entry.change_id
        assert restored.section == entry.section
        assert restored.changed_keys == ["max_pct"]
        assert "run" + "_mode" not in row
