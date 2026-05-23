# CRSP Rolling Window Validation

## 目标

滚动窗口验证要回答一个更严格的问题：

```text
Alpha158-only + sector_cap_2_top10 是否只在 2024-2025 表现好？
EDGAR mini-core + sector_cap_2_top10 是否有跨市场阶段的稳定增量？
```

这一步不新增宏观、不新增更多 EDGAR 字段，也不调模型参数。它只把同一条策略放到多个历史测试窗口里，检查收益、alpha、回撤和 Rank IC 是否稳定。

## 为什么要做

单一测试期容易误导。

如果一个策略只在一个市场阶段赚钱，它可能学到的是那段行情的偶然结构，而不是稳定的选股能力。当前 `2024-2025` 结果里，`Alpha158-only + sector_cap_2_top10` 是默认主线，`EDGAR mini-core + sector_cap_2_top10` 是候选研究分支。两者都需要离开当前窗口再验证。

## 验证对象

| 线 | 特征输入 | 选股规则 | 目的 |
|---|---|---|---|
| A | Alpha158-only | sector_cap_2_top10 | 当前默认主线稳定性 |
| B | Alpha158 + EDGAR mini-core | sector_cap_2_top10 | EDGAR 是否有稳定增量 |

两条线都使用：

```text
CRSP 2010-2025
US Common Equity monthly dynamic Top500
10 日未来收益标签
10 个交易日调仓
次日 open 入场
0bps 主成本
conservative LightGBM 参数
```

## 滚动窗口

| 窗口 | Train | Valid | Test |
|---|---|---|---|
| 2018-2019 | 2010-2015 | 2016-2017 | 2018-2019 |
| 2020-2021 | 2010-2017 | 2018-2019 | 2020-2021 |
| 2022-2023 | 2010-2019 | 2020-2021 | 2022-2023 |
| 2024-2025 | 2010-2021 | 2022-2023 | 2024-2025 |

这样做的好处是：每个测试窗口都只使用它之前的数据训练和验证，避免把后面市场状态提前泄露给前面窗口。

## 输出

配置位于：

```text
analysis/nasdaq_top500_score/configs/crsp_rolling_windows/
```

汇总输出位于：

```text
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/
```

关键文件：

```text
crsp_rolling_window_summary.csv
crsp_rolling_window_comparison.yaml
report.md
```

每个子实验还会输出自己的：

```text
report.md
test_predictions.csv
strategy_comparison.csv
backtest_nav.csv
backtest_positions.csv
```

## 评价规则

当前默认主线通过标准：

```text
Alpha158-only + sector_cap_2 至少 3/4 个测试窗口 alpha 为正。
50bps 压力下不能大面积坍塌。
Rank IC 不要求每窗都正，但不能长期明显为负且收益只来自单一窗口。
最大回撤不能在多数窗口明显恶化。
```

EDGAR mini-core 替代标准：

```text
EDGAR mini-core 至少 3/4 个窗口的 sector_cap_2 alpha 不低于 Alpha158-only。
平均最大回撤不高于 Alpha158-only。
Rank IC 平均改善，且不是只靠 2024-2025。
如果只在 1-2 个窗口有效，保留为研究分支，不进入默认主线。
```

## 结果分级

| 分级 | 含义 |
|---|---|
| stable_default | 可作为当前默认研究主线 |
| candidate_branch | 有局部价值，但不能替代默认 |
| unstable_observation | 只作为学习观察 |
| needs_data_or_feature_repair | 数据或特征口径需要重新检查 |
| incomplete | 实验尚未完整跑完 |

## 当前状态

滚动窗口框架已经建立并完成 8 组真实训练：

```text
8 个实验配置
manifest 驱动运行脚本
跳过已完成 run 的机制
only-summary 汇总模式
fake run 汇总测试
```

当前汇总分类为 `candidate_branch`：

```text
Alpha158-only + sector_cap_2：1/4 个窗口 alpha 为正。
EDGAR mini-core + sector_cap_2：3/4 个窗口 alpha 高于 Alpha158-only。
最佳窗口：2020-2021 EDGAR mini-core，sector_cap_2 alpha 约 13.05%，Rank IC 约 0.0198。
最弱窗口：2022-2023，两条线 sector_cap_2 alpha 都为负。
```

这说明：当前 Alpha158-only + sector_cap_2 不能直接升级为稳定默认策略；EDGAR mini-core 有跨窗口增量，但还不够强，仍应作为候选分支。

## 失败复盘更新

后续已补做 [[CRSP Rolling Window Failure Review]]，重点复盘 `sector_cap_2_top10`，并补齐 variant-level 的 0/25/50bps 压力测试。

复盘后的主线状态进一步明确：

```text
Alpha158-only + sector_cap_2：unstable_default_candidate
EDGAR mini-core + sector_cap_2：candidate_branch
2022-2023：第一优先级失效窗口
```

补齐压力测试后发现，`sector_cap_2_top10` 在 50bps 压力口径下没有一个 rolling 行为正 alpha。这不代表策略必然不可用，但说明当前结果对交易摩擦和换手敏感，不能只看 0bps 主收益。

## 结果摘要

| 窗口 | Alpha158 sector_cap_2 alpha | EDGAR mini-core sector_cap_2 alpha | 解读 |
|---|---:|---:|---|
| 2018-2019 | -3.30% | 6.97% | EDGAR 改善明显 |
| 2020-2021 | -0.04% | 13.05% | EDGAR 最强窗口 |
| 2022-2023 | -15.05% | -11.15% | 两条线都失效，EDGAR 跌得少 |
| 2024-2025 | 13.03% | 11.10% | Alpha158 alpha 更高，EDGAR 年化更高但 alpha 较低 |

关键结论：

```text
Alpha158-only 不是跨窗口稳定默认。
EDGAR mini-core 不是最终替代，但有研究价值。
2022-2023 是必须重点复盘的失效窗口。
下一步应分析 2022-2023 的行业暴露、beta、选股贡献和市场 regime，而不是继续堆新特征。
```

## 常用命令

完整运行：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_rolling_window_validation.py
```

只重建汇总：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_rolling_window_validation.py --only-summary
```

强制重跑全部：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_rolling_window_validation.py --force
```

## 解释原则

不要只看最高年化收益。

滚动窗口验证优先看稳定性：alpha 是否多窗口为正，回撤是否可控，Rank IC 是否长期不恶化，EDGAR 是否在不同年份都能提供增量。只有跨窗口稳定的结果，才有资格进入默认主线。

所有结果只用于学习研究，不作为投资建议。
