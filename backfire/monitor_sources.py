"""趋势监控的多源行情接入。

监控表里既有 A股指数，也有美股/港股/全球指数和商品现货，数据源各不相同。
这里按来源分流抓取，统一标准化为 [date, open, high, low, close, volume]。
所有来源均已在本机实测可用（走 Sina，绕过系统代理）。
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import config

config.apply_network_env()
import akshare as ak  # noqa: E402


@dataclass(frozen=True)
class MonitorItem:
    """一条监控标的：展示代码、名称、数据源、源符号。"""
    code: str        # 表格展示用代码（对齐图片，如 KS11/QQQ/399006）
    name: str        # 中文名
    source: str      # a_index | us_index | hk_index | global_index | sge_spot
    symbol: str      # 该数据源的实际查询符号


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
