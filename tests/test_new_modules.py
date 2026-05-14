#!/usr/bin/env python3
"""Quick test for new modules"""
import sys, os
sys.path.insert(0, os.path.expanduser('~/quant-agent'))

import py_compile

for mod in ['signals/factors.py', 'backtest/analytics.py', 'backtest/pipeline.py', 'broker/__init__.py']:
    py_compile.compile(mod, doraise=True)
    print(f'SYNTAX OK: {mod}')

print()
from signals.factors import RawFactor as F, Factor
import pandas as pd

df = pd.DataFrame({
    'close': [10, 11, 12, 11, 13, 14, 15, 14, 16, 17],
    'roe': [0.12, 0.12, 0.15, 0.15, 0.18, 0.18, 0.20, 0.20, 0.22, 0.22],
    'pe_ttm': [25, 24, 22, 23, 20, 19, 18, 19, 16, 15],
}, index=pd.date_range('2025-01-01', periods=10, freq='B'))

close = F('close')
mom = Factor.pct_change(close, 3)
mom_result = mom.load(df)
print(f'Factor DSL: momentum 3d mean = {mom_result.mean():.4f}')

ma3 = Factor.rolling(close, 3, 'mean')
ma_result = ma3.load(df)
print(f'Factor DSL: MA3 = {[round(v,1) for v in ma_result.dropna().values]}')

from backtest.analytics import RiskAnalytics
returns = pd.Series([0.01, -0.02, 0.03, 0.01, -0.01, 0.02, 0.01, -0.03, 0.04, 0.01])
r = RiskAnalytics.compute(returns)
print(f'Analytics: sharpe={r.sharpe:.2f}, max_dd={r.max_drawdown:.4f}, win_rate={r.win_rate:.2f}')

from broker import PaperBroker
broker = PaperBroker(initial_cash=100000)
broker.set_prices({'000001': 12.50})
oid = broker.submit_order('000001', price=12.50, volume=1000, side='buy')
bal = broker.get_balance()
print(f'Broker: cash={bal.cash:.2f}, mv={bal.market_value:.2f}, total={bal.total_asset:.2f}')

print('\nALL TESTS PASSED')
