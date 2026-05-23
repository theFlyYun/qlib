# CRSP Industry Constraint And Relative Feature Recovery

## 主题

本阶段恢复 CRSP 2010 主线下的行业路径，但分成两步验证：

1. 只改变 Top10 组合约束，不重新训练模型。
2. 再把行业内 market 相对特征放进模型输入，重新训练。

这样能把两个问题拆开：

- 行业约束是否能让组合更稳？
- 行业相对特征是否真的能提高模型排序能力？

本阶段不接 EDGAR，不接 FRED/ALFRED macro，不恢复历史长度桶名额。

## 数据与实验口径

- 数据源：CRSP 本地日级数据。
- 股票池：US Common Equity 月度动态市值 Top500。
- 时间窗口：2010-01-01 到 2025-12-31。
- 测试期：2024-01-02 到 2025-12-31。
- 标签：未来 10 个交易日总收益。
- 调仓：每 10 个交易日一次。
- 入场：信号日后 1 个交易日 open。
- 主成本：0 bps。
- 行业口径：CRSP 月末 row-level PIT SIC2 / SIC4。
- 当前 strict PIT 状态：通过。

SIC2 作为 sector，SIC4 作为 industry。它不是 GICS，但本阶段已经避免了用最新 security master 回填历史行业的问题。

## 工程动作

### 非分桶 TopK 行业约束

之前行业约束只在 `bucket_ranking.enabled=true` 时生效，不适合当前 2010 全局 Top10 baseline。

本阶段新增了非分桶 TopK 约束逻辑：

```text
先按模型 score 全局排序
再逐只检查 sector / industry 名额
符合约束才进入组合
直到选满 Top10
```

这样只改变最终选股规则，不改变模型分数。

### 预测复用

行业约束对照使用：

```text
training.reuse_test_predictions_path
```

直接复用 `crsp_alpha158_10d_conservative_2010_2025/test_predictions.csv`，避免为了只改组合规则而重训 LightGBM。

### PIT 行业相对特征

行情相对特征从 `industry_master.parquet` 读取 PIT 行业归属：

```text
instrument + datetime
-> effective_start / effective_end
-> sector / industry
```

只有信号日当时有效的行业记录才能参与分组。缺行业映射时不会静默回填 latest security master。

## 实验 A：行业约束 Top10 对照

配置：

```text
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_industry_strategy_comparison_10d_conservative_2010_2025.yaml
```

四组对照：

| Variant | 含义 |
|---|---|
| `global_top10` | 不限制 sector / industry |
| `sector_cap_2_top10` | 单 SIC2 sector 最多 2 只，单 SIC4 industry 最多 2 只 |
| `sector_cap_3_top10` | 单 SIC2 sector 最多 3 只，单 SIC4 industry 最多 2 只 |
| `sector_cap_4_top10` | 单 SIC2 sector 最多 4 只，单 SIC4 industry 最多 2 只 |

结果：

| Variant | 累计收益 | 年化收益 | 最大回撤 | 年化 alpha | beta | 最大单 sector 权重 | Sector HHI |
|---|---:|---:|---:|---:|---:|---:|---:|
| `global_top10` | 93.34% | 39.41% | -17.73% | 6.74% | 1.515 | 60% | 0.173 |
| `sector_cap_2_top10` | 112.64% | 46.26% | -15.62% | 13.03% | 1.433 | 20% | 0.144 |
| `sector_cap_3_top10` | 96.24% | 40.47% | -17.63% | 7.51% | 1.515 | 30% | 0.158 |
| `sector_cap_4_top10` | 95.54% | 40.21% | -17.27% | 7.36% | 1.511 | 40% | 0.165 |

结论：

```text
sector_cap_2 在收益、回撤、alpha、beta 和行业集中度上都优于 global_top10。
sector_cap_3 也比 global_top10 略好，但不如 sector_cap_2。
sector_cap_4 太接近不约束，对集中度改善有限。
```

这说明当前 CRSP 2010 baseline 的高分股票存在行业扎堆问题。限制行业名额不是单纯牺牲收益换分散，至少在这次测试期内，它同时改善了收益和风险。

## 实验 B：行业内 Market 相对特征

配置：

```text
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_industry_market_relative_10d_conservative_2010_2025.yaml
```

新增特征：

- 成交额分位。
- 20 / 60 / 120 日动量分位。
- 20 / 60 日波动率分位。
- 历史长度分位。

这些分位都在同一日期、同一 PIT sector / industry 内计算。

结果：

| 指标 | 数值 |
|---|---:|
| 行情相对特征数量 | 31 |
| 特征失败记录 | 19 |
| best iteration | 5 |
| Test IC | -0.014267 |
| Test Rank IC | -0.012379 |
| 累计收益 | -15.04% |
| 年化收益 | -7.89% |
| 最大回撤 | -24.48% |
| 年化 alpha | -28.55% |
| beta | 1.183 |

结论：

```text
行业内 market 相对特征本轮不能进入默认主线。
```

它没有提高横截面排序能力，反而让模型更快早停，并显著拖累 Top10 回测。

## 为什么行业约束有效，但行业相对特征无效

这两件事不是同一个问题。

行业约束发生在组合构建阶段：

```text
模型分数不变
只限制最终 Top10 不要过度集中
```

它像一个风险控制器，目标是避免模型在某些行业中过度押注。

行业相对特征发生在模型训练阶段：

```text
改变模型输入
让 LightGBM 学习新的排序规则
```

它要求新增特征本身稳定、有可学习规律，并且能在训练期和测试期保持一致。本轮结果说明，这些简单的行业内动量、波动、成交额分位没有带来稳定增量，可能原因包括：

- Alpha158 已经包含大量价格成交量信息，新特征重复度较高。
- 行业内分位压缩了绝对强弱信息，反而削弱模型。
- SIC 行业分组较粗或较碎，部分组内样本不稳定。
- 2024-2025 测试期的有效模式和 2010-2023 训练/验证期不一致。
- 新特征增加了噪声，LightGBM 验证集很快早停。

## 当前默认建议

本阶段后，候选主线应改为：

```text
CRSP 2010 Alpha158-only conservative score
+ sector_cap_2_top10 组合约束
```

不建议把行业内 market 相对特征放进默认模型。

更稳妥的说法是：

```text
行业信息目前更适合先作为组合约束和风险复盘工具，而不是直接作为模型输入。
```

## 遗留问题

- `sector_cap_2` 只在 2024-2025 测试期验证过，还需要看更多滚动窗口。
- SIC2 / SIC4 不是 GICS，行业解释要谨慎。
- 行业约束改善收益，可能来自减少错误集中押注，也可能来自测试期偶然适配。
- 行业相对特征失败，不代表所有行业特征都无效，只说明这组简单 market relative features 不适合作为当前默认。

## 下一步

1. 把 `sector_cap_2_top10` 作为候选默认，与原 global Top10 持续并行记录。
2. 做行业约束下的持仓贡献和行业暴露复盘，确认收益不是少数调仓期偶然贡献。
3. 暂缓行业内 market 相对特征。
4. 下一条主线转向 EDGAR 覆盖率与 `PERMNO -> CIK` 映射评估，再决定是否加入财报/估值特征。

## 相关笔记

[[CRSP Industry Mapping Repair]]
[[CRSP 2010 Baseline Cleanup And Industry Recovery]]
[[CRSP History Bucket Top10 And Industry Unknown Review]]
[[Industry Constraint Sensitivity]]
[[Industry Neutralization]]
[[TopK Strategy]]
