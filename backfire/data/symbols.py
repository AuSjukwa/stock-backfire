"""标的代码归一化与类型识别。

统一把用户输入（'600000'、'sh600000'、'510300.SH'）转成 Sina 格式 'sh600000'，
并判断标的类型（股票/ETF/指数），以便分流到不同抓取接口。

注意 A股 6 位代码存在歧义：000xxx 在深市是股票（000001=平安银行），
在沪市是指数（000300=沪深300）。因此：
- 带前缀输入（sh000300 / 000300.SH）是最可靠的方式，直接采用；
- 纯 6 位 000xxx：命中已知沪市指数表则按指数处理，否则当深市股票。
"""
from __future__ import annotations

import re
from enum import Enum


class AssetType(str, Enum):
    STOCK = "stock"
    ETF = "etf"
    INDEX = "index"


# 常用沪市指数（000xxx 在沪市为指数；与深市同号股票冲突时以带前缀输入为准）
KNOWN_SH_INDEX = {
    "000001",  # 上证指数（与深市平安银行同号，纯数字默认解析为股票，需用 sh000001）
    "000300",  # 沪深300
    "000016",  # 上证50
    "000905",  # 中证500
    "000852",  # 中证1000
    "000688",  # 科创50
    "000010",  # 上证180
    "000009",  # 上证380
}
# 纯数字默认解析为股票的歧义码（用户要指数须带 sh 前缀）
_AMBIGUOUS_AS_STOCK = {"000001"}

_PREFIXED_RE = re.compile(r"^(sh|sz)\s*\.?\s*(\d{6})$")
_DOTTED_RE = re.compile(r"^(\d{6})\s*\.\s*(sh|sz|ss|xshg|xshe)$")
_CODE_RE = re.compile(r"(\d{6})")


def _infer_exchange(code6: str) -> str:
    """按 6 位代码推断交易所前缀（纯数字、无前缀时）。"""
    if code6.startswith(("60", "68", "9", "11", "13")):
        return "sh"  # 沪主板/科创板/沪B/沪债
    if code6.startswith(("51", "56", "58")):
        return "sh"  # 沪市 ETF
    if code6.startswith("000") and code6 in KNOWN_SH_INDEX and code6 not in _AMBIGUOUS_AS_STOCK:
        return "sh"  # 已知沪市指数
    if code6.startswith(("00", "30", "15", "16", "18", "20", "39")):
        return "sz"  # 深主板/创业板/深ETF/深指数
    return "sh"


def normalize(symbol: str) -> str:
    """归一化为 Sina 格式，如 'sh600000' / 'sz000001'。带前缀输入直接采用。"""
    s = symbol.strip().lower()
    m = _PREFIXED_RE.match(s)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    m = _DOTTED_RE.match(s)
    if m:
        ex = m.group(2)
        ex = "sh" if ex in ("sh", "ss", "xshg") else "sz"
        return f"{ex}{m.group(1)}"
    m = _CODE_RE.search(s)
    if m:
        code = m.group(1)
        return f"{_infer_exchange(code)}{code}"
    raise ValueError(f"无法识别的标的代码: {symbol!r}")


def code6(symbol: str) -> str:
    """取 6 位数字代码。"""
    return normalize(symbol)[2:]


def classify(symbol: str, hint: "AssetType | str | None" = None) -> AssetType:
    """识别标的类型。hint 优先；否则按归一化后的代码规则推断。"""
    if hint is not None:
        return AssetType(hint)
    norm = normalize(symbol)
    ex, c = norm[:2], norm[2:]
    # 指数: sh000xxx(已知指数) / sz399xxx
    if ex == "sz" and c.startswith("399"):
        return AssetType.INDEX
    if ex == "sh" and c.startswith("000") and c in KNOWN_SH_INDEX:
        return AssetType.INDEX
    # ETF: sh 51/56/58, sz 15/16
    if (ex == "sh" and c.startswith(("51", "56", "58"))) or (ex == "sz" and c.startswith(("15", "16"))):
        return AssetType.ETF
    return AssetType.STOCK
