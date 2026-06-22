"""单标的技术择时策略。

支持多种信号模式，参数化选择：
- ma_cross: 双均线金叉买入/死叉卖出
- macd: MACD 金叉买入/死叉卖出
- rsi: RSI 超卖买入/超买卖出
- boll: 布林带下轨买入/上轨卖出
仓位用 order_target_percent 控制，受基类 T+1/涨跌停规则约束。
"""
from __future__ import annotations

import backtrader as bt

from .base import ABaseStrategy


class SingleTimingStrategy(ABaseStrategy):
    params = (
        ("mode", "ma_cross"),    # ma_cross | macd | rsi | boll
        ("fast", 10),            # 快均线 / 通用短周期
        ("slow", 30),            # 慢均线 / 通用长周期
        ("rsi_period", 14),
        ("rsi_low", 30),
        ("rsi_high", 70),
        ("boll_period", 20),
        ("boll_dev", 2.0),
        ("target", 0.95),        # 满仓目标仓位（留现金缓冲手续费）
    )

    def __init__(self):
        super().__init__()
        d = self.datas[0]
        self.signal_long = None
        self.signal_exit = None

        if self.p.mode == "ma_cross":
            fast = bt.ind.SMA(d.close, period=self.p.fast)
            slow = bt.ind.SMA(d.close, period=self.p.slow)
            self.cross = bt.ind.CrossOver(fast, slow)
        elif self.p.mode == "macd":
            macd = bt.ind.MACD(d.close)
            self.cross = bt.ind.CrossOver(macd.macd, macd.signal)
        elif self.p.mode == "rsi":
            self.rsi = bt.ind.RSI(d.close, period=self.p.rsi_period)
        elif self.p.mode == "boll":
            self.boll = bt.ind.BollingerBands(d.close, period=self.p.boll_period,
                                              devfactor=self.p.boll_dev)
        else:
            raise ValueError(f"未知 mode: {self.p.mode}")

    def next(self):
        d = self.datas[0]
        pos = self.getposition(d).size

        if self.p.mode in ("ma_cross", "macd"):
            if self.cross[0] > 0 and pos == 0:
                self.safe_order_target_percent(d, target=self.p.target)
            elif self.cross[0] < 0 and pos > 0:
                self.safe_order_target_percent(d, target=0.0)
        elif self.p.mode == "rsi":
            if self.rsi[0] < self.p.rsi_low and pos == 0:
                self.safe_order_target_percent(d, target=self.p.target)
            elif self.rsi[0] > self.p.rsi_high and pos > 0:
                self.safe_order_target_percent(d, target=0.0)
        elif self.p.mode == "boll":
            if d.close[0] <= self.boll.lines.bot[0] and pos == 0:
                self.safe_order_target_percent(d, target=self.p.target)
            elif d.close[0] >= self.boll.lines.top[0] and pos > 0:
                self.safe_order_target_percent(d, target=0.0)
