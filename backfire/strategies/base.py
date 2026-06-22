"""策略基类：封装 A股 T+1 与涨跌停规则，子类只需实现信号逻辑。

子类重写 `next()` 时，调用 self.buy_target_percent / self.safe_order 等辅助方法，
基类负责拦截违反 T+1（当日买入当日卖出）和涨跌停（涨停买/跌停卖）的下单。
"""
from __future__ import annotations

import backtrader as bt


class ABaseStrategy(bt.Strategy):
    """所有策略的基类，注入 A股交易规则。"""

    params = (
        ("verbose", False),
    )

    def __init__(self):
        # 记录每个 data 的最近买入日，用于 T+1 锁仓
        self._buy_bar = {d._name: -1 for d in self.datas}

    # ------------------------------------------------------------------
    # 规则校验
    # ------------------------------------------------------------------
    def _can_buy(self, data) -> bool:
        """涨停日禁止买入。"""
        if len(data) == 0:
            return False
        return data.limit_up[0] < 0.5

    def _can_sell(self, data) -> bool:
        """跌停日禁止卖出；T+1：当日买入不可卖。"""
        if data.limit_down[0] >= 0.5:
            return False
        if self._buy_bar.get(data._name, -1) == len(self):
            return False  # 当日买入
        return True

    # ------------------------------------------------------------------
    # 安全下单封装（子类应优先使用这些）
    # ------------------------------------------------------------------
    def safe_buy(self, data=None, **kwargs):
        data = data if data is not None else self.datas[0]
        if not self._can_buy(data):
            if self.p.verbose:
                self.log(f"跳过买入 {data._name}: 涨停")
            return None
        return self.buy(data=data, **kwargs)

    def safe_sell(self, data=None, **kwargs):
        data = data if data is not None else self.datas[0]
        if not self._can_sell(data):
            if self.p.verbose:
                self.log(f"跳过卖出 {data._name}: 跌停或T+1锁仓")
            return None
        return self.sell(data=data, **kwargs)

    def safe_close(self, data=None, **kwargs):
        data = data if data is not None else self.datas[0]
        if not self._can_sell(data):
            if self.p.verbose:
                self.log(f"跳过平仓 {data._name}: 跌停或T+1锁仓")
            return None
        return self.close(data=data, **kwargs)

    def safe_order_target_percent(self, data=None, target: float = 0.0, **kwargs):
        """按目标仓位下单，自动校验买卖方向的规则。"""
        data = data if data is not None else self.datas[0]
        pos = self.getposition(data).size
        value = self.broker.getvalue()
        price = data.close[0]
        target_size = int((value * target) / price) if price > 0 else 0
        if target_size > pos and not self._can_buy(data):
            return None
        if target_size < pos and not self._can_sell(data):
            return None
        return self.order_target_percent(data=data, target=target, **kwargs)

    # ------------------------------------------------------------------
    def notify_order(self, order):
        if order.status == order.Completed:
            if order.isbuy():
                self._buy_bar[order.data._name] = len(self)
                if self.p.verbose:
                    self.log(f"买入 {order.data._name} {order.executed.size}@{order.executed.price:.3f}")
            elif self.p.verbose:
                self.log(f"卖出 {order.data._name} {order.executed.size}@{order.executed.price:.3f}")

    def log(self, txt):
        dt = self.datas[0].datetime.date(0)
        print(f"{dt} {txt}")
