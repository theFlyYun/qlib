# CRSP 2022 2023 Failure Deep Dive

## 目标

这一步专门复盘 rolling window 中最关键的失败窗口：`2022-2023`。

我们不重新训练模型，也不新增任何特征，只复用已经完成的两条线：

```text
Alpha158-only + sector_cap_2_top10
EDGAR mini-core + sector_cap_2_top10
```

核心问题是：

```text
为什么 Test IC 和 Rank IC 都是弱正，但 Top10 组合仍然亏损？
```

这就是典型的 `IC / TopK 背离`：模型在全市场横截面上有一点排序能力，但最终选出的 10 只股票没有把这种能力转化成组合收益。

## 当前结论

| 线 | IC | Rank IC | Top10 平均收益 | Top10 - 候选均值 | 结论 |
|---|---:|---:|---:|---:|---|
| Alpha158-only | 0.0166 | 0.0064 | -0.55% | -0.54% | 弱正排序，TopK 转化失败 |
| EDGAR mini-core | 0.0290 | 0.0123 | -0.40% | -0.39% | 排序改善，但仍未转化为盈利 |

更具体地说：

```text
Alpha158-only：51 个调仓期里，31 个调仓期 Top10 跑输候选池均值。
EDGAR mini-core：51 个调仓期里，28 个调仓期 Top10 跑输候选池均值。
Alpha158-only：9 个调仓期出现 IC 和 Rank IC 同时为正，但 Top10 亏损。
EDGAR mini-core：12 个调仓期出现 IC 和 Rank IC 同时为正，但 Top10 亏损。
```

这说明问题不是“模型完全没有信号”，而是：

```text
弱信号不足以支撑非常集中的 Top10 组合。
Top10 选股对极端个股、行业暴露和 beta 暴露过于敏感。
```

## 回撤区间

| 线 | Peak | Trough | 最大回撤 | 回撤期数 |
|---|---|---|---:|---:|
| Alpha158-only | 2022-03-16 | 2023-10-18 | -43.44% | 41 |
| EDGAR mini-core | 2022-03-16 | 2022-06-27 | -39.29% | 8 |

EDGAR mini-core 把持续回撤缩短了，但并没有避免大幅亏损。它更像是“少亏一点”，不是修复策略结构。

## 主要亏损来源

### 行业

Alpha158-only 在最大回撤区间中，亏损最重的 SIC2 sector 是：

| Sector | 净贡献 | 持仓数 | 胜率 | 最差单笔 |
|---|---:|---:|---:|---:|
| 60 | -0.1175 | 26 | 46.15% | -42.81% |
| 48 | -0.1161 | 28 | 32.14% | -43.39% |
| 28 | -0.0783 | 35 | 48.57% | -37.85% |

EDGAR mini-core 在最大回撤区间中，亏损最重的 sector 仍包括：

| Sector | 净贡献 | 持仓数 | 胜率 | 最差单笔 |
|---|---:|---:|---:|---:|
| 60 | -0.0830 | 9 | 44.44% | -42.81% |
| 48 | -0.0783 | 13 | 38.46% | -43.39% |
| 73 | -0.0455 | 16 | 37.50% | -28.70% |

这说明行业约束 `sector_cap_2` 只能限制单期持仓数量，不能避免多个亏损行业在很长时间里轮流造成伤害。

### 单票

Alpha158-only 最大回撤区间中最差单票：

| Symbol | 净贡献 | 持仓次数 | 胜率 | 最差单笔 |
|---|---:|---:|---:|---:|
| P20892 | -0.1027 | 7 | 28.57% | -42.81% |
| P16140 | -0.0649 | 12 | 33.33% | -19.96% |
| P14763 | -0.0407 | 3 | 0.00% | -37.85% |

EDGAR mini-core 最大回撤区间中仍然被 `P20892` 拖累：

| Symbol | 净贡献 | 持仓次数 | 胜率 | 最差单笔 |
|---|---:|---:|---:|---:|
| P20892 | -0.0751 | 5 | 40.00% | -42.81% |
| P16140 | -0.0451 | 8 | 37.50% | -19.96% |
| P89393 | -0.0428 | 3 | 33.33% | -43.39% |

这提示后续应考虑单票风险过滤，例如：

```text
连续入选但持续亏损的股票降权
高波动个股限制
单票最大亏损后的冷却期
极端 drawdown 股票剔除或降权
```

## EDGAR 到底改善了什么

2022-2023 中，EDGAR mini-core 和 Alpha158-only 的持仓差异：

```text
EDGAR 新增持仓行：202
EDGAR 移除 Alpha158 持仓行：202
EDGAR 新增持仓净贡献：-0.0963
被移除 Alpha158 持仓原净贡献：-0.1732
替换净改善：+0.0769
```

这很关键：

```text
EDGAR 并不是选出了强赢家，而是减少了一部分更差的持仓。
新增持仓本身仍然是亏的，只是亏得比被替换掉的 Alpha158 持仓少。
```

所以 EDGAR mini-core 的定位仍然是 `candidate_branch`，不能替代默认策略。

## IC / TopK 背离如何理解

IC 是全市场候选股票上的平均排序质量。TopK 是最后拿钱买的 10 只股票。

两者可能背离，常见原因包括：

| 原因 | 当前是否可疑 | 说明 |
|---|---|---|
| 信号太弱 | 是 | IC 为正但很小，Top10 集中后容易被噪声淹没 |
| Top10 太集中 | 是 | 10 只股票太少，极端个股影响很大 |
| 行业风险未充分控制 | 是 | sector_cap_2 限制数量，但不能限制长期行业贡献 |
| beta 暴露偏高 | 是 | 2022-2023 下跌环境中，高 beta 会放大亏损 |
| 单票极端亏损 | 是 | 多只股票出现 -30% 到 -40% 级别单期亏损 |
| 模型完全无效 | 否 | 两条线 IC / Rank IC 都不是明显负数 |

因此，当前更像是：

```text
弱信号 + 高集中 Top10 + 风险暴露控制不足
```

而不是：

```text
模型完全没有任何预测力
```

## 下一步怎么改

优先级应该是组合构建和风险过滤，而不是继续堆新特征。

建议顺序：

1. **Top10 扩展对照**
   - 对比 Top10 / Top20 / Top30。
   - 如果 Top20/Top30 更稳定，说明问题主要是 Top10 太集中。

2. **单票风险过滤**
   - 限制近期高波动股票。
   - 对近期大回撤股票设置冷却期。
   - 对连续入选但亏损的股票降权。

3. **beta 控制**
   - 用历史 60/120 日 beta 过滤或降权。
   - 检查 2022-2023 高 beta 持仓是否解释大部分亏损。

4. **行业贡献约束升级**
   - `sector_cap_2` 只限制数量，不限制行业风险贡献。
   - 后续可测试 sector contribution cap 或行业亏损冷却。

5. **再决定是否改特征**
   - 如果改组合后仍然 IC/TopK 背离，才回到模型特征。
   - 如果 IC 也在其他窗口恶化，再重新设计标签或特征。

## 输出文件

```text
analysis/nasdaq_top500_score/crsp_2022_2023_failure_deep_dive.py
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023_failure_deep_dive/2022_2023_failure_deep_dive_report.md
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023_failure_deep_dive/ic_topk_divergence_by_period.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023_failure_deep_dive/beta_by_period.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023_failure_deep_dive/drawdown_period_attribution.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023_failure_deep_dive/sector_failure_contribution.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023_failure_deep_dive/symbol_failure_contribution.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023_failure_deep_dive/edgar_vs_alpha_2022_2023_delta.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023_failure_deep_dive/edgar_delta_by_sector.csv
```

## 常用命令

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_2022_2023_failure_deep_dive.py
```

查看报告：

```bash
sed -n '1,260p' analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023_failure_deep_dive/2022_2023_failure_deep_dive_report.md
```

所有结果只用于学习研究，不作为投资建议。
