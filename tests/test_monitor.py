"""趋势监控逻辑测试（离线，合成数据）。"""
import numpy as np
import pandas as pd
import pytest

from backfire.monitor import compute_row_metrics, build_snapshot, MA_WINDOW


def _df(closes, volumes=None):
    n = len(closes)
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="B"),
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": volumes if volumes is not None else [np.nan] * n,
    })


def test_bias_and_ma():
    # 前20天=10，最后一天跳到 12 → MA20≈(10*19+12)/20=10.1, 偏离=(12-10.1)/10.1
    closes = [10.0] * 19 + [10.0, 12.0]  # 21 个点
    m = compute_row_metrics(_df(closes))
    assert m.price == 12.0
    assert m.ma20 == pytest.approx((10.0 * 19 + 12.0) / 20, abs=1e-6)
    assert m.bias_pct == pytest.approx((12.0 - m.ma20) / m.ma20 * 100, abs=1e-6)
    assert m.above_ma is True


def test_change_pct():
    closes = [10.0] * 20 + [11.0]
    m = compute_row_metrics(_df(closes))
    assert m.change_pct == pytest.approx(10.0, abs=1e-6)  # 10→11 = +10%


def test_vol_ratio():
    closes = [10.0] * 25
    vols = [100.0] * 24 + [300.0]  # 今日量 300, 过去5日均量 100 → 量比 3
    m = compute_row_metrics(_df(closes, vols))
    assert m.vol_ratio == pytest.approx(3.0, abs=1e-6)


def test_vol_ratio_none_when_no_volume():
    closes = [10.0] * 25
    m = compute_row_metrics(_df(closes))  # volume 全 NaN
    assert m.vol_ratio is None


def test_state_change_and_range():
    # 价格长期在 MA 下方，最后几天上穿 → 状态转变日为上穿那天
    closes = [10.0] * 20 + [9.0, 9.0, 9.0, 12.0, 13.0]
    m = compute_row_metrics(_df(closes))
    assert m.above_ma is True
    assert m.state_change_date is not None
    # 区间涨幅 = 现价(13) 相对 上穿日收盘 的涨幅，应为正
    assert m.range_pct > 0


def test_insufficient_data_raises():
    with pytest.raises(ValueError):
        compute_row_metrics(_df([10.0] * (MA_WINDOW - 1)))


def test_asof_slices_history():
    closes = list(range(10, 40))  # 递增
    full = compute_row_metrics(_df(closes))
    asof = pd.Timestamp("2024-01-01") + pd.tseries.offsets.BDay(24)
    sliced = compute_row_metrics(_df(closes), asof=asof)
    # 截断到第25个交易日，现价应不同于全量末值
    assert sliced.price != full.price


def test_build_snapshot_offline(monkeypatch):
    """用假数据源验证 build_snapshot 的排序与列。"""
    from backfire import monitor_sources as ms

    items = [
        ms.MonitorItem("AAA", "强势", "a_index", "x"),
        ms.MonitorItem("BBB", "弱势", "a_index", "y"),
    ]
    # AAA 偏离率高（价远在MA上），BBB 偏离率低（价在MA下）
    data = {
        "x": _df([10.0] * 20 + [15.0]),
        "y": _df([10.0] * 20 + [8.0]),
    }
    monkeypatch.setattr(ms, "fetch_item", lambda it: data[it.symbol])

    snap = build_snapshot(watchlist=items)
    assert list(snap.columns) == ["排序", "代码", "名称", "涨幅%", "现价", "20日均线",
                                  "偏离率%", "量比", "状态转变时间", "区间涨幅%", "排序变化"]
    # 强势(AAA) 偏离率更高 → 排第一
    assert snap.iloc[0]["代码"] == "AAA"
    assert snap.iloc[1]["代码"] == "BBB"
    assert snap.iloc[0]["偏离率%"] > snap.iloc[1]["偏离率%"]


def test_build_snapshot_skips_failures(monkeypatch):
    from backfire import monitor_sources as ms

    items = [
        ms.MonitorItem("OK", "可用", "a_index", "ok"),
        ms.MonitorItem("BAD", "失败", "a_index", "bad"),
    ]

    def fake(it):
        if it.symbol == "bad":
            raise RuntimeError("source down")
        return _df([10.0] * 20 + [11.0])

    monkeypatch.setattr(ms, "fetch_item", fake)
    snap = build_snapshot(watchlist=items)
    assert len(snap) == 1
    assert snap.iloc[0]["代码"] == "OK"
