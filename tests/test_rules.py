"""A股交易规则测试：涨跌停标记、佣金/印花税（离线）。"""
import pandas as pd
import pytest

from backfire.config import LIMIT, COST
from backfire.engine.feed import with_limit_flags, _limit_pct
from backfire.engine.commission import AStockCommission


def _make_df(closes):
    n = len(closes)
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1] * n, "amount": [1] * n,
    })


def test_limit_up_down_flags():
    # +10% 涨停, -10% 跌停
    df = _make_df([10.0, 11.0, 11.0, 9.9])
    f = with_limit_flags(df, "sh600000", None, LIMIT)
    assert list(f["limit_up"]) == [0.0, 1.0, 0.0, 0.0]
    assert list(f["limit_down"]) == [0.0, 0.0, 0.0, 1.0]


def test_limit_pct_by_board():
    assert _limit_pct("sh600000", None, LIMIT) == LIMIT.limit_main   # 主板 10%
    assert _limit_pct("sz300750", None, LIMIT) == LIMIT.limit_star   # 创业板 20%
    assert _limit_pct("sh688981", None, LIMIT) == LIMIT.limit_star   # 科创板 20%
    assert _limit_pct("sh510300", "etf", LIMIT) == LIMIT.limit_etf   # ETF 10%


def test_etf_limit_20pct_not_triggered_on_main_board_threshold():
    # 创业板 +12% 不算涨停（阈值 20%）
    df = _make_df([10.0, 11.2])
    f = with_limit_flags(df, "sz300750", None, LIMIT)
    assert f["limit_up"].iloc[1] == 0.0


def _comm():
    return AStockCommission(
        commission=COST.commission_rate, min_commission=COST.min_commission,
        stamp_duty=COST.stamp_duty, transfer_fee=COST.transfer_fee_rate,
    )


def test_commission_min_floor():
    # 买入1万: max(10000*0.00025, 5) + 过户0.1 = 5.0 + 0.1
    fee = _comm()._getcommission(1000, 10.0, False)
    assert fee == pytest.approx(5.10, abs=1e-6)


def test_commission_large_trade():
    # 买入100万: 1_000_000*0.00025=250 > 5, + 过户10 = 260
    fee = _comm()._getcommission(100_000, 10.0, False)
    assert fee == pytest.approx(260.0, abs=1e-6)


def test_stamp_duty_on_sell_only():
    buy = _comm()._getcommission(100_000, 10.0, False)   # 无印花
    sell = _comm()._getcommission(-100_000, 10.0, False)  # 含印花 1000
    assert sell - buy == pytest.approx(1_000_000 * COST.stamp_duty, abs=1e-6)
