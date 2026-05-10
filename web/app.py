"""
Quant Agent Web Dashboard — 专业金融风格
启动: streamlit run web/app.py
"""
import os, sys
from datetime import datetime
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# 延迟导入避免循环依赖 — TOTAL_ACTIVE 在 sidebar 需要
from data.symbols import TOTAL_ACTIVE

for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
    os.environ.pop(key, None)
os.environ["no_proxy"] = "eastmoney.com,10jqka.com.cn,sina.com.cn,qianlong.com,163.com,qq.com"

st.set_page_config(
    page_title="Quant Agent · A股量化",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 金融暗黑主题 CSS
# ============================================================
st.markdown("""
<style>
    /* 全局 */
    .stApp { background: #0a0e14; }
    .main .block-container { padding-top: 1rem; }

    /* 侧边栏 */
    [data-testid="stSidebar"] {
        background: #11161d;
        border-right: 1px solid #1e2530;
    }
    [data-testid="stSidebar"] * { color: #a0aec0 !important; }

    /* KPI 卡片 */
    .kpi-card {
        background: linear-gradient(135deg, #111820, #151d28);
        border: 1px solid #1e2a3a;
        border-radius: 8px;
        padding: 1.2rem 1.5rem;
        margin-bottom: 0.8rem;
    }
    .kpi-card .label {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #64748b;
        margin-bottom: 0.3rem;
    }
    .kpi-card .value {
        font-size: 1.8rem;
        font-weight: 700;
        font-family: 'SF Mono', 'Menlo', monospace;
    }
    .kpi-card .sub {
        font-size: 0.8rem;
        color: #64748b;
        margin-top: 0.2rem;
    }
    .kpi-green  .value { color: #00d4aa; }
    .kpi-red    .value { color: #ff4d6a; }
    .kpi-gold   .value { color: #f0b90b; }
    .kpi-blue   .value { color: #4dabf7; }
    .kpi-green  { border-left: 3px solid #00d4aa; }
    .kpi-red    { border-left: 3px solid #ff4d6a; }
    .kpi-gold   { border-left: 3px solid #f0b90b; }
    .kpi-blue   { border-left: 3px solid #4dabf7; }

    /* 标题 */
    h1 { color: #e2e8f0 !important; font-weight: 700 !important; font-size: 1.5rem !important; }
    h3 { color: #cbd5e1 !important; font-size: 1.1rem !important; margin-top: 1.5rem !important; }

    /* 表格 */
    [data-testid="stDataFrame"] { border: 1px solid #1e2a3a !important; border-radius: 6px; }
    [data-testid="stDataFrame"] th { background: #111820 !important; color: #64748b !important;
        font-size: 0.7rem !important; text-transform: uppercase; letter-spacing: 0.05em; }
    [data-testid="stDataFrame"] td { color: #cbd5e1 !important; font-size: 0.8rem; }

    /* 按钮 */
    .stButton > button {
        background: #1a2332 !important; border: 1px solid #2a3a50 !important;
        color: #a0aec0 !important; border-radius: 6px; font-size: 0.8rem;
    }
    .stButton > button:hover { border-color: #4dabf7 !important; color: #e2e8f0 !important; }

    /* 分割线 */
    hr { border-color: #1e2a3a !important; }

    /* header banner */
    .header-banner {
        padding: 0.3rem 0;
        border-bottom: 1px solid #1e2a3a;
        margin-bottom: 1rem;
        display: flex; justify-content: space-between; align-items: center;
    }
    .header-banner .brand { font-size: 1.0rem; color: #e2e8f0; font-weight: 700; }
    .header-banner .status { font-size: 0.75rem; color: #64748b; }
    .dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 4px; }
    .dot-live { background: #00d4aa; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 数据加载
# ============================================================

@st.cache_data(ttl=600)
def load_market_data():
    from cybernetics.orchestrator import QuantOrchestrator
    orch = QuantOrchestrator()
    snapshot = orch.detect()
    return snapshot, orch

@st.cache_data(ttl=3600)
def load_buffett_scan():
    from data.symbols import CIRCLE_STOCKS, SYMBOL_INDUSTRY, SYMBOL_SECTOR, FALLBACK_SECTOR, SYMBOL_NAME
    from data.financials import get_buffett_inputs
    from buffett.filters import buffett_filter, Verdict

    results = []
    all_symbols = sorted(CIRCLE_STOCKS)
    progress = st.progress(0, "加载扫描...")
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
    from data.fetcher import get_index_daily, get_stock_daily
    bench = get_index_daily("sh000001")
    if bench is not None and "date" in bench.columns:
        bench["date"] = pd.to_datetime(bench["date"])
        bench = bench[bench["date"] >= pd.Timestamp("2020-01-01")].copy()
    pool = ["603288", "002415", "600036", "600030", "601318",
            "601225", "600938", "601939", "002142", "601838"]
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
    cache_dir = os.path.join(PROJECT_DIR, "data", "cache")
    if not os.path.exists(cache_dir):
        return []
    files = []
    for f in sorted(os.listdir(cache_dir)):
        if f.endswith(".parquet"):
            path = os.path.join(cache_dir, f)
            st = os.stat(path)
            files.append({"file": f, "size_kb": round(st.st_size / 1024, 1),
                         "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%m-%d %H:%M"),
                         "age_h": round((datetime.now() - datetime.fromtimestamp(st.st_mtime)).total_seconds() / 3600, 1)})
    return files

# ============================================================
# Header
# ============================================================
st.markdown(f"""
<div class="header-banner">
    <span class="brand">📊 Quant Agent</span>
    <span class="status"><span class="dot dot-live"></span>Live · {datetime.now().strftime('%H:%M')}</span>
</div>
""", unsafe_allow_html=True)

# ============================================================
# 侧边栏
# ============================================================
with st.sidebar:
    st.markdown("### 🎯 导航")
    page = st.radio("", ["📈 市场概览", "🔍 巴菲特筛选", "📊 回测分析", "💾 数据管理"], label_visibility="collapsed")
    st.markdown("---")
    st.caption("**架构** 巴菲特价值投资 + 钱学森控制论")
    st.caption(f"**股票池** 全市场Top500 · {TOTAL_ACTIVE}只")

# ============================================================
# 页面1: 市场概览
# ============================================================
if page == "📈 市场概览":
    snapshot, orch = load_market_data()
    params = orch.get_params()

    # KPI 行
    c1, c2, c3, c4 = st.columns(4)
    regime_icon = {"bull": "🐂 多头", "bear": "🐻 空头", "sideways": "↔ 震荡"}.get(snapshot.regime.value, "—")
    with c1:
        st.markdown(f"""<div class="kpi-card kpi-gold"><div class="label">市场状态</div>
            <div class="value">{regime_icon}</div><div class="sub">{snapshot.index_ma_trend[:30]}...</div></div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="kpi-card kpi-blue"><div class="label">仓位上限</div>
            <div class="value">{params['position_size']*100:.0f}%</div><div class="sub">止损 {params['stop_loss']*100:.0f}%</div></div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="kpi-card kpi-green"><div class="label">涨跌比 20D</div>
            <div class="value">{snapshot.breadth:.0%}</div><div class="sub">量能 {snapshot.volume_trend}</div></div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="kpi-card kpi-blue"><div class="label">最大持仓</div>
            <div class="value">{params['max_positions']}</div><div class="sub">置信度 ≥{params['confidence_threshold']}</div></div>""", unsafe_allow_html=True)

    st.markdown("---")

    # 上证K线
    bench, stocks = load_backtest_data()
    if bench is not None:
        bench_60 = bench.tail(120)
        ma5 = bench_60["close"].rolling(5).mean()
        ma20 = bench_60["close"].rolling(20).mean()
        ma60 = bench_60["close"].rolling(60).mean()

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=bench_60["date"], y=bench_60["close"],
            mode="lines", name="上证指数", line=dict(color="#e2e8f0", width=2)))
        fig.add_trace(go.Scatter(x=bench_60["date"], y=ma5,
            mode="lines", name="MA5", line=dict(color="#ff4d6a", width=1, dash="dot")))
        fig.add_trace(go.Scatter(x=bench_60["date"], y=ma20,
            mode="lines", name="MA20", line=dict(color="#f0b90b", width=1, dash="dot")))
        fig.add_trace(go.Scatter(x=bench_60["date"], y=ma60,
            mode="lines", name="MA60", line=dict(color="#00d4aa", width=1, dash="dot")))
        fig.update_layout(
            template="plotly_dark", paper_bgcolor="#0a0e14", plot_bgcolor="#0a0e14",
            height=420, margin=dict(l=0, r=0, t=10, b=0),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(color="#a0aec0")),
            xaxis=dict(gridcolor="#1e2530", zeroline=False),
            yaxis=dict(gridcolor="#1e2530", zeroline=False),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# ============================================================
# 页面2: 巴菲特筛选
# ============================================================
elif page == "🔍 巴菲特筛选":
    with st.spinner("加载扫描结果..."):
        results = load_buffett_scan()

    if not results:
        st.warning("无数据")
    else:
        passed = [r for r in results if "✅" in r.verdict.value]
        failed_moat = [r for r in results if "护城河" in r.verdict.value]
        failed_margin = [r for r in results if "安全边际" in r.verdict.value]

        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f"""<div class="kpi-card kpi-blue"><div class="label">总股票</div>
            <div class="value">{len(results)}</div></div>""", unsafe_allow_html=True)
        c2.markdown(f"""<div class="kpi-card kpi-green"><div class="label">✅ 通过</div>
            <div class="value">{len(passed)}</div><div class="sub">{len(passed)/len(results)*100:.1f}%</div></div>""", unsafe_allow_html=True)
        c3.markdown(f"""<div class="kpi-card kpi-red"><div class="label">❌ 护城河</div>
            <div class="value">{len(failed_moat)}</div></div>""", unsafe_allow_html=True)
        c4.markdown(f"""<div class="kpi-card kpi-gold"><div class="label">❌ 安全边际</div>
            <div class="value">{len(failed_margin)}</div></div>""", unsafe_allow_html=True)

        st.markdown("---")

        # 表格
        df_results = pd.DataFrame([{
            "代码": r.symbol, "名称": r.name, "行业": r.industry,
            "判定": r.verdict.value, "评分": r.score,
            "ROE": f"{r.avg_roe_5y*100:.1f}%",
            "毛利率": f"{r.avg_gross_margin_5y*100:.1f}%" if r.avg_gross_margin_5y > 0 else "—",
            "净利率": f"{r.avg_net_margin_5y*100:.1f}%" if r.avg_net_margin_5y > 0 else "—",
            "D/E": f"{r.debt_equity_ratio:.1f}",
            "安全边际": f"{r.safety_margin_pct*100:.1f}%",
        } for r in sorted(results, key=lambda x: -x.score)])

        st.dataframe(df_results, use_container_width=True, height=580, hide_index=True,
            column_config={"评分": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d")})

        # 精选池展示
        if passed:
            st.markdown("### 🏆 精选池")
            cols = st.columns(min(len(passed), 6))
            for i, r in enumerate(sorted(passed, key=lambda x: -x.score)):
                with cols[i % len(cols)]:
                    color = "#00d4aa" if r.score >= 80 else "#f0b90b" if r.score >= 70 else "#a0aec0"
                    st.markdown(f"""
                    <div style="background:#111820; border:1px solid #1e2a3a; border-radius:8px;
                        padding:0.8rem; margin-bottom:0.5rem; text-align:center;">
                        <div style="font-size:0.7rem; color:#64748b;">{r.symbol}</div>
                        <div style="font-size:0.85rem; color:#e2e8f0; font-weight:600;">{r.name}</div>
                        <div style="font-size:1.4rem; font-weight:700; color:{color};">{r.score}</div>
                        <div style="font-size:0.65rem; color:#64748b;">{r.industry}</div>
                    </div>""", unsafe_allow_html=True)

# ============================================================
# 页面3: 回测分析
# ============================================================
elif page == "📊 回测分析":
    bench, stocks = load_backtest_data()

    if bench is None:
        st.warning("无数据")
    else:
        bench["date"] = pd.to_datetime(bench["date"])
        bench_start = bench["close"].iloc[0]
        bench_end = bench["close"].iloc[-1]
        bench_ret = (bench_end / bench_start - 1) * 100

        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f"""<div class="kpi-card"><div class="label">回测区间</div>
            <div class="value" style="font-size:1.2rem">{bench['date'].iloc[0].strftime('%Y')}→{bench['date'].iloc[-1].strftime('%Y')}</div></div>""", unsafe_allow_html=True)
        c2.markdown(f"""<div class="kpi-card"><div class="label">上证基准</div>
            <div class="value" style="color:#f0b90b">{bench_ret:+.2f}%</div></div>""", unsafe_allow_html=True)
        c3.markdown(f"""<div class="kpi-card kpi-red"><div class="label">策略回报</div>
            <div class="value">+6.85%</div><div class="sub">α -28.63%</div></div>""", unsafe_allow_html=True)
        c4.markdown(f"""<div class="kpi-card"><div class="label">交易次数</div>
            <div class="value" style="font-size:1.2rem">47</div></div>""", unsafe_allow_html=True)

        st.markdown("---")

        # 归一化走势
        fig = go.Figure()
        bench_ret_series = bench["close"] / bench["close"].iloc[0]
        fig.add_trace(go.Scatter(x=bench["date"], y=bench_ret_series,
            mode="lines", name="上证指数", line=dict(color="#64748b", width=2, dash="dash")))

        colors = ["#00d4aa", "#f0b90b", "#4dabf7", "#ff4d6a", "#a78bfa",
                  "#ff922b", "#20c997", "#e599f7", "#74c0fc", "#ffa94d"]
        for i, sym in enumerate(stocks):
            df = stocks[sym].copy()
            df["date"] = pd.to_datetime(df["date"])
            ret = df["close"] / df["close"].iloc[0]
            fig.add_trace(go.Scatter(x=df["date"], y=ret,
                mode="lines", name=sym, line=dict(color=colors[i % len(colors)], width=1.2)))

        fig.update_layout(
            template="plotly_dark", paper_bgcolor="#0a0e14", plot_bgcolor="#0a0e14",
            height=480, margin=dict(l=0, r=0, t=10, b=0),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(color="#a0aec0", size=9)),
            xaxis=dict(gridcolor="#1e2530"), yaxis=dict(gridcolor="#1e2530", tickformat=".1%"),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# ============================================================
# 页面4: 数据管理
# ============================================================
elif page == "💾 数据管理":
    files = load_cache_status()
    total_size = sum(f["size_kb"] for f in files)
    oldest = max((f["age_h"] for f in files), default=0)

    c1, c2, c3 = st.columns(3)
    c1.markdown(f"""<div class="kpi-card"><div class="label">缓存文件</div>
        <div class="value" style="font-size:1.2rem">{len(files)}</div></div>""", unsafe_allow_html=True)
    c2.markdown(f"""<div class="kpi-card"><div class="label">总大小</div>
        <div class="value" style="font-size:1.2rem">{total_size/1024:.1f} MB</div></div>""", unsafe_allow_html=True)
    c3.markdown(f"""<div class="kpi-card"><div class="label">最旧文件</div>
        <div class="value" style="font-size:1.2rem">{oldest:.0f}h</div></div>""", unsafe_allow_html=True)

    st.markdown("---")
    df_files = pd.DataFrame(files)
    st.dataframe(df_files, use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    if c1.button("🔄 刷新扫描缓存", use_container_width=True):
        load_buffett_scan.clear()
        st.rerun()
    if c2.button("🧹 清理过期缓存", use_container_width=True):
        os.system(f"cd {PROJECT_DIR} && make cache-clean")
        st.rerun()
