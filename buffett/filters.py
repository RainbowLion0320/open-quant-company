"""
巴菲特决策约束层 — 安全边际、护城河、能力圈三重过滤

核心理念（引用自巴菲特致股东信）：
1. 安全边际 (Margin of Safety): "用40美分买1美元的东西"
2. 护城河 (Moat): "伟大的公司有持久的竞争优势"
3. 能力圈 (Circle of Competence): "知道自己不知道什么，和知道自己知道什么同样重要"

作用：在信号系统之上增加一层硬约束——不符合标准的，信号再强也不操作。
"""
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from enum import Enum
import yaml
import os


# ----- 配置加载 -----
_config = None


def _load_config():
    global _config
    if _config is None:
        path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")
        with open(path) as f:
            _config = yaml.safe_load(f)["buffett"]
    return _config


# ----- 过滤结果 -----
class Verdict(Enum):
    PASS = "✅"
    FAIL_MARGIN = "❌ 安全边际不足"
    FAIL_MOAT = "❌ 护城河不够宽"
    FAIL_CIRCLE = "❌ 超出能力圈"
    INSUFFICIENT_DATA = "⚠️ 数据不足"


@dataclass
class BuffettScore:
    """巴菲特综合评分"""
    symbol: str
    name: str = ""
    verdict: Verdict = Verdict.INSUFFICIENT_DATA
    # 板块
    sector: str = ""              # bank / insurance / securities / consumer / manufacturing
    industry: str = ""
    # 安全边际
    dcf_value: float = 0.0       # DCF估算内在价值
    market_cap: float = 0.0      # 当前市值
    safety_margin_pct: float = 0.0  # 安全边际百分比
    margin_pass: bool = False
    # 护城河（消费/制造）
    avg_roe_5y: float = 0.0      # 5年平均ROE
    avg_gross_margin_5y: float = 0.0
    debt_equity_ratio: float = 0.0
    # 护城河（金融板块专属）
    avg_net_margin_5y: float = 0.0  # 5年平均销售净利率
    moat_pass: bool = False
    # 能力圈
    in_circle: bool = False
    # 综合
    score: int = 0               # 0-100 综合得分
    details: List[str] = field(default_factory=list)


# ----- 安全边际 (Margin of Safety) -----
def calc_margin_of_safety(
    fcf: float,              # 自由现金流（亿）
    growth_rate: float,      # 未来5年平均增长率
    shares_outstanding: float,  # 总股本（亿股）
    current_price: float,    # 当前股价
) -> Tuple[float, float, float, bool]:
    """
    简化DCF估值模型
    返回: (内在价值/股, 当前股价, 安全边际%, 是否通过)
    """
    cfg = _load_config()["margin_of_safety"]
    discount = cfg["dcf_discount_rate"]
    terminal_g = cfg["growth_rate_terminal"]
    required_margin = cfg["safety_margin_pct"]

    # 两阶段DCF: 高增长期(5年) + 永续期
    cashflows = [fcf * (1 + growth_rate) ** i for i in range(1, 6)]

    # 永续价值
    terminal_value = cashflows[-1] * (1 + terminal_g) / (discount - terminal_g)

    # 折现
    pv_cashflows = sum(cf / (1 + discount) ** i for i, cf in enumerate(cashflows, 1))
    pv_terminal = terminal_value / (1 + discount) ** 5

    enterprise_value = pv_cashflows + pv_terminal
    intrinsic_per_share = enterprise_value / shares_outstanding

    margin = 1 - current_price / intrinsic_per_share if intrinsic_per_share > 0 else -1
    passed = margin >= required_margin

    return intrinsic_per_share, current_price, margin, passed


# ----- 护城河 (Moat) -----
def assess_moat(
    roe_history: List[float],         # 历年ROE
    gross_margin_history: List[float],  # 历年毛利率（金融板块为空）
    debt_equity: float,                # 最新负债权益比（产权比率）
    net_margin_history: List[float] = None,  # 销售净利率（金融板块替代毛利率）
    sector: str = "consumer",          # 板块类型
) -> Tuple[float, float, float, bool, List[str]]:
    """
    护城河评估 — 板块感知
    消费/制造: ROE + 毛利率 + 负债权益比
    金融板块: ROE + 销售净利率 + 负债权益比（放宽）
    返回: (avg_roe, avg_margin_or_gm, debt_equity, passed, 详细说明)
    """
    cfg = _load_config()["moat"]
    min_years = cfg["min_roe_years"]

    # 加载板块特定参数
    sector_cfg = cfg.get("sectors", {}).get(sector, {})
    min_roe = sector_cfg.get("min_roe", cfg["min_roe"])
    max_de = sector_cfg.get("max_debt_equity", cfg["max_debt_equity"])
    skip_gm = sector_cfg.get("skip_gross_margin", False)
    min_gm = sector_cfg.get("min_gross_margin", cfg.get("min_gross_margin", 0.30))
    min_nm = sector_cfg.get("min_net_margin", 0.15)
    min_gm = sector_cfg.get("min_gross_margin", cfg.get("min_gross_margin", 0.30))

    details = []
    passed = True

    # 1. ROE检查（所有板块通用，阈值可能不同）
    recent_roe = roe_history[-min_years:] if len(roe_history) >= min_years else roe_history
    avg_roe = sum(recent_roe) / len(recent_roe) if recent_roe else 0

    years_above = sum(1 for r in recent_roe if r >= min_roe)
    if years_above < min_years:
        passed = False
        details.append(f"ROE>{min_roe*100:.0f}%仅{years_above}/{min_years}年 (平均{avg_roe*100:.1f}%)")
    else:
        details.append(f"ROE>{min_roe*100:.0f}%持续{years_above}年 ✓ (平均{avg_roe*100:.1f}%)")

    # 2. 利润率检查 — 金融板块用净利率，消费/制造用毛利率
    if skip_gm:
        # 金融板块：用销售净利率替代毛利率
        nm_history = net_margin_history or []
        avg_nm = sum(nm_history) / len(nm_history) if nm_history else 0
        if avg_nm < min_nm:
            passed = False
            details.append(f"销售净利率{avg_nm*100:.1f}% < {min_nm*100:.0f}% ({sector})")
        else:
            details.append(f"销售净利率{avg_nm*100:.1f}% ✓ ({sector}标准{min_nm*100:.0f}%)")
        avg_gm = 0  # 金融板块无毛利率
    else:
        # 消费/制造：标准毛利率检查
        avg_gm = sum(gross_margin_history) / len(gross_margin_history) if gross_margin_history else 0
        if avg_gm < min_gm:
            passed = False
            details.append(f"毛利率{avg_gm*100:.1f}% < {min_gm*100:.0f}%")
        else:
            details.append(f"毛利率{avg_gm*100:.1f}% ✓")
        avg_nm = 0

    # 3. 负债检查（所有板块，阈值不同）
    if debt_equity > max_de:
        passed = False
        details.append(f"负债权益比{debt_equity:.1f} > {max_de:.0f} ({sector})")
    else:
        details.append(f"负债权益比{debt_equity:.1f} ✓ ({sector}上限{max_de:.0f})")

    return avg_roe, avg_gm, debt_equity, passed, details, avg_nm


# ----- 能力圈 (Circle of Competence) -----
def check_circle(industry: str) -> Tuple[bool, str]:
    """
    检查是否在能力圈内
    """
    cfg = _load_config()["circle_of_competence"]
    industries = cfg["industries"]
    in_circle = industry in industries
    return in_circle, industry


# ----- 综合过滤器 -----
def buffett_filter(
    symbol: str,
    name: str = "",
    industry: str = "",
    sector: str = "consumer",
    fcf: float = 0,
    growth_rate: float = 0.05,
    shares_outstanding: float = 1,
    current_price: float = 0,
    roe_history: List[float] = None,
    gross_margin_history: List[float] = None,
    net_margin_history: List[float] = None,
    debt_equity: float = 0,
) -> BuffettScore:
    """
    巴菲特三重过滤器——一站式评估
    顺序：能力圈 → 护城河 → 安全边际（成本由低到高）
    板块感知：金融行业自动切换为 ROE+净利率+放宽杠杆 的护城河检查
    """
    score = BuffettScore(symbol=symbol, name=name, industry=industry, sector=sector)

    # 1. 能力圈（最快检查）
    in_circle, industry_name = check_circle(industry)
    score.in_circle = in_circle
    score.industry = industry_name
    if not in_circle:
        score.verdict = Verdict.FAIL_CIRCLE
        score.details = [f"行业'{industry}'不在能力圈内"]
        return score

    # 2. 护城河（板块感知）
    roe_history = roe_history or []
    gross_margin_history = gross_margin_history or []
    net_margin_history = net_margin_history or []
    avg_roe, avg_gm, de, moat_pass, moat_details, avg_nm = assess_moat(
        roe_history, gross_margin_history, debt_equity,
        net_margin_history=net_margin_history,
        sector=sector,
    )
    score.avg_roe_5y = avg_roe
    score.avg_gross_margin_5y = avg_gm
    score.avg_net_margin_5y = avg_nm
    score.debt_equity_ratio = de
    score.moat_pass = moat_pass
    score.details = moat_details
    if not moat_pass:
        score.verdict = Verdict.FAIL_MOAT
        return score

    # 3. 安全边际
    iv_per_share, price, margin, margin_pass = calc_margin_of_safety(
        fcf, growth_rate, shares_outstanding, current_price
    )
    score.dcf_value = iv_per_share
    score.market_cap = price * shares_outstanding
    score.safety_margin_pct = margin
    score.margin_pass = margin_pass
    score.details.append(
        f"内在价值: {iv_per_share:.2f}, 安全边际: {margin*100:.1f}%"
        f"({'✓' if margin_pass else '✗'})"
    )
    if not margin_pass:
        score.verdict = Verdict.FAIL_MARGIN
        return score

    # 全部通过 — 综合评分（按板块调整权重）
    score.verdict = Verdict.PASS
    # 金融板块用净利率替代毛利率参与评分
    margin_indicator = avg_nm if avg_nm > 0 else avg_gm
    score.score = min(100, int(
        30 * min(avg_roe / 0.25, 1.0) +         # ROE贡献
        20 * min(margin_indicator / 0.60, 1.0) + # 利润率贡献
        50 * min(margin / 0.50, 1.0)             # 安全边际贡献
    ))
    return score
