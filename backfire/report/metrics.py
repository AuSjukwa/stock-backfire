"""绩效指标计算与基准对比。

核心指标直接从净值/收益序列计算，稳健且与引擎解耦。
另提供 quantstats HTML 报告导出（可选）。
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from .. import config
from ..data import loader


@dataclass
class Metrics:
    total_return: float       # 累计收益
    cagr: float               # 年化收益
    max_drawdown: float       # 最大回撤（负值）
    sharpe: float             # 夏普
    calmar: float             # 卡玛 = 年化/|最大回撤|
    volatility: float         # 年化波动率
    win_rate: float           # 日胜率（正收益天数占比）
    # 相对基准
    benchmark_return: float = float("nan")
    excess_return: float = float("nan")

    def to_dict(self):
        return asdict(self)


def _max_drawdown(equity: pd.Series) -> float:
    roll_max = equity.cummax()
    dd = equity / roll_max - 1.0
    return float(dd.min())


def compute_metrics(
    equity: pd.Series,
    returns: pd.Series | None = None,
    benchmark_returns: pd.Series | None = None,
    periods_per_year: int = config.TRADING_DAYS_PER_YEAR,
) -> Metrics:
    """从净值曲线计算绩效指标。"""
    equity = equity.dropna()
    if returns is None:
        returns = equity.pct_change().fillna(0.0)
    n = len(equity)
    if n < 2:
        raise ValueError("净值序列过短，无法计算指标")

    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1)
    years = n / periods_per_year
    cagr = float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1) if years > 0 else float("nan")
    mdd = _max_drawdown(equity)
    vol = float(returns.std() * np.sqrt(periods_per_year))
    sharpe = float(returns.mean() / returns.std() * np.sqrt(periods_per_year)) if returns.std() > 0 else 0.0
    calmar = float(cagr / abs(mdd)) if mdd < 0 else float("nan")
    win_rate = float((returns > 0).sum() / (returns != 0).sum()) if (returns != 0).any() else 0.0

    m = Metrics(
        total_return=total_return, cagr=cagr, max_drawdown=mdd,
        sharpe=sharpe, calmar=calmar, volatility=vol, win_rate=win_rate,
    )
    if benchmark_returns is not None and len(benchmark_returns) > 1:
        bench_cum = float((1 + benchmark_returns.reindex(returns.index).fillna(0.0)).prod() - 1)
        m.benchmark_return = bench_cum
        m.excess_return = total_return - bench_cum
    return m


def load_benchmark_returns(benchmark: str, start: str, end: str) -> pd.Series:
    """加载基准指数日收益（用于对比）。benchmark 可为 'sh000300' 或 '沪深300'。"""
    code = config.BENCHMARKS.get(benchmark, benchmark)
    df = loader.load(code, start, end, asset_type="index")
    s = df.set_index("date")["close"].pct_change().fillna(0.0)
    s.name = "benchmark"
    return s


def export_quantstats_html(returns: pd.Series, out_path: str,
                           benchmark_returns: pd.Series | None = None,
                           title: str = "回测报告") -> str:
    """用 quantstats 生成完整 HTML 报告（可选）。"""
    import quantstats as qs
    r = returns.copy()
    r.index = pd.to_datetime(r.index)
    qs.reports.html(r, benchmark=benchmark_returns, output=out_path, title=title)
    return out_path
