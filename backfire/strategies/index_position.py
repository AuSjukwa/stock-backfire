"""大盘择时控仓策略。

用大盘指数的信号（如均线方向）控制整体仓位：
- 指数在长均线上方 → 满仓持有目标标的
- 指数跌破长均线 → 降仓/空仓
data0 = 交易标的（通常宽基ETF），data1 = 指数信号源。
若只传一个标的，则用其自身作为信号源。
"""
from __future__ import annotations

import backtrader as bt

from .base import ABaseStrategy


class IndexPositionStrategy(ABaseStrategy):
    params = (
        ("ma_period", 60),       # 指数择时均线
        ("full_target", 0.95),   # 看多时目标仓位
        ("defensive_target", 0.0),  # 看空时目标仓位
        ("use_slope", False),    # True 则额外要求均线向上
    )

    def __init__(self):
        super().__init__()
        self.trade_data = self.datas[0]
        self.signal_data = self.datas[1] if len(self.datas) > 1 else self.datas[0]
        self.ma = bt.ind.SMA(self.signal_data.close, period=self.p.ma_period)

    def next(self):
        if len(self.signal_data) <= self.p.ma_period:
            return
        bullish = self.signal_data.close[0] > self.ma[0]
        if self.p.use_slope:
            bullish = bullish and self.ma[0] > self.ma[-1]
        target = self.p.full_target if bullish else self.p.defensive_target
        cur = self.getposition(self.trade_data).size
        # 只在需要改变方向时下单
        if target > 0 and cur == 0:
            self.safe_order_target_percent(self.trade_data, target=target)
        elif target == 0 and cur > 0:
            self.safe_order_target_percent(self.trade_data, target=0.0)
