"""A股回测平台 Web 面板。

运行：
  .venv/bin/streamlit run app/streamlit_app.py
默认仅监听 localhost，不对外暴露、无需鉴权。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 让 app/ 能 import 到 backfire 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from backfire import config
from backfire.registry import REGISTRY
from backfire.engine.runner import run_backtest
from backfire.report.metrics import compute_metrics, load_benchmark_returns
from backfire.report import charts
from backfire.data import universe
from backfire import monitor

st.set_page_config(page_title="A股回测平台", layout="wide")


# ===========================================================================
# 访问口令（可选）
# 仅当配置了 secrets["app_password"] 时启用；本地未配置则照常无鉴权运行。
# 云端部署：在平台 Secrets 里写 app_password = "你的口令"
# ===========================================================================
def _check_password() -> bool:
    try:
        expected = st.secrets["app_password"]
    except (FileNotFoundError, KeyError):
        return True  # 未配置口令 → 不启用鉴权（本地开发）
    if not expected:
        return True

    if st.session_state.get("password_ok"):
        return True

    def _verify():
        import hmac
        st.session_state["password_ok"] = hmac.compare_digest(
            st.session_state.get("password_input", ""), str(expected)
        )

    st.text_input("访问口令", type="password", key="password_input", on_change=_verify)
    if "password_ok" in st.session_state and not st.session_state["password_ok"]:
        st.error("口令错误")
    return False


if not _check_password():
    st.stop()


# 顶部页面切换
PAGE = st.sidebar.radio("页面", ["策略回测", "趋势监控"], horizontal=True)
st.sidebar.divider()


# ===========================================================================
# 页面一：策略回测
# ===========================================================================
def page_backtest():
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
    start = col_s.text_input("开始", value="2021-01-01")
    end = col_e.text_input("结束", value="2024-12-31")
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


# ===========================================================================
# 页面二：趋势监控
# ===========================================================================
@st.cache_data(ttl=1800, show_spinner=False)
def _load_snapshot(asof: str | None):
    return monitor.build_snapshot(asof=asof)


def _style_snapshot(df: pd.DataFrame):
    """偏离率红绿渐变：>0 红(强势)，<0 绿(弱势)，对齐图片配色。"""
    def color_bias(v):
        if pd.isna(v):
            return ""
        if v > 0:
            a = min(abs(v) / 12, 1.0)  # 归一化到 12%
            return f"background-color: rgba(244,67,54,{0.15 + 0.5 * a})"
        a = min(abs(v) / 12, 1.0)
        return f"background-color: rgba(76,175,80,{0.15 + 0.5 * a})"

    def color_chg(v):
        if pd.isna(v):
            return ""
        return "color: #d32f2f" if v > 0 else ("color: #388e3c" if v < 0 else "")

    sty = (df.style
           .map(color_bias, subset=["偏离率%"])
           .map(color_chg, subset=["涨幅%"])
           .format({"涨幅%": "{:.2f}", "现价": "{:.2f}", "20日均线": "{:.2f}",
                    "偏离率%": "{:.2f}", "量比": "{:.2f}", "区间涨幅%": "{:.2f}"},
                   na_rep="-"))
    return sty


def page_monitor():
    st.title("鱼盆趋势模型监控")
    st.caption("按偏离率(现价相对MA20)排序 · 红=强势 绿=弱势 · 数据仅供市场风格趋势观察，不构成投资建议")

    sb = st.sidebar
    sb.header("监控设置")
    asof = sb.text_input("截止日期(留空=最新)", value="")
    asof = asof.strip() or None
    if sb.button("刷新数据", type="primary", use_container_width=True):
        _load_snapshot.clear()

    with st.spinner("抓取并计算中…"):
        try:
            snap = _load_snapshot(asof)
        except Exception as e:  # noqa: BLE001
            st.error(f"加载失败：{type(e).__name__}: {e}")
            return

    if snap.empty:
        st.warning("未取到任何标的数据。")
        return

    st.dataframe(_style_snapshot(snap), use_container_width=True, hide_index=True,
                 height=min(70 + 35 * len(snap), 800))
    st.caption("偏离率% = (现价 − 20日均线) / 20日均线 ; 量比 = 今日量 / 过去5日均量 ; "
               "状态转变时间 = 最近一次价格上穿/下穿MA20的日期 ; 排序变化 = 较上一交易日排名变动")


# ===========================================================================
if PAGE == "策略回测":
    page_backtest()
else:
    page_monitor()


