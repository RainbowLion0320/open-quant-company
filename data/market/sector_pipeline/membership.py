"""Sector membership constants and stock-to-sector builder."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from data.storage.datahub import DataHub


SW_INDUSTRIES: dict[str, str] = {
    "801010": "农林牧渔", "801030": "基础化工", "801040": "钢铁",
    "801050": "有色金属", "801080": "电子", "801110": "家用电器",
    "801120": "食品饮料", "801130": "纺织服饰", "801140": "轻工制造",
    "801150": "医药生物", "801160": "公用事业", "801170": "交通运输",
    "801180": "房地产", "801200": "商贸零售", "801210": "社会服务",
    "801230": "综合", "801710": "建筑材料", "801720": "建筑装饰",
    "801730": "电力设备", "801740": "国防军工", "801750": "计算机",
    "801760": "传媒", "801770": "通信", "801780": "银行",
    "801790": "非银金融", "801880": "汽车", "801890": "机械设备",
    "801950": "石油石化", "801960": "煤炭", "801970": "环保",
    "801980": "美容护理",
}

_SW_NAME_ALIASES: dict[str, str] = {
    "采掘": "煤炭",
    "化工": "基础化工",
    "纺织服装": "纺织服饰",
    "休闲服务": "社会服务",
}


def _store(hub: DataHub | None = None) -> Path:
    """Return the sector store under the active DataHub."""
    hub = hub or DataHub()
    store = hub.store_path("sector")
    store.mkdir(parents=True, exist_ok=True)
    return store


def _snapshot_path(hub: DataHub, dimension: str, run_date: date) -> Path:
    return hub.dimension_path(dimension, YYYYMMDD=run_date.strftime("%Y%m%d"))


def _canonical_sector_name(name: str) -> str:
    return _SW_NAME_ALIASES.get(str(name).strip(), str(name).strip())


def build_membership(hub: DataHub | None = None) -> pd.DataFrame:
    """Build stock-sector membership from known symbol lists."""
    hub = hub or DataHub()

    from data.market.symbols import SYMBOL_INDUSTRY

    name_to_code = {name: code for code, name in SW_INDUSTRIES.items()}
    rows = []
    for symbol, industry in SYMBOL_INDUSTRY.items():
        if not industry or industry == "待分类":
            continue
        sector_name = _canonical_sector_name(industry)
        sector_code = name_to_code.get(sector_name, "")
        if not sector_code:
            continue
        rows.append({
            "symbol": symbol,
            "sector_code": sector_code,
            "sector_name": sector_name,
            "sector_level": 1,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        path = hub.dimension_path("sector_membership")
        hub.write_parquet(df, path, producer="sectors.build_membership")
    return df
