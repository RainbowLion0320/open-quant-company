"""
Crypto Asset Adapter — real spot snapshot data for multi-asset coverage.

The current implementation uses AKShare `crypto_js_spot`, which returns a
latest-market snapshot rather than a full historical OHLCV series. We normalize
that snapshot into one daily row so the asset can participate in coverage and
research-readiness checks without inventing historical bars.

Full historical K-line support should be added through a contracted exchange
or CCXT data adapter before crypto is used for backtests that require history.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from data.market.assets.base import AssetAdapter


CRYPTO_UNIVERSE = [
    "BTC/USDT",  # Bitcoin
    "ETH/USDT",  # Ethereum
    "BNB/USDT",  # BNB
    "SOL/USDT",  # Solana
    "XRP/USDT",  # Ripple
]

CRYPTO_NAMES = {
    "BTC/USDT": "Bitcoin",
    "ETH/USDT": "Ethereum",
    "BNB/USDT": "BNB",
    "SOL/USDT": "Solana",
    "XRP/USDT": "XRP",
}


def _first_existing(row: pd.Series, *names: str):
    for name in names:
        if name in row and pd.notna(row[name]):
            return row[name]
    return None


def _to_float(value, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        if isinstance(value, str):
            value = value.replace(",", "").replace("%", "").strip()
        return float(value)
    except Exception:
        return default


def _symbol_candidates(symbol: str) -> list[str]:
    compact = symbol.replace("/", "").upper()
    base = compact
    quote = ""
    for suffix in ("USDT", "USD", "CNY", "JPY", "EUR"):
        if compact.endswith(suffix):
            base = compact[: -len(suffix)]
            quote = suffix
            break

    candidates = [compact]
    if quote == "USDT":
        candidates.append(f"{base}USD")
    if base:
        candidates.append(base)
    return list(dict.fromkeys(candidates))


class CryptoAsset(AssetAdapter):
    """Crypto asset adapter backed by AKShare latest spot quotes."""

    asset_type: str = "crypto"
    label: str = "加密货币"
    description: str = "BTC/ETH 等主流币种现货行情快照"
    DATA_SOURCE: str = "real"
    DATA_SOURCE_DETAIL: str = (
        "AKShare crypto_js_spot latest spot snapshot normalized to one daily row; "
        "historical K-line adapter not integrated"
    )
    TRADING_CALENDAR: str = "24x7"
    CURRENCY: str = "USDT"
    TRADABLE: bool = False
    RESEARCH_READY: bool = True

    def __init__(self, store_root: Path | str | None = None):
        super().__init__(store_root)
        self._universe = list(CRYPTO_UNIVERSE)

    def fetch_daily(
        self,
        symbol: str,
        start_date: str = "20180101",
        end_date: str = "",
    ) -> Optional[pd.DataFrame]:
        """Fetch the latest spot quote and normalize it to one daily OHLCV row."""
        try:
            import akshare as ak

            spot = ak.crypto_js_spot()
        except Exception:
            return None

        if spot is None or spot.empty:
            return None

        row = self._match_spot_row(spot, symbol)
        if row is None:
            return None

        close = _to_float(_first_existing(row, "最近报价", "price", "close", "last"))
        if close <= 0:
            return None

        change = _to_float(_first_existing(row, "涨跌额", "change"), 0.0)
        open_price = _to_float(_first_existing(row, "open", "开盘"), close - change)
        high = _to_float(_first_existing(row, "24小时最高", "high"), close)
        low = _to_float(_first_existing(row, "24小时最低", "low"), close)
        volume = _to_float(_first_existing(row, "24小时成交量", "volume", "vol"), 0.0)
        timestamp = _first_existing(row, "更新时间", "date", "time", "timestamp")
        date = pd.to_datetime(timestamp, errors="coerce")
        if pd.isna(date):
            date = pd.Timestamp.now(tz=None)

        result = pd.DataFrame({
            "date": [date.strftime("%Y-%m-%d")],
            "open": [open_price],
            "high": [high],
            "low": [low],
            "close": [close],
            "volume": [volume],
        })
        return result

    def _match_spot_row(self, spot: pd.DataFrame, symbol: str) -> Optional[pd.Series]:
        candidates = _symbol_candidates(symbol)
        text_columns = [col for col in ("交易品种", "symbol", "name", "pair") if col in spot.columns]
        for col in text_columns:
            values = spot[col].astype(str).str.upper().str.replace("/", "", regex=False)
            for candidate in candidates:
                exact = spot[values == candidate]
                if not exact.empty:
                    return exact.iloc[0]
            for candidate in candidates:
                contains = spot[values.str.contains(candidate, regex=False, na=False)]
                if not contains.empty:
                    return contains.iloc[0]
        return None

    def get_universe(self) -> List[str]:
        return self._universe

    def get_metadata(self, symbol: str) -> Dict:
        return {
            "name": CRYPTO_NAMES.get(symbol, symbol),
            "industry": "crypto",
            "sector": "crypto",
            "asset_type": "crypto",
            "currency": self.CURRENCY,
        }

    def __repr__(self) -> str:
        return f"<CryptoAsset: {len(self._universe)} pairs>"
