from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def risk_free_curve(tmp_path, monkeypatch):
    """Provide a synthetic risk-free curve for tests that exercise performance analytics."""
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("ASTROLABE_VAR", str(runtime))

    from data.storage.datahub import get_datahub, reset_datahub

    reset_datahub()
    curve_path = get_datahub().store_dir("bond") / "treasury_yields.parquet"
    curve_path.parent.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("1990-01-01", "2100-12-31", freq="7D")
    pd.DataFrame(
        {
            "日期": dates,
            "中国国债收益率2年": 2.0,
            "中国国债收益率5年": 2.2,
            "中国国债收益率10年": 2.5,
            "中国国债收益率30年": 3.0,
            "美国国债收益率2年": 3.5,
            "美国国债收益率5年": 3.7,
            "美国国债收益率10年": 4.0,
            "美国国债收益率30年": 4.2,
        }
    ).to_parquet(curve_path, index=False)
    yield curve_path
    reset_datahub()
