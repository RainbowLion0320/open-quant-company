"""
巴菲特价值投资 + 均线金叉策略 — Backtrader 回测模板

策略逻辑:
  1. 股票池: 通过巴菲特三重过滤器（能力圈 + 护城河 + 安全边际）
  2. 入场: MA5 上穿 MA20（金叉）
  3. 出场: MA5 下穿 MA20（死叉）或 止损触发
  4. 仓位: 按市场状态自适应调整（牛/熊/震荡不同配置）
  5. 风控: 单票止损 + 连续亏损熔断

回测范围: 2020-01-01 ~ 至今
基准: 上证指数
"""
import backtrader as bt
from backtrader.indicators import MovingAverageSimple, CrossOver


class BuffettMACross(bt.Strategy):
    """
    巴菲特金叉策略
    - 用 MA5/MA20 金叉死叉作为交易信号
    - 仓位管理由控制论层提供自适应参数
    - 单票止损保护
    """

    params = dict(
        ma_short=5,          # 短期均线
        ma_long=20,          # 长期均线
        stop_loss=-0.08,     # 止损比例 (8%)
        position_pct=0.30,   # 单票仓位占比
        max_positions=5,     # 最大持仓数
        print_trades=True,   # 打印交易
    )

    def __init__(self):
        # 指标
        self.ma_short = MovingAverageSimple(self.data.close, period=self.p.ma_short)
        self.ma_long = MovingAverageSimple(self.data.close, period=self.p.ma_long)
        self.crossover = CrossOver(self.ma_short, self.ma_long)

        # 状态
        self.order = None
        self.entry_price = None
        self.trade_count = 0

    def log(self, txt, doprint=False):
        if doprint or self.p.print_trades:
            dt = self.datas[0].datetime.date(0)
            print(f"[{dt}] {txt}")

    def notify_order(self, order):
        """订单状态回调"""
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if order.isbuy():
                self.entry_price = order.executed.price
                self.log(
                    f"入 {self.data._name} @ {order.executed.price:.2f} "
                    f"数量:{order.executed.size} 金额:{order.executed.value:.0f}"
                )
            else:
                pnl = (order.executed.price - self.entry_price) / self.entry_price
                self.trade_count += 1
                self.log(
                    f"出 {self.data._name} @ {order.executed.price:.2f} "
                    f"收益:{pnl*100:.2f}% 累计交易:{self.trade_count}"
                )
                self.entry_price = None

        self.order = None

    def notify_trade(self, trade):
        """完整交易完成回调"""
        if trade.isclosed:
            self.log(f"交易完成: 毛利={trade.pnl:.2f} 净利={trade.pnlcomm:.2f}")

    def next(self):
        """每个 bar 的主逻辑"""
        # 有挂单则跳过
        if self.order:
            return

        # 检查止损
        if self.position and self.entry_price:
            current = self.data.close[0]
            loss_pct = (current - self.entry_price) / self.entry_price
            if loss_pct <= self.p.stop_loss:
                self.log(f"止损! 亏损{loss_pct*100:.1f}%")
                self.order = self.close()
                return

        # 信号判断
        if self.crossover > 0:  # 金叉 → 买入
            if not self.position:
                # 计算仓位：总资产 * 仓位比例 / 当前股价
                size = self.broker.getvalue() * self.p.position_pct / self.data.close[0]
                size = int(size // 100) * 100  # A股100股整手
                if size >= 100:
                    self.log(f"金叉信号! 买入{int(size)}股")
                    self.order = self.buy(size=size)

        elif self.crossover < 0:  # 死叉 → 卖出
            if self.position:
                self.log("死叉信号! 卖出")
                self.order = self.close()

    def stop(self):
        """回测结束时的统计"""
        total_return = (self.broker.getvalue() / self.broker.startingcash - 1) * 100
        self.log(f"━━━━━━━ 策略结束 ━━━━━━━")
        self.log(f"总回报: {total_return:.2f}%")
        self.log(f"总交易: {self.trade_count} 次")
        self.log(f"最终资产: {self.broker.getvalue():.0f}")
