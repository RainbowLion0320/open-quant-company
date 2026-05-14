"""
巴菲特回测 — 滚动估值评分（消除前视偏差）

原理: 用 Tushare daily_basic 获取每只股票全历史 PE/PB/股息率
回测时每月查该月的估值数据，而非用今天的筛选结果
"""
import os, sys, time, pickle, yaml
from pathlib import Path
import pandas as pd
import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _get_token():
    """从 config 读取 tushare token"""
    cfg_path = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    return cfg["data"]["tushare"]["token"]


def fetch_valuation(pool, start="20150101", end="20260510", token=None):
    """
    批量拉取 daily_basic 估值数据 → parquet 缓存
    每只股票一次请求覆盖全历史，3s间隔防限流
    """
    import tushare as ts
    if token is None:
        token = _get_token()
    pro = ts.pro_api(token)

    cache_dir = DATA_DIR / "cache" / "valuation"
    cache_dir.mkdir(parents=True, exist_ok=True)

    fetched, skipped, failed = 0, 0, 0
    for i, sym in enumerate(pool):
        cache_path = cache_dir / f"{sym}.parquet"
        if cache_path.exists():
            skipped += 1
            continue

        ts_code = f"{sym}.SH" if sym.startswith("6") else f"{sym}.SZ"
        # 北交所代码特殊处理
        if sym.startswith("8") or sym.startswith("4"):
            ts_code = f"{sym}.BJ"

        try:
            df = pro.daily_basic(
                ts_code=ts_code,
                start_date=start,
                end_date=end,
                fields="trade_date,pe,pe_ttm,pb,dv_ratio,total_mv",
            )
            if df is not None and len(df) > 0:
                df["trade_date"] = pd.to_datetime(df["trade_date"])
                df = df.set_index("trade_date").sort_index()
                df.to_parquet(cache_path)
                fetched += 1
                if fetched % 10 == 0:
                    print(f"  已拉取 {fetched} 只...")
            else:
                failed += 1
        except Exception as e:
            failed += 1
            if failed <= 3:
                print(f"  {sym} 失败: {e}")

        time.sleep(0.5)  # Tushare 免费用户 200次/分钟 ≈ 0.3s间隔，留余量

    print(f"估值数据: 新拉取 {fetched}, 缓存命中 {skipped}, 失败 {failed}")
    return fetched, skipped, failed


def load_valuation_cache(pool):
    """加载估值缓存 → {symbol: DataFrame(index=trade_date, columns=[pe,pe_ttm,pb,dv_ratio,total_mv])}"""
    cache_dir = DATA_DIR / "cache" / "valuation"
    cache = {}
    for sym in pool:
        path = cache_dir / f"{sym}.parquet"
        if path.exists():
            df = pd.read_parquet(path)
            if len(df) > 0:
                cache[sym] = df
    return cache


def create_buffett_scorer(valuation_cache):
    """
    工厂函数: 返回一个消除了前视偏差的巴菲特评分器

    评分逻辑 (按月):
    - PE < 15 → +15分
    - PE < 25 → +10分
    - PB < 2  → +10分
    - 股息率 > 3% → +10分
    - 过去12月正收益 → +5分
    - 市值 > 500亿 → +5分 (大盘)
    - 波动率 < 30% → +5分
    基础分 40，满分 100
    """

    def scorer(sym, series, idx, regime):
        # 查找该月估值数据
        month_dt = series.index[idx]
        cache_df = valuation_cache.get(sym)
        if cache_df is None:
            return 0

        try:
            # 找最接近且不晚于 month_dt 的估值数据
            available = cache_df[cache_df.index <= month_dt]
            if len(available) == 0:
                return 0
            row = available.iloc[-1]

            pe = row.get("pe", np.nan)
            pb = row.get("pb", np.nan)
            dv = row.get("dv_ratio", np.nan)
            mv = row.get("total_mv", np.nan)
        except Exception:
            return 0

        score = 40  # 基础分

        # PE 估值
        if not np.isnan(pe) and pe > 0:
            if pe < 15:
                score += 15
            elif pe < 25:
                score += 10
            elif pe < 40:
                score += 5
        else:
            score -= 5  # 无PE或负数PE扣分

        # PB 估值
        if not np.isnan(pb) and pb > 0:
            if pb < 1.5:
                score += 10
            elif pb < 3:
                score += 5

        # 股息率
        if not np.isnan(dv) and dv > 0:
            if dv > 4:
                score += 10
            elif dv > 2:
                score += 5

        # 市值 (亿元)
        if not np.isnan(mv) and mv > 0:
            mv_yi = mv / 1e8
            if mv_yi > 500:
                score += 5
            elif mv_yi > 100:
                score += 2

        # 价格动量 (过去12月)
        close = series[:idx + 1].values
        if len(close) >= 252:
            ret_12m = close[-1] / close[-252] - 1
            if ret_12m > 0.05:
                score += 5
            elif ret_12m < -0.30:
                score -= 10  # 腰斩股警惕

        # 波动率 (低波动 = 价值股特征)
        if len(close) >= 63:
            rets = np.diff(close[-63:]) / close[-63:-1]
            vol = np.std(rets) * np.sqrt(252)
            if vol < 0.25:
                score += 5
            elif vol > 0.50:
                score -= 5

        return max(0, min(100, score))

    return scorer


if __name__ == "__main__":
    """独立运行: 拉取估值数据"""
    from data.symbols import CIRCLE_STOCKS
    import yaml
    cfg_path = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    pool_size = cfg.get("backtest", {}).get("pool_size", 0)
    pool = list(CIRCLE_STOCKS)
    if pool_size > 0:
        pool = pool[:pool_size]
    print(f"拉取 {len(pool)} 只股票估值数据...")
    fetch_valuation(pool)
    print("完成")
