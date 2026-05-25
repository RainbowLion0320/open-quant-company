from pathlib import Path

import pandas as pd


def test_settings_loader_supports_project_root_env_and_dotted_sections(tmp_path, monkeypatch):
    root = tmp_path / "project"
    cfg_dir = root / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "settings.yaml").write_text(
        """
project:
  name: test-project
data:
  tushare:
    token: file-token
signals:
  multifactor:
    buy_threshold: 60
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("ASTROLABE_HOME", str(root))
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("TUSHARE_PRO_TOKEN", raising=False)

    from core.settings import get_section, get_settings, get_tushare_token, resolve_settings_path

    assert resolve_settings_path() == cfg_dir / "settings.yaml"
    assert get_settings(refresh=True)["project"]["name"] == "test-project"
    assert get_section("signals.multifactor") == {"buy_threshold": 60}
    assert get_tushare_token() == "file-token"

    monkeypatch.setenv("TUSHARE_TOKEN", "env-token")
    assert get_tushare_token() == "env-token"


def test_symbol_helpers_normalize_a_share_codes_and_exchange_formats():
    from data.symbols import normalize_symbol, to_sina_symbol, to_ts_code

    assert normalize_symbol("SH600519") == "600519"
    assert normalize_symbol("000001.SZ") == "000001"
    assert normalize_symbol("688001") == "688001"
    assert to_sina_symbol("600519.SH") == "sh600519"
    assert to_sina_symbol("000001") == "sz000001"
    assert to_ts_code("600519") == "600519.SH"
    assert to_ts_code("000001") == "000001.SZ"


def test_fetcher_base_rate_limiter_uses_configurable_jitter(monkeypatch):
    calls: list[float] = []

    monkeypatch.setattr("data.fetchers.base.time.sleep", lambda seconds: calls.append(seconds))
    monkeypatch.setattr("data.fetchers.base.random.uniform", lambda low, high: 0.25)

    from data.fetchers.base import RateLimiter

    RateLimiter(base_seconds=1.0, jitter_seconds=0.5).sleep()
    assert calls == [1.25]


def test_api_serializer_converts_nan_and_time_series_consistently():
    from web.api.serializers import date_value_series, safe_float, safe_int

    assert safe_float(float("nan"), default=-1.0) == -1.0
    assert safe_int(None, default=7) == 7

    df = pd.DataFrame(
        {
            "date": ["2026-05-20", "bad-date", "2026-05-21"],
            "close": [1.23456, 999.0, 2.34567],
        }
    )
    assert date_value_series(df, "close", limit=5) == [
        {"date": "2026-05-20", "value": 1.2346},
        {"date": "2026-05-21", "value": 2.3457},
    ]


def test_snapshot_finder_prefers_registry_path_with_legacy_fallback(tmp_path):
    from web.api.services.snapshots import latest_snapshot

    registry_root = tmp_path / "registry"
    legacy_root = tmp_path / "legacy"
    registry_root.mkdir()
    legacy_root.mkdir()
    old = registry_root / "2026-05-20.parquet"
    new = registry_root / "2026-05-22.parquet"
    legacy = legacy_root / "sector_performance_20260521.parquet"
    for path in [old, new, legacy]:
        path.touch()

    assert latest_snapshot(registry_root=registry_root, legacy_root=legacy_root, legacy_prefix="sector_performance_") == new

    for path in [old, new]:
        path.unlink()
    assert latest_snapshot(registry_root=registry_root, legacy_root=legacy_root, legacy_prefix="sector_performance_") == legacy

    assert latest_snapshot(
        registry_root=Path("/does/not/exist"),
        legacy_root=Path("/does/not/exist"),
        legacy_prefix="missing_",
    ) is None


def test_buffett_score_estimator_is_shared_and_bounded():
    from signals.scoring import estimate_buffett_score

    assert estimate_buffett_score({"roe_history": [0.12, 0.14, 0.16]}) == 70.0
    assert estimate_buffett_score({"roe_history": [0.5, 0.6, 0.7, 0.8, 0.9]}) == 100.0
    assert estimate_buffett_score({"roe_history": []}) == 0.0
