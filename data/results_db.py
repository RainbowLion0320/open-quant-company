"""
结果存储 — Parquet 主存储 + DuckDB 只读视图

设计理念:
  写: pd.DataFrame.to_parquet() → data/store/signals/{strategy}.parquet
  读: DuckDB 只读连接 → read_parquet() → SQL 查询 (零拷贝, 列存优化)

表结构 (Parquet 文件):
  signals/{strategy}.parquet  — 策略信号 (一文件一策略)
  scan_meta.parquet           — 扫描元数据 (KV)
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

import pandas as pd

from data.datahub import get_datahub
from data.db import get_db, reset_db

# ── Parquet 存储路径 ──
HUB = get_datahub()
STORE = HUB.store_dir()
SIGNALS_DIR = HUB.signals_dir()
SIGNALS_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now().isoformat()


# ── 初始化 ────────────────────────────────────────────────

def init():
    """确保存储目录存在 (幂等)"""
    for d in [SIGNALS_DIR, STORE / "equity", STORE / "financials"]:
        d.mkdir(parents=True, exist_ok=True)


# ── 写入 (Parquet, 无锁) ──────────────────────────────────

def save_buffett_results(results: List[dict]):
    """批量写入巴菲特结果 → Parquet (buffett_scan.parquet, 含财务详情)"""
    now = _now()
    rows = []
    for r in results:
        rows.append({
            "symbol": r["symbol"],
            "name": r["name"],
            "industry": r.get("industry", ""),
            "sector": r.get("sector", ""),
            "verdict": r.get("verdict", ""),
            "score": r.get("score", 0),
            "avg_roe_5y": r.get("roe", 0),
            "avg_gross_margin_5y": r.get("gross_margin") or 0,
            "avg_net_margin_5y": r.get("net_margin") or 0,
            "debt_equity_ratio": r.get("de", 0),
            "safety_margin_pct": r.get("safety_margin", 0),
            "dcf_value": r.get("dcf_value", 0),
            "current_price": r.get("current_price", 0),
            "updated_at": now,
        })

    pq_path = HUB.buffett_scan_path()
    df = pd.DataFrame(rows, columns=[
        "symbol", "name", "industry", "sector", "verdict", "score",
        "avg_roe_5y", "avg_gross_margin_5y", "avg_net_margin_5y",
        "debt_equity_ratio", "safety_margin_pct", "dcf_value",
        "current_price", "updated_at",
    ])
    HUB.write_parquet(df, pq_path)

    # 元数据
    _save_meta("buffett_scan", {
        "total": len(results),
        "passed": sum(1 for r in results if _is_pass(r)),
        "last_scan": now
    })

    reset_db()


def save_strategy_signals(strategy: str, signals: List[dict]):
    """批量写入策略信号 → Parquet"""
    now = _now()
    rows = []
    for s in signals:
        detail = s.get("detail", {})
        if isinstance(detail, dict):
            detail = json.dumps(detail, ensure_ascii=False)
        rows.append({
            "strategy": strategy,
            "symbol": s["symbol"],
            "name": s.get("name", s["symbol"]),
            "industry": s.get("industry", ""),
            "score": s.get("score", 0),
            "signal": s.get("signal", "hold"),
            "detail": str(detail),
            "computed_at": now,
        })

    pq_path = HUB.signal_path(strategy)
    df = pd.DataFrame(rows, columns=[
        "strategy", "symbol", "name", "industry", "score",
        "signal", "detail", "computed_at",
    ])
    HUB.write_parquet(df, pq_path)

    # 元数据
    _save_meta(f"strategy_{strategy}", {"total": len(signals), "buys": sum(1 for s in signals if s.get("signal") == "buy"), "last_computed": now})

    reset_db()


# ── 读取 (DuckDB → Parquet 视图) ─────────────────────────

def _load_parquet_view(view_name: str) -> List[dict]:
    """通用: 从 Parquet 视图读取全部数据"""
    db = get_db(read_only=True)
    try:
        rows = db.fetchall(f"SELECT * FROM {view_name}")
        return [_row_to_dict(r) for r in rows]
    except Exception:
        return []


def load_buffett_results(sort: str = "score", order: str = "desc", limit: int = 0) -> List[dict]:
    """加载巴菲特结果 (从 Parquet 视图)"""
    db = get_db(read_only=True)
    valid_sorts = {"score", "symbol", "name", "safety_margin_pct", "avg_roe_5y"}
    if sort not in valid_sorts:
        sort = "score"
    order = "asc" if str(order).lower() == "asc" else "desc"
    sql = f"SELECT * FROM buffett_scan ORDER BY {sort} {order.upper()}"
    if limit:
        sql += f" LIMIT {limit}"
    try:
        rows = db.fetchall(sql)
        return [_row_to_dict(r) for r in rows]
    except Exception:
        return []


def get_buffett_meta() -> dict:
    """获取扫描元数据 (从 Parquet 视图)"""
    db = get_db(read_only=True)
    try:
        rows = db.fetchall("SELECT key, value FROM scan_meta WHERE key = 'buffett_scan'")
        if rows:
            val = rows[0]["value"]
            return json.loads(val) if isinstance(val, str) else val
    except Exception:
        pass
    return {"total": 0, "passed": 0, "last_scan": ""}


def load_strategy_signals(strategy: str, sort: str = "score", order: str = "desc", limit: int = 0) -> List[dict]:
    """加载某策略的全部信号"""
    db = get_db(read_only=True)
    view = f"{strategy}_signals"
    valid_sorts = {"score", "symbol", "name", "computed_at"}
    if sort not in valid_sorts:
        sort = "score"
    order = "asc" if str(order).lower() == "asc" else "desc"
    sql = f"SELECT * FROM {view} ORDER BY {sort} {order.upper()}"
    if limit:
        sql += f" LIMIT {int(limit)}"
    try:
        rows = db.fetchall(sql)
        return [_row_to_dict(r) for r in rows]
    except Exception:
        return []


def list_strategies() -> List[dict]:
    """扫描 Parquet 文件, 列出所有策略及统计"""
    from data.registry import get_enabled_strategies, get_strategy_label
    registry = {s["name"]: s for s in get_enabled_strategies()}

    strategies = []
    for pq in HUB.list_parquet(SIGNALS_DIR):
        name = pq.stem
        if name not in registry:
            continue

        label = get_strategy_label(name)
        db = get_db(read_only=True)
        try:
            rows = db.fetchall(f"SELECT signal, COUNT(*) as cnt FROM {name}_signals GROUP BY signal")
            total = sum(r["cnt"] for r in rows)
            buys = sum(r["cnt"] for r in rows if r["signal"] == "buy")
            computed = ""
            try:
                meta_rows = db.fetchall(f"SELECT computed_at FROM {name}_signals ORDER BY computed_at DESC LIMIT 1")
                computed = meta_rows[0]["computed_at"] if meta_rows else ""
            except Exception:
                pass
        except Exception:
            total = 0
            buys = 0
            computed = ""

        strategies.append({"name": name, "label": label, "total": total, "buys": buys, "last_computed": computed})

    return strategies


# ── 辅助 ──────────────────────────────────────────────────

def _save_meta(key: str, data: dict):
    """写入元数据到 scan_meta.parquet"""
    meta_path = HUB.scan_meta_path()
    now = _now()
    new_row = pd.DataFrame([{"key": key, "value": json.dumps(data, ensure_ascii=False), "updated_at": now}])

    if meta_path.exists():
        existing = HUB.read_parquet(meta_path, default=pd.DataFrame())
        existing = existing[existing["key"] != key]
        merged = pd.concat([existing, new_row], ignore_index=True)
    else:
        merged = new_row

    HUB.write_parquet(merged, meta_path)


def _to_signal(r: dict) -> str:
    verdict = r.get("verdict", "")
    return "buy" if ("通过" in verdict or "✅" in verdict) else "hold"


def _is_pass(r: dict) -> bool:
    return _to_signal(r) == "buy"


def _row_to_dict(row) -> dict:
    """将 DuckDB Column 或普通 dict 转为 dict"""
    if hasattr(row, "keys"):
        return {k: row[k] for k in row.keys()}
    if isinstance(row, dict):
        return row
    if isinstance(row, tuple):
        return {"value": row[0]}
    return {"value": row}


# ── 兼容旧接口 ────────────────────────────────────────────

def create_cache_views():
    """已将 cache parquet 的映射整合进 db._register_views(), 此函数保留空壳兼容"""
    pass
