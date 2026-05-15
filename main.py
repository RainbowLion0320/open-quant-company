#!/usr/bin/env python3
"""
Quant Agent — 个人A股量化AI
${HERMES_PROMPT} 占位符供Hermes Agent注入上下文

用法:
  python main.py fetch    # 更新所有数据
  python main.py filter   # 巴菲特筛选
  python main.py regime   # 市场状态检测
  python main.py status   # 系统状态
"""
import sys
import os

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data import get_index_daily, get_stock_daily, StockUniverse
from signals.buffett import buffett_filter
from cybernetics import QuantOrchestrator


def cmd_fetch():
    """拉取数据"""
    print("📊 拉取数据...")
    # 指数
    from data import BENCHMARKS
    for name, code in BENCHMARKS.items():
        try:
            df = get_index_daily(code)
            print(f"  {name} ({code}): {len(df)} 条, 最新 {df['date'].iloc[-1]}")
        except Exception as e:
            print(f"  {name} ({code}): ❌ {e}")

    # 个股
    universe = StockUniverse()
    for symbol in sorted(universe.symbols):
        try:
            df = get_stock_daily(symbol)
            latest = df["date"].iloc[-1] if "date" in df.columns else df["date"].iloc[-1]
            print(f"  {symbol}: {len(df)} 条, 最新 {latest}")
        except Exception as e:
            print(f"  {symbol}: ❌ {e}")


def cmd_filter():
    """巴菲特筛选 (演示用茅台数据)"""
    print("🔍 巴菲特筛选示例 — 贵州茅台(600519)")
    # 贵州茅台模拟数据（实际应从财务数据接口获取）
    result = buffett_filter(
        symbol="600519",
        name="贵州茅台",
        industry="白酒",
        fcf=600,             # 自由现金流（亿）
        growth_rate=0.08,    # 增长预期
        shares_outstanding=12.56,  # 总股本
        current_price=1373,  # 当前股价
        roe_history=[0.31, 0.30, 0.32, 0.29, 0.30],  # 近5年ROE
        gross_margin_history=[0.91, 0.92, 0.91, 0.90, 0.91],
        debt_equity=0.21,
    )
    print(f"  判定: {result.verdict.value}")
    print(f"  评分: {result.score}/100")
    print(f"  详情:")
    for d in result.details:
        print(f"    - {d}")


def cmd_regime():
    """市场状态检测"""
    print("📈 市场状态检测...")
    orch = QuantOrchestrator()
    from data import BENCHMARKS
    try:
        df = get_index_daily(BENCHMARKS["上证指数"])
        orch.set_regime({"sh000001": df})
        s = orch.status()
        print(f"  市场状态: {s['regime']}")
        print(f"  自适应参数: {s['params']}")
    except Exception as e:
        print(f"  ❌ {e}")


def cmd_status():
    """系统状态"""
    print("📋 Quant Agent 状态")
    print(f"  项目: ~/quant-agent")
    print(f"  Python: ~/.hermes/hermes-agent/venv/bin/python3")
    from data import StockUniverse
    u = StockUniverse()
    print(f"  股票池: {len(u.symbols)} 只")
    for ind, syms in u.by_industry.items():
        print(f"    {ind}: {', '.join(syms)}")


COMMANDS = {
    "fetch": cmd_fetch,
    "filter": cmd_filter,
    "regime": cmd_regime,
    "status": cmd_status,
}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd in COMMANDS:
        COMMANDS[cmd]()
    else:
        print(f"未知命令: {cmd}")
        print(f"可用: {', '.join(COMMANDS.keys())}")
