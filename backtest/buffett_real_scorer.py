"""
巴菲特真实过滤回测评分器

使用完整的 buffett_filter() 三重过滤 (能力圈→护城河→安全边际)
每回测年重新评分，消除前视偏差

数据源: financials.py 的 parquet 磁盘缓存
"""
import os, sys
from pathlib import Path
import pandas as pd
import numpy as np

# 项目根
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def create_buffett_real_scorer(pool):
    """
    工厂函数: 返回一个使用真实巴菲特过滤器的评分器

    每个回测月: 确定当年年份 → 用当年之前5年的年报数据跑 buffett_filter()
    结果按年缓存，同年各月共用
    """
    # 按年缓存的过滤结果: {year: {symbol: score}}
    yearly_results = {}

    def scorer(sym, series, idx, regime):
        # 确定回测月所属年份
        month_dt = series.index[idx]
        year = month_dt.year

        # 年缓存查找
        if year not in yearly_results:
            _build_year_cache(year, pool)

        year_cache = yearly_results.get(year, {})
        return year_cache.get(sym, 0)

    def _build_year_cache(year, stock_pool):
        """构建某一年的巴菲特过滤结果"""
        from data.financials import (
            get_financial_summary, extract_roe_history,
            extract_gross_margin_history, extract_net_margin_history,
            extract_debt_equity_ratio, extract_latest_net_profit,
        )
        from data.symbols import SYMBOL_NAME, SYMBOL_INDUSTRY, SYMBOL_SECTOR, FALLBACK_SECTOR
        from buffett.filters import buffett_filter, Verdict

        result = {}
        cutoff = pd.Timestamp(f"{year - 1}-12-31")

        for sym in stock_pool:
            try:
                df = get_financial_summary(sym)
                if df is None or len(df) == 0:
                    continue

                report_col = "报告期"
                df[report_col] = pd.to_datetime(df[report_col])
                historical = df[df[report_col] <= cutoff].copy()

                # 至少5年数据
                annual_count = len(historical[historical[report_col].astype(str).str.endswith("-12-31")])
                if annual_count < 5:
                    continue

                roe = extract_roe_history(historical)
                gm = extract_gross_margin_history(historical)
                nm = extract_net_margin_history(historical)
                debt = extract_debt_equity_ratio(historical)
                net_profit = extract_latest_net_profit(historical)

                if not roe or len(roe) < 5:
                    continue

                name = SYMBOL_NAME.get(sym, sym)
                industry = SYMBOL_INDUSTRY.get(sym, "待分类")
                sector = SYMBOL_SECTOR.get(sym, FALLBACK_SECTOR)

                filter_result = buffett_filter(
                    symbol=sym, name=name, industry=industry, sector=sector,
                    fcf=net_profit * 0.7, roe_history=roe,
                    gross_margin_history=gm, net_margin_history=nm,
                    debt_equity=debt, current_price=0,
                )

                if filter_result.verdict == Verdict.PASS:
                    result[sym] = filter_result.score
                # 不通过的不加入 (score = 0)
            except Exception:
                pass

        yearly_results[year] = result
        if result:
            print(f"  巴菲特 {year}年: {len(result)} 只通过 (数据截止{year-1}年报)")

    return scorer


if __name__ == "__main__":
    """独立运行: 预热财务缓存 + 测试"""
    from data.symbols import CIRCLE_STOCKS
    import yaml
    cfg_path = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    pool_size = cfg.get("backtest", {}).get("pool_size", 0)
    pool = list(CIRCLE_STOCKS)
    if pool_size > 0:
        pool = pool[:pool_size]

    print(f"预热财务数据缓存 ({len(pool)} 只)...")
    succeeded = 0
    from data.financials import get_financial_summary
    for sym in pool:
        try:
            df = get_financial_summary(sym)
            if df is not None and len(df) > 0:
                succeeded += 1
        except Exception:
            pass
    print(f"财务缓存: {succeeded}/{len(pool)} 只有效数据")

    print("\n测试评分器 (2016年)...")
    scorer = create_buffett_real_scorer(pool)

    # 手动触发 2016 年缓存构建
    scorer._build_year_cache(2016, pool)
    print(f"  2016 年结果: {scorer.yearly_results.get(2016, {})}")
