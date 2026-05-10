"""
巴菲特+控制论 综合策略 — Backtrader v2.0

三重确认机制:
  1. 巴菲特过滤 — 股票在精选池内 (buffett_score > 0)
  2. 市场允许   — 控制论层判市, 根据regime调整仓位上限
  3. 技术信号   — MA金叉/死叉 (参数可网格搜索)

仓位管理:
  - 按巴菲特评分加权: 高分多配, 低分少配
  - 牛市积极, 熊市防御, 震荡谨慎
  - 单票仓位上限由控制论层动态决定

风控:
  - 自适应止损 (牛市-8%, 熊市-3%)
  - 连续亏损熔断
"""
import backtrader as bt
from backtrader.indicators import MovingAverageSimple, CrossOver


class BuffettCyberStrategy(bt.Strategy):
    """
    巴菲特价值投资 + 钱学森控制论 综合策略
    市场状态在策略外检测，通过 params 传入
    """

    params = dict(
        ma_short=5, ma_long=20,
        stop_loss=-0.08, position_pct=0.30, max_positions=8,
        score_weight=True, print_log=False,
    )

    def __init__(self):
        self.ma_short = MovingAverageSimple(self.data.close, period=self.p.ma_short)
        self.ma_long = MovingAverageSimple(self.data.close, period=self.p.ma_long)
        self.crossover = CrossOver(self.ma_short, self.ma_long)
        self.order = None
        self.entry_price = None
        self.trade_count = 0
        self.consecutive_losses = 0
        self.circuit_breaker = False

    def log(self, txt):
        if self.p.print_log:
            dt = self.datas[0].datetime.date(0)
            print(f"[{dt}] {txt}")

    def _get_score_weight(self):
        if not self.p.score_weight:
            return 1.0
        name = self.data._name
        if "_" in name:
            parts = name.rsplit("_", 1)
            try:
                score = float(parts[-1])
                return 0.5 + score / 100.0
            except ValueError:
                pass
        return 1.0

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.entry_price = order.executed.price
            else:
                if self.entry_price:
                    pnl = (order.executed.price - self.entry_price) / self.entry_price
                    self.trade_count += 1
                    if pnl <= 0:
                        self.consecutive_losses += 1
                    else:
                        self.consecutive_losses = 0
                self.entry_price = None
        self.order = None

    def next(self):
        if self.order or self.circuit_breaker:
            return

        # 熔断
        if self.consecutive_losses >= 3:
            self.circuit_breaker = True
            return

        # 止损
        if self.position and self.entry_price:
            loss_pct = (self.data.close[0] - self.entry_price) / self.entry_price
            if loss_pct <= self.p.stop_loss:
                self.order = self.close()
                return

        # 仓位上限
        if len(self.broker.positions) >= self.p.max_positions and not self.position:
            return

        # 信号
        if self.crossover > 0 and not self.position:
            base_size = self.broker.getvalue() * self.p.position_pct / self.data.close[0]
            weight = self._get_score_weight()
            size = int(base_size * weight // 100) * 100
            if size >= 100:
                self.order = self.buy(size=size)

        elif self.crossover < 0 and self.position:
            self.order = self.close()

    def stop(self):
        total_ret = (self.broker.getvalue() / self.broker.startingcash - 1) * 100
        self.log(f"结束: {total_ret:.2f}% 交易{self.trade_count}次")


def make_data_name(symbol, name, score):
    """生成 Backtrader data name: symbol_name_score"""
    return f"{symbol}_{name}_{score}"
