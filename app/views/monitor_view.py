"""趋势监控页面。"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from backfire import monitor


# ===========================================================================
# 页面二：趋势监控
# ===========================================================================
@st.cache_data(ttl=1800, show_spinner=False)
def _load_snapshot(asof: str | None):
    fetched_at = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
    return monitor.build_snapshot(asof=asof), fetched_at


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


def render():
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
            snap, fetched_at = _load_snapshot(asof)
        except Exception as e:  # noqa: BLE001
            st.error(f"加载失败：{type(e).__name__}: {e}")
            return

    if snap.empty:
        st.warning("未取到任何标的数据。")
        return

    st.caption(f"数据更新时间：{fetched_at}")
    st.dataframe(_style_snapshot(snap), use_container_width=True, hide_index=True,
                 height=min(70 + 35 * len(snap), 800))
    st.caption("偏离率% = (现价 − 20日均线) / 20日均线 ; 量比 = 今日量 / 过去5日均量 ; "
               "状态转变时间 = 最近一次价格上穿/下穿MA20的日期 ; 排序变化 = 较上一交易日排名变动")
