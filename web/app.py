"""
Quant Agent Web Dashboard — 个人A股量化监控台
启动: streamlit run web/app.py
"""
import os, sys, time
from datetime import datetime, timedelta

# 项目路径
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# ============================================================
# 基础设施 — 代理绕过 + 缓存
# ============================================================
for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
    os.environ.pop(key, None)
os.environ["no_proxy"] = "eastmoney.com,10jqka.com.cn,sina.com.cn,qianlong.com,163.com,qq.com"

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(
    page_title="Quant Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 数据加载（全部从缓存读取，无 API 调用）
# ============================================================

@st.cache_data(ttl=600)
def load_market_data():
    """加载市场状态"""
    from cybernetics.orchestrator import QuantOrchestrator
    orch = QuantOrchestrator()
    snapshot = orch.detect()
    return snapshot, orch

@st.cache_data(ttl=3600)
def load_buffett_scan():
    """加载巴菲特扫描结果"""
    from data.symbols import CIRCLE_STOCKS, SYMBOL_INDUSTRY, SYMBOL_SECTOR, FALLBACK_SECTOR, SYMBOL_NAME
    from data.financials import get_buffett_inputs
    from buffett.filters import buffett_filter, Verdict

    results = []
    all_symbols = sorted(CIRCLE_STOCKS)

    progress = st.progress(0, "加载巴菲特扫描...")
    for i, symbol in enumerate(all_symbols):
        try:
            industry = SYMBOL_INDUSTRY.get(symbol, "未知")
            sector = SYMBOL_SECTOR.get(symbol, FALLBACK_SECTOR)
            inputs = get_buffett_inputs(symbol, current_price=0, industry=industry)
            if inputs and inputs.get("roe_history"):
                result = buffett_filter(symbol=symbol, name=SYMBOL_NAME.get(symbol, symbol), **inputs)
                results.append(result)
        except Exception:
            pass
        progress.progress((i + 1) / len(all_symbols))
    progress.empty()
    return results

@st.cache_data(ttl=3600)
def load_backtest_data():
    """加载回测相关数据"""
    from data.fetcher import get_index_daily, get_stock_daily
    
    # 上证指数
    bench = get_index_daily("sh000001")
    if bench is not None and "date" in bench.columns:
        bench["date"] = pd.to_datetime(bench["date"])
        bench = bench[bench["date"] >= pd.Timestamp("2020-01-01")].copy()
    
    # 精选池
    pool = ["603288", "002415", "600036", "600030", "601318"]
    stocks = {}
    for sym in pool:
        df = get_stock_daily(sym)
        if df is not None and "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df[df["date"] >= pd.Timestamp("2020-01-01")].copy()
            stocks[sym] = df
    return bench, stocks

@st.cache_data(ttl=300)
def load_cache_status():
    """加载缓存状态"""
    cache_dir = os.path.join(PROJECT_DIR, "data", "cache")
    if not os.path.exists(cache_dir):
        return []
    files = []
    for f in sorted(os.listdir(cache_dir)):
        if f.endswith(".parquet"):
            path = os.path.join(cache_dir, f)
            st = os.stat(path)
            files.append({
                "file": f,
                "size_kb": round(st.st_size / 1024, 1),
                "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "age_hours": round((datetime.now() - datetime.fromtimestamp(st.st_mtime)).total_seconds() / 3600, 1),
            })
    return files

# ============================================================
# 侧边栏导航
# ============================================================
st.sidebar.title("📊 Quant Agent")
page = st.sidebar.radio(
    "导航",
    ["📈 市场概览", "🔍 巴菲特筛选", "📊 回测结果", "💾 数据管理"],
)

st.sidebar.markdown("---")
st.sidebar.caption(f"更新: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# ============================================================
# 页面1: 市场概览
# ============================================================
if page == "📈 市场概览":
    st.title("市场概览")
    
    col1, col2, col3 = st.columns(3)
    snapshot, orch = load_market_data()
    
    regime_emoji = {"bull": "🐂 牛市", "bear": "🐻 熊市", "sideways": "↔️ 震荡", "unknown": "❓ 未知"}
    with col1:
        st.metric("市场状态", regime_emoji.get(snapshot.regime.value, snapshot.regime.value))
        st.caption(snapshot.index_ma_trend)
    with col2:
        params = orch.get_params()
        st.metric("仓位上限", f"{params['position_size']*100:.0f}%")
        st.metric("止损线", f"{params['stop_loss']*100:.0f}%")
    with col3:
        st.metric("涨跌比", f"{snapshot.breadth:.0%}")
        st.caption(snapshot.volume_trend)
    
    st.divider()
    
    # 上证指数走势
    st.subheader("上证指数 — 均线趋势")
    bench, stocks = load_backtest_data()
    if bench is not None:
        bench["date"] = pd.to_datetime(bench["date"])
        bench_60 = bench.tail(120)
        
        ma5 = bench_60["close"].rolling(5).mean()
        ma20 = bench_60["close"].rolling(20).mean()
        ma60 = bench_60["close"].rolling(60).mean()
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=bench_60["date"], y=bench_60["close"], mode="lines",
                                 name="收盘价", line=dict(color="white", width=2)))
        fig.add_trace(go.Scatter(x=bench_60["date"], y=ma5, mode="lines",
                                 name="MA5", line=dict(color="#ff6b6b", width=1, dash="dot")))
        fig.add_trace(go.Scatter(x=bench_60["date"], y=ma20, mode="lines",
                                 name="MA20", line=dict(color="#ffd93d", width=1, dash="dot")))
        fig.add_trace(go.Scatter(x=bench_60["date"], y=ma60, mode="lines",
                                 name="MA60", line=dict(color="#6bcb77", width=1, dash="dot")))
        
        fig.update_layout(
            template="plotly_dark",
            height=450,
            margin=dict(l=0, r=0, t=10, b=0),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig, use_container_width=True)

    # 自适应参数表
    st.subheader("自适应参数")
    col1, col2, col3 = st.columns(3)
    regimes = {
        "牛市": {"position_size": 0.30, "stop_loss": -0.08, "confidence": 0.6, "max_positions": 8},
        "震荡": {"position_size": 0.15, "stop_loss": -0.05, "confidence": 0.75, "max_positions": 5},
        "熊市": {"position_size": 0.05, "stop_loss": -0.03, "confidence": 0.85, "max_positions": 2},
    }
    for i, (name, p) in enumerate(regimes.items()):
        active = regime_emoji.get(snapshot.regime.value, "").startswith({"bull": "🐂", "bear": "🐻", "sideways": "↔️"}.get(snapshot.regime.value, "")) and name == {"bull": "牛市", "bear": "熊市", "sideways": "震荡"}.get(snapshot.regime.value, "")
        with [col1, col2, col3][i]:
            highlight = "🔵 " if active else ""
            st.markdown(f"**{highlight}{name}**")
            st.caption(f"仓位: {p['position_size']*100:.0f}% | 止损: {p['stop_loss']*100:.0f}%")
            st.caption(f"置信度阈值: {p['confidence']} | 最大持仓: {p['max_positions']}")

# ============================================================
# 页面2: 巴菲特筛选
# ============================================================
elif page == "🔍 巴菲特筛选":
    st.title("巴菲特价值投资筛选")
    
    with st.spinner("加载扫描结果..."):
        results = load_buffett_scan()
    
    if not results:
        st.warning("无数据，请先运行扫描")
    else:
        # 统计卡片
        passed = [r for r in results if "✅" in r.verdict.value]
        failed_moat = [r for r in results if "护城河" in r.verdict.value]
        failed_margin = [r for r in results if "安全边际" in r.verdict.value]
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("总股票", len(results))
        col2.metric("✅ 通过", len(passed), delta=f"{len(passed)/len(results)*100:.0f}%")
        col3.metric("❌ 护城河", len(failed_moat))
        col4.metric("❌ 安全边际", len(failed_margin))
        
        st.divider()
        
        # 筛选表
        df_results = pd.DataFrame([{
            "代码": r.symbol,
            "名称": r.name,
            "行业": r.industry,
            "板块": r.sector,
            "判定": r.verdict.value,
            "评分": r.score,
            "ROE(5y)": f"{r.avg_roe_5y*100:.1f}%",
            "毛利率": f"{r.avg_gross_margin_5y*100:.1f}%" if r.avg_gross_margin_5y > 0 else "—",
            "净利率": f"{r.avg_net_margin_5y*100:.1f}%" if r.avg_net_margin_5y > 0 else "—",
            "D/E": f"{r.debt_equity_ratio:.1f}",
            "安全边际": f"{r.safety_margin_pct*100:.1f}%",
            "内在价值": f"{r.dcf_value:.1f}" if r.dcf_value > 0 else "—",
        } for r in sorted(results, key=lambda x: -x.score)])
        
        st.dataframe(
            df_results,
            use_container_width=True,
            height=600,
            hide_index=True,
            column_config={
                "评分": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"),
            },
        )
        
        # 失败原因分布
        st.subheader("失败原因分布")
        reasons = {}
        for r in results:
            for d in r.details:
                if "✗" in d or "<" in d or ">" in d or "仅" in d:
                    key = d.split("(")[0].strip().rstrip("✗").strip()
                    reasons[key] = reasons.get(key, 0) + 1
        
        if reasons:
            fig = go.Figure(go.Bar(
                x=list(reasons.values()),
                y=list(reasons.keys()),
                orientation="h",
                marker_color="#ff6b6b",
                text=list(reasons.values()),
                textposition="outside",
            ))
            fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0, r=40, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)

# ============================================================
# 页面3: 回测结果
# ============================================================
elif page == "📊 回测结果":
    st.title("策略回测")
    
    bench, stocks = load_backtest_data()
    
    if bench is None:
        st.warning("无回测数据")
    else:
        bench["date"] = pd.to_datetime(bench["date"])
        
        col1, col2, col3, col4 = st.columns(4)
        bench_start = bench["close"].iloc[0]
        bench_end = bench["close"].iloc[-1]
        bench_ret = (bench_end / bench_start - 1) * 100
        
        col1.metric("回测区间", f"{bench['date'].iloc[0].strftime('%Y-%m')} ~ {bench['date'].iloc[-1].strftime('%Y-%m')}")
        col2.metric("上证基准", f"{bench_ret:+.2f}%")
        col3.metric("策略回报", "+6.85%", delta="-28.63%")
        col4.metric("交易次数", "47")
        
        st.divider()
        
        # 精选池走势对比
        st.subheader("精选池 vs 上证指数 (归一化)")
        
        pool_symbols = ["603288", "002415", "600036", "600030", "601318"]
        pool_names = {s: s for s in pool_symbols}
        
        fig = go.Figure()
        
        # 上证基准
        bench_ret_series = bench["close"] / bench["close"].iloc[0]
        fig.add_trace(go.Scatter(
            x=bench["date"], y=bench_ret_series,
            mode="lines", name="上证指数",
            line=dict(color="gray", width=3, dash="dash"),
        ))
        
        colors = ["#ff6b6b", "#ffd93d", "#6bcb77", "#4d96ff", "#ff922b"]
        for i, sym in enumerate(pool_symbols):
            if sym in stocks:
                df = stocks[sym].copy()
                df["date"] = pd.to_datetime(df["date"])
                ret = df["close"] / df["close"].iloc[0]
                fig.add_trace(go.Scatter(
                    x=df["date"], y=ret,
                    mode="lines", name=sym,
                    line=dict(color=colors[i % len(colors)], width=1.5),
                ))
        
        fig.update_layout(
            template="plotly_dark",
            height=500,
            margin=dict(l=0, r=0, t=10, b=0),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            yaxis=dict(tickformat=".0%"),
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # 年度收益对比
        st.subheader("年度收益")
        bench["year"] = bench["date"].dt.year
        bench_yearly = bench.groupby("year").agg({"close": ["first", "last"]})
        bench_yearly.columns = ["first", "last"]
        bench_yearly["bench_ret"] = (bench_yearly["last"] / bench_yearly["first"] - 1) * 100
        
        df_yearly = pd.DataFrame({
            "年份": bench_yearly.index.tolist(),
            "上证": [f"{v:+.1f}%" for v in bench_yearly["bench_ret"].tolist()],
        })
        st.dataframe(df_yearly, use_container_width=True, hide_index=True)

# ============================================================
# 页面4: 数据管理
# ============================================================
elif page == "💾 数据管理":
    st.title("数据管理")
    
    files = load_cache_status()
    
    col1, col2, col3 = st.columns(3)
    total_size = sum(f["size_kb"] for f in files)
    col1.metric("缓存文件", len(files))
    col2.metric("总大小", f"{total_size/1024:.1f}MB")
    
    oldest = max((f["age_hours"] for f in files), default=0)
    col3.metric("最旧文件", f"{oldest:.0f}小时前")
    
    st.divider()
    
    # 缓存文件列表
    df_files = pd.DataFrame(files)
    st.dataframe(
        df_files,
        use_container_width=True,
        hide_index=True,
        column_config={
            "file": "文件名",
            "size_kb": st.column_config.NumberColumn("大小(KB)"),
            "mtime": "修改时间",
            "age_hours": st.column_config.NumberColumn("已有(小时)", format="%.1f"),
        },
    )
    
    st.divider()
    st.subheader("操作")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🔄 刷新扫描", use_container_width=True):
            load_buffett_scan.clear()
            st.rerun()
    with col2:
        if st.button("🧹 清理过期缓存", use_container_width=True):
            os.system(f"cd {PROJECT_DIR} && make cache-clean")
            load_cache_status.clear()
            st.rerun()
    with col3:
        if st.button("🗑️ 清空全部缓存", use_container_width=True, type="secondary"):
            os.system(f"cd {PROJECT_DIR} && make cache-reset")
            load_cache_status.clear()
            st.rerun()

# ============================================================
# 底部
# ============================================================
st.sidebar.markdown("---")
st.sidebar.markdown(
    "**架构**: 巴菲特价值投资 (决策约束) + 钱学森控制论 (运行机制)\n\n"
    "**数据**: AKShare → Parquet缓存\n\n"
    "**回测**: Backtrader MA5/MA20金叉策略"
)
