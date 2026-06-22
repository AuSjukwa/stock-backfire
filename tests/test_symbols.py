"""标的代码归一化与类型识别测试（离线）。"""
import pytest

from backfire.data.symbols import normalize, classify, code6, AssetType


@pytest.mark.parametrize("raw,expected", [
    ("600000", "sh600000"),
    ("sh600000", "sh600000"),
    ("600000.SH", "sh600000"),
    ("000001", "sz000001"),       # 纯数字默认深市股票（平安银行）
    ("sh000001", "sh000001"),     # 带前缀 → 上证指数
    ("510300", "sh510300"),
    ("159915", "sz159915"),
    ("000300", "sh000300"),       # 已知沪市指数
    ("399006", "sz399006"),
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected


def test_code6():
    assert code6("sh600000") == "600000"
    assert code6("000300") == "000300"


@pytest.mark.parametrize("raw,expected", [
    ("600000", AssetType.STOCK),
    ("sz300750", AssetType.STOCK),
    ("510300", AssetType.ETF),
    ("159915", AssetType.ETF),
    ("000300", AssetType.INDEX),
    ("sh000300", AssetType.INDEX),
    ("399006", AssetType.INDEX),
])
def test_classify(raw, expected):
    assert classify(raw) == expected


def test_classify_hint_overrides():
    # 000001 默认股票，但 hint 可强制
    assert classify("000001") == AssetType.STOCK
    assert classify("000001", "index") == AssetType.INDEX


def test_invalid_symbol():
    with pytest.raises(ValueError):
        normalize("not-a-code")
