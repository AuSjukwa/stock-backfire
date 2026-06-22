"""命令行回测入口。

示例：
  python -m backfire.cli --symbol 600000 --start 2022-01-01 --end 2024-12-31 \
      --strategy single_timing --mode ma_cross --fast 10 --slow 30
"""
from __future__ import annotations

import argparse

from . import config
from .engine.runner import run_backtest
from .strategies.timing_single import SingleTimingStrategy
from .strategies.index_position import IndexPositionStrategy
from .strategies.rotation import RotationStrategy
from .strategies.factor_rank import FactorRankStrategy

STRATEGIES = {
    "single_timing": SingleTimingStrategy,
    "index_position": IndexPositionStrategy,
    "rotation": RotationStrategy,
    "factor_rank": FactorRankStrategy,
}


def _print_summary(res):
    dd = res.analyzers["drawdown"]
    ret = res.analyzers["returns"]
    sharpe = res.analyzers["sharpe"].get("sharperatio")
    total_ret = res.final_value / res.start_value - 1
    print("=" * 50)
    print(f"起始资金: {res.start_value:,.0f}")
    print(f"期末资金: {res.final_value:,.0f}")
    print(f"累计收益: {total_ret:.2%}")
    print(f"年化收益: {ret.get('rnorm100', float('nan')):.2f}%")
    print(f"最大回撤: {dd.get('max', {}).get('drawdown', float('nan')):.2f}%")
    print(f"夏普比率: {sharpe if sharpe is not None else float('nan')}")
    print(f"交易笔数: {res.trades['trades'].iloc[0]}  胜率: {res.trades['win_rate'].iloc[0]:.2%}")
    print("=" * 50)


def main():
    p = argparse.ArgumentParser(description="A股回测平台 CLI")
    p.add_argument("--symbol", required=True, help="标的代码，如 600000 / sh000300 / 510300")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--cash", type=float, default=config.DEFAULT_CASH)
    p.add_argument("--strategy", default="single_timing", choices=list(STRATEGIES))
    p.add_argument("--mode", default="ma_cross")
    p.add_argument("--fast", type=int, default=10)
    p.add_argument("--slow", type=int, default=30)
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    strat_params = {
        "mode": args.mode, "fast": args.fast, "slow": args.slow, "verbose": args.verbose,
    }
    res = run_backtest(
        STRATEGIES[args.strategy], args.symbol, args.start, args.end,
        cash=args.cash, strategy_params=strat_params,
    )
    _print_summary(res)


if __name__ == "__main__":
    main()
