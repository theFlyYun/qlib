# nasdaq_alpha158_lgbm_1d Report

Generated at: 2026-05-17T10:44:38+08:00

## 结论口径

- 这次结果经过了 Qlib 模型流程：Qlib 数据格式、Alpha158 特征、LightGBM 模型训练、最新日预测分数排序。
- 结果是学习研究材料，不是投资建议。

## 实验名

- `nasdaq_alpha158_lgbm_1d`

## 股票池规则

- 交易所：NASDAQ
- 总市值前 N：500
- 排除 ETF：True
- 排除测试证券：True
- 最小历史行数：180

## 数据口径

- 数据源：nasdaq_public
- 回看自然日：900
- 频率：day
- VWAP 近似：ohlc_mean

## 标签与特征

- 标签名：`LABEL0`
- 标签表达式：`Ref($close, -2) / Ref($close, -1) - 1`
- 特征处理器：`Alpha158`
- 特征股票范围：`all`

## 模型参数

```yaml
loss: mse
learning_rate: 0.05
num_leaves: 64
max_depth: 8
n_estimators: 300
subsample: 0.85
colsample_bytree: 0.85
lambda_l1: 1.0
lambda_l2: 10.0
num_threads: 8
```

## 训练/验证/测试区间

- Fit: 2023-11-29 到 2025-06-10
- Train: 2024-02-27 到 2025-06-10
- Valid: 2025-06-11 到 2025-11-17
- Test: 2025-11-18 到 2026-05-15
- 最新预测日：2026-05-15

## Top 5 预测结果

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

IC 可以粗略理解为：每个交易日横截面上，模型预测分数和真实后续收益的相关性。

## 数据失败数量

- 最新日可预测股票数：480
- 下载失败或历史不足：19

## 输出文件

- `universe.csv`：本次实验股票池。
- `download_failures.csv`：下载失败或历史不足的股票。
- `predictions.csv`：最新日全部模型分数。
- `report.md`：本报告。
- `resolved_config.yaml`：本次实际使用配置，复盘时优先看它。
- `qlib_source_csv/`：逐股票原始日线 CSV。
- `qlib_data/`：转换后的 Qlib bin 数据。
