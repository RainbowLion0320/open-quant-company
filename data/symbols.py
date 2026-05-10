"""
股票池管理 — 基于沪深300+中证500 官方成分股（申万行业分类）

数据来源:
- 成分股: AKShare index_stock_cons_sina() (新浪)
- 沪深300 (000300): 300只大盘蓝筹
- 中证500 (000905): 500只中盘成长
- 申万一级行业: AKShare sw_index_first_info() (31个)
"""
import json, os
from dataclasses import dataclass, field
from typing import List, Dict, Optional

# ============================================================
# 加载原始数据
# ============================================================
_RAW_PATH = os.path.join(os.path.dirname(__file__), "universe_raw.json")

def _load_raw() -> list:
    if os.path.exists(_RAW_PATH):
        with open(_RAW_PATH) as f:
            return json.load(f)
    return []

# 全部成分股 (沪深300 + 中证500 去重)
ALL_STOCKS_RAW = _load_raw()

# ============================================================
# 申万一级行业（31个）
# ============================================================
SW_INDUSTRY_FIRST: Dict[str, str] = {
    "801010": "农林牧渔", "801030": "基础化工", "801040": "钢铁",
    "801050": "有色金属", "801080": "电子",   "801110": "家用电器",
    "801120": "食品饮料", "801130": "纺织服饰", "801140": "轻工制造",
    "801150": "医药生物", "801160": "公用事业", "801170": "交通运输",
    "801180": "房地产",   "801200": "商贸零售", "801210": "社会服务",
    "801230": "综合",     "801710": "建筑材料", "801720": "建筑装饰",
    "801730": "电力设备", "801740": "国防军工", "801750": "计算机",
    "801760": "传媒",     "801770": "通信",     "801780": "银行",
    "801790": "非银金融", "801880": "汽车",     "801890": "机械设备",
    "801950": "石油石化", "801960": "煤炭",     "801970": "环保",
    "801980": "美容护理",
}

# ============================================================
# 已知行业映射（从之前的手工分类 + 公开数据）
# ============================================================
KNOWN_INDUSTRY: Dict[str, str] = {
    # 食品饮料
    "600519": "食品饮料", "000858": "食品饮料", "000568": "食品饮料",
    "002304": "食品饮料", "600809": "食品饮料", "000596": "食品饮料",
    "603369": "食品饮料", "600559": "食品饮料", "600779": "食品饮料",
    "603589": "食品饮料", "603288": "食品饮料", "600887": "食品饮料",
    "000895": "食品饮料",
    # 家用电器
    "000333": "家用电器", "600690": "家用电器", "000651": "家用电器",
    "002032": "家用电器", "002050": "家用电器",
    # 医药生物
    "600276": "医药生物", "000538": "医药生物", "300760": "医药生物",
    "603259": "医药生物", "002001": "医药生物", "300015": "医药生物",
    "600085": "医药生物", "000963": "医药生物", "300122": "医药生物",
    "002007": "医药生物",
    # 银行
    "600036": "银行", "000001": "银行", "601166": "银行",
    "601398": "银行", "601288": "银行", "600016": "银行",
    # 非银金融
    "601318": "非银金融", "600030": "非银金融", "601688": "非银金融",
    "601601": "非银金融",
    # 能源/公用事业
    "601088": "煤炭", "600028": "石油石化", "601857": "石油石化",
    "600900": "公用事业", "600025": "公用事业", "601985": "公用事业",
    "600886": "公用事业", "600674": "公用事业", "600011": "公用事业",
    "003816": "公用事业",
    # 电子
    "002415": "电子",
    # 汽车
    "002050": "汽车",
}

# ============================================================
# 板块类型推断（名称匹配，不做手工映射）
# ============================================================

def _infer_sector(code: str, name: str, industry: str) -> str:
    """
    推断板块类型: bank / insurance / securities / consumer
    优先级: 行业分类 > 名称关键词 > 默认
    """
    # 申万行业直接判定
    if industry == "银行":
        return "bank"
    if industry == "非银金融":
        # 非银内部区分
        if any(kw in name for kw in ["保险", "人寿", "太保", "平安"]):
            return "insurance"
        if any(kw in name for kw in ["证券", "券商"]):
            return "securities"
        return "insurance"  # 非银默认保险

    # 名称关键词兜底（沪深300里行业分类可能缺失）
    if "银行" in name:
        return "bank"
    if any(kw in name for kw in ["保险", "人寿", "太保", "平安"]):
        return "insurance"
    if any(kw in name for kw in ["证券", "券商", "建投", "中信建投"]):
        return "securities"

    return "consumer"


# 同时推断申万行业
def _infer_industry(name: str) -> str:
    """从名称推断申万一级行业（仅用于 KNOWN_INDUSTRY 未覆盖的股票）"""
    if "银行" in name:
        return "银行"
    if any(kw in name for kw in ["保险", "人寿", "太保", "平安"]):
        return "非银金融"
    if any(kw in name for kw in ["证券", "券商"]):
        return "非银金融"
    return "待分类"


# ============================================================
# 便捷查询（基于 Tushare 数据）
# ============================================================

def _get_industry(code: str) -> str:
    """从 Tushare 申万二级 → 映射到申万一级"""
    from .industry import get_sw1
    return get_sw1(code)


def _get_name(code: str) -> str:
    """从 Tushare 获取公司名称"""
    from .industry import get_name as _t_name
    name = _t_name(code)
    if name and name != code:
        return name
    for s in ALL_STOCKS_RAW:
        if s["code"] == code:
            return s.get("name", code)
    return code


SYMBOL_NAME: Dict[str, str] = {}
SYMBOL_INDUSTRY: Dict[str, str] = {}
SYMBOL_SECTOR: Dict[str, str] = {}

# ============================================================
# 股票池分层
# ============================================================

# 默认池: 沪深300 (大盘核心，300只)
POOL_HS300: List[Dict] = [
    s for s in ALL_STOCKS_RAW
    if s.get("pool", "hs300") == "hs300"
]

# 如果 raw 数据没有 pool 字段（首次拉取），按市值排序取前300
if not POOL_HS300:
    sorted_by_cap = sorted(ALL_STOCKS_RAW, key=lambda x: -x.get("mktcap", 0))
    POOL_HS300 = sorted_by_cap[:300]

# 扩展池: 中证500
POOL_CSI500: List[Dict] = [
    s for s in ALL_STOCKS_RAW
    if s not in POOL_HS300
]

# ============================================================
# 活跃股票池
# ============================================================

# 当前使用的池（默认 top500，可通过环境变量切换）
ACTIVE_POOL = os.environ.get("QUANT_POOL", "all")  # all | top500 | hs300 | csi500

if ACTIVE_POOL == "csi500":
    CIRCLE_STOCKS = sorted(set(s["code"] for s in POOL_CSI500))
elif ACTIVE_POOL == "all":
    CIRCLE_STOCKS = sorted(set(s["code"] for s in ALL_STOCKS_RAW))
elif ACTIVE_POOL == "hs300":
    CIRCLE_STOCKS = sorted(set(s["code"] for s in POOL_HS300))
else:  # top500: 全量按市值取前500
    sorted_all = sorted(ALL_STOCKS_RAW, key=lambda x: -x.get("mktcap", 0))
    CIRCLE_STOCKS = sorted(set(s["code"] for s in sorted_all[:500]))

# ============================================================
# 填充映射表（动态推断，不手工维护）
# ============================================================

SYMBOL_NAME = {c: _get_name(c) for c in CIRCLE_STOCKS}
SYMBOL_INDUSTRY = {c: _get_industry(c) for c in CIRCLE_STOCKS}
SYMBOL_SECTOR = {
    c: _infer_sector(c, SYMBOL_NAME[c], SYMBOL_INDUSTRY[c])
    for c in CIRCLE_STOCKS
}

FALLBACK_SECTOR = "consumer"

# 行业 → 股票列表
INDUSTRY_STOCKS: Dict[str, List[str]] = {}
for code in CIRCLE_STOCKS:
    ind = SYMBOL_INDUSTRY[code]
    INDUSTRY_STOCKS.setdefault(ind, []).append(code)

# 能力圈: 全部出现的行业
CIRCLE_OF_COMPETENCE_INDUSTRIES: List[str] = sorted(set(SYMBOL_INDUSTRY.values()))

# ============================================================
# 基准指数
# ============================================================
BENCHMARKS = {
    "上证指数": "sh000001",
    "深证成指": "sz399001",
    "沪深300": "sh000300",
}

# 统计
TOTAL_POOL = len(ALL_STOCKS_RAW)
TOTAL_HS300 = len(POOL_HS300)
TOTAL_CSI500 = len(POOL_CSI500)
TOTAL_ACTIVE = len(CIRCLE_STOCKS)


@dataclass
class StockUniverse:
    symbols: List[str] = field(default_factory=lambda: CIRCLE_STOCKS.copy())
    benchmarks: List[str] = field(default_factory=lambda: list(BENCHMARKS.values()))

    @property
    def by_industry(self) -> Dict[str, List[str]]:
        return {ind: codes for ind, codes in INDUSTRY_STOCKS.items()}

    def filter_by_industry(self, industries: List[str]) -> List[str]:
        result = []
        for ind in industries:
            result.extend(INDUSTRY_STOCKS.get(ind, []))
        return [s for s in result if s in self.symbols]


def list_industries() -> Dict[str, str]:
    return SW_INDUSTRY_FIRST.copy()


def set_pool(pool_name: str):
    """切换股票池：hs300 / csi500 / all"""
    global ACTIVE_POOL, CIRCLE_STOCKS, SYMBOL_NAME, SYMBOL_INDUSTRY, INDUSTRY_STOCKS, CIRCLE_OF_COMPETENCE_INDUSTRIES
    ACTIVE_POOL = pool_name
    if pool_name == "csi500":
        CIRCLE_STOCKS = sorted(set(s["code"] for s in POOL_CSI500))
    elif pool_name == "all":
        CIRCLE_STOCKS = sorted(set(s["code"] for s in ALL_STOCKS_RAW))
    else:
        CIRCLE_STOCKS = sorted(set(s["code"] for s in POOL_HS300))
    SYMBOL_NAME = {c: _get_name(c) for c in CIRCLE_STOCKS}
    SYMBOL_INDUSTRY = {c: _get_industry(c) for c in CIRCLE_STOCKS}
    INDUSTRY_STOCKS = {}
    for code in CIRCLE_STOCKS:
        ind = SYMBOL_INDUSTRY[code]
        INDUSTRY_STOCKS.setdefault(ind, []).append(code)
    CIRCLE_OF_COMPETENCE_INDUSTRIES = sorted(set(SYMBOL_INDUSTRY.values()))
