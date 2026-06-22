"""绩效指标计算测试（离线，合成净值）。"""
import numpy as np
import pandas as pd
import pytest

from backfire.report.metrics import compute_metrics, _max_drawdown


def _equity(values):
    idx = pd.date_range("2020-01-01", periods=len(values), freq="B")
    return pd.Series(values, index=idx, name="equity")


def test_total_return():
    eq = _equity([100, 110, 121])
    m = compute_metrics(eq, periods_per_year=252)
    assert m.total_return == pytest.approx(0.21, abs=1e-9)


def test_max_drawdown():
    eq = _equity([100, 120, 90, 130])  # 峰120→谷90 = -25%
    assert _max_drawdown(eq) == pytest.approx(-0.25, abs=1e-9)


def test_drawdown_in_metrics():
    eq = _equity([100, 120, 90, 130])
    m = compute_metrics(eq)
    assert m.max_drawdown == pytest.approx(-0.25, abs=1e-9)


def test_cagr_one_year():
    # 252 个交易日 = 1 年，翻倍 → CAGR≈100%
    vals = list(np.linspace(100, 200, 253))
    eq = _equity(vals)
    m = compute_metrics(eq, periods_per_year=252)
    assert m.cagr == pytest.approx(1.0, rel=0.05)


def test_benchmark_excess():
    eq = _equity([100, 105, 110])  # +10%
    bench = pd.Series([0.0, 0.02, 0.02], index=eq.index)  # 约 +4.04%
    m = compute_metrics(eq, benchmark_returns=bench)
    assert m.benchmark_return == pytest.approx(0.0404, abs=1e-3)
    assert m.excess_return == pytest.approx(m.total_return - m.benchmark_return, abs=1e-9)


def test_win_rate():
    eq = _equity([100, 101, 100, 102])  # 涨,跌,涨 → 2/3
    m = compute_metrics(eq)
    assert m.win_rate == pytest.approx(2 / 3, abs=1e-9)


def test_too_short_raises():
    with pytest.raises(ValueError):
        compute_metrics(_equity([100]))
