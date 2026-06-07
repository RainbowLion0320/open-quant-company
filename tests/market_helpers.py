from __future__ import annotations

import pandas as pd


def market_index_frame(offset: float = 0) -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=4, freq="D"),
        "close": [100 + offset, 101 + offset, 102 + offset, 103 + offset],
    })


def fake_core_index_loader(symbol: str):
    frames = {
        "sh000300": market_index_frame(10),
        "sz399006": market_index_frame(20),
        "sh000688": market_index_frame(30),
    }
    return frames[symbol], "real", "test source"
