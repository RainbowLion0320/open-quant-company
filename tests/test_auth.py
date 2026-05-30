"""Contract tests for API auth middleware and run mode enforcement."""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from starlette.testclient import TestClient


# ── Test app factory ──

@pytest.fixture
def app():
    """Create a fresh FastAPI app with auth middleware for testing."""
    import yaml
    import tempfile

    # Write a temp settings.yaml with a known API key
    tmpdir = tempfile.mkdtemp()
    config_dir = Path(tmpdir) / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "settings.yaml"

    test_config = {
        "project": {
            "name": "test",
            "version": "1.0.0",
            "run_mode": "research",
            "api_key": "test-secret-key",
        },
        "strategies": {},
        "risk_control": {},
    }
    with open(config_file, "w") as f:
        yaml.dump(test_config, f)

    # Patch the settings path used by auth.py
    with patch("web.api.auth._settings_path", return_value=config_file), \
         patch("web.api.routes.settings._config_path", return_value=str(config_file)):
        from web.api.app import create_app
        app = create_app()
        yield app

    # Cleanup
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def client(app):
    return TestClient(app)


class TestAuthMiddleware:
    def test_health_is_public(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_spa_fallback_is_public(self, client):
        resp = client.get("/")
        # SPA fallback serves index.html or 404; both are OK (not 401/403)
        assert resp.status_code not in (401, 403)

    def test_api_without_key_returns_401(self, client):
        resp = client.get("/api/settings")
        assert resp.status_code == 401

    def test_api_with_wrong_key_returns_403(self, client):
        resp = client.get("/api/settings", headers={"Authorization": "Bearer wrong-key"})
        assert resp.status_code == 403

    def test_api_with_correct_key_returns_200(self, client):
        resp = client.get("/api/settings", headers={"Authorization": "Bearer test-secret-key"})
        assert resp.status_code == 200
        data = resp.json()
        assert "config" in data

    def test_api_without_bearer_prefix(self, client):
        resp = client.get("/api/settings", headers={"Authorization": "test-secret-key"})
        assert resp.status_code == 200  # raw token also accepted

    def test_protected_route_with_auth(self, client):
        """Test that a PATCH to settings with auth works."""
        resp = client.patch(
            "/api/settings/section/risk_control",
            json={"max_pct": 0.5},
            headers={"Authorization": "Bearer test-secret-key"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"

    def test_cors_preflight_is_not_blocked_by_auth(self, client):
        resp = client.options(
            "/api/settings",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code in (200, 204)

    def test_dotted_section_patch_updates_nested_config_without_top_level_duplicate(self, tmp_path):
        """Config Center PATCH for dotted sections must preserve canonical nested YAML."""
        import yaml

        config_file = tmp_path / "settings.yaml"
        config_file.write_text(
            yaml.safe_dump({
                "project": {"name": "test", "run_mode": "research", "api_key": "test-secret-key"},
                "strategies": {},
                "risk_control": {},
                "data": {"fetcher": {"min_interval": 3.0, "max_retries": 3}},
            }, allow_unicode=True),
            encoding="utf-8",
        )

        with patch("web.api.auth._settings_path", return_value=config_file), \
             patch("web.api.routes.settings._config_path", return_value=str(config_file)):
            from web.api.app import create_app
            client = TestClient(create_app())

            resp = client.patch(
                "/api/settings/section/data.fetcher",
                json={"min_interval": 4.5, "max_retries": 4},
                headers={"Authorization": "Bearer test-secret-key"},
            )

        assert resp.status_code == 200
        saved = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert saved["data"]["fetcher"]["min_interval"] == 4.5
        assert saved["data"]["fetcher"]["max_retries"] == 4
        assert "data.fetcher" not in saved


class TestRunModeEnforcement:
    @pytest.fixture
    def config_with_mode(self):
        """Return a fresh app with a specific run mode."""
        import yaml
        import tempfile

        tmpdir = tempfile.mkdtemp()
        config_dir = Path(tmpdir) / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "settings.yaml"

        def _make_app(run_mode: str):
            test_config = {
                "project": {
                    "name": "test",
                    "version": "1.0.0",
                    "run_mode": run_mode,
                    "api_key": "test-key",
                },
                "strategies": {},
                "risk_control": {},
                "paper_trading": {},
            }
            with open(config_file, "w") as f:
                yaml.dump(test_config, f)
            return config_file

        yield _make_app, config_file

        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_live_mode_blocks_put(self, config_with_mode):
        make_app, config_file = config_with_mode
        config_path = make_app("live")

        with patch("web.api.auth._settings_path", return_value=config_path), \
             patch("web.api.routes.settings._config_path", return_value=str(config_path)):
            from web.api.app import create_app
            app = create_app()
            client = TestClient(app)

            resp = client.put(
                "/api/settings",
                json={"strategies": {}, "risk_control": {}, "extra": {}},
                headers={"Authorization": "Bearer test-key"},
            )
            assert resp.status_code == 403

    def test_paper_mode_blocks_non_paper_section(self, config_with_mode):
        make_app, config_file = config_with_mode
        config_path = make_app("paper")

        with patch("web.api.auth._settings_path", return_value=config_path), \
             patch("web.api.routes.settings._config_path", return_value=str(config_path)):
            from web.api.app import create_app
            app = create_app()
            client = TestClient(app)

            resp = client.patch(
                "/api/settings/section/risk_control",
                json={"max_pct": 0.5},
                headers={"Authorization": "Bearer test-key"},
            )
            assert resp.status_code == 403

    def test_paper_mode_allows_paper_trading_section(self, config_with_mode):
        make_app, config_file = config_with_mode
        config_path = make_app("paper")

        with patch("web.api.auth._settings_path", return_value=config_path), \
             patch("web.api.routes.settings._config_path", return_value=str(config_path)):
            from web.api.app import create_app
            app = create_app()
            client = TestClient(app)

            resp = client.patch(
                "/api/settings/section/paper_trading",
                json={"auto_execute": True},
                headers={"Authorization": "Bearer test-key"},
            )
            assert resp.status_code == 200

    def test_research_mode_allows_all(self, config_with_mode):
        make_app, config_file = config_with_mode
        config_path = make_app("research")

        with patch("web.api.auth._settings_path", return_value=config_path), \
             patch("web.api.routes.settings._config_path", return_value=str(config_path)):
            from web.api.app import create_app
            app = create_app()
            client = TestClient(app)

            resp = client.patch(
                "/api/settings/section/risk_control",
                json={"max_pct": 0.5},
                headers={"Authorization": "Bearer test-key"},
            )
            assert resp.status_code == 200


class TestAuditOnSettingsWrite:
    @pytest.fixture
    def research_app(self):
        import yaml
        import tempfile

        tmpdir = tempfile.mkdtemp()
        config_dir = Path(tmpdir) / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "settings.yaml"

        test_config = {
            "project": {
                "name": "test",
                "version": "1.0.0",
                "run_mode": "research",
                "api_key": "test-key",
            },
            "strategies": {"test_strategy": {"enabled": True}},
            "risk_control": {"max_pct": 0.25},
        }
        with open(config_file, "w") as f:
            yaml.dump(test_config, f)

        # Need to patch both auth and settings path
        with patch("web.api.auth._settings_path", return_value=config_file), \
             patch("web.api.routes.settings._config_path", return_value=str(config_file)):
            from web.api.app import create_app
            app = create_app()
            yield TestClient(app), config_file

        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_patch_creates_audit_entry(self, research_app):
        client, _ = research_app

        from data.audit import ConfigAuditLedger
        ledger = ConfigAuditLedger()
        ledger.clear()

        try:
            resp = client.patch(
                "/api/settings/section/risk_control",
                json={"max_pct": 0.30},
                headers={"Authorization": "Bearer test-key"},
            )
            assert resp.status_code == 200

            hist = ledger.history(section="risk_control")
            assert len(hist) >= 1
            assert "max_pct" in hist[0].changed_keys
        finally:
            ledger.clear()

    def test_system_mode_endpoint(self, research_app):
        client, _ = research_app

        resp = client.get(
            "/api/system/mode",
            headers={"Authorization": "Bearer test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "research"
        assert data["has_api_key"] is True
        assert data["allows_settings_write"] is True

    def test_audit_endpoint(self, research_app):
        client, _ = research_app

        from data.audit import ConfigAuditLedger
        ledger = ConfigAuditLedger()
        ledger.clear()

        try:
            ledger.record(section="test", new_data={"x": 1})

            resp = client.get(
                "/api/system/audit",
                headers={"Authorization": "Bearer test-key"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] >= 1
            assert data["entries"][0]["section"] == "test"
        finally:
            ledger.clear()


class TestAuthHelpers:
    def test_no_api_key_does_not_autogenerate_or_block(self, tmp_path):
        import yaml

        cfg_path = tmp_path / "settings.yaml"
        cfg = {"project": {"name": "test", "run_mode": "research"}, "strategies": {}, "risk_control": {}}
        cfg_path.write_text(yaml.dump(cfg), encoding="utf-8")

        with patch("web.api.auth._settings_path", return_value=cfg_path), \
             patch("web.api.routes.settings._config_path", return_value=str(cfg_path)):
            from web.api.auth import get_api_key
            from web.api.app import create_app

            assert get_api_key() == ""
            client = TestClient(create_app())
            resp = client.get("/api/settings")
            assert resp.status_code == 200

        saved = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        assert "api_key" not in saved["project"]

    def test_api_key_can_come_from_astrolabe_env(self, monkeypatch):
        monkeypatch.setenv("ASTROLABE_API_KEY", "env-secret")
        from web.api.auth import get_api_key

        assert get_api_key() == "env-secret"

    def test_renamed_project_env_aliases_are_not_read(self, monkeypatch):
        old_quant_env = "QUANT" + "_AGENT_API_KEY"
        old_chinese_name_env = "XING" + "PAN_API_KEY"
        monkeypatch.setenv(old_quant_env, "old-secret")
        monkeypatch.setenv(old_chinese_name_env, "old-secret")
        monkeypatch.delenv("ASTROLABE_API_KEY", raising=False)
        from web.api.auth import get_api_key

        with patch("web.api.auth._read_settings", return_value={"project": {}}):
            assert get_api_key() == ""

    def test_get_run_mode_default(self):
        """get_run_mode returns 'research' when no config."""
        with patch("web.api.auth._read_settings", return_value={}):
            from web.api.auth import get_run_mode
            assert get_run_mode() == "research"

    def test_is_readonly_mode(self):
        with patch("web.api.auth.get_run_mode", return_value="live"):
            from web.api.auth import is_readonly_mode
            assert is_readonly_mode() is True

        with patch("web.api.auth.get_run_mode", return_value="research"):
            from web.api.auth import is_readonly_mode
            assert is_readonly_mode() is False
