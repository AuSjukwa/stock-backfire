"""行情抓取：统一走 Sina 源（本机 eastmoney 不可达）。

对外统一返回列：[date, open, high, low, close, volume, amount]
- date: pandas datetime
- 个股支持前复权(qfq)；ETF/指数 Sina 源为未复权，amount 缺失时填 NaN。
"""
from __future__ import annotations

import pandas as pd

from .. import config
from .symbols import AssetType, classify, normalize

config.apply_network_env()  # 绕过系统代理
import akshare as ak  # noqa: E402  (must come after proxy bypass)

_STD_COLS = ["date", "open", "high", "low", "close", "volume", "amount"]


def _standardize(df: pd.DataFrame) -> pd.DataFrame:
    """统一列名、类型、排序，补齐缺失列。"""
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "amount" not in df.columns:
        df["amount"] = pd.NA
    df["date"] = pd.to_datetime(df["date"])
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[_STD_COLS].sort_values("date").reset_index(drop=True)
    df = df.dropna(subset=["open", "high", "low", "close"])
    return df


def fetch_stock(symbol: str, adjust: str = "qfq") -> pd.DataFrame:
    norm = normalize(symbol)  # e.g. sh600000
    df = ak.stock_zh_a_daily(symbol=norm, adjust=adjust)
    return _standardize(df)


def fetch_etf(symbol: str, adjust: str = "qfq") -> pd.DataFrame:
    norm = normalize(symbol)
    # Sina ETF 接口不支持复权参数（未复权）
    df = ak.fund_etf_hist_sina(symbol=norm)
    return _standardize(df)


def fetch_index(symbol: str, adjust: str = "qfq") -> pd.DataFrame:
    norm = normalize(symbol)
    df = ak.stock_zh_index_daily(symbol=norm)
    return _standardize(df)


_DISPATCH = {
    AssetType.STOCK: fetch_stock,
    AssetType.ETF: fetch_etf,
    AssetType.INDEX: fetch_index,
}


def fetch(symbol: str, adjust: str = "qfq", asset_type: AssetType | str | None = None) -> pd.DataFrame:
    """按标的类型分流抓取，返回标准化全历史数据。"""
    at = classify(symbol, asset_type)
    return _DISPATCH[at](symbol, adjust=adjust)
