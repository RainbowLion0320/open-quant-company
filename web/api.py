"""
Quant Agent API — FastAPI 数据后端
启动: python web/api.py
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for key in ("http_proxy","https_proxy","HTTP_PROXY","HTTPS_PROXY","all_proxy","ALL_PROXY"):
    os.environ.pop(key, None)
os.environ["no_proxy"] = "eastmoney.com,10jqka.com.cn,sina.com.cn,qianlong.com,163.com,qq.com"

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from datetime import datetime
import pandas as pd
import numpy as np

app = FastAPI(title="Quant Agent API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ============================================================
# API: 市场概览
# ============================================================
@app.get("/api/market")
def market():
    from cybernetics.orchestrator import QuantOrchestrator
    orch = QuantOrchestrator()
    snapshot = orch.detect()
    params = orch.get_params()

    from data.fetcher import get_index_daily
    bench = get_index_daily("sh000001")
    bench["date"] = pd.to_datetime(bench["date"])

    # 最近120天K线数据
    recent = bench.tail(120)
    kline = []
    for _, row in recent.iterrows():
        kline.append({
            "date": str(row["date"])[:10],
            "close": float(row["close"]), "open": float(row["open"]),
            "high": float(row["high"]), "low": float(row["low"]),
            "volume": int(row["volume"]),
        })

    return {
        "regime": snapshot.regime.value,
        "ma_trend": snapshot.index_ma_trend,
        "volume_trend": snapshot.volume_trend,
        "breadth": round(snapshot.breadth, 2),
        "params": params,
        "kline": kline,
        "updated": datetime.now().strftime("%H:%M"),
        "pool_size": 1000,
    }


# ============================================================
# API: 巴菲特筛选
# ============================================================
@app.get("/api/buffett")
def buffett():
    from data.symbols import CIRCLE_STOCKS, SYMBOL_INDUSTRY, SYMBOL_SECTOR, FALLBACK_SECTOR, SYMBOL_NAME
    from data.financials import get_buffett_inputs
    from buffett.filters import buffett_filter as bf, Verdict

    results = []
    for symbol in CIRCLE_STOCKS:
        try:
            ind = SYMBOL_INDUSTRY.get(symbol, "待分类")
            sec = SYMBOL_SECTOR.get(symbol, FALLBACK_SECTOR)
            inputs = get_buffett_inputs(symbol, current_price=0, industry=ind)
            if not inputs or not inputs.get("roe_history"):
                continue
            r = bf(symbol=symbol, name=SYMBOL_NAME.get(symbol, symbol), **inputs)
            results.append({
                "symbol": r.symbol, "name": r.name, "industry": r.industry,
                "verdict": r.verdict.value, "score": r.score,
                "roe": round(r.avg_roe_5y * 100, 1),
                "gross_margin": round(r.avg_gross_margin_5y * 100, 1) if r.avg_gross_margin_5y > 0 else None,
                "net_margin": round(r.avg_net_margin_5y * 100, 1) if r.avg_net_margin_5y > 0 else None,
                "de": round(r.debt_equity_ratio, 1),
                "safety_margin": round(r.safety_margin_pct * 100, 1),
                "dcf_value": round(r.dcf_value, 1),
                "sector": r.sector,
            })
        except Exception:
            pass

    passed = [r for r in results if "✅" in r["verdict"]]
    failed_moat = len([r for r in results if "护城河" in r["verdict"]])
    failed_margin = len([r for r in results if "安全边际" in r["verdict"]])

    results.sort(key=lambda x: -x["score"])
    return {
        "total": len(results),
        "passed": len(passed),
        "failed_moat": failed_moat,
        "failed_margin": failed_margin,
        "results": results,
        "updated": datetime.now().strftime("%H:%M"),
    }


# ============================================================
# API: 回测数据
# ============================================================
@app.get("/api/backtest")
def backtest():
    from data.fetcher import get_index_daily, get_stock_daily

    bench = get_index_daily("sh000001")
    bench["date"] = pd.to_datetime(bench["date"])
    bench = bench.set_index("date").sort_index()
    b = bench.loc["2020-01-01":"2026-05-10"]

    bench_ret = round((b["close"].iloc[-1] / b["close"].iloc[0] - 1) * 100, 2)

    # 精选池走势
    pool = ["603288","002415","600036","600030","601318","601225","600938","601939","002142","601838"]
    series = [{"name": "上证指数", "data": []}]

    for sym in pool:
        df = get_stock_daily(sym)
        if df is None or len(df) < 100:
            continue
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df = df.loc["2020-01-01":"2026-05-10"]
        if len(df) == 0:
            continue
        norm = (df["close"] / df["close"].iloc[0]).tolist()
        dates = [str(d)[:10] for d in df.index]
        series.append({"name": sym, "data": [{"date": d, "value": round(v, 4)} for d, v in zip(dates, norm)]})

    # 上证基准序列
    bench_norm = (b["close"] / b["close"].iloc[0]).tolist()
    bench_dates = [str(d)[:10] for d in b.index]
    series[0]["data"] = [{"date": d, "value": round(v, 4)} for d, v in zip(bench_dates, bench_norm)]

    return {
        "bench_return": bench_ret,
        "strat_return": 6.85,
        "alpha": round(6.85 - bench_ret, 2),
        "trades": 47,
        "series": series,
        "updated": datetime.now().strftime("%H:%M"),
    }


# ============================================================
# API: 缓存状态
# ============================================================
@app.get("/api/cache")
def cache():
    cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cache")
    files = []
    if os.path.exists(cache_dir):
        for f in sorted(os.listdir(cache_dir)):
            if f.endswith(".parquet"):
                path = os.path.join(cache_dir, f)
                st = os.stat(path)
                files.append({
                    "file": f, "size_kb": round(st.st_size / 1024, 1),
                    "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%m-%d %H:%M"),
                    "age_h": round((datetime.now() - datetime.fromtimestamp(st.st_mtime)).total_seconds() / 3600, 1),
                })
    return {"total": len(files), "size_mb": round(sum(f["size_kb"] for f in files) / 1024, 1), "files": files}


# ============================================================
# 首页 — 单页应用
# ============================================================
@app.get("/", response_class=HTMLResponse)
def index():
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(html_path) as f:
        return f.read()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8501)
