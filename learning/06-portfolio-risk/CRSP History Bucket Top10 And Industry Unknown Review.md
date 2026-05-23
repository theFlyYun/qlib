# CRSP History Bucket Top10 And Industry Unknown Review

## 本阶段目标

在 `2010-2025` CRSP 新主线上完成两件事：

1. 验证历史长度桶内 Top10 是否比全局 Top10 更稳。
2. 检查 CRSP 行业字段 `UNKNOWN` 到底集中在哪些年份、哪些证券。

这一步仍然不加 EDGAR、不加宏观、不启用行业约束，只比较组合规则和数据覆盖。

## 实验口径

共同口径：

```text
数据源：CRSP 本地日级数据
窗口：2010-01-01 ~ 2025-12-31
股票池：US Common Equity 月度动态市值 Top500
标签：未来 10 个交易日收益
模型：Alpha158-only conservative LightGBM
调仓：每 10 个交易日一次
入场：信号日后 1 个交易日 open
主成本：0bps
测试期：2024-2025
```

对照组：

```text
global_top10：直接按模型 score 取前 10
bucket_4_3_2_1：按历史长度桶内名额取前 10
```

桶内名额：

```text
full_10y: 4
5_10y: 3
2_5y: 2
lt_2y: 1
```

## 历史长度桶分布

`history_buckets.csv` 中共有 1142 只股票：

```text
full_10y: 763
5_10y: 248
2_5y: 93
lt_2y: 38
```

这说明当前 CRSP Top500 动态池里，大多数股票在 2010 窗口下都有完整或较长历史。短历史股票数量不多，但仍可能在模型高分里出现。

## Bucket Top10 对照结果

总体结果：

| Variant | Cumulative Return | Annualized Return | Max Drawdown | Alpha | Beta | Avg Turnover |
|---|---:|---:|---:|---:|---:|---:|
| global_top10 | 85.86% | 36.67% | -17.12% | 5.10% | 1.491 | 121.20% |
| bucket_4_3_2_1 | 64.16% | 28.38% | -20.47% | -0.00% | 1.415 | 135.60% |

结论很直接：

```text
强制 4/3/2/1 桶内名额没有改善组合。
收益下降。
最大回撤变差。
alpha 几乎归零。
换手更高。
```

所以桶内 Top10 不能作为当前默认策略。

## 分桶贡献

全局 Top10 的持仓贡献：

| Bucket | Holding Count | Avg Gross Return | Win Rate | Net Contribution | Excess Contribution |
|---|---:|---:|---:|---:|---:|
| full_10y | 282 | 0.85% | 51.42% | 23.84% | 5.23% |
| 5_10y | 107 | 0.61% | 51.40% | 6.48% | -4.61% |
| 2_5y | 85 | 3.36% | 52.94% | 28.58% | 21.16% |
| lt_2y | 26 | 3.59% | 69.23% | 9.34% | 7.46% |

桶内名额 Top10 的持仓贡献：

| Bucket | Holding Count | Avg Gross Return | Win Rate | Net Contribution | Excess Contribution |
|---|---:|---:|---:|---:|---:|
| full_10y | 200 | 0.59% | 51.00% | 11.89% | -3.71% |
| 5_10y | 150 | 0.18% | 48.00% | 2.71% | -8.99% |
| 2_5y | 100 | 3.10% | 56.00% | 31.04% | 23.24% |
| lt_2y | 50 | 1.90% | 70.00% | 9.52% | 5.62% |

解读：

- `2_5y` 和 `lt_2y` 并不是主要拖累，甚至贡献不错。
- 问题在于硬性名额改变了模型自然选择，把更多仓位分给表现较弱的 `5_10y`，同时压低了 `full_10y` 的优质候选数量。
- 全局 Top10 已经自然选到一些高质量短历史股票，没有必要强制每期都给短历史名额。

## 压力测试

只看主入场口径 `lag1_open`：

| Variant | 0bps Annualized | 25bps Annualized | 50bps Annualized |
|---|---:|---:|---:|
| global_top10 | 36.67% | 26.71% | 17.45% |
| bucket_4_3_2_1 | 28.38% | 17.92% | 8.28% |

桶内名额在成本压力下更差，主要因为平均换手更高。

这再次说明：桶内名额如果要用，必须服务于风险控制，而不是为了提高收益。

## 行业 UNKNOWN 来源

新增可复跑脚本：

```bash
.venv/bin/python analysis/nasdaq_top500_score/crsp_industry_unknown_review.py \
  --run-dir analysis/nasdaq_top500_score/runs/crsp_alpha158_bucket_top10_10d_conservative_2010_2025
```

输出：

```text
crsp_industry_unknown_by_year.csv
crsp_industry_unknown_by_security.csv
crsp_industry_unknown_by_security_type.csv
crsp_industry_unknown_examples.csv
crsp_industry_unknown_review_summary.yaml
```

汇总结果：

```text
membership_rows: 96000
unknown_rows: 14887
sic2_coverage: 84.49%
unknown_security_count: 336
unknown_naics_valid_share: 0.0%
unknown_icb_valid_share: 0.0%
```

最差年份：

| Year | SIC2 Coverage | UNKNOWN Share |
|---:|---:|---:|
| 2010 | 68.63% | 31.37% |
| 2011 | 69.15% | 30.85% |
| 2012 | 72.35% | 27.65% |
| 2013 | 73.53% | 26.47% |
| 2014 | 74.90% | 25.10% |

最重要的发现：

```text
UNKNOWN 不是因为混入了 warrant / preferred / fund。
UNKNOWN 大多仍是 EQTY / COM / A 的正常普通股。
这些 UNKNOWN 股票的 NAICS 和 ICB 也基本不可用。
```

例子包括：

```text
K
HES
DFS
PXD
ANSS
ATVI
VMW
MRO
CERN
CTXS
```

这些都是正常大中型股票或曾经的重要成分，不是脏证券。问题是当前 CRSP daily 文件里的行业字段对这些证券没有覆盖。

## 当前结论

1. 历史长度桶内强制名额暂不作为默认。

全局 Top10 已经自然选择到有贡献的短历史股票。强制 `4/3/2/1` 反而降低收益、提高换手、恶化回撤。

2. 短历史股票不应统一剔除。

`2_5y` 和 `lt_2y` 当前贡献为正。更合理的做法是继续做短历史风险复盘，而不是简单禁止。

3. 行业约束暂时不能恢复。

CRSP SIC2 在测试期覆盖达标，但训练期 2010-2014 覆盖太低，而且 UNKNOWN 是正常普通股，不是清洗规则能解决的。

4. 行业字段需要补充数据源。

如果要恢复行业约束和行业内相对特征，需要优先解决行业分类口径，例如：

```text
用 CUSIP / PERMNO / ticker 做外部行业映射
接入 Compustat / CRSP link table / vendor industry classification
先建立静态行业映射做研究对照，再评估 PIT 行业要求
```

## 下一步

推荐顺序：

1. 不把 bucket quota 设为默认。
2. 保留全局 Top10 作为当前 2010 baseline 主策略。
3. 做 `2_5y / lt_2y` 短历史赢家和输家复盘，确认短历史收益是否集中在少数股票。
4. 先解决行业分类覆盖，再恢复行业约束和行业内相对特征。
5. 在行业路径恢复前，不急着继续加宏观。

## 相关产物

```text
analysis/nasdaq_top500_score/runs/crsp_alpha158_bucket_top10_10d_conservative_2010_2025/report.md
analysis/nasdaq_top500_score/runs/crsp_alpha158_bucket_top10_10d_conservative_2010_2025/bucket_vs_global_comparison.csv
analysis/nasdaq_top500_score/runs/crsp_alpha158_bucket_top10_10d_conservative_2010_2025/bucket_vs_global_bucket_contribution.csv
analysis/nasdaq_top500_score/runs/crsp_alpha158_bucket_top10_10d_conservative_2010_2025/crsp_industry_unknown_review_summary.yaml
```

## 相关笔记

[[CRSP 2010 Baseline Cleanup And Industry Recovery]]
[[Stock Pool Cleaning And History Buckets]]
[[Short History Stock Review]]
[[Industry Features And Relative Ranking]]
[[Market Derived Relative Features]]
