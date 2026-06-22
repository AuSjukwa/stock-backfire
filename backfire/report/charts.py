"""Plotly 图表：资金曲线、回撤、月度收益热力图。用于 Streamlit 面板。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go


def equity_vs_benchmark(equity: pd.Series, benchmark_returns: pd.Series | None = None,
                        bench_name: str = "基准") -> go.Figure:
    """归一化资金曲线 vs 基准。"""
    eq = equity / equity.iloc[0]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=eq.index, y=eq.values, name="策略", line=dict(width=2)))
    if benchmark_returns is not None and len(benchmark_returns) > 1:
        b = benchmark_returns.reindex(equity.index).fillna(0.0)
        bench_cum = (1 + b).cumprod()
        fig.add_trace(go.Scatter(x=bench_cum.index, y=bench_cum.values,
                                 name=bench_name, line=dict(width=1.5, dash="dash")))
    fig.update_layout(title="净值曲线（归一化）", xaxis_title="日期", yaxis_title="净值",
                      hovermode="x unified", height=420, legend=dict(orientation="h"))
    return fig


def drawdown_curve(equity: pd.Series) -> go.Figure:
    """回撤曲线。"""
    roll_max = equity.cummax()
    dd = (equity / roll_max - 1.0) * 100
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dd.index, y=dd.values, fill="tozeroy",
                             line=dict(color="crimson", width=1), name="回撤"))
    fig.update_layout(title="回撤 (%)", xaxis_title="日期", yaxis_title="回撤 %",
                      height=300, hovermode="x unified")
    return fig


def monthly_returns_heatmap(returns: pd.Series) -> go.Figure:
    """月度收益热力图（行=年，列=月）。"""
    r = returns.copy()
    r.index = pd.to_datetime(r.index)
    monthly = (1 + r).resample("ME").prod() - 1
    table = monthly.to_frame("ret")
    table["year"] = table.index.year
    table["month"] = table.index.month
    pivot = table.pivot_table(index="year", columns="month", values="ret")
    pivot = pivot.reindex(columns=range(1, 13))
    z = (pivot.values * 100)
    fig = go.Figure(data=go.Heatmap(
        z=z, x=[f"{m}月" for m in range(1, 13)], y=[str(y) for y in pivot.index],
        colorscale="RdYlGn", zmid=0,
        text=np.round(z, 1), texttemplate="%{text}",
        colorbar=dict(title="%"),
    ))
    fig.update_layout(title="月度收益热力图 (%)", height=300)
    return fig
