# Nasdaq Top 500 Qlib Alpha158 LightGBM Report

Generated at: 2026-05-17T00:40:54+08:00

## 结论口径

- 这次结果经过了 Qlib 模型流程：Qlib 数据格式、Alpha158 特征、LightGBM 模型训练、最新日预测分数排序。
- 股票池：Nasdaq-listed、非 ETF、非测试证券，并按 Nasdaq screener 总市值取前 500。
- 标签：Qlib Alpha158 默认标签，即预测未来短期收益 `Ref($close, -2)/Ref($close, -1)-1`。
- 价格数据：Nasdaq historical endpoint 的近 2 年日线 OHLCV；`vwap` 用 OHLC 均值近似。
- 结果是研究模型分数，不是投资建议。

## 训练区间

- Train: 2024-02-27 到 2025-06-10
- Valid: 2025-06-11 到 2025-11-17
- Test: 2025-11-18 到 2026-05-15
- 最新预测日：2026-05-15

## Top 5

| Rank | Symbol | Name | Qlib Score | Market Cap | Last Sale | Sector | Industry |
|---:|---|---|---:|---:|---:|---|---|
| 1 | AXTI | AXT Inc Common Stock | 0.04929583 | $6.88B | 123.78 | Technology | Semiconductors |
| 2 | LUNR | Intuitive Machines Inc. Class A Common Stock | 0.03980474 | $7.35B | 33.89 | Industrials | Industrial Machinery/Components |
| 3 | NBIS | Nebius Group N.V. Class A Ordinary Shares | 0.03980474 | $55.84B | 219.94 | Technology | Computer Software: Programming Data Processing |
| 4 | MXL | MaxLinear Inc. Common Stock | 0.02667781 | $8.27B | 92.34 | Technology | Semiconductors |
| 5 | FTNT | Fortinet Inc. Common Stock | 0.01425165 | $89.95B | 122.78 | Technology | Computer peripheral equipment |

## 模型验证

- Test 日均 IC：-0.009905
- Test 日均 Rank IC：-0.003036
- 参与 IC 计算的交易日：121

IC 可以粗略理解为：模型预测分数和真实后续收益的相关性。它不是收益率，样本短时尤其容易不稳定。

## 怎么读

- 当前排名代表：在这个股票池里，模型认为这些股票的下一期相对收益分数更高。
- 模型只看价格和成交量派生出来的 Alpha158，没有看财报、估值、新闻、宏观和行业基本面。
- 这份结果适合作为学习 Qlib 流程的样例；实盘前还需要更长历史、更干净复权数据、交易成本、回测和风控。

## 文件

- `qlib_source_csv/`：每只股票的原始日线 CSV。
- `qlib_data/`：转换后的 Qlib bin 数据。
- `nasdaq_qlib_lightgbm_predictions.csv`：最新日全部模型分数。
- `nasdaq_qlib_lightgbm_top5_report.md`：本报告。
- `nasdaq_qlib_download_failures.csv`：下载失败或历史不足的股票。

## 数据质量

- 最新日可预测股票数：480。
- 下载失败或历史不足：19。
