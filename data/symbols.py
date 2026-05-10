"""
股票池管理 — 基于申万一级行业分类（官方数据源）

数据来源:
- 申万一级行业名称: AKShare sw_index_first_info() (31个行业)
- 股票→行业映射: 按 2024 申万分类标准
- A股代码列表: AKShare stock_info_a_code_name() (5513只)
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional

# ============================================================
# 申万一级行业（31个）— 来源: sw_index_first_info()
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
# 巴菲特能力圈 — 用户选择的申万行业（可自由增删）
# ============================================================
CIRCLE_OF_COMPETENCE_INDUSTRIES: List[str] = [
    "食品饮料",   # 白酒/调味品/乳制品/肉制品
    "家用电器",   # 白电/小家电
    "医药生物",   # 制药/器械/服务
    "银行",       # 国有/股份/城商行
    "非银金融",   # 保险/券商
    "煤炭",       # 能源央企
    "公用事业",   # 电力
    "汽车",       # 汽车及零部件
]

# ============================================================
# 股票池 — 申万行业分类 + 公司名称（50只 + 扩展空间）
# ============================================================
STOCK_UNIVERSE: List[Dict] = [
    # ----- 食品饮料 (801120) -----
    {"code": "600519", "name": "贵州茅台", "industry": "食品饮料"},
    {"code": "000858", "name": "五粮液",   "industry": "食品饮料"},
    {"code": "000568", "name": "泸州老窖", "industry": "食品饮料"},
    {"code": "002304", "name": "洋河股份", "industry": "食品饮料"},
    {"code": "600809", "name": "山西汾酒", "industry": "食品饮料"},
    {"code": "000596", "name": "古井贡酒", "industry": "食品饮料"},
    {"code": "603369", "name": "今世缘",   "industry": "食品饮料"},
    {"code": "600559", "name": "老白干酒", "industry": "食品饮料"},
    {"code": "600779", "name": "水井坊",   "industry": "食品饮料"},
    {"code": "603589", "name": "口子窖",   "industry": "食品饮料"},
    {"code": "603288", "name": "海天味业", "industry": "食品饮料"},
    {"code": "600887", "name": "伊利股份", "industry": "食品饮料"},
    {"code": "000895", "name": "双汇发展", "industry": "食品饮料"},

    # ----- 家用电器 (801110) -----
    {"code": "000333", "name": "美的集团", "industry": "家用电器"},
    {"code": "600690", "name": "海尔智家", "industry": "家用电器"},
    {"code": "000651", "name": "格力电器", "industry": "家用电器"},
    {"code": "002032", "name": "苏泊尔",   "industry": "家用电器"},
    {"code": "002050", "name": "三花智控", "industry": "家用电器"},

    # ----- 医药生物 (801150) -----
    {"code": "600276", "name": "恒瑞医药", "industry": "医药生物"},
    {"code": "000538", "name": "云南白药", "industry": "医药生物"},
    {"code": "300760", "name": "迈瑞医疗", "industry": "医药生物"},
    {"code": "603259", "name": "药明康德", "industry": "医药生物"},
    {"code": "002001", "name": "新和成",   "industry": "医药生物"},
    {"code": "300015", "name": "爱尔眼科", "industry": "医药生物"},
    {"code": "600085", "name": "同仁堂",   "industry": "医药生物"},
    {"code": "000963", "name": "华东医药", "industry": "医药生物"},
    {"code": "300122", "name": "智飞生物", "industry": "医药生物"},
    {"code": "002007", "name": "华兰生物", "industry": "医药生物"},

    # ----- 银行 (801780) -----
    {"code": "600036", "name": "招商银行", "industry": "银行"},
    {"code": "000001", "name": "平安银行", "industry": "银行"},
    {"code": "601166", "name": "兴业银行", "industry": "银行"},
    {"code": "601398", "name": "工商银行", "industry": "银行"},
    {"code": "601288", "name": "农业银行", "industry": "银行"},
    {"code": "600016", "name": "民生银行", "industry": "银行"},

    # ----- 非银金融 (801790) -----
    {"code": "601318", "name": "中国平安", "industry": "非银金融"},
    {"code": "600030", "name": "中信证券", "industry": "非银金融"},
    {"code": "601688", "name": "华泰证券", "industry": "非银金融"},
    {"code": "601601", "name": "中国太保", "industry": "非银金融"},

    # ----- 煤炭 (801960) -----
    {"code": "601088", "name": "中国神华", "industry": "煤炭"},
    {"code": "600028", "name": "中国石化", "industry": "石油石化"},
    {"code": "601857", "name": "中国石油", "industry": "石油石化"},

    # ----- 公用事业 (801160) -----
    {"code": "600900", "name": "长江电力", "industry": "公用事业"},
    {"code": "600025", "name": "华能水电", "industry": "公用事业"},
    {"code": "601985", "name": "中国核电", "industry": "公用事业"},
    {"code": "600886", "name": "国投电力", "industry": "公用事业"},
    {"code": "600674", "name": "川投能源", "industry": "公用事业"},
    {"code": "600011", "name": "华能国际", "industry": "公用事业"},
    {"code": "003816", "name": "中国广核", "industry": "公用事业"},

    # ----- 汽车 (801880) -----
    # 预留空间
]

# 总股票数
TOTAL_STOCKS = len(STOCK_UNIVERSE)

# ============================================================
# 便捷查询
# ============================================================

# 代码 → 名称
SYMBOL_NAME: Dict[str, str] = {s["code"]: s["name"] for s in STOCK_UNIVERSE}

# 代码 → 行业
SYMBOL_INDUSTRY: Dict[str, str] = {s["code"]: s["industry"] for s in STOCK_UNIVERSE}

# 行业 → 股票列表
INDUSTRY_STOCKS: Dict[str, List[str]] = {}
for s in STOCK_UNIVERSE:
    INDUSTRY_STOCKS.setdefault(s["industry"], []).append(s["code"])

# 能力圈内的股票列表
CIRCLE_STOCKS = sorted(set(
    code for ind, codes in INDUSTRY_STOCKS.items()
    if ind in CIRCLE_OF_COMPETENCE_INDUSTRIES
    for code in codes
))

# ============================================================
# 板块类型（用于巴菲特过滤器行业适配）
# ============================================================
INDUSTRY_SECTOR_TYPE: Dict[str, str] = {
    "银行": "finance",
    "非银金融": "finance",
}

SYMBOL_SECTOR: Dict[str, str] = {
    # 银行
    "600036": "bank", "000001": "bank", "601166": "bank",
    "601398": "bank", "601288": "bank", "600016": "bank",
    # 保险
    "601318": "insurance", "601601": "insurance",
    # 券商
    "600030": "securities", "601688": "securities",
}

FALLBACK_SECTOR = "consumer"

# ============================================================
# 基准指数
# ============================================================
BENCHMARKS = {
    "上证指数": "sh000001",
    "深证成指": "sz399001",
    "沪深300": "sh000300",
}


@dataclass
class StockUniverse:
    """当前股票池"""
    symbols: List[str] = field(default_factory=lambda: CIRCLE_STOCKS.copy())
    benchmarks: List[str] = field(default_factory=lambda: list(BENCHMARKS.values()))

    @property
    def by_industry(self) -> Dict[str, List[str]]:
        return {
            ind: codes
            for ind, codes in INDUSTRY_STOCKS.items()
            if ind in CIRCLE_OF_COMPETENCE_INDUSTRIES
        }

    def filter_by_industry(self, industries: List[str]) -> List[str]:
        result = []
        for ind in industries:
            result.extend(INDUSTRY_STOCKS.get(ind, []))
        return [s for s in result if s in self.symbols]


def list_available_industries() -> Dict[str, str]:
    """列出所有申万一级行业"""
    return SW_INDUSTRY_FIRST.copy()


def add_to_circle(industry: str):
    """添加行业到能力圈"""
    if industry not in SW_INDUSTRY_FIRST.values():
        raise ValueError(f"'{industry}' 不是有效的申万一级行业")
    if industry not in CIRCLE_OF_COMPETENCE_INDUSTRIES:
        CIRCLE_OF_COMPETENCE_INDUSTRIES.append(industry)
