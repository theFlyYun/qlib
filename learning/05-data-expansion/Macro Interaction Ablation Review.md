# Macro Interaction Ablation Review

这篇笔记记录宏观交互特征的 ablation 复盘。

核心问题是：上一阶段 `macro interactions` 的收益和 Rank IC 都提升了，但我们还不知道提升来自哪一类交互。Ablation 的目的不是再发明一个新模型，而是把 10 个宏观交互特征分组拆掉，观察哪些组合真正贡献了收益、alpha、Rank IC 和风险控制。

## 为什么要做 Ablation

`macro interactions` 第一版使用 10 个特征：

```text
VIX × 动量/波动
利率 × 估值
信用利差 × 负债/现金
收益率曲线/利率/油价/美元 × 行业 flag
```

完整模型结果很好：

```text
IC = 0.022432
Rank IC = 0.012953
sector_cap_2_top10 年化收益 = 43.55%
最大回撤 = -24.19%
年化 alpha = 17.16%
beta = 0.922
```

但这个结果可能来自几种完全不同的原因：

- VIX 交互真的提高了风险环境下的排序能力。
- 利率和估值交互帮助模型识别高利率下的估值压力。
- 信用利差和负债/现金交互帮助过滤脆弱公司。
- 行业 flag 交互只是让模型更像行业轮动。
- 某些交互其实是噪声，删掉反而更好。

Ablation 就是逐组移除或单独保留，判断每一类宏观交互到底在做什么。

## 实验口径

本次所有实验保持一致：

```text
股票池：as-of 2023-12-31 近似冻结 Nasdaq Top500
训练窗口：固定 10 年窗口
测试期：2024-01-02 到 2026-05-15
标签：未来 5 日收益
回测：信号日后 1 个交易日入场，持有 5 个交易日
主策略：sector_cap_2_top10
基础特征：Alpha158 + EDGAR + market_features
只改变：macro interaction feature group
```

本次新增配置放在：

```text
analysis/nasdaq_top500_score/configs/macro_ablation/
```

汇总输出放在：

```text
analysis/nasdaq_top500_score/runs/macro_interaction_ablation_review/
```

## 分组设计

| Variant | 含义 | 交互特征数 |
|---|---|---:|
| `baseline` | 不使用 raw macro，也不使用 macro interactions | 0 |
| `direct_macro` | 直接把 raw FRED/ALFRED 宏观变量输入模型 | 0 |
| `full_interactions` | 使用完整 10 个宏观交互特征 | 10 |
| `drop_vix_interactions` | 去掉 VIX × 动量/波动交互 | 8 |
| `drop_rate_valuation_interactions` | 去掉利率 × 估值，以及利率 × Technology 交互 | 7 |
| `drop_credit_quality_interactions` | 去掉信用利差 × 负债/现金交互 | 8 |
| `drop_sector_flag_interactions` | 去掉宏观 × 行业 flag 交互 | 6 |
| `only_vix_interactions` | 只保留 VIX × 动量/波动交互 | 2 |

注意：`drop_*` 的含义是“在完整模型基础上删掉这一组”。如果删掉后效果变差，说明这一组大概率有贡献；如果删掉后效果变好，说明这一组可能引入了噪声或过拟合。

## 结果总表

主表来自：

```text
analysis/nasdaq_top500_score/runs/macro_interaction_ablation_review/macro_ablation_summary.csv
```

| Variant | IC | Rank IC | 年化收益 | 最大回撤 | 超额累计收益 | 年化 Alpha | Beta | 年化收益相对 full |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `baseline` | 0.016978 | 0.003683 | 33.75% | -29.36% | 10.51% | 7.88% | 1.042 | -9.80% |
| `direct_macro` | 0.012456 | 0.009214 | 20.23% | -22.92% | -13.90% | 1.20% | 0.813 | -23.32% |
| `full_interactions` | 0.022432 | 0.012953 | 43.55% | -24.19% | 30.39% | 17.16% | 0.922 | 0.00% |
| `drop_vix_interactions` | 0.029901 | 0.007859 | 42.53% | -29.85% | 28.24% | 13.30% | 1.067 | -1.01% |
| `drop_rate_valuation_interactions` | 0.023215 | 0.009148 | 34.08% | -19.00% | 11.13% | 9.06% | 0.983 | -9.47% |
| `drop_credit_quality_interactions` | 0.025907 | 0.007062 | 67.26% | -17.50% | 86.50% | 30.62% | 1.013 | +23.71% |
| `drop_sector_flag_interactions` | 0.025704 | 0.011266 | 28.14% | -37.18% | -0.04% | 4.32% | 0.964 | -15.40% |
| `only_vix_interactions` | 0.023075 | 0.005085 | 46.31% | -34.98% | 36.34% | 18.92% | 0.985 | +2.76% |

## 关键结论

### 1. 完整交互模型的 Rank IC 最好

`full_interactions` 的 Rank IC 是 `0.012953`，是所有组里最高的。

这说明如果目标是“整体横截面排序更稳”，完整 10 个交互仍然最好。它不一定带来最高 TopK 收益，但它最接近“模型整体排序能力改善”。

这点很重要，因为 TopK 收益可能由少数股票、少数行业或某几个调仓期贡献；Rank IC 更像是全样本排序能力的体检。

### 2. 信用质量交互在本次窗口里拖累了 TopK

`drop_credit_quality_interactions` 年化收益达到 `67.26%`，最大回撤只有 `-17.50%`，年化 alpha 达到 `30.62%`。

这说明本次实验中这两类交互可能是拖累项：

```text
macro_baa10y_credit_spread_change_20d × edgar_liabilities_to_assets
macro_baa10y_credit_spread × edgar_cash_to_assets
```

直觉上，信用压力和负债/现金应该有经济含义；但它们在这个模型、这个股票池、这个测试期里可能存在几个问题：

- EDGAR 负债、现金字段覆盖率或更新频率不均衡。
- Nasdaq 成长股里，现金多/负债低不一定等于短期收益更高。
- 信用利差变化对大盘风险更敏感，对 5 日横截面个股收益不一定稳定。
- 这组交互可能把模型引向“质量防御”，但错过了测试期里真正上涨的成长/动量股票。

结论不是“信用质量无用”，而是：第一版信用质量交互不适合直接进入默认主模型，需要重新设计或先下线。

### 3. 行业 flag 交互很重要，删掉后风险明显变差

`drop_sector_flag_interactions` 年化收益降到 `28.14%`，最大回撤扩大到 `-37.18%`，超额累计收益接近 0。

被删掉的是：

```text
收益率曲线倒挂 × Finance flag
利率变化 × Technology flag
油价变化 × Energy / Industrials flag
美元变化 × Technology flag
```

这说明宏观变量对不同行业的影响确实不同。宏观交互不是只在做“全市场择时”，它也在帮助模型理解行业条件。

但这也带来一个风险：收益可能部分来自行业配置，而不是纯个股选择。后续需要继续看 sector contribution 和行业暴露，确认它有没有过度押注少数行业。

### 4. VIX 交互有用，但不是唯一收益来源

`drop_vix_interactions` 年化收益 `42.53%`，只比完整模型低 `1.01%`，但 Rank IC 从 `0.012953` 降到 `0.007859`，最大回撤也从 `-24.19%` 变成 `-29.85%`。

这说明 VIX 交互不是收益的唯一来源，但它改善了排序稳定性和风险控制。

`only_vix_interactions` 年化收益 `46.31%`，但 Rank IC 只有 `0.005085`，最大回撤 `-34.98%`。这说明只靠 VIX 也能在 TopK 上赚到钱，但整体排序不稳，风险更高。

当前判断：

```text
VIX 交互适合作为辅助风险状态特征
不适合单独成为主模型
```

### 5. 利率 × 估值交互增加收益，但也增加风险暴露

`drop_rate_valuation_interactions` 年化收益降到 `34.08%`，但最大回撤改善到 `-19.00%`。

这说明利率估值交互大概率在贡献收益和 alpha，但也让组合承担了更多波动。它不是明显有害项，更像“收益增强但风险也增强”的特征。

后续可以考虑：

- 保留利率 × 估值，但降低树模型对它的过度依赖。
- 在 low VIX 或曲线倒挂环境下单独检查这组交互。
- 把利率上行和利率水平拆开，不混在同一组里判断。

## Regime 发现

本次 `macro_ablation_review_summary.yaml` 里显示：

- `full_interactions` 在 `high_vix` 下相对 baseline 年化收益差最高，达到 `+79.46%`，alpha 差 `+57.27%`。
- `drop_credit_quality_interactions` 在多个 regime 下都表现很强，尤其是 `rates_flat_or_falling`、`oil_flat_or_down`、`vix_rising`、`curve_not_inverted`。
- `only_vix_interactions` 在 `curve_inverted` 下表现很强，但在 `high_vix`、`curve_not_inverted`、`vix_flat_or_falling` 下明显不稳。
- `drop_rate_valuation_interactions` 在 `low_vix`、`curve_inverted`、`dollar_stronger` 下表现很差。

这说明宏观交互不是一个单一开关。不同交互在不同 regime 下可能有完全不同的贡献。

## 如何理解“收益更高但 Rank IC 更低”

`drop_credit_quality_interactions` 收益最高，但 Rank IC 低于完整模型。

这不能简单理解为“它只是运气”，但必须警惕：

- 它可能只是在 Top10 里押中了少数大赢家。
- 它可能改善了组合层面的行业和股票选择，但全市场排序反而没那么好。
- 它可能更适合当前 2024-2026 测试期，而不一定长期稳健。
- 它可能提高了某些 regime 下的收益，但在其他 regime 中还没有被充分检验。

所以当前不能直接把 `drop_credit_quality_interactions` 升级为默认主模型。它应该成为下一轮候选模型，再做集中度、贡献来源、换手成本和滚动窗口验证。

## 当前建议

当前默认主策略：

```text
default_no_credit_quality
含义：默认去掉 credit spread × liabilities/cash 两个信用质量交互。
原因：本次 ablation 中收益、alpha 和最大回撤最好。
状态：作为下一轮主策略候选，但仍需要集中度和稳健性验证。
```

研究保留配置：

```text
full_interactions
优点：Rank IC 最高，整体排序更稳。
保留原因：用于研究对照，防止只根据一次 TopK 收益就永久删除有经济含义的信用质量假设。
```

不建议直接采用：

```text
direct_macro
原因：收益和 alpha 明显弱。

only_vix_interactions
原因：收益尚可，但 Rank IC 低、最大回撤大。

drop_sector_flag_interactions
原因：收益和回撤都明显变差。
```

## 下一步

下一步不应该继续盲目堆宏观变量，而应该验证 `drop_credit_quality_interactions` 的收益是否可靠：

1. 检查收益是否集中在少数股票、少数行业、少数调仓期。
2. 对比 `full_interactions` 和 `drop_credit_quality_interactions` 的持仓差异。
3. 做换手率和交易成本敏感性。
4. 做滚动窗口或至少另一段测试期验证。
5. 重新设计信用质量交互，例如改成行业内负债分位、现金分位，而不是直接用原始比率。

## 相关笔记

- [[FRED ALFRED Macro Features Integration]]
- [[FRED ALFRED Macro Experiment Review]]
- [[Macro Features New Information And Return Degradation]]
- [[Macro Regime Review And Interaction Features]]
- [[Industry Exposure Strategy Comparison]]
