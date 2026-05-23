# CRSP Industry Mapping Repair

## 目标

本阶段解决的是 CRSP 主线里的行业分类口径问题：行业约束和行业内相对特征之前在 Nasdaq 数据源里有效，但迁移到 CRSP 后不能直接恢复，因为行业字段必须先满足 PIT 验收。

最终目标不是马上开启行业约束，而是先建立一层统一的 `industry_master`：

```text
CRSP 月末动态 Top500 行 -> PIT 行业映射 -> 覆盖率验收 -> 决定是否恢复行业路径
```

## 为什么要修

旧版行业验收先读 `membership.csv`，如果缺 `siccd`，就回退到 `security_master.csv`。这有两个问题：

1. `security_master.csv` 更像每只股票的代表性或最新证券信息，不适合代表历史每个月的 PIT 行业。
2. 旧 prepared dataset 复用了缺行业字段的 `membership.csv`，导致 2010-2014 年行业覆盖看起来很差。

所以这次修复的核心是：行业分类优先来自“月末选 Top500 当天的 CRSP row-level SIC/NAICS”，而不是事后回填。

## 新行业映射层

新增产物：

```text
industry_master.parquet
industry_mapping_coverage.csv
industry_mapping_failures.csv
industry_mapping_summary.yaml
```

`industry_master.parquet` 的核心字段：

```text
instrument
permno
effective_start
effective_end
sector_scheme
sector
industry_scheme
industry
raw_siccd
raw_naics
source
is_pit
confidence
evidence_date
```

第一版来源优先级：

```text
1. crsp_monthly_row
2. sec_edgar_sic fallback
3. UNKNOWN
```

本次真实重跑中，`sec_edgar_sic` 没有被使用，因为 CRSP 月末行已经能覆盖所有 membership 行。

## PIT 口径

PIT 的意思是 point-in-time，也就是只使用当时可见的数据。

本阶段的行业 PIT 口径是：

```text
月末用 DlyCap 排 Top500
同时读取同一天 CRSP row 上的 SICCD / NAICS / ICBIndustry
membership 从下一个交易日生效
行业字段跟着这个 membership interval 生效
```

这样做的好处是，模型和组合在某个交易日看到的行业分类，不来自未来某一天的公司状态。

## Schema 防复用

为了避免继续复用旧 prepared dataset，本阶段把 `industry_mapping.schema_version` 加进 CRSP prepared dataset key。

也就是说，行业 schema 或映射口径变化后，会生成新的 prepared dataset：

```text
runs/crsp_prepared_datasets/crsp_<new_hash>/
```

这比手动删除旧缓存更稳，因为实验配置本身决定数据缓存是否可复用。

## 本次结果

运行配置：

```text
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_10d_conservative_2010_2025.yaml
```

行业映射摘要：

```text
rows: 96000
crsp_pit_rows: 96000
edgar_fallback_rows: 0
unknown_rows: 0
non_pit_or_unverified_rows: 0
train_min_annual_strict_sector_coverage: 100%
test_min_strict_sector_coverage: 100%
conclusion: industry_mapping_pass
```

行业验收摘要：

```text
source: industry_master
fallback_to_security_master: false
train_min_annual_sic2_coverage: 100%
test_min_rebalance_sic2_coverage: 100%
industry_features_allowed: true
industry_constraints_allowed: true
conclusion: industry_pit_validation_pass
```

这说明之前行业覆盖不足，主要不是 CRSP 原始数据没有行业字段，而是旧 prepared dataset 和 validation fallback 路径造成的口径问题。

## 对策略路径的影响

现在可以恢复行业路径，但仍要分阶段做：

1. 先做行业暴露和行业贡献复盘。
2. 再跑行业约束 Top10，对照全局 Top10。
3. 再跑行业内 market 相对特征，例如行业内动量、波动率、成交额、历史长度分位。
4. 最后再考虑 EDGAR 财务/估值的行业内相对特征。

暂时不要直接把行业约束设成默认。原因是：行业覆盖通过只说明“字段口径可用”，还没有证明行业约束在 CRSP 2010 主线里能提升收益、回撤或 Rank IC。

## 遗留问题

- SIC 不是 GICS。它更偏企业主营业务/标准行业分类，和投资组合常用的 GICS sector 不完全等价。
- SIC 分类在不同年代可能有定义和公司业务变化问题，本阶段只保证 row-level PIT，不保证经济含义永远稳定。
- EDGAR fallback 暂未实际使用；后续如果 CRSP 某些区间缺 SIC，必须确认 EDGAR SIC 的 evidence date，不能用当前 SEC 公司页回填历史。

## 下一步

下一阶段建议先恢复行业暴露复盘，再做行业约束对照：

```text
global_top10
sector_capped_top10: max_sector=3, max_industry=2
sector_capped_top10: max_sector=2, max_industry=2
```

如果行业约束改善回撤或 alpha，再进入行业内 market 相对特征。
