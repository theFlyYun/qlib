# CRSP Rolling Window Failure Review

## 目标

这一步不是继续训练新模型，而是复盘已经完成的 8 个 rolling window run，回答三个问题：

```text
Alpha158-only + sector_cap_2 为什么不能继续当稳定默认主线？
2022-2023 为什么是两条线共同失效的压力窗口？
EDGAR mini-core 的改善到底是稳定选股能力，还是局部窗口/持仓替换贡献？
```

本阶段复用已有预测、持仓、净值、行业贡献和 benchmark 输出，不重新训练 LightGBM。

## 当前说明了什么问题

滚动窗口验证已经把原来的主线结论降级：

| 对象 | 结果 | 解释 |
|---|---:|---|
| Alpha158-only + sector_cap_2 | 1/4 个窗口 alpha 为正 | 不能作为稳定默认策略 |
| EDGAR mini-core + sector_cap_2 | 3/4 个窗口 alpha 高于 Alpha158-only | 有边际价值，但只能作为候选分支 |
| 2022-2023 | 两条线都亏损且 alpha 为负 | 问题不是某个单一特征，而是市场状态、beta、持仓和组合规则共同压力 |
| 50bps 压力 | sector_cap_2 没有一个 rolling 行为正 alpha | 策略对交易摩擦和换手比较敏感 |

原来的强结果主要集中在 2024-2025。单一窗口表现好不能证明策略稳定，尤其当 2018-2023 中大部分窗口没有通过 alpha 检验时。

## 复盘口径

默认复盘对象：

```text
Alpha158-only + sector_cap_2_top10
EDGAR mini-core + sector_cap_2_top10
```

默认窗口：

```text
2018-2019
2020-2021
2022-2023
2024-2025
```

默认策略口径：

```text
CRSP monthly dynamic Top500
10 日未来收益标签
10 个交易日调仓
次日 open 入场
0bps 主成本
sector_cap_2_top10
```

压力测试补齐：

```text
sector_cap_2_top10: 0bps / 25bps / 50bps
```

这次补齐很重要。此前 rolling summary 只有 global Top10 的 50bps 压力值，不能代表主策略 `sector_cap_2_top10`。现在每个 rolling run 都在自己的 sector_cap_2 variant 下生成 `backtest_stress_matrix.csv`。

## 结果摘要

| 窗口 | 特征线 | 年化收益 | Alpha | Beta | 最大回撤 | 50bps 年化 |
|---|---|---:|---:|---:|---:|---:|
| 2018-2019 | Alpha158 | 4.68% | -3.30% | 0.93 | -18.40% | -15.43% |
| 2018-2019 | EDGAR mini-core | 18.07% | 6.97% | 1.13 | -17.54% | -4.00% |
| 2020-2021 | Alpha158 | 25.77% | -0.04% | 1.53 | -33.36% | 2.37% |
| 2020-2021 | EDGAR mini-core | 42.25% | 13.05% | 1.45 | -31.48% | 16.01% |
| 2022-2023 | Alpha158 | -18.30% | -15.05% | 1.64 | -43.44% | -31.23% |
| 2022-2023 | EDGAR mini-core | -14.16% | -11.15% | 1.50 | -39.29% | -27.20% |
| 2024-2025 | Alpha158 | 46.26% | 13.03% | 1.43 | -15.62% | 25.55% |
| 2024-2025 | EDGAR mini-core | 48.84% | 11.10% | 1.64 | -19.59% | 25.92% |

最弱窗口是 `2022-2023 Alpha158-only`：

```text
年化收益：-18.30%
alpha：-15.05%
beta：1.64
最大回撤：-43.44%
50bps 年化：-31.23%
回撤区间：2022-03-16 到 2023-10-18
```

这说明 2022-2023 不是一个短暂失误，而是持续多期失效。

## EDGAR 增量拆解

EDGAR mini-core 的最好改善窗口是 2018-2019：

```text
EDGAR 新增持仓行：357
Alpha158 被移除持仓行：356
新增持仓净贡献：0.2036
被移除 Alpha158 持仓原净贡献：-0.0465
共同持仓贡献变化：0.0011
总替换贡献差：0.2511
```

这表示 EDGAR 在 2018-2019 的改善主要来自换掉了一批 Alpha158 原本会选入、但表现较差的股票。

但也要注意：

```text
2018-2019 新增持仓的 EDGAR 字段缺失率仍较高。
2022-2023 EDGAR 只是把亏损减轻，并没有让 alpha 转正。
2024-2025 EDGAR 年化略高，但 alpha 低于 Alpha158-only，beta 更高。
```

所以 EDGAR mini-core 的当前定位仍是 `candidate_branch`，不是默认替代品。

## 为什么 2022-2023 需要单独复盘

2022-2023 同时具备几个危险信号：

```text
两条特征线都 alpha 为负
两条特征线 beta 都偏高
最大回撤深且恢复不足
50bps 压力后结果进一步恶化
top exposure sector 仍集中在 SIC2=73
```

这更像是策略结构在特定市场 regime 下失效，而不是简单加一个新字段就能修复。

下一步应重点拆：

| 方向 | 要回答的问题 |
---|---|
| beta 暴露 | 亏损是否来自高 beta 组合在下跌期被放大？ |
| 行业贡献 | SIC2=73 等行业是否长期贡献负收益？ |
| 单票贡献 | 是否少数股票造成主要亏损？ |
| 回撤区间 | 2022-03 到 2023-10 的持仓换手是否持续选错？ |
| IC vs TopK | 模型排序是否仍有弱预测力，只是 Top10 组合构建失败？ |

## 如何解决

当前不应该继续堆新特征。更合理的修复顺序是：

1. **做 2022-2023 专项失败归因**
   - 逐期查看 sector_cap_2 持仓、行业贡献、单票贡献和 drawdown。
   - 如果亏损集中在少数行业，先做行业风险控制。
   - 如果亏损集中在少数股票，先做单票风险过滤。

2. **检查 beta 和市场下跌敏感度**
   - 若 beta 长期高于 1.4，说明组合很可能靠市场弹性放大收益，也会在压力期放大亏损。
   - 下一步可测试 beta cap、低 beta 替补、或持仓波动率约束。

3. **补完整 variant-level 压力测试**
   - 已补齐 sector_cap_2 的 0/25/50bps。
   - 如果 50bps 大面积坍塌，策略只能保留为研究观察，不能作为实盘候选。

4. **判断是模型问题还是组合问题**
   - 如果 IC / Rank IC 在失效窗口仍不差，但 TopK 亏损，优先改组合构建。
   - 如果 IC / Rank IC 和 TopK 都失效，回到标签、特征、训练窗口设计。

5. **重定主线状态**
   - Alpha158-only + sector_cap_2：`unstable_default_candidate`
   - EDGAR mini-core + sector_cap_2：`candidate_branch`
   - 2024-2025：只能作为局部成功窗口，不能单独作为策略结论。

## 输出文件

复盘脚本：

```text
analysis/nasdaq_top500_score/crsp_rolling_window_failure_review.py
```

复盘输出：

```text
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/failure_review/rolling_window_failure_summary.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/failure_review/rolling_window_sector_contribution.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/failure_review/rolling_window_position_contribution.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/failure_review/rolling_window_drawdown_events.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/failure_review/rolling_window_beta_exposure.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/failure_review/rolling_edgar_delta_by_window.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/failure_review/sector_cap_2_stress_matrix.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/failure_review/rolling_window_failure_review.md
```

每个 rolling run 的 sector_cap_2 variant 也会补齐：

```text
strategy_comparison/sector_cap_2_top10/backtest_stress_matrix.csv
strategy_comparison/sector_cap_2_top10/sector_cap_2_stress_matrix.csv
strategy_comparison/sector_cap_2_top10/sector_cap_2_stress_summary.yaml
```

## 常用命令

运行失败复盘并刷新 rolling summary：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_rolling_window_failure_review.py
```

只看复盘报告：

```bash
sed -n '1,240p' analysis/nasdaq_top500_score/runs/crsp_rolling_windows/failure_review/rolling_window_failure_review.md
```

重新汇总 rolling window：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_rolling_window_validation.py --only-summary
```

## 当前结论

```text
Alpha158-only + sector_cap_2 不是稳定默认主线。
EDGAR mini-core 有边际改善，但仍只是候选分支。
2022-2023 是第一优先级复盘窗口。
下一步不应继续加新数据，而应先解释失败来源：beta、行业、单票、回撤区间和组合构建。
```

所有结果只用于学习研究，不作为投资建议。
