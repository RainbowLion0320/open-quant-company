#!/usr/bin/env python3
"""Quick test for new modules"""
import sys, os
from pathlib import Path

import py_compile

for mod in ['signals/expression.py', 'signals/dsl_parser.py', 'backtest/analytics.py', 'backtest/pipeline.py', 'broker/__init__.py']:
    py_compile.compile(mod, doraise=True)
    print(f'SYNTAX OK: {mod}')

print()
from signals.expression import Ret, Delta, MA
import pandas as pd

df = pd.DataFrame({
    'close': [10, 11, 12, 11, 13, 14, 15, 14, 16, 17],
}, index=pd.date_range('2025-01-01', periods=10, freq='B'))

def compute_series(factor, df):
    return pd.Series([factor.compute(df, i) for i in range(len(df))], index=df.index)

close = Ret("close")
mom_factor = Delta(close, 3) / close
mom_result = compute_series(mom_factor, df)
print(f'Factor DSL: momentum 3d mean = {mom_result.mean():.4f}')

ma_result = compute_series(MA(close, 3), df)
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
