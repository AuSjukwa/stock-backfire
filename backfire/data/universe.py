"""标的池：用于多标的轮动与因子选股策略。

提供几个开箱即用的标的池，用户也可在回测时自定义传入列表。
"""
from __future__ import annotations

# 宽基 + 行业 ETF 轮动池（常用、流动性好）
ETF_ROTATION = {
    "sh510300": "沪深300ETF",
    "sh510500": "中证500ETF",
    "sh588000": "科创50ETF",
    "sz159915": "创业板ETF",
    "sh518880": "黄金ETF",
    "sh513100": "纳指ETF",
    "sh511260": "十年国债ETF",
}

# 主要宽基指数
INDEX_BROAD = {
    "sh000300": "沪深300",
    "sh000905": "中证500",
    "sh000852": "中证1000",
    "sh000001": "上证指数",
    "sz399006": "创业板指",
}

# 一个示例蓝筹股票池（用于因子/打分演示，非投资建议）
STOCK_BLUECHIP = {
    "sh600519": "贵州茅台",
    "sh601318": "中国平安",
    "sh600036": "招商银行",
    "sh600900": "长江电力",
    "sz000333": "美的集团",
    "sz000651": "格力电器",
    "sh601012": "隆基绿能",
    "sz300750": "宁德时代",
}

PRESETS = {
    "ETF轮动池": ETF_ROTATION,
    "宽基指数": INDEX_BROAD,
    "蓝筹股票池": STOCK_BLUECHIP,
}


def get(name: str) -> list[str]:
    """按名称取标的池代码列表。"""
    if name not in PRESETS:
        raise KeyError(f"未知标的池: {name}，可选: {list(PRESETS)}")
    return list(PRESETS[name].keys())
