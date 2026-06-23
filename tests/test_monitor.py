"""趋势监控逻辑测试（离线，合成数据）。"""
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from backfire import monitor
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


def test_realtime_price_does_not_change_daily_state_change_or_range():
    """盘中实时价只覆盖现价口径，不改日线状态转变和区间涨幅。"""
    closes = [10.0] * 20 + [9.0, 9.0, 9.0, 12.0, 13.0]
    daily = _df(closes)
    daily_metrics = compute_row_metrics(daily)
    realtime_date = "2024-02-15"
    realtime_price = 8.0

    m = compute_row_metrics(daily, realtime_price=realtime_price, realtime_date=realtime_date)

    assert daily_metrics.above_ma is True
    assert realtime_price < daily_metrics.ma20
    assert m.ma20 == pytest.approx(daily_metrics.ma20, abs=1e-6)
    assert m.price == realtime_price
    assert m.above_ma is False
    assert m.state_change_date == daily_metrics.state_change_date
    assert m.range_pct == pytest.approx(daily_metrics.range_pct, abs=1e-6)


def test_realtime_price_none_keeps_daily_crossover_result():
    closes = [10.0] * 20 + [9.0, 9.0, 9.0, 12.0, 13.0]
    daily = _df(closes)
    pure_daily = compute_row_metrics(daily)

    with_realtime_none = compute_row_metrics(
        daily,
        realtime_price=None,
        realtime_date="2024-02-15",
    )

    assert with_realtime_none == pure_daily


def test_realtime_date_matching_last_daily_date_keeps_daily_crossover_result():
    closes = [10.0] * 20 + [12.0] * 5
    daily = _df(closes)
    pure_daily = compute_row_metrics(daily)
    last_daily_date = daily["date"].iloc[-1].date().isoformat()

    with_duplicate_realtime_date = compute_row_metrics(
        daily,
        realtime_price=9.0,
        realtime_date=last_daily_date,
    )

    assert with_duplicate_realtime_date == pure_daily


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
    monkeypatch.setattr(ms, "fetch_quote_time", lambda it: "06-23 11:35:57")
    monkeypatch.setattr(ms, "fetch_quote", lambda it: None)

    snap = build_snapshot(watchlist=items)
    assert list(snap.columns) == ["排序", "代码", "名称", "报价时间", "涨幅%", "现价", "20日均线",
                                  "偏离率%", "量比", "状态转变时间", "区间涨幅%", "排序变化", "状态"]
    # 强势(AAA) 偏离率更高 → 排第一
    assert snap.iloc[0]["代码"] == "AAA"
    assert snap.iloc[0]["报价时间"] == "-"
    assert snap.iloc[0]["状态"] == "已收盘"
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
    def fail_quote(it):
        raise RuntimeError("quote source down")

    monkeypatch.setattr(ms, "fetch_quote", fail_quote)
    snap = build_snapshot(watchlist=items)
    assert len(snap) == 1
    assert snap.iloc[0]["代码"] == "OK"
    assert snap.iloc[0]["报价时间"] == "-"
    assert snap.iloc[0]["状态"] == "已收盘"


def test_build_snapshot_overlays_realtime_quote(monkeypatch):
    """实时报价成功时，现价/涨幅/偏离率/排序使用实时价，MA20 仍来自日线。"""
    from backfire import monitor_sources as ms

    items = [
        ms.MonitorItem("AAA", "实时强势", "a_index", "x"),
        ms.MonitorItem("BBB", "日线强势", "a_index", "y"),
    ]
    data = {
        "x": _df([10.0] * 20 + [9.0]),
        "y": _df([10.0] * 20 + [12.0]),
    }

    def quote(it):
        if it.symbol == "x":
            return {
                "price": 13.0,
                "prev_close": 10.0,
                "quote_date": pd.Timestamp.now(tz="Asia/Shanghai").date().isoformat(),
                "quote_time": "10:35:57",
                "display": "06-23 10:35:57",
            }
        return None

    monkeypatch.setattr(ms, "fetch_item", lambda it: data[it.symbol])
    monkeypatch.setattr(ms, "fetch_quote", quote)

    snap = build_snapshot(watchlist=items)
    row = snap[snap["代码"] == "AAA"].iloc[0]
    pure_daily = compute_row_metrics(data["x"])
    assert snap.iloc[0]["代码"] == "AAA"
    assert row["现价"] == 13.0
    assert row["涨幅%"] == pytest.approx(30.0)
    assert row["20日均线"] == pytest.approx(9.95)
    assert row["偏离率%"] == pytest.approx(round((13.0 - 9.95) / 9.95 * 100, 2))
    assert row["报价时间"] == "06-23 10:35:57"
    assert row["状态"] == "盘中"
    assert row["状态转变时间"] == (
        pure_daily.state_change_date.date().isoformat()
        if pure_daily.state_change_date is not None
        else "-"
    )
    assert row["区间涨幅%"] == (
        round(pure_daily.range_pct, 2)
        if pure_daily.range_pct is not None
        else None
    )


def test_build_snapshot_falls_back_when_quote_missing(monkeypatch):
    """实时报价失败时保留原日线口径，报价时间为 '-'，不丢行。"""
    from backfire import monitor_sources as ms

    item = ms.MonitorItem("AAA", "日线回退", "a_index", "x")
    monkeypatch.setattr(ms, "fetch_item", lambda it: _df([10.0] * 20 + [12.0]))
    monkeypatch.setattr(ms, "fetch_quote", lambda it: None)

    snap = build_snapshot(watchlist=[item])
    row = snap.iloc[0]
    assert row["代码"] == "AAA"
    assert row["现价"] == 12.0
    assert row["涨幅%"] == 20.0
    assert row["偏离率%"] == pytest.approx(round((12.0 - 10.1) / 10.1 * 100, 2))
    assert row["报价时间"] == "-"
    assert row["状态"] == "已收盘"


def test_is_market_open_a_index_sessions():
    now = datetime(2026, 6, 23, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert monitor.is_market_open("a_index", "sh000300", "2026-06-23", "10:00:00", now) is True
    assert monitor.is_market_open("a_index", "sh000300", "2026-06-23", "12:00:00", now) is False
    assert monitor.is_market_open("a_index", "sh000300", "2026-06-23", "15:30:00", now) is False
    assert monitor.is_market_open("a_index", "sh000300", "2026-06-22", "10:00:00", now) is False


def test_is_market_open_global_index_sessions():
    now = datetime(2026, 6, 23, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert monitor.is_market_open("global_index", "日经225指数", "2026-06-23", "09:00:00", now) is True
    assert monitor.is_market_open("global_index", "日经225指数", "2026-06-23", "14:45:00", now) is False


def test_is_market_open_sge_spot_night_session():
    now = datetime(2026, 6, 23, 21, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert monitor.is_market_open("sge_spot", "Au99.99", "2026-06-23", "21:00:00", now) is True
    assert monitor.is_market_open("sge_spot", "Au99.99", "2026-06-23", "16:00:00", now) is False


def test_is_market_open_us_index_uses_eastern_dst():
    now = datetime(2026, 7, 1, 22, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert monitor.is_market_open("us_index", ".NDX", "2026-07-01", "22:00:00", now) is True
    assert monitor.is_market_open("us_index", ".NDX", "2026-07-01", "12:00:00", now) is False


def test_extract_quote_time_formats():
    from backfire import monitor_sources as ms

    a_fields = [""] * 32
    a_fields[2], a_fields[3], a_fields[30], a_fields[31] = "1900", "1940.65", "2026-06-23", "11:35:57"
    us_fields = [""] * 5
    us_fields[1], us_fields[3], us_fields[4] = "22000", "2026-06-23 05:30:00", "120"
    znb_fields = [""] * 8
    znb_fields[1], znb_fields[2], znb_fields[6], znb_fields[7] = "39000", "300", "2026-06-23", "11:51:15"
    hk_fields = [""] * 19
    hk_fields[3], hk_fields[6], hk_fields[17], hk_fields[18] = "18500", "18600", "2026/06/23", "11:51:29"
    gds_fields = [""] * 13
    gds_fields[0], gds_fields[6], gds_fields[7], gds_fields[12] = "780", "11:51:00", "775", "2026-06-23"

    assert ms._extract_quote_time("a_index", a_fields) == "06-23 11:35:57"
    assert ms._extract_quote_time("us_index", us_fields) == "06-23 05:30:00"
    assert ms._extract_quote_time("global_index", znb_fields) == "06-23 11:51:15"
    assert ms._extract_quote_time("hk_index", hk_fields) == "06-23 11:51:29"
    assert ms._extract_quote_time("sge_spot", gds_fields) == "06-23 11:51:00"
