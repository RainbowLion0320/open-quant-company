#!/usr/bin/env python3
"""
全量巴菲特扫描 — 对 25 只能力圈内股票跑三重过滤器
输出: 通过/未通过名单 + 失败原因分布
"""
import os, sys, time
sys.path.insert(0, os.path.expanduser("~/quant-agent"))

# 模块级代理清理（必须在 import akshare 前）
for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
    os.environ.pop(key, None)
os.environ["no_proxy"] = "eastmoney.com,10jqka.com.cn,sina.com.cn,qianlong.com,163.com,qq.com"

from data.symbols import CIRCLE_OF_COMPETENCE, SYMBOL_SECTOR, FALLBACK_SECTOR
from data.financials import get_buffett_inputs
from buffett.filters import buffett_filter, Verdict

# ----- 行情获取（优先批量，回退单只）-----
def get_current_prices(symbols: list) -> dict:
    """批量获取最新收盘价"""
    prices = {}
    # 尝试批量接口 stock_zh_a_spot_em
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        code_map = {row["代码"]: row["最新价"] for _, row in df.iterrows()}
        for symbol in symbols:
            if symbol in code_map:
                prices[symbol] = float(code_map[symbol])
        return prices
    except Exception as e:
        print(f"  ⚠️ 批量行情失败: {e}, 使用单只回退...")

    # 单只回退：用历史日线的最后收盘价
    from data.fetcher import get_stock_daily
    for i, symbol in enumerate(symbols):
        try:
            df = get_stock_daily(symbol)
            if "close" in df.columns:
                prices[symbol] = float(df["close"].iloc[-1])
            elif "收盘" in df.columns:
                prices[symbol] = float(df["收盘"].iloc[-1])
            if i > 0 and i % 5 == 0:
                time.sleep(3)  # 节流
        except Exception as e:
            print(f"  ⚠️ {symbol} 行情失败: {e}")
    return prices


def main():
    print("=" * 70)
    print("巴菲特全量扫描 — 25只能力圈内A股")
    print("=" * 70)

    # 1. 收集全部标的
    all_symbols = []
    symbol_industry = {}
    for industry, symbols in CIRCLE_OF_COMPETENCE.items():
        all_symbols.extend(symbols)
        for s in symbols:
            symbol_industry[s] = industry

    all_symbols = sorted(set(all_symbols))
    print(f"\n股票池: {len(all_symbols)} 只 ({len(CIRCLE_OF_COMPETENCE)} 个行业)")
    for ind, syms in CIRCLE_OF_COMPETENCE.items():
        print(f"  {ind}: {', '.join(syms)}")

    # 2. 获取行情
    print(f"\n📊 获取行情...")
    prices = get_current_prices(all_symbols)
    print(f"  获取到 {len(prices)}/{len(all_symbols)} 只行情")

    # 3. 逐只扫描
    results = []
    passed = []
    failed = []
    data_missing = []

    print(f"\n🔍 巴菲特过滤器扫描...")
    for i, symbol in enumerate(all_symbols):
        industry = symbol_industry[symbol]
        price = prices.get(symbol, 0)
        sector = SYMBOL_SECTOR.get(symbol, FALLBACK_SECTOR)

        try:
            inputs = get_buffett_inputs(symbol, current_price=price, industry=industry)
            if not inputs or not inputs.get("roe_history"):
                data_missing.append((symbol, industry, "财务数据为空"))
                print(f"  [{i+1:2d}/25] {symbol} ⚠️ 数据不足")
                continue

            result = buffett_filter(symbol=symbol, name=symbol, **inputs)
            results.append(result)

            icon = "✅" if result.verdict == Verdict.PASS else "❌"
            status = result.verdict.value
            print(f"  [{i+1:2d}/25] {symbol} {icon} {status} (评分:{result.score})")
            print(f"          {' | '.join(result.details)}")

            if result.verdict == Verdict.PASS:
                passed.append(result)
            else:
                failed.append(result)

        except Exception as e:
            data_missing.append((symbol, industry, str(e)))
            print(f"  [{i+1:2d}/25] {symbol} ⚠️ 错误: {e}")

        # 节流
        if i < len(all_symbols) - 1:
            time.sleep(2)

    # 4. 汇总
    print(f"\n{'='*70}")
    print(f"扫描汇总")
    print(f"{'='*70}")
    print(f"  总计: {len(all_symbols)} 只")
    print(f"  ✅ 通过: {len(passed)} 只")
    print(f"  ❌ 未通过: {len(failed)} 只")
    print(f"  ⚠️ 数据不足: {len(data_missing)} 只")

    if passed:
        print(f"\n✅ 巴菲特精选池:")
        for r in sorted(passed, key=lambda x: -x.score):
            print(f"  {r.symbol} ({r.industry}) 评分:{r.score} "
                  f"ROE:{r.avg_roe_5y*100:.1f}% 安全边际:{r.safety_margin_pct*100:.1f}%")

    if failed:
        print(f"\n❌ 未通过名单:")
        by_reason = {}
        for r in failed:
            reason = r.verdict.value.split(" ")[1] if " " in r.verdict.value else r.verdict.value
            by_reason.setdefault(reason, []).append(r.symbol)
        for reason, syms in sorted(by_reason.items(), key=lambda x: -len(x[1])):
            print(f"  {reason} ({len(syms)}只): {', '.join(syms)}")

    if data_missing:
        print(f"\n⚠️ 数据不足:")
        for symbol, industry, err in data_missing:
            print(f"  {symbol} ({industry}): {err}")

    print(f"\n⏱️ 扫描完成")


if __name__ == "__main__":
    main()
