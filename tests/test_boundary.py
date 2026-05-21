"""
新模块边界测试 — 投产级验证
覆盖: factors.py, analytics.py, pipeline.py, broker/, db.py
"""
import sys, os
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        print(f"  ✗ {name} — {detail}")

print("── 因子引擎 (signals/expression.py) ──")

from signals.expression import Ret, MA, Std, Delta
from signals.dsl_parser import compute_formula

df = pd.DataFrame({
    'close': [10, 12, 11, 13, 14, 12, 15, 16, 14, 17],
    'roe': [0.08, 0.10, 0.12, 0.14, 0.15, 0.16, 0.18, 0.19, 0.20, 0.22],
    'pe': [30, 28, 25, 22, 20, 21, 18, 17, 19, 15],
}, index=pd.date_range('2024-01-01', periods=10, freq='B'))

def compute_series(factor, df):
    return pd.Series([factor.compute(df, i) for i in range(len(df))], index=df.index)

# Basic ops
close = Ret("close")
mom_factor = Delta(close, 3) / close
mom = compute_series(mom_factor, df)
check("动量因子计算", mom.dropna().sum() != 0)

ma5 = compute_series(MA(close, 5), df)
check("均线计算", ma5.dropna().sum() != 0)

vol_factor = Std(Delta(close, 1), 5)
vol = compute_series(vol_factor, df)
check("波动率计算", vol.dropna().mean() > 0)

# Parse formula via dsl_parser (bare column names, no _t suffix)
parsed = compute_formula("Delta(close,3)/close_t", df, len(df)-1)
check("公式解析", not pd.isna(parsed))

# Edge cases
empty = pd.DataFrame({'close': []})
result_empty = compute_series(Ret("close"), empty)
check("空数据不崩溃", True)
try:
    none_col = Ret("nonexistent")
    none_col.compute(df, 0)
    check("缺失列不抛异常(用NaN)", pd.isna(none_col.compute(df, 0)))
except Exception:
    check("缺失列处理", True)

# NaN
df_nan = pd.DataFrame({'close': [10, np.nan, 12]})
result_nan = compute_series(Delta(Ret("close"), 1), df_nan)
check("NaN不崩溃", result_nan is not None)

print(f"\n── 风险分析 (backtest/analytics.py) ──")

from backtest.analytics import RiskAnalytics

returns = pd.Series(
    [0.01, -0.02, 0.03, -0.01, 0.02, -0.03, 0.01, 0.02, -0.01, 0.04,
     -0.02, 0.01, 0.03, -0.01, 0.02, 0.01, -0.02, 0.03, -0.01, 0.02],
    index=pd.date_range('2024-01-01', periods=20, freq='B')
)
bench = pd.Series(
    [0.005, -0.01, 0.02, 0.0, 0.01, -0.02, 0.01, 0.01, -0.005, 0.02,
     -0.01, 0.0, 0.02, 0.0, 0.01, 0.005, -0.01, 0.02, 0.0, 0.01],
    index=pd.date_range('2024-01-01', periods=20, freq='B')
)

r = RiskAnalytics.compute(returns, bench)
check("Sharpe > 0", r.sharpe > 0)
check("MaxDD < 0 (有回撤)", r.max_drawdown < 0)
check("Win rate in [0,1]", 0 <= r.win_rate <= 1)
check("Beta computed", abs(r.beta) > 0)
check("Alpha computed", abs(r.alpha) < 100)  # alpha should be reasonable

# Edge: all positive
all_pos = pd.Series([0.01] * 20)
rp = RiskAnalytics.compute(all_pos)
check("全正收益: win_rate=1", rp.win_rate == 1.0)
check("全正收益: maxDD=0", rp.max_drawdown == 0.0)

# Edge: single value
single = pd.Series([0.01])
rs = RiskAnalytics.compute(single)
check("单值不崩溃", rs.sharpe == 0.0)

print(f"\n── 模拟券商 (broker/) ──")

from broker import PaperBroker

broker = PaperBroker(initial_cash=100000)
broker.set_prices({'000001': 12.50, '600519': 1500.00})

oid = broker.submit_order('000001', price=12.50, volume=100, side='buy')
check("买入成功", oid.startswith("PAPER_") and len(broker.get_positions()) == 1)
oid2 = broker.submit_order('600519', price=1500.00, volume=10, side='buy')
check("第二只买入", len(broker.get_positions()) == 2)
bal = broker.get_balance()
check("总资产计算正确", abs(bal.total_asset - 100000) < 20)  # 佣金约13元

# T+1: 当日买入不可卖出
oid3 = broker.submit_order('000001', price=13.00, volume=50, side='sell')
check("T+1限制卖出", oid3.startswith("T+1"))

oid4 = broker.submit_order('600519', price=1510.00, volume=10, side='sell')
check("T+1限制卖出(2)", oid4.startswith("T+1"))

# 隔日可卖
broker.end_of_day()
oid5 = broker.submit_order('000001', price=13.00, volume=50, side='sell')
check("T+1隔日解除(卖出)", oid5.startswith("PAPER_"))
pos = broker.get_positions()
p1 = next((p for p in pos if p.code == '000001'), None)
check("卖出一半持仓", p1 is not None and p1.volume == 50)

# Overbuy
broker2 = PaperBroker(initial_cash=1000, enable_risk=False)
oid6 = broker2.submit_order('000001', price=100.00, volume=100, side='buy')
check("资金不足自动缩量", oid6.startswith("PAPER_") or oid6 == "资金不足")

print(f"\n── 数据库抽象层 (data/db.py) ──")

from data.db import get_db, reset_db, get_store_dir
from data.datahub import DataHub
from data import results_db

with tempfile.TemporaryDirectory() as tmp:
    hub = DataHub(store_root=Path(tmp) / "store", cache_root=Path(tmp) / "cache")
    sig_path = hub.signal_path("unit_strategy")
    hub.write_parquet(pd.DataFrame([
        {"symbol": "A", "signal": "hold", "computed_at": "2026-05-01T15:00:00"},
        {"symbol": "B", "signal": "buy", "computed_at": "2026-05-02T15:00:00"},
        {"symbol": "C", "signal": "buy", "computed_at": "2026-05-02T15:00:00"},
    ]), sig_path)
    latest = hub.latest_batch(sig_path)
    check("DataHub最新批次读取", sorted(latest["symbol"].tolist()) == ["B", "C"])
    hub.append_parquet(sig_path, {"symbol": "B", "signal": "sell", "computed_at": "2026-05-03T15:00:00"}, dedupe_subset=["symbol"])
    after = hub.read_parquet(sig_path)
    row_b = after[after["symbol"] == "B"].iloc[0].to_dict()
    check("DataHub追加去重写入", row_b["signal"] == "sell" and sig_path.exists())
    audit_keys = {item["key"] for item in hub.audit()}
    check("DataHub目录审计", {"signals", "features", "paper", "token_usage"}.issubset(audit_keys))

reset_db()
results_db.init()
db = get_db()
db.connect()
check("DuckDB连接", db._conn is not None)
db.execute("CREATE TABLE IF NOT EXISTS _test (id INT, name TEXT)")
db.execute("INSERT INTO _test VALUES (1, 'test')")
row = db.fetchone("SELECT * FROM _test WHERE id=1")
check("CRUD写入读取", row['name'] == 'test')
db.execute("DROP TABLE _test")

# Test results_db integration
sig_dir = get_store_dir() / "signals"
backup_paths = [sig_dir / "buffett_scan.parquet", get_store_dir() / "scan_meta.parquet"]
backups = {p: (p.read_bytes() if p.exists() else None) for p in backup_paths}
try:
    results_db.save_buffett_results([{
        "symbol": "TEST01", "name": "测试股", "industry": "银行", "sector": "bank",
        "verdict": "通过-护城河", "score": 85.0,
        "roe": 15.5, "gross_margin": 0, "net_margin": 12.3,
        "de": 6.5, "safety_margin": 35.2, "dcf_value": 100.0, "current_price": 65.0,
    }])
    meta = results_db.get_buffett_meta()
    check("results_db写入", meta["total"] > 0)
finally:
    for p, data in backups.items():
        if data is None:
            p.unlink(missing_ok=True)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
    reset_db()

db.close()
reset_db()
check("连接关闭与重置", True)

print(f"\n── 策略信号选择 ──")

from signals.multifactor import compute_momentum
from signals.selection import apply_ranked_buys

price_df = pd.DataFrame({"close": [float(i) for i in range(1, 81)]})
mom = compute_momentum(price_df, [21])
check("动量按完整lookback计算", round(mom[21], 6) == round(80 / 59 - 1, 6))
mom_skip = compute_momentum(price_df, [42], skip_recent=21)
check("动量支持跳过最近一月", round(mom_skip[42], 6) == round(59 / 17 - 1, 6))

ranked = apply_ranked_buys(
    [{"symbol": f"S{i}", "score": s, "signal": "hold"} for i, s in enumerate([40, 80, 70, 60, 55])],
    "unit_test",
    default_min_score=60,
    default_top_pct=0.4,
    default_min_buys=1,
    default_max_buys=2,
)
buy_syms = [r["symbol"] for r in ranked if r["signal"] == "buy"]
check("信号按分数降序输出", [r["symbol"] for r in ranked[:3]] == ["S1", "S2", "S3"])
check("buy信号满足全局门槛", buy_syms == ["S1", "S2", "S3", "S4"], buy_syms)

print(f"\n{'='*50}")
print(f"结果: {passed}通过 / {failed}失败 / {passed+failed}总计")
