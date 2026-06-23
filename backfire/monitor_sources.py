"""趋势监控的多源行情接入。

监控表里既有 A股指数，也有美股/港股/全球指数和商品现货，数据源各不相同。
这里按来源分流抓取，统一标准化为 [date, open, high, low, close, volume]。
所有来源均已在本机实测可用（走 Sina，绕过系统代理）。
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TypedDict

import pandas as pd

from . import config

config.apply_network_env()
import akshare as ak  # noqa: E402
import requests  # noqa: E402


@dataclass(frozen=True)
class MonitorItem:
    """一条监控标的：展示代码、名称、数据源、源符号。"""
    code: str        # 表格展示用代码（对齐图片，如 KS11/QQQ/399006）
    name: str        # 中文名
    source: str      # a_index | us_index | hk_index | global_index | sge_spot
    symbol: str      # 该数据源的实际查询符号


class Quote(TypedDict):
    price: float
    prev_close: float
    quote_date: str
    quote_time: str
    display: str


# 监控清单（对齐图片，按可靠性 curated；取不到的会自动跳过）
DEFAULT_WATCHLIST: list[MonitorItem] = [
    MonitorItem("KS11", "韩国综合", "global_index", "首尔综合指数"),
    MonitorItem("TWII", "台湾加权", "global_index", "中国台湾加权指数"),
    MonitorItem("N225", "日经225", "global_index", "日经225指数"),
    MonitorItem("QQQ", "纳指100", "us_index", ".NDX"),
    MonitorItem("399006", "创业板指", "a_index", "sz399006"),
    MonitorItem("SPY", "标普500", "us_index", ".INX"),
    MonitorItem("1B0688", "科创50", "a_index", "sh000688"),
    MonitorItem("399300", "沪深300", "a_index", "sh000300"),
    MonitorItem("000510", "中证A500", "a_index", "sh000510"),
    MonitorItem("AUUSDO", "黄金现货", "sge_spot", "Au99.99"),
    MonitorItem("HS2083", "恒生科技", "hk_index", "HSTECH"),
    MonitorItem("1B0016", "上证50", "a_index", "sh000016"),
    MonitorItem("HSI", "恒生指数", "hk_index", "HSI"),
    MonitorItem("399905", "中证500", "a_index", "sh000905"),
    MonitorItem("HSCEI", "国企指数", "hk_index", "HSCEI"),
    MonitorItem("1B0852", "中证1000", "a_index", "sh000852"),
    MonitorItem("899050", "北证50", "a_index", "bj899050"),
]


def _standardize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "volume" not in df.columns:
        df["volume"] = pd.NA
    df["date"] = pd.to_datetime(df["date"])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[["date", "open", "high", "low", "close", "volume"]]
    df = df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
    return df


def _fetch_a_index(symbol: str) -> pd.DataFrame:
    return _standardize(ak.stock_zh_index_daily(symbol=symbol))


def _fetch_us_index(symbol: str) -> pd.DataFrame:
    return _standardize(ak.index_us_stock_sina(symbol=symbol))


def _fetch_hk_index(symbol: str) -> pd.DataFrame:
    return _standardize(ak.stock_hk_index_daily_sina(symbol=symbol))


def _fetch_global_index(symbol: str) -> pd.DataFrame:
    return _standardize(ak.index_global_hist_sina(symbol=symbol))


def _fetch_sge_spot(symbol: str) -> pd.DataFrame:
    # 上海金交所现货：列为 date,open,close,low,high（无 volume）
    return _standardize(ak.spot_hist_sge(symbol=symbol))


_DISPATCH = {
    "a_index": _fetch_a_index,
    "us_index": _fetch_us_index,
    "hk_index": _fetch_hk_index,
    "global_index": _fetch_global_index,
    "sge_spot": _fetch_sge_spot,
}


def fetch_item(item: MonitorItem) -> pd.DataFrame:
    """抓取单条监控标的的日线历史，标准化返回。"""
    return _DISPATCH[item.source](item.symbol)


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

_GLOBAL_REALTIME_SYMBOLS = {
    "日经225指数": "znb_NKY",
    "首尔综合指数": "znb_KOSPI",
    "中国台湾加权指数": "znb_TWJQ",
}


def _resolve_realtime_symbol(item: MonitorItem) -> str | None:
    if item.source == "a_index":
        return item.symbol
    if item.source == "us_index":
        return f"gb_${item.symbol.removeprefix('.').lower()}"
    if item.source == "global_index":
        return _GLOBAL_REALTIME_SYMBOLS.get(item.symbol)
    if item.source == "hk_index":
        return f"rt_hk{item.symbol}"
    if item.source == "sge_spot":
        return "gds_AUTD"
    return None


def _normalize_quote_time(date_text: str, time_text: str) -> str | None:
    date_text = date_text.strip().replace("/", "-")
    time_text = time_text.strip()
    if not _DATE_RE.match(date_text) or not _TIME_RE.match(time_text):
        return None
    return f"{date_text[5:]} {time_text}"


def _to_float(value: str) -> float | None:
    try:
        number = float(value.strip())
    except (TypeError, ValueError):
        return None
    return number if pd.notna(number) else None


def _quote_result(price: float | None, prev_close: float | None,
                  date_text: str, time_text: str) -> Quote | None:
    if price is None or prev_close is None:
        return None
    quote_date = date_text.strip().replace("/", "-")
    quote_time = time_text.strip()
    display = _normalize_quote_time(quote_date, quote_time)
    if display is None:
        return None
    return {
        "price": price,
        "prev_close": prev_close,
        "quote_date": quote_date,
        "quote_time": quote_time,
        "display": display,
    }


def _extract_quote(source: str, fields: list[str]) -> Quote | None:
    """按 Sina 实时行情各格式提取报价：price/prev_close/date/time。

    字段表（0-based，GBK payload 逗号切分）：
    - a_index: price[3], prev_close[2], date[30], time[31]
    - us_index: price[1], change_amount[4], datetime[3]，prev_close=price-change
    - global_index: price[1], change_amount[2], date[6], time[7]，prev_close=price-change
    - hk_index: price[6], prev_close[3], date[17], time[18]
    - sge_spot: price[0], prev_close[7], date[12], time[6]
    """
    try:
        if source == "a_index":
            return _quote_result(_to_float(fields[3]), _to_float(fields[2]), fields[30], fields[31])

        if source == "us_index":
            price = _to_float(fields[1])
            change_amount = _to_float(fields[4])
            value = fields[3].strip()
            if price is None or change_amount is None or not _DATETIME_RE.match(value):
                return None
            return _quote_result(price, price - change_amount, value[:10], value[11:])

        if source == "global_index":
            price = _to_float(fields[1])
            change_amount = _to_float(fields[2])
            if price is None or change_amount is None:
                return None
            return _quote_result(price, price - change_amount, fields[6], fields[7])

        if source == "hk_index":
            return _quote_result(_to_float(fields[6]), _to_float(fields[3]), fields[17], fields[18])

        if source == "sge_spot":
            return _quote_result(_to_float(fields[0]), _to_float(fields[7]), fields[12], fields[6])
    except (IndexError, TypeError, ValueError):
        return None
    return None


def _fetch_realtime_fields(item: MonitorItem) -> list[str] | None:
    realtime_symbol = _resolve_realtime_symbol(item)
    if not realtime_symbol:
        return None

    try:
        r = requests.get(
            "https://hq.sinajs.cn/list=" + realtime_symbol,
            timeout=4,
            headers={"Referer": "https://finance.sina.com.cn"},
        )
        if r.status_code != 200 or not r.content:
            return None
        text = r.content.decode("gbk", errors="ignore").strip()
        if not text or '=""' in text or '"' not in text:
            return None
        payload = text.split('"', 1)[1].rsplit('"', 1)[0]
        if not payload:
            return None
        return payload.split(",")
    except Exception:  # noqa: BLE001
        return None


def _extract_quote_time(source: str, fields: list[str]) -> str | None:
    """按 Sina 实时行情各格式提取报价时间，返回 MM-DD HH:MM:SS。"""
    quote = _extract_quote(source, fields)
    return quote["display"] if quote is not None else None


def fetch_quote(item: MonitorItem) -> Quote | None:
    """抓取 Sina 实时报价；失败返回 None，不影响日线指标计算。"""
    fields = _fetch_realtime_fields(item)
    if fields is None:
        return None
    return _extract_quote(item.source, fields)


def fetch_quote_time(item: MonitorItem) -> str | None:
    """抓取 Sina 实时报价时间；失败返回 None，不影响日线指标计算。"""
    quote = fetch_quote(item)
    return quote["display"] if quote is not None else None
