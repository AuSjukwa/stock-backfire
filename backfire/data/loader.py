"""本地缓存 + 统一加载接口。

策略：Sina 接口返回全历史，按 (norm_symbol, adjust) 缓存为 parquet。
- 缓存当天已更新过则直接读本地；否则重新抓取并覆盖（增量价值不大且 Sina 全量返回）。
- load() 对外只暴露按日期区间切片后的标准 DataFrame。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from .. import config
from . import fetcher
from .symbols import AssetType, classify, normalize


def _cache_path(norm_symbol: str, adjust: str) -> Path:
    return config.CACHE_DIR / f"{norm_symbol}_{adjust}.parquet"


def _is_fresh(path: Path) -> bool:
    """缓存文件今天写过则视为新鲜（盘后数据当日内不变）。"""
    if not path.exists():
        return False
    mtime = dt.date.fromtimestamp(path.stat().st_mtime)
    return mtime >= dt.date.today()


def get_full_history(
    symbol: str,
    adjust: str = "qfq",
    asset_type: AssetType | str | None = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """取标的全历史（带缓存）。"""
    norm = normalize(symbol)
    at = classify(symbol, asset_type)
    path = _cache_path(norm, adjust)

    if not force_refresh and _is_fresh(path):
        return pd.read_parquet(path)

    try:
        df = fetcher.fetch(symbol, adjust=adjust, asset_type=at)
    except Exception:
        # 抓取失败时回退到旧缓存（若有），避免完全中断
        if path.exists():
            return pd.read_parquet(path)
        raise

    df.to_parquet(path, index=False)
    return df


def load(
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    adjust: str = "qfq",
    asset_type: AssetType | str | None = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """对外统一加载接口：返回 [date, open, high, low, close, volume, amount]，
    date 升序，索引为 0..n-1。上层不感知数据来源。
    """
    df = get_full_history(symbol, adjust=adjust, asset_type=asset_type, force_refresh=force_refresh)
    if start is not None:
        df = df[df["date"] >= pd.to_datetime(start)]
    if end is not None:
        df = df[df["date"] <= pd.to_datetime(end)]
    return df.reset_index(drop=True)


def load_many(
    symbols: list[str],
    start: str | None = None,
    end: str | None = None,
    adjust: str = "qfq",
    field: str = "close",
) -> pd.DataFrame:
    """加载多标的某字段，按日期对齐成宽表（列=标的代码）。用于轮动/因子策略。"""
    series = {}
    for sym in symbols:
        df = load(sym, start, end, adjust=adjust)
        s = df.set_index("date")[field]
        series[normalize(sym)] = s
    wide = pd.DataFrame(series).sort_index()
    return wide
