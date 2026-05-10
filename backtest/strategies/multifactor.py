"""
多因子月度调仓策略 — Backtrader

每月末:
  1. 对所有股票计算多因子得分
  2. 选 Top-N, 买/调仓
  3. 控制论判市 → 调整仓位和最大持仓
"""
import backtrader as bt
import numpy as np
from datetime import datetime, timedelta


class MultiFactorMonthly(bt.Strategy):
    """
    多因子月度调仓
    每月最后一个交易日重打分调仓
    """

    params = dict(
        top_n=10,              # 持仓数
        max_per_sector=3,      # 每板块最多
        rebalance_day=25,      # 每月25号附近调仓
        position_bull=0.30,    # 牛市仓位
        position_side=0.15,    # 震荡仓位
        position_bear=0.05,    # 熊市仓位
        max_pos_bull=10, max_pos_side=5, max_pos_bear=3,
        regime_data_idx=0,     # regime数据索引
    )

    def __init__(self):
        self.last_rebalance = None
        self.current_scores = {}
        self.order_list = []

    def _regime(self):
        if len(self.datas) > self.p.regime_data_idx:
            r = self.datas[self.p.regime_data_idx].close[0]
            try: return int(r)
            except: pass
        return 0

    def _get_params(self):
        regime = self._regime()
        if regime > 0:
            return self.p.position_bull, self.p.max_pos_bull
        elif regime < 0:
            return self.p.position_bear, self.p.max_pos_bear
        return self.p.position_side, self.p.max_pos_side

    def _should_rebalance(self, dt):
        """判断是否该调仓了"""
        if self.last_rebalance is None:
            return True
        # 每月调仓: 间隔 >= 20 个交易日
        if hasattr(self.last_rebalance, 'date'):
            last_dt = self.last_rebalance
        else:
            last_dt = datetime.strptime(str(self.last_rebalance)[:10], "%Y-%m-%d")
        current_dt = datetime.strptime(str(dt)[:10], "%Y-%m-%d")
        return (current_dt - last_dt).days >= 20

    def _compute_scores(self):
        """计算所有股票当前的多因子得分"""
        scores = {}
        for i, data in enumerate(self.datas):
            if data._name == "REGIME":
                continue
            if len(data) < 60:
                continue

            symbol = data._name.split("_")[0]

            # 技术因子
            close_arr = np.array(data.close.array[-60:])
            if len(close_arr) < 60:
                continue
            current = close_arr[-1]

            # 1月动量
            mom_1m = (current / close_arr[-21] - 1) if len(close_arr) >= 21 else 0
            # 3月动量
            mom_3m = (current / close_arr[-60] - 1) if len(close_arr) >= 60 else 0
            # 波动率
            rets = np.diff(close_arr[-21:]) / close_arr[-21:-1]
            vol = np.std(rets) * np.sqrt(252) if len(rets) > 0 else 0.3

            # 用 close 价本身做最简单的排序（真实场景会接入多因子引擎）
            # 这里用 1月动量 + 低波动 模拟打分
            score = 50 + mom_1m * 100 - vol * 50
            scores[symbol] = score

        return scores

    def _rebalance(self):
        """调仓"""
        scores = self._compute_scores()
        pos_pct, max_pos = self._get_params()

        # 排序选 Top-N
        sorted_stocks = sorted(scores.items(), key=lambda x: -x[1])
        target = {s for s, _ in sorted_stocks[:max_pos]}
        current = {d._name.split("_")[0] for d in self.datas
                   if d._name != "REGIME" and self.getposition(d).size > 0}

        # 卖出不在目标池的
        for data in self.datas:
            if data._name == "REGIME":
                continue
            sym = data._name.split("_")[0]
            pos = self.getposition(data)
            if pos.size > 0 and sym not in target:
                self.close(data)

        # 买入目标池中未持仓的
        value = self.broker.getvalue()
        for data in self.datas:
            if data._name == "REGIME":
                continue
            sym = data._name.split("_")[0]
            if sym in target and self.getposition(data).size == 0:
                size = int(value * pos_pct / data.close[0] // 100) * 100
                if size >= 100 and len(self.broker.positions) < max_pos:
                    self.buy(data, size=size)

        self.current_scores = scores
        self.last_rebalance = self.datas[0].datetime.date(0)

    def next(self):
        # 跳过 REGIME 数据
        if self.data._name == "REGIME":
            return

        dt = self.datas[0].datetime.date(0)
        if self._should_rebalance(dt):
            self._rebalance()

    def notify_order(self, order):
        if order.status == order.Completed:
            pass

    def stop(self):
        ret = (self.broker.getvalue() / self.broker.startingcash - 1) * 100
        self.log(f"结束 {ret:.2f}%")

    def log(self, txt, doprint=False):
        if doprint:
            print(txt)
