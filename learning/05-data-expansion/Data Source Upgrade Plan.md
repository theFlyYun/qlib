# Data Source Upgrade Plan

## 目标

阶段 E 的目标是先把数据地基想清楚，再继续优化标签、模型和策略。

核心问题不是“哪里能下载数据”，而是：

```text
这个数据能不能用于回测过去？
它有没有复权、退市、动态成分和 PIT 口径？
它能否解释模型为什么有效或失效？
```

## 当前结论

短期继续保留 `nasdaq_public` 作为学习数据源。它适合练习 Qlib 流水线，但不适合当作严谨回测基线。

中期建议优先选一条可落地路线：

```text
个人学习路线：Norgate / Nasdaq Data Link / SEC EDGAR / FRED
严谨研究路线：WRDS CRSP + Compustat + FRED/ALFRED
```

长期目标是把数据源抽象成配置项：

```yaml
data:
  source: nasdaq_public | local_csv | norgate | wrds_crsp_compustat | custom_warehouse
```

每个数据源进入 Qlib 前都必须先通过验收表。

当前已开始接入 Norgate。详细记录见 [[Norgate Data Integration]]。

## 数据分层

### 1. 价格行情

用途：

```text
计算收益率
构造 Alpha158 / Alpha360 这类价格成交量特征
回测买卖价格和交易成本
```

最低字段：

```text
date
symbol
open
high
low
close
volume
vwap
adjust_factor
```

关键口径：

```text
是否前复权或后复权
是否保留原始价格
是否包含分红、拆股、合并、退市价格
是否有成交量异常处理
```

推荐：

```text
学习：继续用 Nasdaq public 或 Nasdaq Data Link
严谨：CRSP / Norgate / 自建 vendor 数据仓库
```

### 2. 退市与幸存者偏差

如果只用今天还活着的股票回测过去，模型会天然避开已经退市、破产或被并购的差样本，收益会虚高。

必须验收：

```text
是否包含 delisted securities
是否有退市日期
是否有退市收益或最终可交易价格
是否能还原历史某一天真实可交易股票池
```

推荐：

```text
严谨美股研究优先 CRSP
个人学习可看 Norgate 的 delisted stocks 和 historical index constituents
```

### 3. 动态成分股

“现在的 Nasdaq 市值前 500”不能直接拿去回测 2010 年。2010 年当时能看到的股票池，和今天完全不同。

必须验收：

```text
指数或股票池每次调入调出日期
每个交易日当时的成员列表
是否包含后续退市成员
```

推荐：

```text
学习：先用静态股票池，但报告必须标注偏差
进阶：使用 Norgate 历史指数成分或 vendor index membership
严谨：使用 CRSP/Compustat/指数供应商数据重建可交易股票池
```

### 4. 财报数据

财报特征不能用“后来修正后的最终值”直接回测过去，否则会产生未来函数。

最低字段：

```text
period_end_date
report_date
accepted_or_filed_date
fiscal_period
revenue
net_income
eps
assets
liabilities
cash_flow
shares
```

关键口径：

```text
PIT：模型在某天只能看到那天之前已经披露的数据
披露延迟：财报期末和真实披露日不是同一天
重述：后续修正不能污染历史训练样本
```

推荐：

```text
学习：SEC EDGAR Company Facts / submissions
严谨：Compustat PIT 或 vendor fundamentals
```

### 5. 估值数据

估值通常是“市场价格 + 财报字段”的组合，不应盲目下载一个 PE 字段就直接使用。

最低字段：

```text
market_cap
enterprise_value
pe
pb
ps
ev_to_ebitda
dividend_yield
shares_outstanding
```

关键口径：

```text
估值分母使用哪个财报口径
TTM、FY1、FY2 是否混用
市值日期和财报披露日期是否对齐
是否 PIT
```

推荐：

```text
先自己用价格、市值和 PIT 财报计算核心估值
不要一开始就混用多个供应商的估值字段
```

### 6. 行业分类

行业是解决 Nasdaq 成分复杂的第一层工具。

用途：

```text
行业内排序
行业中性化
风险暴露控制
结果归因
```

推荐顺序：

```text
先用 vendor 自带 sector / industry
再用 SIC / NAICS
需要机构级一致性时再用 GICS
```

### 7. 宏观数据

宏观数据频率低，不适合像日线价格那样直接横截面排序，但适合做市场状态变量。

可用字段：

```text
利率
收益率曲线
通胀
失业率
美元指数
信用利差
VIX
```

推荐：

```text
FRED 适合学习和研究宏观序列
如果做严格历史回测，优先使用 ALFRED vintage 数据处理发布时间和修订
```

### 8. 新闻与事件

新闻数据最容易引入时间错位。

先不要直接做“新闻情绪大模型”。更稳妥的顺序是：

```text
SEC filing events
earnings announcement dates
dividend / split / buyback events
analyst rating changes
news sentiment
```

验收重点：

```text
发布时间是否精确到分钟
是否能映射到证券
是否能处理盘前、盘中、盘后
是否有历史回填和修订问题
```

## 数据口径验收表

| 数据类型 | 必要字段 | 频率 | PIT | 复权 | 退市 | 动态成分 | 接入优先级 |
|---|---|---:|---|---|---|---|---|
| 价格行情 | OHLCV、VWAP、adjust factor | 日频 | 不强制 | 必须 | 必须 | 可选 | 最高 |
| 股票池成员 | symbol、start、end、原因 | 日频/事件 | 必须 | 不适用 | 必须 | 必须 | 最高 |
| 财报 | period、filed、accepted、核心科目 | 季频 | 必须 | 不适用 | 需要 | 不适用 | 高 |
| 估值 | 市值、PE、PB、PS、EV/EBITDA | 日频/月频 | 必须 | 依赖价格 | 需要 | 不适用 | 高 |
| 行业 | sector、industry、SIC/NAICS/GICS | 事件/月频 | 最好 | 不适用 | 需要 | 不适用 | 高 |
| 宏观 | 利率、通胀、信用、就业 | 日频/月频 | 最好 | 不适用 | 不适用 | 不适用 | 中 |
| 新闻事件 | timestamp、symbol、event、source | 分钟/事件 | 必须 | 不适用 | 需要 | 不适用 | 低 |

## Qlib 接入方式

Qlib 本身更像研究框架，不是完整数据供应商。它负责：

```text
统一数据格式
表达式特征
DataHandler / Dataset
模型训练
Recorder
策略回测
PIT 数据读取机制
```

它不直接提供完整美股 40 年价格、退市、财报、估值、新闻数据库。

后续接入建议：

```text
第一步：把 vendor 原始数据落到 raw/
第二步：做口径校验和字段映射
第三步：生成 Qlib source csv 或 bin
第四步：写 resolved_config.yaml 记录数据源版本
第五步：再训练模型
```

## 推荐路线

### 短期：继续学习

```text
数据源：nasdaq_public
用途：跑通配置化流水线、理解标签和 IC
限制：只做学习，不解释为真实可交易结论
```

### 中期：个人可落地

```text
价格和成分：Norgate 或 Nasdaq Data Link
财报：SEC EDGAR
宏观：FRED / ALFRED
行业：vendor sector + SIC / NAICS
目标：减少幸存者偏差，开始做行业内排序和 TopK 回测
```

### 长期：严谨研究

```text
价格、退市、股票池：CRSP
财报和估值：Compustat
宏观：FRED / ALFRED
新闻事件：专业新闻或公告事件库
目标：40 年美股样本、可复盘、可审计、可写研究报告
```

## 官方参考

- [Qlib Data 文档](https://qlib.readthedocs.io/en/latest/component/data.html)
- [Qlib PIT 文档](https://qlib.readthedocs.io/en/latest/advanced/PIT.html)
- [WRDS CRSP Coverage](https://wrds-www.wharton.upenn.edu/pages/grid-items/crsp-coverage/)
- [WRDS S&P Global Market Intelligence / Compustat](https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/sp-global-market-intelligence/)
- [Norgate Data Content Tables](https://norgatedata.com/data-content-tables.php)
- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [FRED API](https://fred.stlouisfed.org/docs/api/fred/)
- [Nasdaq Data Link Getting Started](https://docs.data.nasdaq.com/docs/getting-started)

## 下一步

先不要马上接入新闻或宏观。下一步更稳的是：

```text
1. 选定一个价格和股票池数据源路线
2. 明确是否能覆盖退市和动态成分
3. 再回到阶段 C，对比 1 日标签和 5 日标签
```
