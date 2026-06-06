"""
Data Fetchers — New data dimensions (Phase 4.1)

All fetchers use AKShare (free, unlimited) — zero Tushare积分 required.

P0 (核心因子):
  moneyflow.py — 个股资金流向 (主力/散户净流入, smart money ratio)
  holders.py   — 股东户数 (筹码集中度)

P1 (宏观/情绪):
  macro.py     — 宏观经济指标 (M2/PMI/CPI/PPI/GDP/Shibor/LPR)

派生因子:
  Each module exports a derive_*_factors() function that converts raw data
  to normalized factor values suitable for PIT feature store.
"""
