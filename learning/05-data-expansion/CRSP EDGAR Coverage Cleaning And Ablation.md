# CRSP EDGAR Coverage Cleaning And Ablation

这一步不是为了把 EDGAR 直接塞进默认模型，而是回答一个更基础的问题：

```text
SEC EDGAR 财报数据在 CRSP 2010 主线里覆盖够不够？
极端估值和亏损公司会不会污染模型？
财报指标按行业相对化后有没有增量？
哪些财报组可能有用，哪些更像噪声？
```

当前结论很明确：**EDGAR 数据链路已经可用，但还不适合进入默认主模型。** Alpha158-only 仍然是本轮收益和 alpha 最好的基线。

## 当前主线

固定口径：

```text
数据源：CRSP 本地日级数据
窗口：2010-01-01 到 2025-12-31
股票池：CRSP US Common Equity 月度动态市值 Top500
标签：未来 10 个交易日总收益
调仓：每 10 个交易日
入场：信号日后 1 个交易日 open
模型：conservative LightGBM
默认特征：Alpha158
```

加入 EDGAR 前，模型只使用 Alpha158 价格成交量特征。行业约束属于选股阶段规则，不是模型输入。

## 为什么先做覆盖审计

财报数据和行情数据不同。行情每天都有，财报按季度披露，而且不同公司字段并不统一。

如果直接把所有 EDGAR 字段拼进模型，会遇到几个问题：

- 有些 CRSP instrument 找不到 CIK。
- 有些公司有 CIK，但 companyfacts 中缺关键 XBRL tag。
- 有些字段只适合部分行业，比如金融、能源、REIT 的口径和普通工业公司不同。
- 亏损公司、负自由现金流公司会让市盈率、市值/自由现金流等估值指标失去常规含义。
- 跨行业直接比较 ROE、毛利率、估值倍数，容易让模型学到行业差异，而不是公司好坏。

所以本阶段顺序是：

```text
覆盖率审计 -> 固定规则清洗 -> 行业内相对化 -> 分组 ablation
```

## 覆盖率结果

本轮 EDGAR cleaned run 输出：

```text
universe instruments: 1,161
CIK mapped: 855
CIK mapping coverage: 73.64%
feature instruments: 816
feature instrument coverage: 70.28%
feature rows: 2,820,566
feature columns: 29
failure count: 918
```

失败原因：

```text
missing_fields: 573
missing_cik: 306
no_effective_filing_dates: 28
insufficient_filings: 11
```

缺失最明显的字段包括：

```text
gross_margin missing 74.76%
market_cap_to_fcf missing 67.05%
fcf_margin missing 60.31%
free_cash_flow_ttm missing 56.97%
liabilities_to_assets missing 56.46%
revenue_yoy_growth missing 51.99%
price_to_earnings missing 51.79%
price_to_sales missing 47.71%
```

这说明 EDGAR 可用，但并不是一个“满覆盖”的稳定特征源。模型会同时看到大量真实缺失和行业口径差异。

## 清洗规则

本轮不用全样本分位数清洗，因为全样本分位数可能把测试期信息带回训练期。

采用固定经济规则：

```text
负或无意义估值：
price_to_earnings 分母 <= 0 时设为 NaN
market_cap_to_fcf 分母 <= 0 时设为 NaN

静态裁剪：
margin: [-2, 2]
ROE / ROA: [-5, 5]
growth: [-5, 5]
cfo_to_net_income: [-10, 10]
fcf_margin: [-5, 5]
liabilities_to_assets / cash_to_assets: [0, 5]
price_to_sales / price_to_book: [0, 100]
price_to_earnings / market_cap_to_fcf: [0, 200]
filing lag: [0, 730]
```

清洗统计：

```text
set NaN by negative valuation policy: 438,721
clipped low: 302,481
clipped high: 279,351
```

清洗后模型读取 `fundamental_features_cleaned.parquet`，原始 `fundamental_features.parquet` 保留用于复盘。

## 行业内相对特征

行业相对化的动机是：估值、ROE、利润率更适合同业比较。

例如：

```text
软件公司的 price_to_sales 高，不一定贵。
银行的负债/资产高，不一定差。
零售和半导体的毛利率不可直接比较。
```

本轮使用 CRSP PIT `industry_master.parquet`，按每个日期的 SIC2/SIC4 归属计算分位。

规则：

```text
优先 SIC4 industry
如果 SIC4 样本数 < 10，fallback 到 SIC2 sector
只在同一天、同一行业组内计算 percentile
缺行业映射或原始 EDGAR 值缺失则保留 NaN
```

实际结果显示，SIC4 细行业组样本普遍太小，本轮几乎全部回退到 SIC2 sector。相对特征覆盖也不高：

```text
price_to_sales relative coverage: 29.90%
price_to_book relative coverage: 32.12%
price_to_earnings relative coverage: 29.07%
roe relative coverage: 33.49%
gross_margin relative coverage: 13.38%
net_margin relative coverage: 31.15%
```

这意味着“行业内财报相对化”目前更像 sector-level 相对化，而不是精细 industry-level 相对化。

## Ablation 结果

本轮固定同一 CRSP 股票池、同一标签、同一切分、同一 LightGBM 参数，只改变 EDGAR 特征组。

| 实验 | IC | Rank IC | 年化收益 | Alpha | 最大回撤 | Beta |
|---|---:|---:|---:|---:|---:|---:|
| Alpha158-only | 0.0155 | -0.0092 | 36.67% | 5.10% | -17.12% | 1.4907 |
| Clean EDGAR | 0.0015 | -0.0046 | 22.04% | -12.08% | -20.29% | 1.8446 |
| Clean EDGAR + Relative | -0.0035 | -0.0097 | 21.34% | -9.04% | -20.25% | 1.6126 |
| Drop valuation | 0.0022 | -0.0022 | 25.90% | -7.92% | -21.76% | 1.7764 |
| Drop profitability / quality | -0.0043 | -0.0038 | 14.48% | -19.51% | -25.65% | 1.8883 |
| Drop growth | -0.0009 | -0.0050 | 25.95% | -6.69% | -16.29% | 1.7134 |
| Drop balance sheet stability | 0.0031 | -0.0149 | 25.69% | -8.08% | -19.73% | 1.7582 |
| Drop filing state | -0.0035 | -0.0052 | 22.27% | -10.77% | -20.33% | 1.7599 |

## 怎么解读

第一，Alpha158-only 仍然最好。

它的年化收益、alpha、最大回撤都优于所有 EDGAR 组。说明在当前 2010-2025、10 日标签、两周调仓口径下，EDGAR 财报数据没有稳定改善主策略。

第二，清洗是有帮助的，但不够。

Raw EDGAR 之前年化约 17.43%，cleaned EDGAR 提升到 22.04%。清洗负估值和极端值确实减少了噪声，但没有解决财报覆盖、行业口径和短周期预测不匹配的问题。

第三，估值组可能是当前最大拖累之一。

`drop_valuation` 的 Rank IC 最接近 0，说明去掉估值后排序噪声有所降低。原因可能是：

- 10 日收益太短，估值不是短周期信号。
- 亏损公司和高成长公司估值倍数解释困难。
- 不同行业估值中枢差异太大。
- EDGAR shares、equity、earnings 与市场价格的对齐仍可能存在口径差。

第四，盈利质量组不能简单删除。

`drop_profitability_quality` 收益和 alpha 最差，说明利润率、ROE/ROA、现金流质量这类信息可能仍有价值。但它没有在全量 EDGAR 模型里形成稳定增量，可能需要更细的行业口径、更长标签或非线性分组处理。

第五，行业相对特征没有救回来。

当前行业相对特征受两个限制：

- SIC4 样本不足，几乎全部回退到 SIC2。
- 原始 EDGAR 缺失率高，相对特征覆盖也有限。

所以这一步没有证明“EDGAR 行业内相对化有效”。

## 当前决策

默认主线暂时不启用 EDGAR。

更合理的默认是：

```text
CRSP 2010 Alpha158-only conservative score
+ 选股阶段 sector_cap_2_top10 行业约束
```

EDGAR 保留为研究分支，不作为默认模型输入。

## 下一步

短期不继续堆 EDGAR 字段。更合理的方向是：

1. 做 EDGAR coverage-aware 训练，只让模型显式知道哪些财报字段可用。
2. 单独测试盈利质量组，而不是 all features 一起喂。
3. 把 EDGAR 标签周期拉长到 20/60 日，验证财报数据是否更适合中期收益。
4. 先恢复 sector_cap_2 作为选股约束，再看 EDGAR 是否能在该组合规则下改善边际候选。
5. 暂停估值组进入默认模型，除非后续能证明估值在行业内、长周期标签下有效。

## 覆盖修复实验

针对“为什么不使用上一次最近发布的财报”的问题，代码已经确认：旧版确实按最近一份 filing 做日频 as-of 合并，但它没有做“字段级续用”。如果最新 10-Q 缺某个字段，旧版不会单独沿用上一期同字段。

本次新增：

```text
字段级 as-of forward fill
每个字段 stale 上限，默认 540 天
coverage-aware 特征
XBRL tag 命中记录
缺失根因报告
```

字段级续用只允许使用已经披露过的字段值，不允许未来倒填。超过 stale 上限后仍然设为 NaN。

新增输出：

```text
edgar_missingness_root_cause.csv
edgar_field_availability_by_year.csv
edgar_tag_resolution_report.csv
```

修复后覆盖变化：

```text
feature instrument coverage: 70.28% -> 70.28%
missing_fields: 573 -> 519
gross_margin missing: 74.76% -> 71.11%
fcf_margin missing: 60.31% -> 46.36%
operating_margin missing: 53.73% -> 45.97%
```

覆盖改善主要来自字段级续用和 tag alias 扩展，但 CIK 映射覆盖没有变，因为当前 CRSP warehouse 里还没有额外 CIK 字段可用。

修复后模型结果：

| 实验 | IC | Rank IC | 年化收益 | Alpha | 最大回撤 | Beta |
|---|---:|---:|---:|---:|---:|---:|
| Alpha158-only | 0.0155 | -0.0092 | 36.67% | 5.10% | -17.12% | 1.4907 |
| Clean EDGAR | 0.0015 | -0.0046 | 22.04% | -12.08% | -20.29% | 1.8446 |
| Repaired quality only | 0.0146 | -0.0029 | 26.88% | -4.27% | -18.59% | 1.6155 |
| Repaired no valuation | -0.0006 | -0.0023 | 9.26% | -22.40% | -21.82% | 1.7823 |

这说明：

- 字段级修复有价值，尤其是盈利质量组。
- EDGAR 不是完全没用，但全量加入仍然拖累组合收益。
- `repaired_quality_only` 的 IC 已接近 Alpha158-only，Rank IC 也比 Alpha158-only 更接近 0，但 alpha 仍为负。
- `repaired_no_valuation` 说明“去掉估值但保留全部其他 EDGAR”并不自动有效，其他财报组之间仍可能互相引入噪声。

当前更新后的结论：

```text
EDGAR 可以继续研究，但默认模型仍不启用。
如果后续继续用 EDGAR，优先只研究 profitability_quality + coverage_state。
不要把 repaired_no_valuation 当默认候选。
```

## Quality Core 字段保留规则

本次新增 `quality core` 口径：不再把 EDGAR 全量字段一次性喂给模型，而是只保留最可能对中短期个股质量判断有帮助的三组字段。

默认保留：

```text
profitability_quality:
gross_margin, operating_margin, net_margin, roe, roa,
operating_cash_flow_ttm, free_cash_flow_ttm, cfo_to_net_income, fcf_margin

filing_state:
days_since_last_10q, days_since_last_10k, filing_lag_days,
is_recent_filing, is_amended_filing

coverage_state:
has_profitability_quality, has_growth, has_balance_sheet_stability, has_valuation,
days_since_revenue, days_since_net_income, days_since_operating_cash_flow,
days_since_assets, days_since_equity
```

默认剔除：

```text
valuation:
price_to_sales, price_to_book, price_to_earnings, market_cap_to_fcf
```

原因是：估值字段在当前 10 日标签下更像中长期定价信息，且容易受亏损、负自由现金流、不同行业估值中枢和 shares / market cap 口径影响。它可以保留在研究 ablation 中，但不作为默认候选字段。

## 字段有效性审计

新增 `edgar_effectiveness_review`，用于回答“哪些 EDGAR 字段真的有信息”。它不会自动按测试期结果筛字段，只生成诊断证据：

```text
edgar_feature_effectiveness_summary.yaml
edgar_feature_ic_summary.csv
edgar_feature_ic_by_year.csv
edgar_feature_ic_by_sector.csv
edgar_feature_quantile_spread.csv
```

审计逻辑：

```text
1. 每个交易日做横截面 IC / Rank IC：字段值 vs 未来 10 日标签。
2. 按年份和 SIC2 sector 拆开，检查字段是否只在少数年份或少数行业有效。
3. 做字段分位组合，比较 Top quantile 和 Bottom quantile 的未来收益差。
4. 结合覆盖率和 stale days 判断字段是否只是缺失状态代理。
```

这一步的核心价值是把 EDGAR 字段分成三类：

```text
可继续研究：Rank IC、分位 spread、覆盖率都相对稳定。
只做辅助状态：预测力弱，但能提示财报是否新鲜或可用。
暂不进入模型：覆盖差、分位收益不单调、跨年份/行业不稳定。
```

新增配置：

```text
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_quality_core_10d_conservative_2010_2025.yaml
```

该配置启用：

```text
field_level_fill
coverage_features
quality core feature groups
edgar_effectiveness_review
```

## Quality Core 真实训练结果

本次已运行 quality core 完整训练：

```text
配置：crsp_alpha158_edgar_quality_core_10d_conservative_2010_2025
best iteration: 10
Test IC: 0.014578
Test Rank IC: -0.002942
global Top10 年化收益: 26.88%
global Top10 alpha: -4.27%
global Top10 beta: 1.6155
global Top10 最大回撤: -18.59%
sector_cap_2_top10 年化收益: 40.95%
sector_cap_2_top10 alpha: 4.81%
sector_cap_2_top10 最大回撤: -19.67%
```

与当前 Alpha158-only 行业约束主线对比：

```text
Alpha158-only + sector_cap_2_top10 年化收益: 46.26%
Alpha158-only + sector_cap_2_top10 alpha: 13.03%
Alpha158-only + sector_cap_2_top10 最大回撤: -15.62%
```

结论：quality core 比 clean EDGAR 更合理，但仍没有超过 Alpha158-only + sector_cap_2。因此它不能进入默认主线。

字段有效性审计显示，Rank IC 靠前的主要是盈利质量字段：

```text
edgar_operating_margin Rank IC: 0.0186
edgar_free_cash_flow_ttm Rank IC: 0.0186
edgar_net_margin Rank IC: 0.0159
edgar_fcf_margin Rank IC: 0.0125
edgar_operating_cash_flow_ttm Rank IC: 0.0123
```

Rank IC 靠后的字段包括：

```text
edgar_roa
edgar_has_profitability_quality
edgar_has_balance_sheet_stability
edgar_has_growth
edgar_days_since_revenue
```

这说明下一步不应继续扩大 EDGAR 字段，而应收缩为更小的 `profitability quality mini core`。尤其要谨慎使用 coverage_state：它可能包含公司披露节奏、公司类型、数据覆盖差异等混合信息，不一定是稳定的基本面 alpha。

新的优化方向：

```text
1. 默认策略继续使用 Alpha158-only + sector_cap_2_top10。
2. 新增 EDGAR mini-core：只保留 operating_margin、free_cash_flow_ttm、net_margin、fcf_margin、operating_cash_flow_ttm。
3. 暂停 coverage_state 直接进模型，只保留为复盘诊断。
4. 做 20 日 / 60 日标签对照，验证财报质量字段是否更适合中期收益。
5. 把 edgar_effectiveness_review 默认设为可选，不在每次训练都跑，避免 200+ 秒额外耗时。
```

## EDGAR Mini-Core 与 Horizon 对照计划落地

本次新增 mini-core 工程口径，用于验证 EDGAR 是否只有少数盈利质量字段值得保留。

入模字段固定为：

```text
edgar_operating_margin
edgar_free_cash_flow_ttm
edgar_net_margin
edgar_fcf_margin
edgar_operating_cash_flow_ttm
```

不再默认入模：

```text
valuation
growth
balance_sheet_stability
filing_state
coverage_state
```

新增配置：

```text
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_mini_core_10d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_20d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_mini_core_20d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_60d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_mini_core_60d_conservative_2010_2025.yaml
```

新增汇总脚本：

```text
analysis/nasdaq_top500_score/crsp_edgar_mini_core_horizon_review.py
```

它会统一输出：

```text
crsp_edgar_mini_core_horizon_summary.csv
crsp_edgar_mini_core_horizon_review.yaml
report.md
```

评价规则：

```text
如果 mini-core 在 10 日仍弱于 Alpha158-only，就不进入默认主线。
如果 20 日或 60 日同时改善 Rank IC 和 sector_cap_2 alpha，说明财报质量字段可能更适合中期收益。
如果只改善收益但不改善 IC / Rank IC，只能标记为组合收益改善，不能认定预测力增强。
```

## EDGAR Mini-Core 与 Horizon 对照结果

完成 10 / 20 / 60 日六组对照：

```text
Alpha158-only 10d
EDGAR mini-core 10d
Alpha158-only 20d
EDGAR mini-core 20d
Alpha158-only 60d
EDGAR mini-core 60d
```

汇总产物：

```text
analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_horizon_review/crsp_edgar_mini_core_horizon_summary.csv
analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_horizon_review/report.md
```

核心结果：

| 组合 | IC | Rank IC | Global 年化 | Global Alpha | Sector Cap2 年化 | Sector Cap2 Alpha |
|---|---:|---:|---:|---:|---:|---:|
| Alpha158 10d | 0.0155 | -0.0092 | 36.67% | 5.10% | N/A | N/A |
| EDGAR mini-core 10d | 0.0133 | -0.0005 | 38.93% | 4.16% | 48.84% | 11.10% |
| Alpha158 20d | -0.0009 | -0.0057 | 34.72% | 0.95% | N/A | N/A |
| EDGAR mini-core 20d | 0.0055 | -0.0047 | 27.62% | -10.26% | 30.91% | -7.27% |
| Alpha158 60d | 0.0124 | -0.0048 | 25.87% | -9.49% | N/A | N/A |
| EDGAR mini-core 60d | 0.0043 | -0.0144 | 22.67% | -13.44% | 11.65% | -26.41% |

解读：

```text
10 日 mini-core 的 Rank IC 从 -0.0092 改善到 -0.0005，global 年化也从 36.67% 提升到 38.93%。
但 10 日 global alpha 从 5.10% 降到 4.16%，说明它不是全维度改善。
10 日 mini-core + sector_cap_2 的年化 48.84%、alpha 11.10%，接近但仍略弱于 Alpha158-only + sector_cap_2 的 alpha 13.03%。
20 日和 60 日加入 mini-core 后，收益、alpha、Rank IC 都没有形成稳定改善。
```

当前判断：

```text
EDGAR mini-core 不是默认主线。
它可以保留为 10 日 sector_cap_2 的研究分支，因为组合结果有边际改善，但证据还不够强。
20 日和 60 日暂时不继续沿 EDGAR 方向优化；更长 horizon 并没有验证“财报更适合中期收益”的假设。
下一步更适合做 10 日 mini-core 持仓差异复盘：看它到底替换了哪些股票、改善来自哪些行业和哪些财报字段。
```

## EDGAR Mini-Core 持仓差异复盘

复盘口径：

```text
Alpha158-only + sector_cap_2_top10
EDGAR mini-core + sector_cap_2_top10
测试期：2024-2025
调仓周期：10 个交易日
成本：0bps 主口径
```

输出位置：

```text
analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_position_diff_review/report.md
analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_position_diff_review/edgar_mini_core_position_diff_summary.yaml
analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_position_diff_review/edgar_mini_core_position_diff.csv
analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_position_diff_review/edgar_mini_core_contribution_diff.csv
analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_position_diff_review/edgar_mini_core_fundamental_diff.csv
```

核心结果：

```text
回测期数：50
共同持仓行数：352
EDGAR 新增持仓行数：148，涉及 115 只股票
EDGAR 移除持仓行数：148，涉及 97 只股票
EDGAR 新增持仓净贡献：0.2308
Alpha158 被移除持仓原净贡献：0.1889
新增 - 移除的贡献差：约 0.0419
Top3 新增正贡献占比：23.71%
最大 sector 新增正贡献占比：17.96%
风险标记：无
```

财报解释：

```text
EDGAR 新增持仓的 operating_margin 均值 0.1966，高于被移除持仓的 0.1296。
EDGAR 新增持仓的 net_margin 均值 0.1570，高于被移除持仓的 0.0904。
EDGAR 新增持仓的 fcf_margin 均值 0.3067，高于被移除持仓的 0.0840。
EDGAR 新增持仓的 operating_cash_flow_ttm 均值 91.56 亿，高于被移除持仓的 71.38 亿。
```

解读：

```text
mini-core 并不是靠 1-3 只股票或单一 sector 把收益抬起来，替换相对分散。
新增持仓的盈利质量和现金流字段整体更好，因此这次组合改善有一定经济解释。
但它仍未明显改善 global alpha，也没有让 Rank IC 转正，所以不能进入默认主线。
当前最合适的定位是：EDGAR mini-core 作为 10 日 sector_cap_2 的研究分支继续保留。
```

## 产出

```text
analysis/nasdaq_top500_score/edgar_coverage.py
analysis/nasdaq_top500_score/crsp_edgar_ablation_review.py
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_quality_core_10d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_clean_10d_conservative_2010_2025/
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_relative_10d_conservative_2010_2025/
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_repaired_quality_10d_conservative_2010_2025/
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_repaired_no_valuation_10d_conservative_2010_2025/
analysis/nasdaq_top500_score/runs/crsp_edgar_ablation_review/
analysis/nasdaq_top500_score/configs/crsp_edgar_ablation/
```

核心报告：

```text
analysis/nasdaq_top500_score/runs/crsp_edgar_ablation_review/report.md
analysis/nasdaq_top500_score/runs/crsp_edgar_ablation_review/crsp_edgar_ablation_summary.csv
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_clean_10d_conservative_2010_2025/edgar_coverage_summary.yaml
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_clean_10d_conservative_2010_2025/fundamental_cleaning_summary.yaml
```

## 相关笔记

[[CRSP EDGAR Fundamentals Integration]]
[[CRSP Industry Constraint And Relative Feature Recovery]]
[[Industry Features And Relative Ranking]]
[[SEC EDGAR Technical Data Flow]]
[[IC And Rank IC]]
