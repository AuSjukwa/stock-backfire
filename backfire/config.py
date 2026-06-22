"""集中配置：费率、基准、缓存路径、网络。

A股交易成本与规则参数集中在此，方便统一调整与测试。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 网络：本机 eastmoney 不可达，akshare 走 Sina 源并绕过系统代理。
# 在导入数据层时调用 apply_network_env() 即可。
# ---------------------------------------------------------------------------
def apply_network_env() -> None:
    """绕过系统代理，让 requests 直连 Sina 等数据源。"""
    for key in list(os.environ):
        if "proxy" in key.lower():
            os.environ.pop(key, None)
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"


# ---------------------------------------------------------------------------
# A股交易成本（默认值，可在回测时覆盖）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CostConfig:
    commission_rate: float = 0.00025  # 佣金 双边 万2.5
    min_commission: float = 5.0       # 单笔最低 5 元
    stamp_duty: float = 0.001         # 印花税 卖出千1（单边）
    transfer_fee_rate: float = 0.00001  # 过户费 万0.1（双边，沪深统一近似）
    slippage_perc: float = 0.0005     # 滑点 万5（双边，按成交价百分比）
    lot_size: int = 100               # 整手 100 股


# ---------------------------------------------------------------------------
# 涨跌停（用于禁止在涨停买入 / 跌停卖出）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LimitConfig:
    limit_main: float = 0.10   # 主板 ±10%
    limit_star: float = 0.20   # 科创板/创业板 ±20%
    limit_etf: float = 0.10    # ETF ±10%
    eps: float = 0.005         # 触停判定的容差（接近即视为触停）


# ---------------------------------------------------------------------------
# 基准
# ---------------------------------------------------------------------------
BENCHMARKS = {
    "沪深300": "sh000300",
    "中证500": "sh000905",
    "上证指数": "sh000001",
    "创业板指": "sz399006",
}
DEFAULT_BENCHMARK = "sh000300"

# 默认回测参数
DEFAULT_CASH = 1_000_000.0
TRADING_DAYS_PER_YEAR = 252

COST = CostConfig()
LIMIT = LimitConfig()
