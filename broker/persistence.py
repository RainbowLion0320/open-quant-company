"""
PaperBroker 状态持久化 — Parquet 存储

将所有 PaperBroker 内部状态持久化到 var/store/paper/:
  - state.parquet     → 资金 + 持仓 (覆盖写入)
  - nav.parquet       → 每日净值快照 (追加)
  - trades.parquet    → 交易记录 (追加)

服务器重启后恢复状态，不丢持仓。

用法:
  from broker.persistence import load_state, save_state, append_nav, append_trade
  state = load_state()       # 恢复 PaperBroker
  ... 执行交易 ...
  save_state(broker)         # 落盘
  append_nav(date, broker)   # 记录净值
"""

from __future__ import annotations
import pandas as pd
from pathlib import Path
from datetime import date as DateType, datetime
from typing import Optional

from broker.state import PaperBrokerState
from core.settings import get_section
from data.storage.datahub import get_datahub

# ── 默认路径 (可在 settings.yaml 覆盖) ──
HUB = get_datahub()
STORE_DIR = HUB.paper_dir()


def _resolve_store() -> Path:
    """读取 config/settings.yaml 的 paper_trading.store_dir, 兜底为默认"""
    try:
        pt = get_section("paper_trading", {}) or {}
        custom = pt.get("store_dir")
        if custom:
            path = HUB.resolve_path(custom)
            path.mkdir(parents=True, exist_ok=True)
            return path
    except Exception:
        pass
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    return STORE_DIR


PaperState = PaperBrokerState


def load_state() -> PaperState:
    """从 Parquet 恢复状态。首次返回空白状态。"""
    store = _resolve_store()
    state_file = store / "state.parquet"
    if not state_file.exists():
        return PaperState()

    try:
        df = HUB.read_parquet(state_file)
        if df is None or df.empty:
            return PaperState()
        row = df.iloc[0].to_dict()

        # 持仓是嵌套 dict, parquet 存为 JSON 字符串
        positions_raw = row.get("positions", {})
        if isinstance(positions_raw, str):
            import json
            positions_raw = json.loads(positions_raw)

        return PaperState(
            cash=float(row.get("cash", 1_000_000)),
            frozen_cash=float(row.get("frozen_cash", 0)),
            peak_equity=float(row.get("peak_equity", 1_000_000)),
            positions={str(k): {
                "volume": int(v.get("volume", 0)),
                "avg_cost": float(v.get("avg_cost", 0)),
                "name": str(v.get("name", "")),
                "current_price": float(v.get("current_price", 0)),
            } for k, v in positions_raw.items()} if positions_raw else {},
            order_counter=int(row.get("order_counter", 0)),
            updated_at=str(row.get("updated_at", "")),
        )
    except Exception:
        return PaperState()


def save_state(state: PaperState):
    """将状态写入 state.parquet (覆盖)"""
    import json
    store = _resolve_store()
    store.mkdir(parents=True, exist_ok=True)
    state.updated_at = datetime.now().isoformat()

    df = pd.DataFrame([{
        "cash": state.cash,
        "frozen_cash": state.frozen_cash,
        "peak_equity": state.peak_equity,
        "positions": json.dumps(state.positions, ensure_ascii=False),
        "order_counter": state.order_counter,
        "updated_at": state.updated_at,
    }])
    HUB.write_parquet(df, store / "state.parquet")


# ── NAV 快照 ──

def append_nav(run_date: DateType, total_asset: float, cash: float, market_value: float):
    """追加一条每日净值快照"""
    store = _resolve_store()
    store.mkdir(parents=True, exist_ok=True)
    nav_file = store / "nav.parquet"

    row = pd.DataFrame([{
        "date": pd.Timestamp(run_date),
        "total_asset": total_asset,
        "cash": cash,
        "market_value": market_value,
    }])

    # fcntl-locked append with date dedup for concurrent safety
    HUB.append_parquet(nav_file, row, dedupe_subset=["date"])


def load_nav() -> pd.DataFrame:
    """加载 NAV 历史"""
    nav_file = _resolve_store() / "nav.parquet"
    if not nav_file.exists():
        return pd.DataFrame(columns=["date", "total_asset", "cash", "market_value"])
    return HUB.read_parquet(nav_file, default=pd.DataFrame(columns=["date", "total_asset", "cash", "market_value"]))


# ── 交易记录 ──

def append_trade(run_date: DateType, code: str, side: str, price: float,
                 volume: int, amount: float, strategy: str = ""):
    """追加一条交易记录"""
    store = _resolve_store()
    store.mkdir(parents=True, exist_ok=True)
    trade_file = store / "trades.parquet"

    row = pd.DataFrame([{
        "date": pd.Timestamp(run_date),
        "code": code,
        "name": "",
        "side": side,
        "price": price,
        "volume": volume,
        "amount": amount,
        "strategy": strategy,
    }])

    if trade_file.exists():
        existing = HUB.read_parquet(trade_file, default=pd.DataFrame())
        df = pd.concat([existing, row], ignore_index=True)
    else:
        df = row
    HUB.write_parquet(df, trade_file)


def load_trades() -> pd.DataFrame:
    """加载交易历史"""
    trade_file = _resolve_store() / "trades.parquet"
    if not trade_file.exists():
        return pd.DataFrame(columns=["date", "code", "name", "side", "price", "volume", "amount", "strategy"])
    return HUB.read_parquet(trade_file, default=pd.DataFrame(columns=["date", "code", "name", "side", "price", "volume", "amount", "strategy"]))


def load_today_trades(run_date: Optional[DateType] = None) -> pd.DataFrame:
    """加载指定日期的交易"""
    df = load_trades()
    if df.empty:
        return df
    if run_date is None:
        run_date = DateType.today()
    target = pd.Timestamp(run_date)
    return df[df["date"] == target]
