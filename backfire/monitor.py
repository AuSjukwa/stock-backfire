"""趋势模型监控：横截面快照。

对每个标的，基于日线计算：
- 现价、MA20、涨幅%(最近一日)、偏离率%((现价-MA20)/MA20)
- 量比(今日量 / 过去5日均量)
- 状态转变时间(最近一次价格上穿/下穿 MA20 的日期)
- 区间涨幅%(现价相对状态转变日收盘的涨幅)
按偏离率降序排序；排序变化 = 今日排名 vs 上一交易日排名。

build_snapshot() 负责抓数 + 组装；compute_row_metrics() 是纯函数，便于单测。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import monitor_sources as ms
from .monitor_sources import MonitorItem


MA_WINDOW = 20
VOL_WINDOW = 5


@dataclass
class RowMetrics:
    price: float
    ma20: float
    change_pct: float        # 最近一日涨幅
    bias_pct: float          # 偏离率
    vol_ratio: float | None  # 量比（无量数据为 None）
    state_change_date: pd.Timestamp | None
    range_pct: float | None  # 区间涨幅
    above_ma: bool


def compute_row_metrics(df: pd.DataFrame, asof: pd.Timestamp | None = None,
                        ma_window: int = MA_WINDOW, vol_window: int = VOL_WINDOW) -> RowMetrics:
    """从单标的日线计算监控指标。df 需含 date/open/high/low/close/volume，按日期升序。"""
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date").reset_index(drop=True)
    if asof is not None:
        d = d[d["date"] <= pd.to_datetime(asof)].reset_index(drop=True)
    if len(d) < ma_window:
        raise ValueError(f"数据不足 {ma_window} 条，无法计算 MA")

    d["ma"] = d["close"].rolling(ma_window).mean()
    d = d.dropna(subset=["ma"]).reset_index(drop=True)

    price = float(d["close"].iloc[-1])
    ma20 = float(d["ma"].iloc[-1])
    prev_close = float(d["close"].iloc[-2]) if len(d) >= 2 else price
    change_pct = (price / prev_close - 1) * 100 if prev_close else 0.0
    bias_pct = (price - ma20) / ma20 * 100 if ma20 else 0.0
    above_ma = price >= ma20

    # 量比：今日量 / 过去 vol_window 日均量（不含今日）
    vol_ratio: float | None = None
    if d["volume"].notna().any():
        vols = d["volume"].astype(float)
        if len(vols) > vol_window and vols.iloc[-vol_window - 1:-1].mean() > 0:
            vol_ratio = float(vols.iloc[-1] / vols.iloc[-vol_window - 1:-1].mean())

    # 状态转变：价格相对 MA 的上方/下方布尔序列，找最近一次翻转
    above_series = d["close"] >= d["ma"]
    flip = above_series != above_series.shift(1)
    flip.iloc[0] = False
    flip_idx = d.index[flip]
    state_change_date = None
    range_pct = None
    if len(flip_idx) > 0:
        last_flip = flip_idx[-1]
        state_change_date = d["date"].iloc[last_flip]
        base = float(d["close"].iloc[last_flip])
        range_pct = (price / base - 1) * 100 if base else None

    return RowMetrics(
        price=price, ma20=ma20, change_pct=change_pct, bias_pct=bias_pct,
        vol_ratio=vol_ratio, state_change_date=state_change_date,
        range_pct=range_pct, above_ma=above_ma,
    )


def _rank_by_bias(rows: list[dict]) -> dict:
    """按 bias_pct 降序给出 {code: 排名(1起)}。"""
    ordered = sorted(rows, key=lambda r: r["_bias_raw"], reverse=True)
    return {r["代码"]: i + 1 for i, r in enumerate(ordered)}


def build_snapshot(
    watchlist: list[MonitorItem] | None = None,
    asof: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """抓取监控清单并组装横截面快照，按偏离率降序。

    取不到数据的标的自动跳过。排序变化 = 上一交易日排名 - 今日排名
    （正数表示排名上升）。
    """
    watchlist = watchlist or ms.DEFAULT_WATCHLIST
    asof_ts = pd.to_datetime(asof) if asof is not None else None

    rows: list[dict] = []
    prev_rows: list[dict] = []  # 上一交易日的 (code, bias) 用于排名变化
    for item in watchlist:
        try:
            df = ms.fetch_item(item)
        except Exception:
            continue
        try:
            m = compute_row_metrics(df, asof=asof_ts)
        except Exception:
            continue

        rows.append({
            "代码": item.code, "名称": item.name,
            "涨幅%": round(m.change_pct, 2),
            "现价": round(m.price, 2),
            "20日均线": round(m.ma20, 2),
            "偏离率%": round(m.bias_pct, 2),
            "量比": round(m.vol_ratio, 2) if m.vol_ratio is not None else None,
            "状态转变时间": m.state_change_date.date().isoformat() if m.state_change_date is not None else "-",
            "区间涨幅%": round(m.range_pct, 2) if m.range_pct is not None else None,
            "_bias_raw": m.bias_pct,
        })

        # 上一交易日快照（用于排名变化）
        try:
            d = df.copy()
            d["date"] = pd.to_datetime(d["date"])
            d = d.sort_values("date")
            if asof_ts is not None:
                d = d[d["date"] <= asof_ts]
            if len(d) >= 2:
                prev_asof = d["date"].iloc[-2]
                pm = compute_row_metrics(df, asof=prev_asof)
                prev_rows.append({"代码": item.code, "_bias_raw": pm.bias_pct})
        except Exception:
            pass

    if not rows:
        return pd.DataFrame()

    today_rank = _rank_by_bias(rows)
    prev_rank = _rank_by_bias(prev_rows) if prev_rows else {}

    for r in rows:
        code = r["代码"]
        if code in prev_rank and code in today_rank:
            r["排序变化"] = prev_rank[code] - today_rank[code]
        else:
            r["排序变化"] = 0

    df = pd.DataFrame(rows).sort_values("_bias_raw", ascending=False).reset_index(drop=True)
    df.insert(0, "排序", range(1, len(df) + 1))
    df = df.drop(columns=["_bias_raw"])
    cols = ["排序", "代码", "名称", "涨幅%", "现价", "20日均线", "偏离率%",
            "量比", "状态转变时间", "区间涨幅%", "排序变化"]
    return df[cols]

