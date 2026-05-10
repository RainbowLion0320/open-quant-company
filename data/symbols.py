"""
股票池管理 — 定义监控范围、能力圈行业分类
"""
from dataclasses import dataclass, field
from typing import List, Dict

# 能力圈行业 → 代表个股 -----
# 聚焦巴菲特能力圈内的行业
CIRCLE_OF_COMPETENCE: Dict[str, List[str]] = {
    "白酒":    ["600519", "000858", "000568", "002304", "600809"],
    "消费":    ["000333", "002415", "600887", "603288", "600690"],
    "医药":    ["600276", "000538", "300760", "603259", "002001"],
    "金融":    ["600036", "601318", "000001", "600030", "601166"],
    "能源":    ["601088", "600028", "601857", "600900", "600025"],
}

# 行业 → 板块类型（用于巴菲特过滤器行业适配）
INDUSTRY_SECTOR_TYPE: Dict[str, str] = {
    "白酒": "consumer",
    "消费": "consumer",
    "医药": "manufacturing",
    "金融": "finance",
    "能源": "manufacturing",
}

# 个股 → 细分板块（金融行业内区分银行/保险/券商）
SYMBOL_SECTOR: Dict[str, str] = {
    # 银行
    "600036": "bank",
    "000001": "bank",
    "601166": "bank",
    # 保险
    "601318": "insurance",
    # 券商
    "600030": "securities",
}

# 默认板块类型（未在 SYMBOL_SECTOR 中的归为 consumer/manufacturing）
FALLBACK_SECTOR = "consumer"

# 沪深300核心标的（大盘基准池）
HS300_CORE = [
    "600519", "000858", "601318", "600036", "000333",
    "600276", "601088", "600900", "600030", "000001",
    "002415", "600887", "000538", "600809", "300750",
]

# Benchmark指数
BENCHMARKS = {
    "上证指数": "sh000001",
    "深证成指": "sz399001",
    "沪深300": "sh000300",
}


@dataclass
class StockUniverse:
    """当前股票池"""
    symbols: List[str] = field(default_factory=lambda: list(
        set().union(*CIRCLE_OF_COMPETENCE.values())
    ))
    benchmarks: List[str] = field(default_factory=lambda: list(BENCHMARKS.values()))

    @property
    def by_industry(self) -> Dict[str, List[str]]:
        """按行业分组"""
        return {
            industry: [s for s in stocks if s in self.symbols]
            for industry, stocks in CIRCLE_OF_COMPETENCE.items()
        }

    def filter_by_industry(self, industries: List[str]) -> List[str]:
        """按行业过滤"""
        result = []
        for ind in industries:
            result.extend(CIRCLE_OF_COMPETENCE.get(ind, []))
        return [s for s in result if s in self.symbols]
