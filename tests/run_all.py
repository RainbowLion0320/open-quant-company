"""
量化项目全模块测试
运行: python tests/run_all.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
    os.environ.pop(key, None)
os.environ["no_proxy"] = "eastmoney.com,10jqka.com.cn,sina.com.cn,qianlong.com,163.com,qq.com"


# ============================================================
# 测试1: 数据缓存
# ============================================================
def test_cache():
    """验证两层缓存: 磁盘 + 内存"""
    from data.fetcher import get_stock_daily, _mem_cache
    _mem_cache.clear()
    
    df1 = get_stock_daily("600036")
    assert df1 is not None and len(df1) > 1000, "缓存加载失败"
    
    _mem_cache.clear()
    df2 = get_stock_daily("600036")
    assert len(df2) == len(df1), "二次加载条数不一致"
    
    df3 = get_stock_daily("600036")
    assert df3 is df2, "内存缓存未命中(应为同一对象)"
    
    # force_refresh
    df4 = get_stock_daily("600036", force_refresh=True)
    assert df4 is not None and len(df4) > 1000, "强制刷新失败"
    
    print("  ✓ 数据缓存(磁盘+内存)")


# ============================================================
# 测试2: 财务数据解析
# ============================================================
def test_financials():
    """验证财务数据提取：ROE/毛利率/净利率/D-E"""
    from data.financials import (
        get_financial_summary, extract_roe_history,
        extract_gross_margin_history, extract_net_margin_history,
        extract_debt_equity_ratio, extract_latest_net_profit,
        extract_latest_revenue,
    )
    
    # 茅台 — 消费股（有毛利率）
    df = get_financial_summary("600519")
    assert len(df) > 0, "茅台财务数据为空"
    
    roe = extract_roe_history(df)
    assert len(roe) >= 5, f"茅台ROE不足5年: {len(roe)}"
    assert roe[-1] > 0.20, f"茅台ROE异常: {roe[-1]:.2%}"
    
    gm = extract_gross_margin_history(df)
    assert len(gm) >= 3, "茅台毛利率不足"
    assert gm[-1] > 0.50, f"茅台毛利率异常: {gm[-1]:.2%}"
    
    np_val = extract_latest_net_profit(df)
    assert np_val > 100, f"茅台净利润异常: {np_val}亿"
    
    rev = extract_latest_revenue(df)
    assert rev > 100, f"茅台营收异常: {rev}亿"
    
    de = extract_debt_equity_ratio(df)
    assert de > 0, f"茅台D/E异常: {de}"
    
    # 招行 — 银行股（无毛利率）
    df2 = get_financial_summary("600036")
    gm2 = extract_gross_margin_history(df2)
    assert len(gm2) == 0, f"银行不应有毛利率: {len(gm2)}条"
    
    nm2 = extract_net_margin_history(df2)
    assert len(nm2) >= 3, f"银行净利率不足: {len(nm2)}"
    assert nm2[-1] > 0.20, f"银行净利率异常: {nm2[-1]:.2%}"
    
    de2 = extract_debt_equity_ratio(df2)
    assert de2 > 5, f"银行D/E应高: {de2}"
    
    print("  ✓ 财务数据解析(消费+银行)")


# ============================================================
# 测试3: 巴菲特过滤器
# ============================================================
def test_buffett_filter():
    """验证三重过滤器: 能力圈/护城河/安全边际"""
    from data.financials import get_financial_summary, extract_roe_history
    from data.financials import extract_gross_margin_history, extract_debt_equity_ratio
    from data.financials import extract_latest_net_profit, extract_net_margin_history
    from signals.buffett import buffett_filter, Verdict
    
    # 茅台 — 应该卡在安全边际 (12.56亿股)
    df = get_financial_summary("600519")
    r = buffett_filter(
        symbol="600519", name="贵州茅台", industry="食品饮料", sector="consumer",
        fcf=extract_latest_net_profit(df) * 0.7,
        shares_outstanding=12.56,  # 真实股本
        roe_history=extract_roe_history(df),
        gross_margin_history=extract_gross_margin_history(df),
        debt_equity=extract_debt_equity_ratio(df),
        current_price=1373,
    )
    assert r.verdict == Verdict.FAIL_MARGIN, f"茅台应卡安全边际, 实际: {r.verdict}"
    assert r.avg_roe_5y > 0.25, f"茅台ROE: {r.avg_roe_5y}"
    
    # 招行 — 应该通过
    df2 = get_financial_summary("600036")
    r2 = buffett_filter(
        symbol="600036", name="招商银行", industry="银行", sector="bank",
        fcf=extract_latest_net_profit(df2) * 0.7,
        roe_history=extract_roe_history(df2),
        gross_margin_history=[],
        net_margin_history=extract_net_margin_history(df2),
        debt_equity=extract_debt_equity_ratio(df2),
        current_price=45.5,
    )
    assert r2.verdict == Verdict.PASS, f"招行应通过, 实际: {r2.verdict}"
    
    print("  ✓ 巴菲特过滤器(茅台拒/招行过)")


# ============================================================
# 测试4: 控制论
# ============================================================
def test_cybernetics():
    """验证市场状态检测"""
    from cybernetics.orchestrator import QuantOrchestrator, MarketRegime
    
    orch = QuantOrchestrator()
    snapshot = orch.detect()
    
    assert snapshot.regime != MarketRegime.UNKNOWN, "市场状态检测失败"
    assert len(snapshot.index_ma_trend) > 0, "均线趋势为空"
    
    params = orch.get_params()
    assert "position_size" in params, "自适应参数缺失"
    
    print(f"  ✓ 控制论(当前: {snapshot.regime.value} {snapshot.index_ma_trend[:30]}...)")


# ============================================================
# 测试5: 板块推断
# ============================================================
def test_sector_inference():
    """验证金融股自动分类"""
    from data.symbols import _infer_sector, _infer_industry
    
    tests = [
        ("601398", "工商银行", "bank", "银行"),
        ("601318", "中国平安", "insurance", "非银金融"),
        ("600030", "中信证券", "securities", "非银金融"),
        ("000776", "广发证券", "securities", "非银金融"),
        ("601628", "中国人寿", "insurance", "非银金融"),
        ("600919", "江苏银行", "bank", "银行"),
        ("600519", "贵州茅台", "consumer", "待分类"),
        ("002415", "海康威视", "consumer", "待分类"),
    ]
    
    for code, name, exp_sec, exp_ind in tests:
        sec = _infer_sector(code, name, "待分类")
        ind = _infer_industry(name)
        assert sec == exp_sec, f"{code} {name}: sector={sec} expected={exp_sec}"
        if exp_ind != "待分类":
            assert ind == exp_ind, f"{code} {name}: industry={ind} expected={exp_ind}"
    
    print("  ✓ 板块推断(8/8正确)")


# ============================================================
# 测试6: 多因子打分
# ============================================================
def test_multifactor():
    """验证多因子评分逻辑"""
    from signals.multifactor import MultiFactorScorer, compute_roe_trend
    
    scorer = MultiFactorScorer(regime="bull")
    
    # 完美股票应高分
    perfect = {
        "buffett_score": 90, "safety_margin": 0.50,
        "roe_5y": 0.25, "roe_trend": "up",
        "momentum_1m": 0.02, "momentum_3m": 0.05,
        "volatility": 0.15, "sector": "bank",
    }
    s1 = scorer.score(perfect)
    assert s1 > 70, f"完美股分太低: {s1}"
    
    # 垃圾股票应低分
    bad = {
        "buffett_score": 10, "safety_margin": -0.30,
        "roe_5y": 0.03, "roe_trend": "down",
        "momentum_1m": -0.15, "momentum_3m": -0.20,
        "volatility": 0.50, "sector": "consumer",
    }
    s2 = scorer.score(bad)
    assert s2 < 40, f"垃圾股分太高: {s2}"
    
    # ROE趋势
    assert compute_roe_trend([0.15, 0.17, 0.20]) == "up"
    assert compute_roe_trend([0.20, 0.17, 0.15]) == "down"
    assert compute_roe_trend([0.15, 0.16, 0.15]) == "flat"
    
    print("  ✓ 多因子打分(完美>70, 垃圾<40)")


# ============================================================
# 测试7: 边界情况
# ============================================================
def test_edge_cases():
    """验证边界: 空数据/极端值/错误输入"""
    from signals.buffett import buffett_filter, calc_margin_of_safety, Verdict
    
    # 空ROE
    r = buffett_filter(symbol="000000", name="test", industry="食品饮料",
                       roe_history=[], gross_margin_history=[], debt_equity=0)
    assert r.verdict in [Verdict.FAIL_MOAT, Verdict.INSUFFICIENT_DATA], f"空ROE应拒: {r.verdict}"
    
    # 零股本
    iv, _, margin, _ = calc_margin_of_safety(fcf=100, growth_rate=0.05, shares_outstanding=1, current_price=50)
    assert iv > 0, "DCF估值异常"
    
    # 负增长
    iv2, _, margin2, _ = calc_margin_of_safety(fcf=100, growth_rate=-0.05, shares_outstanding=1, current_price=50)
    assert iv2 > 0, "负增长DCF异常"
    
    # 行业不在能力圈
    r2 = buffett_filter(symbol="000000", name="test", industry="航天军工",
                        roe_history=[0.20]*5, gross_margin_history=[0.40]*5, debt_equity=0.5)
    assert r2.verdict == Verdict.FAIL_CIRCLE, f"航天应拒: {r2.verdict}"
    
    print("  ✓ 边界情况(空数据/负增长/未知行业)")


# ============================================================
# 运行所有测试
# ============================================================
if __name__ == "__main__":
    tests = [
        test_cache, test_financials, test_buffett_filter,
        test_cybernetics, test_sector_inference, test_multifactor,
        test_edge_cases,
    ]
    
    passed = 0
    failed = 0
    
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  ✗ {t.__name__}: {e}")
    
    print(f"\n{'='*40}")
    print(f"结果: {passed}通过 / {failed}失败 / {len(tests)}总计")
