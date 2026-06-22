"""数据加载与端到端回测的集成测试（需要网络，可用 -m "not network" 跳过）。"""
import pytest

pytestmark = pytest.mark.network


def _has_network():
    from backfire import config
    config.apply_network_env()
    import requests
    try:
        r = requests.get("https://hq.sinajs.cn/list=sh000300", timeout=6,
                         headers={"Referer": "https://finance.sina.com.cn"})
        return r.status_code == 200 and "sh000300" in r.text
    except Exception:
        return False


@pytest.fixture(scope="module", autouse=True)
def _skip_if_offline():
    if not _has_network():
        pytest.skip("无网络或 Sina 不可达，跳过集成测试")


def test_load_stock_columns():
    from backfire.data import loader
    df = loader.load("600000", "2024-01-01", "2024-03-01")
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume", "amount"]
    assert len(df) > 10
    assert df["date"].is_monotonic_increasing


def test_load_index_and_etf():
    from backfire.data import loader
    idx = loader.load("000300", "2024-01-01", "2024-03-01", asset_type="index")
    etf = loader.load("510300", "2024-01-01", "2024-03-01")
    assert len(idx) > 10 and len(etf) > 10


def test_end_to_end_backtest():
    from backfire.engine.runner import run_backtest
    from backfire.strategies.timing_single import SingleTimingStrategy
    res = run_backtest(SingleTimingStrategy, "sh510300", "2022-01-01", "2023-12-31",
                       strategy_params={"mode": "ma_cross"})
    assert res.final_value > 0
    assert len(res.equity_curve) > 100
