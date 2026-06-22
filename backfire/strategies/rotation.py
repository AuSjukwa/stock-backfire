"""多标的轮动 / 再平衡策略。

两种模式：
- momentum: 按过去 lookback 日动量排序，持有 top_n 个最强标的，定期调仓
- rebalance: 等权持有全部标的，定期再平衡到等权
调仓周期由 rebalance_days 控制（交易日计数）。
"""
from __future__ import annotations

import backtrader as bt

from .base import ABaseStrategy


class RotationStrategy(ABaseStrategy):
    params = (
        ("mode", "momentum"),     # momentum | rebalance
        ("lookback", 60),         # 动量回看交易日
        ("top_n", 2),             # 持有标的数（动量模式）
        ("rebalance_days", 20),   # 调仓周期
        ("total_target", 0.95),   # 总目标仓位
    )

    def __init__(self):
        super().__init__()
        self._bar = 0
        # 每个标的的动量 = 现价 / lookback 日前价 - 1
        self.momentum = {
            d._name: bt.ind.PctChange(d.close, period=self.p.lookback)
            for d in self.datas
        }

    def next(self):
        self._bar += 1
        if (self._bar - 1) % self.p.rebalance_days != 0:
            return
        if len(self.datas[0]) <= self.p.lookback:
            return

        if self.p.mode == "rebalance":
            selected = list(self.datas)
        else:  # momentum
            ranked = sorted(
                self.datas,
                key=lambda d: self.momentum[d._name][0],
                reverse=True,
            )
            # 只保留动量为正的标的，最多 top_n 个
            selected = [d for d in ranked[: self.p.top_n]
                        if self.momentum[d._name][0] > 0]

        per = self.p.total_target / len(selected) if selected else 0.0
        selected_names = {d._name for d in selected}

        # 先减仓不在目标里的
        for d in self.datas:
            cur = self.getposition(d).size
            if d._name not in selected_names and cur > 0:
                self.safe_order_target_percent(d, target=0.0)
        # 再调到目标权重
        for d in selected:
            self.safe_order_target_percent(d, target=per)
