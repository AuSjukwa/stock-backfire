"""策略回测页面。"""
from __future__ import annotations

import streamlit as st

from backfire import config
from backfire.data import universe
from backfire.engine.runner import run_backtest
from backfire.registry import REGISTRY
from backfire.report import charts
from backfire.report.metrics import compute_metrics, load_benchmark_returns


# ===========================================================================
# 页面一：策略回测
# ===========================================================================
def render():
    st.title("A股回测平台")
    st.caption("akshare(Sina) · backtrader · 含 T+1/涨跌停/印花税规则")

    sb = st.sidebar
    sb.header("回测设置")

    strat_key = sb.selectbox(
        "策略", options=list(REGISTRY),
        format_func=lambda k: REGISTRY[k].label,
    )
    spec = REGISTRY[strat_key]
    sb.caption(spec.help)

    # 标的输入
    if spec.multi_asset:
        preset = sb.selectbox("标的池预设", ["(自定义)"] + list(universe.PRESETS))
        if preset != "(自定义)":
            default_syms = ", ".join(universe.get(preset))
        elif strat_key == "index_position":
            default_syms = "sh510300, sh000300"
        else:
            default_syms = "sh510300, sh510500, sh588000, sz159915"
        syms_raw = sb.text_area("标的代码（逗号分隔）", value=default_syms, height=80)
        symbols = [s.strip() for s in syms_raw.replace("\n", ",").split(",") if s.strip()]
    else:
        syms_raw = sb.text_input("标的代码", value="sh510300")
        symbols = [syms_raw.strip()]

    col_s, col_e = sb.columns(2)
    start = col_s.text_input("开始", value="2026-01-01")
    end = col_e.text_input("结束", value="2026-12-31")
    cash = sb.number_input("起始资金", value=float(config.DEFAULT_CASH), step=100000.0)

    bench_name = sb.selectbox("对比基准", list(config.BENCHMARKS), index=0)

    # 策略参数控件（按注册表动态渲染）
    sb.subheader("策略参数")
    strat_params: dict = {}
    for ps in spec.params:
        if ps.kind == "choice":
            strat_params[ps.name] = sb.selectbox(ps.label, ps.choices,
                                                  index=ps.choices.index(ps.default))
        elif ps.kind == "int":
            strat_params[ps.name] = int(sb.number_input(
                ps.label, value=int(ps.default), min_value=int(ps.min),
                max_value=int(ps.max), step=int(ps.step or 1)))
        else:  # float
            strat_params[ps.name] = float(sb.number_input(
                ps.label, value=float(ps.default), min_value=float(ps.min),
                max_value=float(ps.max), step=float(ps.step or 0.1)))

    run = sb.button("运行回测", type="primary", use_container_width=True)

    if run:
        if not symbols:
            st.error("请至少输入一个标的代码")
        else:
            with st.spinner("回测中…"):
                try:
                    res = run_backtest(
                        spec.cls, symbols if spec.multi_asset else symbols[0],
                        start, end, cash=cash, strategy_params=strat_params,
                    )
                    bench_returns = load_benchmark_returns(bench_name, start, end)
                    st.success(f"完成：{spec.label} · {len(symbols)} 标的 · {start}~{end}")
                    _render_result(res, bench_returns, bench_name)
                except Exception as e:  # noqa: BLE001
                    st.error(f"回测失败：{type(e).__name__}: {e}")
    else:
        st.info("在左侧设置策略与参数，点击「运行回测」。")


def _render_result(res, bench_returns, bench_name):
    m = compute_metrics(res.equity_curve, res.returns, benchmark_returns=bench_returns)
    c = st.columns(4)
    c[0].metric("累计收益", f"{m.total_return:.2%}")
    c[1].metric("年化收益", f"{m.cagr:.2%}")
    c[2].metric("最大回撤", f"{m.max_drawdown:.2%}")
    c[3].metric("夏普比率", f"{m.sharpe:.2f}")
    c = st.columns(4)
    c[0].metric("卡玛比率", f"{m.calmar:.2f}")
    c[1].metric("年化波动", f"{m.volatility:.2%}")
    c[2].metric("日胜率", f"{m.win_rate:.2%}")
    c[3].metric(f"超额({bench_name})", f"{m.excess_return:.2%}")

    st.plotly_chart(charts.equity_vs_benchmark(res.equity_curve, bench_returns, bench_name),
                    use_container_width=True)
    cc = st.columns(2)
    cc[0].plotly_chart(charts.drawdown_curve(res.equity_curve), use_container_width=True)
    cc[1].plotly_chart(charts.monthly_returns_heatmap(res.returns), use_container_width=True)

    st.subheader("交易摘要")
    st.dataframe(res.trades, use_container_width=True)
