"""因子打分选股策略。

对标的池按多个因子打分，定期持有得分最高的 top_n 个，等权配置。
内置因子（可加权组合）：
- momentum: 动量（lookback 日涨幅），越高越好
- low_vol: 低波动（近 vol_period 日收益标准差的负向），越低波动越好
- reversal: 短期反转（近 rev_period 日跌幅，越跌得分越高）
打分用截面 z-score 标准化后加权。
"""
from __future__ import annotations

import numpy as np
import backtrader as bt

from .base import ABaseStrategy


class FactorRankStrategy(ABaseStrategy):
    params = (
        ("lookback", 60),
        ("vol_period", 20),
        ("rev_period", 5),
        ("top_n", 3),
        ("rebalance_days", 20),
        ("w_momentum", 1.0),
        ("w_low_vol", 0.5),
        ("w_reversal", 0.0),
        ("total_target", 0.95),
    )

    def __init__(self):
        super().__init__()
        self._bar = 0
        self.mom = {d._name: bt.ind.PctChange(d.close, period=self.p.lookback) for d in self.datas}
        self.vol = {d._name: bt.ind.StdDev(bt.ind.PctChange(d.close, period=1),
                                           period=self.p.vol_period) for d in self.datas}
        self.rev = {d._name: bt.ind.PctChange(d.close, period=self.p.rev_period) for d in self.datas}

    @staticmethod
    def _zscore(values: dict) -> dict:
        arr = np.array(list(values.values()), dtype=float)
        mu, sd = np.nanmean(arr), np.nanstd(arr)
        if sd == 0 or np.isnan(sd):
            return {k: 0.0 for k in values}
        return {k: (v - mu) / sd for k, v in values.items()}

    def next(self):
        self._bar += 1
        if (self._bar - 1) % self.p.rebalance_days != 0:
            return
        if len(self.datas[0]) <= max(self.p.lookback, self.p.vol_period):
            return

        names = [d._name for d in self.datas]
        mom = self._zscore({n: self.mom[n][0] for n in names})
        vol = self._zscore({n: self.vol[n][0] for n in names})
        rev = self._zscore({n: self.rev[n][0] for n in names})

        score = {
            n: self.p.w_momentum * mom[n]
               - self.p.w_low_vol * vol[n]    # 低波动得分高 → 负号
               - self.p.w_reversal * rev[n]   # 近期跌得多 → 反转得分高
            for n in names
        }
        ranked = sorted(names, key=lambda n: score[n], reverse=True)
        selected = set(ranked[: self.p.top_n])
        per = self.p.total_target / len(selected) if selected else 0.0

        data_by_name = {d._name: d for d in self.datas}
        for n in names:
            d = data_by_name[n]
            if n not in selected and self.getposition(d).size > 0:
                self.safe_order_target_percent(d, target=0.0)
        for n in selected:
            self.safe_order_target_percent(data_by_name[n], target=per)
