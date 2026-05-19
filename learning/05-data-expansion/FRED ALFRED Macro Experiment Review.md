# FRED ALFRED Macro Experiment Review

本篇记录真实 FRED/ALFRED 宏观增强实验。核心问题是：

```text
把宏观状态变量加入模型后，是否能比无宏观 baseline 带来增量 alpha？
```

结论先说清楚：第一版宏观特征没有带来明确的 TopK 增量收益。它提升了 Rank IC，并降低了一些风险暴露，但收益、超额收益和主要 TopK 回测表现弱于无宏观 baseline。

## 实验口径

对照实验保持这些条件不变：

```text
股票池：as-of 2023-12-31 近似冻结 Nasdaq Top500
数据窗口：2016-05-17 到 2026-05-17
训练期：2016-08-12 到 2021-12-31
验证期：2022-01-03 到 2023-12-29
测试期：2024-01-02 到 2026-05-15
标签：未来 5 个交易日收益
模型：LightGBM
基础特征：Alpha158 + EDGAR + industry + market relative features
```

唯一变化：

```text
baseline：不加入 macro_features
macro enhanced：加入 FRED/ALFRED macro_features
```

## 宏观数据接入结果

本次真实下载结果：

```text
macro_failures：0
macro_features 行数：1,256,500
macro_features 列数：52
平均非空覆盖率：98.99%
```

接入的宏观序列包括：

```text
DGS10 / DGS2 / FEDFUNDS
CPIAUCSL / UNRATE / INDPRO
BAA10Y / VIXCLS
DCOILWTICO / DTWEXBGS
DGS10 - DGS2 收益率曲线
```

低频统计序列使用 FRED initial release 口径，日频市场序列使用最新 observation 并顺延到下一个交易日生效。这个口径不是分钟级完美，但避免了最重要的未来函数：不能让模型在数据发布前看到数据。

## IC 对比

| 实验 | IC | Rank IC | IC 交易日 |
|---|---:|---:|---:|
| 无宏观 baseline | 0.016978 | 0.003683 | 589 |
| 加宏观特征 | 0.012456 | 0.009214 | 589 |

解读：

```text
IC 下降：线性相关变弱。
Rank IC 上升：排序相关变强。
```

这说明宏观变量可能改变了模型排序结构，但这种改善没有稳定转化成组合收益。

## TopK 回测对比

主对照使用当前更稳的 `sector_cap_2_top10`：

| 实验 | 累计收益 | 年化收益 | 最大回撤 | 信息比率 | 超额累计收益 | 年化 alpha | beta |
|---|---:|---:|---:|---:|---:|---:|---:|
| 无宏观 baseline | 97.56% | 33.75% | -29.36% | 0.9766 | 10.51% | 7.88% | 1.0418 |
| 加宏观特征 | 53.92% | 20.23% | -22.92% | 0.7557 | -13.90% | 1.20% | 0.8130 |

解读：

```text
加宏观后收益明显下降。
回撤降低，beta 也降低，说明组合更保守。
但超额收益转负，说明第一版宏观特征没有提供足够的正向选股增量。
```

## 行业暴露对比

在 `sector_cap_2_top10` 下，行业约束本身会限制单 sector 最多 2 只，所以行业集中度差异不大：

| 实验 | 最大平均 sector | 最大平均 sector 暴露 | 任一调仓期最大 sector 权重 | 平均 sector HHI |
|---|---|---:|---:|---:|
| 无宏观 baseline | Health Care | 20.00% | 20.00% | 0.1686 |
| 加宏观特征 | Technology | 19.92% | 20.00% | 0.1725 |

无约束 Top10 下，宏观模型仍会自然集中到 Technology，说明宏观特征没有自动解决行业扎堆问题；行业约束仍然必要。

## 当前判断

第一版宏观特征更像风险状态调节器，而不是直接 alpha 来源：

```text
优点：Rank IC 上升，回撤和 beta 降低。
缺点：累计收益、年化收益、超额收益和 alpha 明显弱于 baseline。
```

因此不能说“宏观变量已经有增量价值”。更准确的判断是：

```text
宏观状态变量有信息，但简单拼接到 LightGBM 中还没有稳定转化成 TopK alpha。
```

## 下一步方向

更合理的下一步不是继续堆更多宏观序列，而是做交互和分 regime 复盘：

```text
宏观状态 × 行业：高利率下哪些行业更吃亏或更占优
宏观状态 × 估值：高利率下高估值股票是否更容易失效
宏观状态 × 动量：VIX 上升时动量是否更不稳定
宏观状态 × 信用压力：信用利差扩大时亏损公司是否更差
```

如果这些交互也无效，再说明当前模型的主要 alpha 仍来自价格、财报、行业和相对行情特征，宏观数据暂时只适合作为风险复盘维度。

## 相关笔记

[[FRED ALFRED Macro Features Integration]]
[[Market Derived Relative Features]]
[[Industry Exposure Strategy Comparison]]
[[PIT Safe Backtest]]
[[Future Information Audit]]
[[Model Validation]]
