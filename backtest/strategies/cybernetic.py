"""
控制论自适应策略 — 根据市场状态切换行为模式

核心理念（钱学森控制论）:
  不预测市场方向，但检测市场状态，根据不同状态切换策略逻辑
  
三态:
  牛市 → 趋势跟踪: MA多头持有, 放宽止损, 不止盈
  震荡 → MA波段:   金叉买死叉卖, 紧止损
  熊市 → 防御:     轻仓或空仓, 严格止损
"""
import backtrader as bt
from backtrader.indicators import SMA, CrossOver
import pandas as pd


class CyberneticStrategy(bt.Strategy):
    """
    控制论自适应策略
    市场状态通过 regime_line 数据传入 (0=熊 -1=震荡 1=牛)
    """

    params = dict(
        ma_short=10, ma_long=20,
        stop_loss_bull=-0.08,   # 牛市宽止损
        stop_loss_side=-0.05,   # 震荡中止损
        stop_loss_bear=-0.03,   # 熊市紧止损
        position_bull=0.30,     # 牛市仓位
        position_side=0.15,     # 震荡仓位
        position_bear=0.05,     # 熊市仓位
        max_pos_bull=8, max_pos_side=5, max_pos_bear=2,
        score_weight=True,
        regime_data_idx=1,      # regime 数据的 data feed 索引
    )

    def __init__(self):
        self.inds = {}  # data_name -> {ma_short, ma_long, cross}
        self.entry_price = {}
        self.order = {}
        self.trades = 0
        self.consec_loss = 0
        for d in self.datas:
            if d._name == "REGIME":
                continue
            ma_s = SMA(d.close, period=self.p.ma_short)
            ma_l = SMA(d.close, period=self.p.ma_long)
            self.inds[d._name] = {
                'ma_short': ma_s,
                'ma_long': ma_l,
                'cross': CrossOver(ma_s, ma_l),
            }
            self.entry_price[d._name] = None
            self.order[d._name] = None

    def _regime(self):
        """读取当前 bar 的市场状态"""
        if len(self.datas) > self.p.regime_data_idx:
            r = self.datas[self.p.regime_data_idx].close[0]
            try:
                return int(r)
            except:
                pass
        return 0  # default: sideways

    def _score_weight(self, d=None):
        if not self.p.score_weight:
            return 1.0
        if d is None:
            d = self.data
        name = d._name
        if "_" in name:
            try:
                return 0.5 + float(name.rsplit("_", 1)[-1]) / 100.0
            except ValueError:
                pass
        return 1.0

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        dname = order.data._name
        if dname == "REGIME":
            return
        if dname not in self.entry_price:
            self.entry_price[dname] = None
        if dname not in self.order:
            self.order[dname] = None
        if order.status == order.Completed:
            if order.isbuy():
                self.entry_price[dname] = order.executed.price
            else:
                if self.entry_price.get(dname):
                    pnl = (order.executed.price - self.entry_price[dname]) / self.entry_price[dname]
                    self.trades += 1
                    self.consec_loss = self.consec_loss + 1 if pnl < 0 else 0
                self.entry_price[dname] = None
        self.order[dname] = None

    def next(self):
        # 遍历所有股票数据（跳过 REGIME）
        for d in self.datas:
            if d._name == "REGIME":
                continue
            self._next_data(d)

    def _next_data(self, d):
        dname = d._name
        ind = self.inds[dname]

        if self.order.get(dname):
            return

        regime = self._regime()

        # 熊市熔断：连续亏3次暂停
        if self.consec_loss >= 3 and regime <= 0:
            return

        # 当前参数
        if regime > 0:  # BULL
            stop_loss = self.p.stop_loss_bull
            pos_pct = self.p.position_bull
            max_pos = self.p.max_pos_bull
        elif regime < 0:  # BEAR
            stop_loss = self.p.stop_loss_bear
            pos_pct = self.p.position_bear
            max_pos = self.p.max_pos_bear
        else:  # SIDEWAYS
            stop_loss = self.p.stop_loss_side
            pos_pct = self.p.position_side
            max_pos = self.p.max_pos_side

        pos = self.getposition(d)

        # 止损
        if pos and self.entry_price.get(dname):
            loss = (d.close[0] - self.entry_price[dname]) / self.entry_price[dname]
            if loss <= stop_loss:
                self.order[dname] = self.close(data=d)
                return

        # 仓位上限
        if len(self.broker.positions) >= max_pos and not pos:
            return

        # 信号 — 按 regime 不同逻辑
        if regime > 0:
            # 牛市: 金叉买入，不因死叉卖出（趋势跟踪）
            if ind['cross'] > 0 and not pos:
                w = self._score_weight(d)
                size = int(self.broker.getvalue() * pos_pct / d.close[0]
                           * w // 100) * 100
                if size >= 100:
                    self.order[dname] = self.buy(data=d, size=size)
            # 牛市死叉不卖（放宽），只靠止损退出

        elif regime < 0:
            # 熊市: 几乎不买，只管理已有仓位
            if ind['cross'] < 0 and pos:
                self.order[dname] = self.close(data=d)

        else:
            # 震荡: 金叉买，死叉卖（波段操作）
            if ind['cross'] > 0 and not pos:
                w = self._score_weight(d)
                size = int(self.broker.getvalue() * pos_pct / d.close[0]
                           * w // 100) * 100
                if size >= 100:
                    self.order[dname] = self.buy(data=d, size=size)
            elif ind['cross'] < 0 and pos:
                self.order[dname] = self.close(data=d)

    def stop(self):
        ret = (self.broker.getvalue() / self.broker.startingcash - 1) * 100
        self.log(f"结束 {ret:.2f}% {self.trades}笔")

    def log(self, txt, doprint=False):
        if doprint:
            dt = self.datas[0].datetime.date(0)
            print(f"[{dt}] {txt}")


def make_regime_data(benchmark_df):
    """
    从基准数据生成市场状态序列 (1=bull, 0=sideways, -1=bear)
    每根 bar 标注该日的市场状态
    """
    close = benchmark_df['close'].values
    regime = pd.Series(0, index=benchmark_df.index, dtype=int)

    for i in range(60, len(close)):
        c = close[i]
        ma5 = close[i-5:i].mean()
        ma20 = close[i-20:i].mean()
        ma60 = close[i-60:i].mean()

        if c > ma5 > ma20 > ma60:
            regime.iloc[i] = 1   # bull
        elif c < ma5 < ma20 < ma60:
            regime.iloc[i] = -1  # bear
        else:
            regime.iloc[i] = 0   # sideways

    # 创建一个 DataFrame 用于 Backtrader PandasData
    df = pd.DataFrame({
        'close': regime.values,
        'open': regime.values,
        'high': regime.values,
        'low': regime.values,
        'volume': [0] * len(regime),
    }, index=benchmark_df.index)

    return df
