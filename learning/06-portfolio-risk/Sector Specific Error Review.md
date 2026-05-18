# Sector Specific Error Review

## 目标

解释模型在 `Technology`、`Health Care`、`Consumer Discretionary` 这三个行业里为什么排对或排错。

这一步不重新设计 Alpha158、EDGAR、LightGBM 或标签。它复用同一批测试期预测分数，把行业内样本拆成四类：

```text
high_score_winners：高分且未来收益靠前
high_score_losers：高分但未来收益靠后
low_score_winners：低分但未来收益靠前
low_score_losers：低分且未来收益靠后
```

## 复盘口径

```text
股票池：as-of 2023-12-31 近似冻结 Nasdaq Top500
测试期：2024-01-02 到 2026-05-15
信号：Qlib LightGBM score
收益：信号日后 1 个交易日入场，持有 5 个交易日
过滤：沿用回测中的 PIT 历史长度和流动性过滤
目标行业：Technology、Health Care、Consumer Discretionary
```

重要说明：本次 5.7C 完整运行重新训练了一次 LightGBM，模型分数和 5.7A/B 记录时略有差异。这个现象说明后续应该固定随机种子或直接复用缓存的 `test_predictions.csv`，否则跨阶段比较会混入训练波动。

## 本次结果

| Sector | 诊断 | Rank IC | Top-Bottom Spread | 高分输家率 | 低分赢家率 | 财报覆盖率 |
|---|---|---:|---:|---:|---:|---:|
| Technology | model_weak | -0.0214 | -0.5044% | 52.63% | 50.93% | 80.57% |
| Health Care | mixed_or_noisy | 0.0191 | 0.5627% | 49.83% | 46.68% | 83.66% |
| Consumer Discretionary | model_weak | -0.0230 | -0.2560% | 51.97% | 52.99% | 77.04% |

## Technology

结论：

```text
当前模型在 Technology 内部排序偏弱。
高分股票并没有稳定跑赢低分股票。
模型明显漏掉了一些更大市值、更高流动性、动量更强的赢家。
```

关键信号：

```text
高分输家率：52.63%
低分赢家率：50.93%
高分输家中短历史股票占比：91.61%
高分输家中亏损公司占比：52.82%
低分赢家 60 日动量均值明显高于高分赢家
低分赢家平均市值和成交额明显高于高分赢家
```

怎么理解：

Technology 里很多高分输家是短历史、亏损或估值较高的公司。与此同时，模型漏掉的低分赢家反而更大、更活跃、近期动量更强。这说明当前特征对科技股内部的“质量 + 流动性 + 动量”组合捕捉不够稳。

## Health Care

结论：

```text
Health Care 不是明显失效，而是混合且噪声较大。
Top-Bottom spread 为正，但 Rank IC 只接近正向阈值。
模型能抓住一部分赢家，也会高分买到昂贵且亏损的生物医药股。
```

关键信号：

```text
Rank IC：0.0191
Top-Bottom spread：0.5627%
高分输家率：49.83%
高分输家中高估值占比：62.98%
高分输家中亏损公司占比：80.81%
高分输家中短历史股票占比：92.78%
```

怎么理解：

Health Care 的收益分布受药物试验、审批、融资和事件驱动影响很大。结构化财报和价格特征能提供一部分排序能力，但单靠它们很难解释生物医药的跳跃式收益。这里不能简单否定模型，但需要更强的事件数据或更严格的风险过滤。

## Consumer Discretionary

结论：

```text
当前模型在 Consumer Discretionary 内部排序偏弱。
低分赢家率高于高分输家率，说明模型漏掉赢家的问题更明显。
```

关键信号：

```text
Rank IC：-0.0230
Top-Bottom spread：-0.2560%
高分输家率：51.97%
低分赢家率：52.99%
高分输家中短历史股票占比：84.38%
高分输家中亏损公司占比：52.93%
低分赢家平均市值和成交额明显高于高分赢家
低分赢家平均估值低于高分赢家
```

怎么理解：

Consumer Discretionary 内部差异很大，餐饮、旅游、平台、教育、零售和 ADR 不能用同一套简单价格财报特征粗暴比较。本次结果显示，模型可能过度偏向短历史、高弹性或特殊类型股票，反而漏掉更大、更稳、更有流动性的赢家。

## 当前判断

```text
Technology：优先排错，当前行业内排序偏弱。
Health Care：保留但谨慎，事件驱动噪声很大。
Consumer Discretionary：需要拆行业或补特征，当前统一模型不稳。
```

这三个行业都显示一个共同问题：

```text
短历史股票在高分输家里占比很高。
模型容易错过更大市值、更高流动性、近期动量更强的低分赢家。
```

## 下一步

优先做三件事：

```text
1. 固定训练随机性或缓存 test_predictions.csv，避免跨阶段结论因重训波动而改变。
2. 给 Technology 和 Consumer Discretionary 增加 size / liquidity / momentum 的行业内相对特征。
3. 对 Health Care 单独考虑事件数据或更严格的估值、亏损、短历史过滤。
```

相关笔记：

[[Within Sector Stock Selection Review]]
[[Industry Constraint Sensitivity]]
[[Industry Exposure Strategy Comparison]]
[[Portfolio Risk Control]]
