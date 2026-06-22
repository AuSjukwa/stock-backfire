"""策略注册表：集中描述每个策略的参数，供 CLI 与 Web 面板共享。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .strategies.timing_single import SingleTimingStrategy
from .strategies.index_position import IndexPositionStrategy
from .strategies.rotation import RotationStrategy
from .strategies.factor_rank import FactorRankStrategy


@dataclass
class ParamSpec:
    name: str
    label: str
    kind: str            # "int" | "float" | "choice"
    default: Any
    choices: list | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None


@dataclass
class StrategySpec:
    key: str
    label: str
    cls: type
    multi_asset: bool
    params: list[ParamSpec]
    help: str = ""


REGISTRY: dict[str, StrategySpec] = {
    "single_timing": StrategySpec(
        key="single_timing", label="单标的技术择时", cls=SingleTimingStrategy,
        multi_asset=False,
        help="对单只股票/ETF/指数用技术指标择时买卖。",
        params=[
            ParamSpec("mode", "信号模式", "choice", "ma_cross",
                      choices=["ma_cross", "macd", "rsi", "boll"]),
            ParamSpec("fast", "快线/短周期", "int", 10, min=1, max=120, step=1),
            ParamSpec("slow", "慢线/长周期", "int", 30, min=5, max=250, step=1),
            ParamSpec("rsi_period", "RSI周期", "int", 14, min=2, max=60, step=1),
            ParamSpec("rsi_low", "RSI超卖", "int", 30, min=5, max=50, step=1),
            ParamSpec("rsi_high", "RSI超买", "int", 70, min=50, max=95, step=1),
            ParamSpec("boll_period", "布林周期", "int", 20, min=5, max=60, step=1),
            ParamSpec("boll_dev", "布林倍数", "float", 2.0, min=1.0, max=3.0, step=0.1),
            ParamSpec("target", "目标仓位", "float", 0.95, min=0.1, max=1.0, step=0.05),
        ],
    ),
    "index_position": StrategySpec(
        key="index_position", label="大盘择时控仓", cls=IndexPositionStrategy,
        multi_asset=True,
        help="用大盘指数均线信号控制目标标的仓位。需传【交易标的, 指数】两个代码。",
        params=[
            ParamSpec("ma_period", "择时均线", "int", 60, min=5, max=250, step=1),
            ParamSpec("full_target", "看多仓位", "float", 0.95, min=0.1, max=1.0, step=0.05),
            ParamSpec("defensive_target", "看空仓位", "float", 0.0, min=0.0, max=1.0, step=0.05),
        ],
    ),
    "rotation": StrategySpec(
        key="rotation", label="多标的轮动/再平衡", cls=RotationStrategy,
        multi_asset=True,
        help="动量轮动持有最强 N 个标的，或等权定期再平衡。",
        params=[
            ParamSpec("mode", "模式", "choice", "momentum", choices=["momentum", "rebalance"]),
            ParamSpec("lookback", "动量回看", "int", 60, min=5, max=250, step=1),
            ParamSpec("top_n", "持有数量", "int", 2, min=1, max=10, step=1),
            ParamSpec("rebalance_days", "调仓周期", "int", 20, min=1, max=120, step=1),
            ParamSpec("total_target", "总仓位", "float", 0.95, min=0.1, max=1.0, step=0.05),
        ],
    ),
    "factor_rank": StrategySpec(
        key="factor_rank", label="因子打分选股", cls=FactorRankStrategy,
        multi_asset=True,
        help="对标的池按动量/低波动/反转因子打分，持有得分最高的 N 个。",
        params=[
            ParamSpec("lookback", "动量回看", "int", 60, min=5, max=250, step=1),
            ParamSpec("vol_period", "波动周期", "int", 20, min=5, max=120, step=1),
            ParamSpec("rev_period", "反转周期", "int", 5, min=1, max=60, step=1),
            ParamSpec("top_n", "持有数量", "int", 3, min=1, max=15, step=1),
            ParamSpec("rebalance_days", "调仓周期", "int", 20, min=1, max=120, step=1),
            ParamSpec("w_momentum", "动量权重", "float", 1.0, min=0.0, max=3.0, step=0.1),
            ParamSpec("w_low_vol", "低波权重", "float", 0.5, min=0.0, max=3.0, step=0.1),
            ParamSpec("w_reversal", "反转权重", "float", 0.0, min=0.0, max=3.0, step=0.1),
        ],
    ),
}
