# Strict Re-Run Result Review

这篇笔记是严格数据修复后重跑实验的结果记录模板。当前阶段已经建立 strict 配置和验收框架，但还没有真实 Norgate / PIT market cap 数据，因此这里先记录重跑标准。

## 重跑对象

严格重跑只比较三组：

```text
strict_baseline_alpha158_edgar_5d
strict_macro_direct_5d
strict_macro_interactions_no_credit_5d
```

三组必须保持一致：

```text
同一 PIT 股票池
同一价格复权口径
同一训练/验证/测试切分
同一未来 5 日收益标签
同一 TopK 和压力测试口径
```

唯一变化：

```text
baseline：Alpha158 + EDGAR + market features
direct macro：baseline + raw macro
macro interactions：baseline + macro interaction features，不直接输入 raw macro
```

## 必须通过的门槛

结果进入主结论前，必须满足：

```text
data_quality_summary.yaml strict_headline_allowed = true
pit_universe_validation.csv 无 HIGH fail
market_cap_validation.csv 无 HIGH fail
security_master_validation.csv 至少包含 listing / delisting date
future_leakage_audit.py 不再报告 R1/R2 高风险
backtest_stress_summary.yaml 没有显示收益完全依赖 entry_lag=1 或 10 bps 成本
```

## 结果记录模板

| 实验 | IC | Rank IC | 累计收益 | 年化收益 | 最大回撤 | Alpha | Beta | 压力测试结论 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| strict baseline | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| strict direct macro | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| strict macro interactions | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

## 水分归因

重跑后要按顺序回答：

```text
当前 Nasdaq public 结果 vs PIT 股票池结果：股票池水分贡献多少？
PIT 股票池结果 vs 压力测试结果：交易假设贡献多少？
压力测试后结果 vs 修订数据口径结果：价格/财报/宏观口径贡献多少？
```

如果严格结果收益大幅下降，不是失败，而是研究变干净了。

## 相关笔记

- [[Strict PIT Data Repair Plan]]
- [[Backtest Stress Test Review]]
- [[Future Leakage And Backtest Water Audit]]
