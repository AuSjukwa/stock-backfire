# A股回测平台 (stock-backfire)

验证 A股股票 / ETF / 大盘指数投资策略的回测平台。数据走 akshare(Sina 源)，
回测引擎用 backtrader，内置 A股交易规则，提供 Streamlit Web 面板。

## 特性

- **数据层**：个股 / ETF / 指数统一加载接口，前复权(个股)，parquet 本地缓存。
- **A股规则**：T+1 锁仓、涨跌停限制(主板10% / 创业板·科创板20% / ETF10%)、
  佣金(双边万2.5、最低5元)、印花税(卖出千1)、过户费、滑点、整手100股。
- **四类策略**：
  - 单标的技术择时(MA交叉 / MACD / RSI / 布林带)
  - 大盘择时控仓(指数均线信号控制仓位)
  - 多标的轮动 / 再平衡(动量轮动 / 等权再平衡)
  - 因子打分选股(动量 / 低波动 / 反转因子)
- **绩效报告**：年化、累计、最大回撤、夏普、卡玛、波动率、胜率，与基准对比，
  资金曲线 / 回撤 / 月度收益热力图。
- **Web 面板**：选标的、调参数、一键回测、即时看图。

## 安装

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 快速开始

### 命令行

```bash
# 单标的 MA 择时
.venv/bin/python -m backfire.cli --symbol 600000 --start 2022-01-01 --end 2024-12-31 \
    --strategy single_timing --mode ma_cross --fast 10 --slow 30
```

### Web 面板

```bash
.venv/bin/streamlit run app/streamlit_app.py
```

浏览器打开 http://localhost:8501 。面板默认仅监听本机，不对外暴露、无鉴权；
若要部署到公网，请自行加访问控制。

面板含两个页面（左上角切换）：
- **策略回测**：选标的/策略/参数，一键回测看资金曲线与绩效。
- **趋势监控**：一张横截面监控表，对一批指数/品种按「偏离率(现价相对MA20)」
  排序，红=强势(在MA20上方)、绿=弱势(跌破MA20)，含涨幅/量比/状态转变时间/
  区间涨幅/排序变化。覆盖 A股指数、美股(标普/纳指)、港股(恒指/恒科/国企)、
  全球指数(日经/台湾/韩国)、黄金现货。数据仅供市场风格趋势观察，不构成投资建议。

### Python API

```python
from backfire.engine.runner import run_backtest
from backfire.strategies.rotation import RotationStrategy
from backfire.report.metrics import compute_metrics, load_benchmark_returns
from backfire.data import universe

res = run_backtest(
    RotationStrategy, universe.get("ETF轮动池"),
    start="2021-01-01", end="2024-12-31",
    strategy_params={"mode": "momentum", "lookback": 60, "top_n": 2},
)
bench = load_benchmark_returns("沪深300", "2021-01-01", "2024-12-31")
m = compute_metrics(res.equity_curve, res.returns, benchmark_returns=bench)
print(m.to_dict())
```

## 标的代码格式

- 纯 6 位：`600000`(沪市股)、`000001`(深市股·平安银行)、`510300`(沪ETF)、`159915`(深ETF)。
- 带前缀(推荐，无歧义)：`sh600000`、`sz000001`、`sh000300`(沪深300指数)。
- 注意 `000001` 纯数字解析为深市平安银行；要上证指数请用 `sh000001`。

## 项目结构

```
backfire/
  config.py            费率/基准/缓存/网络配置
  registry.py          策略参数注册表(CLI 与 Web 共享)
  cli.py               命令行入口
  monitor.py           趋势监控横截面快照(偏离率/量比/状态转变/排序变化)
  monitor_sources.py   监控多源数据接入(A股/美股/港股/全球/商品)
  data/                fetcher / cache+loader / symbols / universe
  engine/              commission / feed(涨跌停标记) / runner
  strategies/          base + 四类策略
  report/              metrics / charts
app/streamlit_app.py   Web 面板(策略回测 + 趋势监控两页)
tests/                 pytest 单测 + 集成测试
```

## 测试

```bash
.venv/bin/python -m pytest            # 全部(含联网集成测试，无网自动跳过)
.venv/bin/python -m pytest -m "not network"   # 仅离线单测
```

## 重要说明与局限

- **数据源**：本平台用 akshare 的 **Sina 源**(eastmoney 在部分网络环境不可达)。
  数据层会自动绕过系统代理直连。Sina 的 **ETF/指数为未复权**，个股为前复权；
  做 ETF 长期回测时注意分红除权的影响。
- **回测假设**：以日线收盘价附近成交，涨跌停用收盘涨跌幅近似判定(含容差)，
  一字板的真实不可成交情形为近似处理。
- **结果解读**：回测结论受幸存者偏差、未来函数、复权方式、交易成本假设影响，
  历史表现不代表未来收益，仅用于策略研究，非投资建议。
