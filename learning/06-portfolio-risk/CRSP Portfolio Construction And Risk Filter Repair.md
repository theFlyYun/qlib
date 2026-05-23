# CRSP Portfolio Construction And Risk Filter Repair

## 目标

本阶段是 `CRSP-19`，目标是修复 rolling window 中暴露出来的核心问题：

```text
弱正 IC 没有稳定转化为 TopK 收益。
```

本阶段不重训模型，不新增 EDGAR 字段，不接宏观数据，只复用已经完成的 rolling run：

```text
Alpha158-only
EDGAR mini-core
2018-2019 / 2020-2021 / 2022-2023 / 2024-2025
```

重点验证四类组合修复：

```text
TopK 宽度
持仓权重
单票风险过滤
beta 控制
```

## 当前基准

当前基准仍是 `sector_cap_2_top10`。

| 窗口 | 特征线 | IC | Rank IC | 年化收益 | Alpha | Beta | 最大回撤 | TopK - 候选均值 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2018-2019 | Alpha158 | 0.0097 | 0.0063 | 4.68% | -3.30% | 0.93 | -18.40% | -0.18% |
| 2018-2019 | EDGAR mini-core | 0.0085 | 0.0050 | 18.07% | 6.97% | 1.13 | -17.54% | 0.31% |
| 2020-2021 | Alpha158 | 0.0268 | 0.0172 | 25.77% | -0.04% | 1.53 | -33.36% | 0.37% |
| 2020-2021 | EDGAR mini-core | 0.0275 | 0.0198 | 42.25% | 13.05% | 1.45 | -31.48% | 0.82% |
| 2022-2023 | Alpha158 | 0.0247 | 0.0136 | -18.30% | -15.05% | 1.64 | -43.44% | -0.54% |
| 2022-2023 | EDGAR mini-core | 0.0325 | 0.0179 | -14.16% | -11.15% | 1.50 | -39.29% | -0.39% |
| 2024-2025 | Alpha158 | 0.0155 | -0.0092 | 46.26% | 13.03% | 1.43 | -15.62% | 1.01% |
| 2024-2025 | EDGAR mini-core | 0.0133 | -0.0005 | 48.84% | 11.10% | 1.64 | -19.59% | 1.10% |

这个表说明：模型不是完全没有信号，但信号很弱。尤其 2022-2023 中，IC 和 Rank IC 都是正的，但 TopK 仍然明显跑输候选池均值。

## TopK 宽度结果

| 组合 | 平均 Alpha | 正 Alpha 窗口 | 平均 Beta | 最差回撤 | 50bps 平均年化 |
|---|---:|---:|---:|---:|---:|
| EDGAR Top30 等权 | 5.64% | 4/4 | 1.20 | -31.71% | 1.41% |
| EDGAR Top10 等权 | 4.99% | 3/4 | 1.43 | -39.29% | 2.68% |
| EDGAR Top50 等权 | 4.26% | 4/4 | 1.11 | -30.43% | 0.87% |
| Alpha158 Top30 等权 | 3.84% | 3/4 | 1.23 | -33.30% | -1.18% |
| Alpha158 Top50 等权 | 3.78% | 3/4 | 1.13 | -32.50% | -1.19% |
| Alpha158 Top10 等权 | -1.34% | 1/4 | 1.38 | -43.44% | -4.68% |

结论：

```text
Top10 确实太窄。
Top30 / Top50 能显著降低最差回撤，并让 Alpha158 从 1/4 正 alpha 改善到 3/4。
但 50bps 压力下仍然没有 alpha 稳定通过。
```

## 权重结果

表现最好的观察项是：

```text
EDGAR mini-core + Top10 + inverse_vol_weight
```

结果：

```text
平均年化收益：24.32%
平均 alpha：6.12%
正 alpha 窗口：3/4
平均 beta：1.35
最差回撤：-36.73%
50bps 平均年化：2.25%
50bps 正 alpha 窗口：0/4
```

这个结果有价值，但不能升级为默认策略。原因是它虽然提高了 0bps 下的平均 alpha，但 50bps alpha 没有任何窗口为正，说明它对交易摩擦仍然敏感。

## 单票风险过滤结果

单票风险过滤明显降低了 beta，但收益和 alpha 同时下降。

最好的风险过滤观察项：

```text
EDGAR mini-core + Top30 + soft risk filter
```

结果：

```text
平均 alpha：2.45%
正 alpha 窗口：3/4
平均 beta：0.89
最差回撤：-30.79%
50bps 平均年化：-4.08%
```

结论：

```text
风险过滤有效降低风险暴露，但也过滤掉了不少收益来源。
它更像风险削减工具，不是完整修复方案。
```

## Beta 控制结果

beta 控制同样能降低 beta，但收益改善不足。

较好的观察项：

```text
EDGAR mini-core + Top10 + beta_neutral_weight
```

结果：

```text
平均 alpha：3.74%
正 alpha 窗口：3/4
平均 beta：1.22
最差回撤：-36.76%
50bps 平均年化：-2.32%
```

结论：

```text
beta 是问题的一部分，但不是唯一问题。
单纯降 beta 会改善风险，但不足以让策略成为稳定主线。
```

## 最终决策

本阶段输出的决策是：

```text
status: no_portfolio_rule_passed
recommended_next_stage: CRSP-20 标签重设计
```

原因：

```text
没有组合规则同时满足：
1. 跨窗口 alpha 稳定；
2. beta 低于当前基准；
3. 50bps 压力下不大面积坍塌。
```

这不是说组合修复没有价值。它给出了两个重要判断：

1. `Top10` 太窄，后续如果继续用当前标签，至少应看 `Top30` 或 `Top50`。
2. 风险过滤和 beta 控制可以降低回撤，但会牺牲收益，说明原始收益中确实含有较多风险暴露。

## 为什么下一步要做标签重设计

当前标签是未来 10 日总收益。这个标签会天然偏向：

```text
高 beta 股票
高波动股票
顺风行业
市场上涨弹性大的股票
```

如果模型学到的是“谁更容易跟随市场大涨”，那么在 2022-2023 这种压力窗口中就会失效。

下一阶段应改成更贴近个股 alpha 的标签：

```text
未来 10 日超额收益
sector-neutral return
beta-adjusted return
risk-adjusted return
```

目标是让模型预测：

```text
这只股票相对市场、相对行业、相对自身风险是否更好。
```

而不是只预测：

```text
这只股票未来 10 日绝对收益是否更高。
```

## 输出文件

脚本：

```text
analysis/nasdaq_top500_score/crsp_portfolio_repair.py
```

输出目录：

```text
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/portfolio_repair/
```

关键输出：

```text
crsp_portfolio_repair_baseline_summary.csv
topk_width_comparison.csv
topk_width_by_window.csv
topk_width_drawdown_summary.csv
portfolio_weighting_comparison.csv
portfolio_weighting_by_window.csv
single_name_risk_filter_comparison.csv
risk_filter_removed_positions.csv
risk_filter_drawdown_impact.csv
beta_control_comparison.csv
beta_exposure_by_period.csv
beta_drawdown_attribution.csv
crsp_portfolio_repair_decision.yaml
crsp_portfolio_repair_report.md
```

## 常用命令

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_portfolio_repair.py
```

查看决策：

```bash
cat analysis/nasdaq_top500_score/runs/crsp_rolling_windows/portfolio_repair/crsp_portfolio_repair_decision.yaml
```

查看报告：

```bash
sed -n '1,220p' analysis/nasdaq_top500_score/runs/crsp_rolling_windows/portfolio_repair/crsp_portfolio_repair_report.md
```

所有结果只用于学习研究，不作为投资建议。
