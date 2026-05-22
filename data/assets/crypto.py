"""
Crypto Asset Adapter — 多资产第五实现 (占位框架)

长期方案:
  - CCXT 统一接口 (Binance/OKX 现货 + 永续)
  - 因子: funding rate, open interest, whale flow
  - 24/7 交易, 无涨跌停

当前: 占位——AssetAdapter 接口已实现, 等待接入 CCXT。
启用时修改 config/settings.yaml: assets.crypto.enabled = true
"""
from typing import Dict, List, Optional
import pandas as pd
from pathlib import Path

from data.assets.base import AssetAdapter


CRYPTO_UNIVERSE = [
    "BTC/USDT",  # 比特币
    "ETH/USDT",  # 以太坊
    "BNB/USDT",  # BNB
    "SOL/USDT",  # Solana
    "XRP/USDT",  # Ripple
]


class CryptoAsset(AssetAdapter):
    """Crypto asset adapter — placeholder for CCXT integration."""

    asset_type: str = "crypto"
    label: str = "加密货币"
    description: str = "BTC/ETH现货 (CCXT接入, 待实现)"
    DATA_SOURCE: str = "placeholder"
    DATA_SOURCE_DETAIL: str = "CCXT integration pending; fetch_daily returns None"
    TRADING_CALENDAR: str = "24x7"
    CURRENCY: str = "USDT"

    def __init__(self, store_root: Path):
        super().__init__(store_root)
        self._universe = list(CRYPTO_UNIVERSE)

    def fetch_daily(
        self, symbol: str, start_date: str = "20180101", end_date: str = "",
    ) -> Optional[pd.DataFrame]:
        """[PLACEHOLDER] Real data requires CCXT: pip install ccxt"""
        return None

    def get_universe(self) -> List[str]:
        return self._universe

    def get_metadata(self, symbol: str) -> Dict:
        return {
            "name": symbol, "industry": "crypto",
            "sector": "crypto", "asset_type": "crypto",
        }

    def __repr__(self) -> str:
        return f"<CryptoAsset: {len(self._universe)} pairs (placeholder)>"
