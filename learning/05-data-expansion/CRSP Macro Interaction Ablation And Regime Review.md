# CRSP Macro Interaction Ablation And Regime Review

这一步的目标是把 CRSP 10 日保守模型里的宏观交互拆开看清楚：哪些交互真的有用，哪些可能只是噪声，以及它们分别在哪些市场状态下有效。

本阶段不接 EDGAR，不使用行业约束，也不使用当前快照行业分类。这样做是为了保持对照干净：股票池、标签、模型参数、训练切分、回测口径都不变，只改变宏观交互特征。

## 固定实验口径

```text
数据源：CRSP 本地日级数据
股票池：US Common Equity 月度动态市值 Top500
训练窗口：2000-01-03 到 2021-12-31
验证窗口：2022-01-01 到 2023-12-31
测试窗口：2024-01-01 到 2025-12-31
标签：未来 10 个交易日总收益
调仓：每 10 个交易日一次
入场：信号日后 1 个交易日 open
模型：10 日保守 LightGBM
```

## 9 组对照

本阶段固定 9 组，不多跑也不少跑：

| 组名 | 含义 |
|---|---|
| `alpha158_only_baseline` | 只使用 Alpha158 |
| `raw_macro_direct` | Alpha158 + raw FRED/ALFRED 宏观特征 |
| `full_macro_interactions` | Alpha158 + 8 个宏观交互 |
| `drop_vix_interactions` | 去掉 VIX 相关交互 |
| `drop_rate_curve_interactions` | 去掉利率和收益率曲线相关交互 |
| `drop_credit_interaction` | 去掉信用利差相关交互 |
| `drop_dollar_oil_interactions` | 去掉美元和油价相关交互 |
| `only_vix_interactions` | 只保留 VIX 相关交互 |
| `only_rate_curve_interactions` | 只保留利率和收益率曲线相关交互 |

如果删除一组交互后结果变差，说明这组交互可能有增量；如果删除后结果变好，说明这组交互可能是噪声或过拟合来源。

## Regime 分段复盘

`regime` 是市场状态。这里不会重新训练模型，而是把每个信号日按当时已经可见的宏观特征打标签，然后比较每组策略在不同状态下的表现。

默认状态包括：

```text
VIX 高/低
VIX 上升/下降
10Y 利率高/低
利率上行/下行
收益率曲线倒挂/未倒挂
信用压力高/低
美元走强/走弱
油价上涨/下跌
```

高低阈值只用测试期之前的历史宏观数据计算，不能用 2024-2025 测试期未来分布来定阈值。

## 如何解读结果

优先看四个层次：

1. `Rank IC`：整体横截面排序是否更好。
2. `alpha` / `beta`：收益是来自个股选择，还是只是市场暴露。
3. 成本压力：50bps 后收益是否还能站住。
4. Regime 稳定性：收益是否只来自少数市场状态。

如果某组收益更高但 Rank IC 没改善，不直接认定预测力增强，只能说 TopK 回测收益改善，需要继续检查持仓集中度和贡献来源。

## 工程入口

配置目录：

```text
analysis/nasdaq_top500_score/configs/crsp_macro_ablation/
```

复盘汇总：

```text
analysis/nasdaq_top500_score/runs/crsp_macro_interaction_ablation_review/
```

核心输出：

```text
crsp_macro_ablation_summary.csv
crsp_macro_ablation_regime_summary.csv
crsp_macro_ablation_review_summary.yaml
report.md
```

## 下一步判断

如果 `full_macro_interactions` 或某个 `only_*` 组合不能超过 Alpha158-only baseline，宏观特征暂时不进入默认主策略，只保留为复盘维度。

如果某一组交互只在特定 regime 中有效，后续再考虑 regime-aware 规则，而不是全时段启用。

## 相关笔记

- [[CRSP Macro Conservative Comparison]]
- [[CRSP Training Speed Optimization]]
- [[FRED ALFRED Macro Features Integration]]
- [[Macro Regime Review And Interaction Features]]
- [[Macro Features New Information And Return Degradation]]
