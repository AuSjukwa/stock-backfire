"""回测引擎：构建并运行 cerebro，返回净值序列与绩效分析。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import backtrader as bt
import pandas as pd

from .. import config
from ..data import loader
from .commission import make_commission
from .feed import make_feed


@dataclass
class BacktestResult:
    equity_curve: pd.Series              # 日净值（index=date）
    returns: pd.Series                   # 日收益率
    analyzers: dict[str, Any]            # backtrader analyzer 原始结果
    trades: pd.DataFrame                 # 成交/交易明细
    final_value: float
    start_value: float
    params: dict = field(default_factory=dict)


class _EquityRecorder(bt.Analyzer):
    """逐日记录账户总净值。"""

    def start(self):
        self.dates = []
        self.values = []

    def next(self):
        self.dates.append(self.strategy.datas[0].datetime.date(0))
        self.values.append(self.strategy.broker.getvalue())

    def get_analysis(self):
        return {"dates": self.dates, "values": self.values}


def run_backtest(
    strategy_cls,
    symbols: str | list[str],
    start: str,
    end: str,
    cash: float = config.DEFAULT_CASH,
    adjust: str = "qfq",
    strategy_params: dict | None = None,
    cost: config.CostConfig | None = None,
    asset_types: dict | None = None,
) -> BacktestResult:
    """运行一次回测。

    symbols: 单个或多个标的代码。多标的策略（轮动/因子）需传 list。
    """
    cost = cost or config.COST
    strategy_params = strategy_params or {}
    asset_types = asset_types or {}
    if isinstance(symbols, str):
        symbols = [symbols]

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=0.0)  # 用自定义 CommInfo 覆盖
    cerebro.broker.addcommissioninfo(make_commission(cost))
    cerebro.broker.set_slippage_perc(perc=cost.slippage_perc)
    # 整手交易
    cerebro.addsizer(bt.sizers.FixedSize, stake=cost.lot_size)

    for sym in symbols:
        df = loader.load(sym, start, end, adjust=adjust)
        if df.empty:
            raise ValueError(f"标的 {sym} 在 {start}~{end} 无数据")
        feed = make_feed(df, sym, asset_types.get(sym))
        cerebro.adddata(feed, name=sym)

    cerebro.addstrategy(strategy_cls, **strategy_params)
    cerebro.addanalyzer(_EquityRecorder, _name="equity")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Days, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")

    start_value = cerebro.broker.getvalue()
    strat = cerebro.run()[0]
    final_value = cerebro.broker.getvalue()

    eq = strat.analyzers.equity.get_analysis()
    equity_curve = pd.Series(eq["values"], index=pd.to_datetime(eq["dates"]), name="equity")
    returns = equity_curve.pct_change().fillna(0.0)

    analyzers = {
        "sharpe": strat.analyzers.sharpe.get_analysis(),
        "drawdown": strat.analyzers.drawdown.get_analysis(),
        "trades": strat.analyzers.trades.get_analysis(),
        "returns": strat.analyzers.returns.get_analysis(),
        "sqn": strat.analyzers.sqn.get_analysis(),
    }
    trades_df = _trades_to_df(strat.analyzers.trades.get_analysis())

    return BacktestResult(
        equity_curve=equity_curve,
        returns=returns,
        analyzers=analyzers,
        trades=trades_df,
        final_value=final_value,
        start_value=start_value,
        params={"symbols": symbols, "start": start, "end": end, **strategy_params},
    )


def _trades_to_df(ta: dict) -> pd.DataFrame:
    """把 TradeAnalyzer 汇总转成单行摘要 DataFrame。"""
    total = ta.get("total", {}).get("total", 0)
    won = ta.get("won", {}).get("total", 0)
    lost = ta.get("lost", {}).get("total", 0)
    pnl_net = ta.get("pnl", {}).get("net", {}).get("total", 0.0)
    win_rate = (won / total) if total else 0.0
    return pd.DataFrame([{
        "trades": total, "won": won, "lost": lost,
        "win_rate": win_rate, "pnl_net": pnl_net,
    }])
