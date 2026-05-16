# Nasdaq Top 500 Market-Cap Score Report

Generated at: 2026-05-17T00:31:58+08:00

## 口径

- 这是一份学习用量化研究榜单，不是投资建议。
- 股票池：NasdaqTrader 当前 Nasdaq-listed、非 ETF、非测试证券。
- 初筛：用 Nasdaq screener 的 marketCap 字段取总市值最高 500 只。
- 历史价格：Nasdaq historical endpoint 的近 2 年日线收盘价。
- 只保留至少 180 个交易日历史价格的股票。
- 双重股权类别按独立交易代码保留，例如 GOOG 与 GOOGL。

## 打分公式

总分采用横截面百分位排名，满分 100：

- 12 个月动量扣除近 1 个月：30%
- 6 个月收益：20%
- 3 个月收益：15%
- 当前价格相对 200 日均线：15%
- 6 个月收益 / 3 个月年化波动：10%
- 近 1 年最大回撤控制：10%

这个公式偏向趋势和风险调整后的强势股，不是价值投资评分，也没有使用财报、估值、新闻或分析师预测。

## Top 5

| Rank | Symbol | Name | Score | Market Cap | Close | 12M | 6M | 3M | 1M | 3M Vol | Max DD 1Y | Sector |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | WDC | Western Digital Corporation Common Stock | 94.75 | $166.14B | 482.02 | 868.88% | 206.71% | 69.66% | 29.39% | 67.68% | -20.59% | Technology |
| 2 | STX | Seagate Technology Holdings PLC Ordinary Shares (Ireland) | 94.54 | $178.37B | 795.47 | 640.45% | 202.97% | 91.25% | 45.23% | 65.37% | -21.00% | Technology |
| 3 | SYRE | Spyre Therapeutics Inc. Common Stock | 94.05 | $6.51B | 74.92 | 415.27% | 231.06% | 108.40% | 2.62% | 75.95% | -20.91% | Health Care |
| 4 | VIAV | Viavi Solutions Inc. Common Stock | 93.66 | $12.03B | 51.43 | 446.55% | 203.78% | 95.55% | 16.53% | 84.78% | -21.13% | Technology |
| 5 | SNDK | Sandisk Corporation Common Stock | 93.43 | $208.45B | 1407.61 | 3372.15% | 477.91% | 138.34% | 52.84% | 95.50% | -31.34% | Technology |

## 怎么读这个结果

- 排名靠前代表：在当前 Nasdaq 大市值股票池里，最近中期趋势强、站在长期均线上方，并且风险调整后表现较好。
- 它不代表：公司一定被低估、未来一定上涨、适合你的账户买入。
- 下一步应补充：估值、盈利质量、行业景气、财报事件、仓位上限、止损规则，以及与 QQQ/SPY 的相对强弱比较。

## 文件

- `nasdaq_top500_universe.csv`：总市值前 500 股票池。
- `nasdaq_top500_scored.csv`：完成历史价格计算后的打分表。
- `nasdaq_top5_report.md`：本报告。

## 数据质量提示

- 初筛股票数：500。
- 可评分股票数：481。
- 历史价格抓取失败或历史不足：19。
- 免费公开接口可能存在延迟、字段缺失、复权口径差异；正式交易前应使用付费且可审计的数据源复核。

失败/跳过样例：
CBRS, BRKRP, MDLN, WSE, AGNCZ, ASND, ARXS, SOLS, PAYP, FRVO, XE, FIGR, LLYVK, LGN, LLYVA, MWH, SATA, EQPT, VSNT
