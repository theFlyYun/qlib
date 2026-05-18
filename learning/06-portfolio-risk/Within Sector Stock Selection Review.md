# Within Sector Stock Selection Review

## 目标

验证模型在同一个行业内部，是否能把未来收益更好的股票排到更前面。

这一步不重新训练模型，不改变 Alpha158、EDGAR 或 LightGBM，只复用当前测试期的模型预测分数。

## 为什么要做

全市场 IC 会混合两个来源：

```text
行业之间的差异
行业内部的个股差异
```

如果模型只是把强势行业排到前面，它可能有行业配置能力，但不一定有个股选择能力。

行业内选股复盘只在同一个 sector 内比较股票：

```text
Technology 内部比较 Technology 股票
Health Care 内部比较 Health Care 股票
Finance 内部比较 Finance 股票
```

这样可以更直接地看模型是否真的会在同行里挑股票。

## 复盘口径

```text
股票池：as-of 2023-12-31 近似冻结 Nasdaq Top500
测试期：2024-01-02 到 2026-05-15
信号：Qlib LightGBM score
收益：信号日后 1 个交易日入场，持有 5 个交易日
过滤：沿用回测中的 PIT 历史长度和流动性过滤
主分组：sector
补充分组：industry
分位：sector 内按 score 分成 5 桶
```

## 关键指标

```text
行业内 IC：
  同一 sector 内，score 和未来 5 日收益的 Pearson 相关。

行业内 Rank IC：
  同一 sector 内，score 排名和未来 5 日收益排名的 Spearman 相关。

Top-Bottom spread：
  同一 sector 内，score 前 20% 股票平均收益 - score 后 20% 股票平均收益。

spread_positive_rate：
  有效交易日里，Top-Bottom spread 为正的比例。
```

## 本次结果

覆盖情况：

```text
sector 数量：12
industry 数量：93
低样本 sector 数量：0
测试期有效信号期数：118
```

Rank IC 较好的 sector：

| Sector | Rank IC | IC | 平均可交易股票数 | Top-Bottom Spread |
|---|---:|---:|---:|---:|
| Telecommunications | 0.0728 | 0.0756 | 13.0 | 1.4920% |
| Miscellaneous | 0.0565 | 0.0573 | 4.0 | N/A |
| Energy | 0.0514 | 0.0609 | 8.9 | N/A |
| Basic Materials | 0.0381 | 0.0830 | 3.0 | N/A |
| Health Care | 0.0215 | 0.0235 | 82.0 | 0.3350% |

Top-Bottom spread 较好的 sector：

| Sector | Rank IC | Top-Bottom Spread | Spread 为正比例 |
|---|---:|---:|---:|
| Telecommunications | 0.0728 | 1.4920% | 56.78% |
| Industrials | 0.0032 | 0.3859% | 58.47% |
| Health Care | 0.0215 | 0.3350% | 55.08% |
| Consumer Staples | -0.0019 | 0.0602% | 50.85% |

表现较弱的 sector：

| Sector | Rank IC | Top-Bottom Spread | Spread 为正比例 |
|---|---:|---:|---:|
| Consumer Discretionary | -0.0218 | -0.3811% | 38.14% |
| Technology | -0.0128 | -0.2904% | 48.31% |
| Finance | -0.0224 | -0.2104% | 48.31% |
| Real Estate | -0.0115 | -0.1584% | 50.85% |

## 怎么理解

第一，行业内选股能力不是均匀存在的。Telecommunications、Health Care、Industrials 有一些正向迹象，但 Technology、Consumer Discretionary、Finance 的行业内排序偏弱。

第二，小行业的 Rank IC 要谨慎看。Miscellaneous、Energy、Basic Materials 的平均可交易股票数不足 10，因此没有计算 Top-Bottom spread，不能只看 Rank IC 下结论。

第三，Technology 是一个重要警讯。它是 Nasdaq 里样本多、权重大、市场关注度高的行业，但本次行业内 Rank IC 为负，Top-Bottom spread 也为负，说明当前模型在 Technology 内部没有稳定挑出赢家。

第四，行业约束变好并不等于模型行业内选股全面有效。行业约束可能主要减少了错误集中，而不是证明所有行业内都有 alpha。

## 当前结论

```text
保留行业约束是合理的。
当前模型在部分行业有行业内排序迹象，但并不稳定。
下一步不能只继续调组合约束，还要检查不同 sector 是否需要不同特征、不同标签或不同模型。
```

## 输出文件

```text
within_sector_daily_metrics.csv
within_sector_summary.csv
within_industry_summary.csv
within_sector_quantile_returns.csv
within_sector_selection_summary.yaml
```

## 遗留问题

```text
sector 分类仍来自当前 Nasdaq public snapshot，不是历史 PIT 行业分类
小行业样本少，Rank IC 容易受少数股票影响
行业内收益仍用免费 Nasdaq 行情，不是专业复权总回报数据
没有按 sector 单独训练模型
没有检验不同行业是否需要不同标签周期
```

## 下一步

优先做：

```text
1. 行业参数敏感性：比较 max_sector=2/3/4。
2. sector-specific 复盘：对 Technology、Health Care、Consumer Discretionary 单独看特征和错误样本。
3. 判断是否需要行业专属模型：一个全市场模型可能无法同时适配生物科技、软件、金融和消费。
```

相关笔记：

[[Industry Exposure Strategy Comparison]]
[[Industry Neutralization]]
[[Portfolio Risk Control]]
[[Benchmark And Excess Return Review]]
[[TopK Cost Backtest]]
