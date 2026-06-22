"""backtrader 数据源构建：把标准 DataFrame 转成带涨跌停标记的 feed。

额外携带两条 line：
- limit_up: 当日是否一字/触及涨停（收盘≈昨收*（1+幅度））→ 禁止买入
- limit_down: 当日是否触及跌停 → 禁止卖出
判定用收盘价相对前收的涨跌幅，配合 LimitConfig.eps 容差近似。
"""
from __future__ import annotations

import backtrader as bt
import pandas as pd

from ..config import LimitConfig
from ..data.symbols import AssetType, classify


def _limit_pct(symbol: str, asset_type, limit: LimitConfig) -> float:
    at = classify(symbol, asset_type)
    if at == AssetType.ETF:
        return limit.limit_etf
    if at == AssetType.INDEX:
        return 1.0  # 指数不设涨跌停（不会触发限制）
    code = symbol[-6:]
    if code.startswith(("30", "68")):  # 创业板/科创板
        return limit.limit_star
    return limit.limit_main


def with_limit_flags(df: pd.DataFrame, symbol: str, asset_type, limit: LimitConfig) -> pd.DataFrame:
    """给标准 DataFrame 加 limit_up / limit_down 列（0/1）。"""
    df = df.copy()
    pct = _limit_pct(symbol, asset_type, limit)
    prev_close = df["close"].shift(1)
    chg = (df["close"] - prev_close) / prev_close
    df["limit_up"] = ((chg >= pct - limit.eps)).astype(float)
    df["limit_down"] = ((chg <= -(pct - limit.eps))).astype(float)
    df.loc[df.index[0], ["limit_up", "limit_down"]] = 0.0  # 首日无前收
    return df


class AStockData(bt.feeds.PandasData):
    """带涨跌停标记的 Pandas 数据源。"""

    lines = ("limit_up", "limit_down")
    params = (
        ("datetime", None),   # 用 DataFrame 的 DatetimeIndex
        ("open", "open"),
        ("high", "high"),
        ("low", "low"),
        ("close", "close"),
        ("volume", "volume"),
        ("openinterest", None),
        ("limit_up", "limit_up"),
        ("limit_down", "limit_down"),
    )


def make_feed(df: pd.DataFrame, symbol: str, asset_type=None, limit: LimitConfig | None = None):
    """从标准 DataFrame 构建 backtrader feed。"""
    from ..config import LIMIT

    limit = limit or LIMIT
    flagged = with_limit_flags(df, symbol, asset_type, limit)
    flagged = flagged.set_index("date")
    return AStockData(dataname=flagged)
