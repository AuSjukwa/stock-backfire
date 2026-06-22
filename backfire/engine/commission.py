"""A股交易成本模型（backtrader CommInfo）。

买入：佣金（双边，最低 5 元）+ 过户费。
卖出：佣金 + 过户费 + 印花税（千1，单边，仅卖出）。
滑点单独由 cerebro 的 set_slippage_perc 处理。
"""
from __future__ import annotations

import backtrader as bt

from ..config import CostConfig


class AStockCommission(bt.CommInfoBase):
    """A股股票/ETF 佣金+印花税+过户费模型。"""

    params = (
        ("stocklike", True),
        ("commtype", bt.CommInfoBase.COMM_PERC),
        ("percabs", True),          # rate 为绝对百分比（如 0.00025）
        ("commission", 0.00025),    # 佣金率
        ("min_commission", 5.0),
        ("stamp_duty", 0.001),      # 卖出印花税
        ("transfer_fee", 0.00001),  # 过户费（双边）
    )

    def _getcommission(self, size, price, pseudoexec):
        """size>0 买入，size<0 卖出。返回该笔交易的总费用。"""
        value = abs(size) * price
        commission = max(value * self.p.commission, self.p.min_commission)
        transfer = value * self.p.transfer_fee
        stamp = value * self.p.stamp_duty if size < 0 else 0.0
        return commission + transfer + stamp


def make_commission(cost: CostConfig) -> AStockCommission:
    return AStockCommission(
        commission=cost.commission_rate,
        min_commission=cost.min_commission,
        stamp_duty=cost.stamp_duty,
        transfer_fee=cost.transfer_fee_rate,
    )
