# Strict PIT Data Repair Plan

这篇笔记记录未来函数与回测水分审计后的第一层修复：把股票池、市值和证券主数据从“当前快照近似”推进到“可验收的 PIT 数据契约”。

核心原则：

```text
严格结果优先于高收益结果。
未通过 PIT 数据验收的实验，只能作为学习观察，不作为策略结论。
```

## 为什么先修股票池

当前最高风险不是 LightGBM，也不是 TopK 回测函数，而是股票池来源。

当前 `nasdaq_public` 有两个问题：

```text
1. 只看当前仍能被 Nasdaq public screener 看到的证券，天然缺少退市、并购、破产、转板股票。
2. approximate_market_cap_asof 用 current_market_cap * asof_close / latest_close 反推历史市值。
```

这会让历史回测更像“在幸存者里选股票”，而不是“在当时真实可投资股票里选股票”。

## 新的数据验收契约

新增数据质量验收输出：

```text
pit_universe_validation.csv
security_master_validation.csv
market_cap_validation.csv
data_quality_summary.yaml
```

验收重点：

```text
股票池是否包含退市股票
是否有历史 listing / delisting date
是否有历史 shares outstanding 或 PIT market cap
是否有 security type
是否有历史成分 membership
是否有 PIT 行业分类
是否仍然使用 market_cap_asof_estimate
```

如果配置启用：

```yaml
strict_pit:
  enabled: true
  enforcement: fail
```

那么缺少关键 PIT 字段时，实验会停止，而不是继续生成一个看似严格的高收益报告。

## 两层股票池

第一层：`launch_pit_2023`

```text
目标：模拟 2023-12-31 当时可见的股票池，用于 2024-2026 测试。
要求：不能使用 2023-12-31 之后的证券状态、市值、shares、行业分类。
```

第二层：`full_pit_dynamic`

```text
目标：做长期严谨研究，按每个历史日期的可交易范围构造动态股票池。
要求：包含历史成分、退市股票、历史 listing/delisting、历史 shares 或 market cap。
```

当前新增 strict 配置默认选择 `full_pit_dynamic`，并使用 Norgate 作为个人可落地数据源路线。

## 当前限制

当前 Mac 环境没有真实 Norgate Data Updater 和订阅，因此 strict 配置只能解析，不能真实拉取 Norgate 数据。

更重要的是：即使接入 Norgate OHLCV 和历史成分，也还要补历史 market cap 或 shares outstanding。否则严格股票池仍会被 `market_cap_validation.csv` 阻断。

## 新增 strict 配置

```text
analysis/nasdaq_top500_score/configs/strict/strict_baseline_alpha158_edgar_5d.yaml
analysis/nasdaq_top500_score/configs/strict/strict_macro_direct_5d.yaml
analysis/nasdaq_top500_score/configs/strict/strict_macro_interactions_no_credit_5d.yaml
```

它们默认：

```text
使用 data.source=norgate
包含 US Equities + US Equities Delisted
禁用当前快照 industry 特征和 industry_constraints
宏观 strict 配置禁用 latest 模式，要求 vintage / real-time period
启用 backtest_stress
```

## 当前结论

修复前，当前 Nasdaq public 高收益只能说明：

```text
学习数据和当前假设下，模型有较强历史表现。
```

不能说明：

```text
策略真实年化收益稳定达到 60%+
策略已经通过严格 PIT 回测
模型可以进入实盘候选
```

下一步应先补 PIT 股票池和历史市值，再重跑 baseline、direct macro、macro interactions。

## 相关笔记

- [[Future Leakage And Backtest Water Audit]]
- [[Backtest Stress Test Review]]
- [[Data Source Upgrade Plan]]
- [[Norgate Data Integration]]
