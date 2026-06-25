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
from datetime import datetime, time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import monitor_sources as ms
from .monitor_sources import MonitorItem


MA_WINDOW = 20
VOL_WINDOW = 5
BEIJING_TZ = ZoneInfo("Asia/Shanghai")
US_EASTERN_TZ = ZoneInfo("America/New_York")

# 以下窗口均为 Sina 行情返回的北京时间，不做市场本地时区转换。
_MARKET_WINDOWS_BEIJING: dict[str, list[tuple[time, time]]] = {
    "a_index": [(time(9, 30), time(11, 30)), (time(13, 0), time(15, 0))],
    "hk_index": [(time(9, 30), time(12, 0)), (time(13, 0), time(16, 0))],
    "sge_spot": [
        (time(9, 0), time(11, 30)),
        (time(13, 30), time(15, 30)),
        (time(20, 0), time(23, 59, 59)),
        (time(0, 0), time(2, 30)),
    ],
}

_GLOBAL_INDEX_WINDOWS_BEIJING: dict[str, list[tuple[time, time]]] = {
    "日经225指数": [(time(8, 0), time(10, 30)), (time(11, 30), time(14, 30))],
    "首尔综合指数": [(time(8, 0), time(14, 30))],
    "中国台湾加权指数": [(time(9, 0), time(13, 30))],
}


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


def _parse_quote_datetime(quote_date: str, quote_time: str) -> datetime | None:
    try:
        date_part = datetime.strptime(quote_date, "%Y-%m-%d").date()
        time_part = datetime.strptime(quote_time, "%H:%M:%S").time()
    except (TypeError, ValueError):
        return None
    return datetime.combine(date_part, time_part, tzinfo=BEIJING_TZ)


def _time_in_windows(value: time, windows: list[tuple[time, time]]) -> bool:
    for start, end in windows:
        if start <= end:
            if start <= value <= end:
                return True
        elif value >= start or value <= end:
            return True
    return False


def is_market_open(
    source: str,
    item_symbol: str,
    quote_date: str,
    quote_time: str,
    now_beijing: datetime,
) -> bool:
    """按行情源北京时间判断该报价是否处在交易时段内。"""
    quote_dt = _parse_quote_datetime(quote_date, quote_time)
    if quote_dt is None:
        return False

    current_beijing = (
        now_beijing.replace(tzinfo=BEIJING_TZ)
        if now_beijing.tzinfo is None
        else now_beijing.astimezone(BEIJING_TZ)
    )
    if quote_dt.date() != current_beijing.date():
        return False

    if source == "us_index":
        eastern_dt = quote_dt.astimezone(US_EASTERN_TZ)
        return (
            eastern_dt.weekday() < 5
            and time(9, 30) <= eastern_dt.time() <= time(16, 0)
        )

    windows = (
        _GLOBAL_INDEX_WINDOWS_BEIJING.get(item_symbol, [])
        if source == "global_index"
        else _MARKET_WINDOWS_BEIJING.get(source, [])
    )
    return _time_in_windows(quote_dt.time(), windows)


def has_opened_today(source: str, item_symbol: str, now_beijing: datetime) -> bool:
    current_beijing = (
        now_beijing.replace(tzinfo=BEIJING_TZ)
        if now_beijing.tzinfo is None
        else now_beijing.astimezone(BEIJING_TZ)
    )
    if source == "us_index":
        et = current_beijing.astimezone(US_EASTERN_TZ)
        return et.weekday() < 5 and et.time() >= time(9, 30)
    windows = (
        _GLOBAL_INDEX_WINDOWS_BEIJING.get(item_symbol, [])
        if source == "global_index"
        else _MARKET_WINDOWS_BEIJING.get(source, [])
    )
    if not windows:
        return False
    first_start = min(start for start, _ in windows)
    return current_beijing.time() >= first_start


def has_closed_today(source: str, item_symbol: str, now_beijing: datetime) -> bool:
    current_beijing = (
        now_beijing.replace(tzinfo=BEIJING_TZ)
        if now_beijing.tzinfo is None
        else now_beijing.astimezone(BEIJING_TZ)
    )
    if source == "us_index":
        et = current_beijing.astimezone(US_EASTERN_TZ)
        return et.weekday() >= 5 or et.time() >= time(16, 0)
    windows = (
        _GLOBAL_INDEX_WINDOWS_BEIJING.get(item_symbol, [])
        if source == "global_index"
        else _MARKET_WINDOWS_BEIJING.get(source, [])
    )
    if not windows:
        return False
    last_end = max(end for _, end in windows)
    return current_beijing.time() >= last_end


def compute_row_metrics(df: pd.DataFrame, asof: pd.Timestamp | None = None,
                        ma_window: int = MA_WINDOW, vol_window: int = VOL_WINDOW,
                        realtime_price: float | None = None,
                        realtime_date: str | pd.Timestamp | None = None) -> RowMetrics:
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
    d_daily = d.copy()

    vol_ratio: float | None = None
    if d["volume"].notna().any():
        vols = d["volume"].astype(float)
        if len(vols) > vol_window and vols.iloc[-vol_window - 1:-1].mean() > 0:
            vol_ratio = float(vols.iloc[-1] / vols.iloc[-vol_window - 1:-1].mean())

    if realtime_price is not None and realtime_date is not None and np.isfinite(realtime_price):
        rt_date = pd.to_datetime(realtime_date)
        last_daily_date = d["date"].iloc[-1]
        if rt_date > last_daily_date:
            # 盘中只把实时价作为额外比较点，MA20 沿用最新日线收盘均线。
            realtime_row = d.iloc[[-1]].copy()
            realtime_row.loc[:, "date"] = rt_date
            realtime_row.loc[:, "close"] = float(realtime_price)
            realtime_row.loc[:, "ma"] = float(d["ma"].iloc[-1])
            d = pd.concat([d, realtime_row], ignore_index=True)

    price = float(d["close"].iloc[-1])
    ma20 = float(d["ma"].iloc[-1])
    prev_close = float(d["close"].iloc[-2]) if len(d) >= 2 else price
    change_pct = (price / prev_close - 1) * 100 if prev_close else 0.0
    bias_pct = (price - ma20) / ma20 * 100 if ma20 else 0.0
    above_ma = price >= ma20

    # 状态转变和区间涨幅只看日线收盘，盘中实时价不参与。
    above_series = d_daily["close"] >= d_daily["ma"]
    flip = above_series != above_series.shift(1)
    flip.iloc[0] = False
    flip_idx = d_daily.index[flip]
    state_change_date = None
    range_pct = None
    if len(flip_idx) > 0:
        last_flip = flip_idx[-1]
        state_change_date = d_daily["date"].iloc[last_flip]
        base = float(d_daily["close"].iloc[last_flip])
        daily_price = float(d_daily["close"].iloc[-1])
        range_pct = (daily_price / base - 1) * 100 if base else None

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
    now_beijing = datetime.now(BEIJING_TZ)

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

        price = m.price
        change_pct = m.change_pct
        bias_pct = m.bias_pct
        quote_time = "-"
        quote_is_today = False
        status = "已收盘"
        try:
            quote = ms.fetch_quote(item)
        except Exception:
            quote = None

        if quote is not None and np.isfinite(quote["price"]):
            quote_is_today = quote["quote_date"] == now_beijing.date().isoformat()
            quote_time = quote["display"]
            if quote_is_today:
                if not has_opened_today(item.source, item.symbol, now_beijing):
                    status = "未开盘"
                elif has_closed_today(item.source, item.symbol, now_beijing):
                    status = "已收盘"
                else:
                    status = "盘中"
        if (
            quote is not None
            and np.isfinite(quote["price"])
            and quote_is_today
            and has_opened_today(item.source, item.symbol, now_beijing)
        ):
            try:
                realtime_m = compute_row_metrics(
                    df,
                    asof=asof_ts,
                    realtime_price=quote["price"],
                    realtime_date=quote["quote_date"],
                )
            except Exception:
                realtime_m = m
            price = quote["price"]
            prev_close = quote["prev_close"]
            change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0.0
            bias_pct = ((price - realtime_m.ma20) / realtime_m.ma20 * 100) if realtime_m.ma20 else 0.0

        rows.append({
            "代码": item.code, "名称": item.name,
            "报价时间": quote_time,
            "状态": status,
            "涨幅%": round(change_pct, 2),
            "现价": round(price, 2),
            "20日均线": round(m.ma20, 2),
            "偏离率%": round(bias_pct, 2),
            "量比": round(m.vol_ratio, 2) if m.vol_ratio is not None else None,
            "状态转变时间": m.state_change_date.date().isoformat() if m.state_change_date is not None else "-",
            "区间涨幅%": round(m.range_pct, 2) if m.range_pct is not None else None,
            "_bias_raw": bias_pct,
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
    cols = ["排序", "代码", "名称", "报价时间", "涨幅%", "现价", "20日均线", "偏离率%",
            "量比", "状态转变时间", "区间涨幅%", "排序变化", "状态"]
    return df[cols]
