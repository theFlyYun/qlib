# Future Leakage And Backtest Water Audit

这篇笔记是对当前 Nasdaq/Qlib 高收益回测的未来函数和收益水分审计。

本次审计对象是当前默认 no-credit macro interactions 主策略。由于正式默认配置刚建立、尚未单独重跑，本次用等价的 ablation run 作为证据来源：

```text
analysis/nasdaq_top500_score/runs/nasdaq_alpha158_edgar_macro_ablation_drop_credit_quality_interactions_10y_frozen_2023_top500_5d_pit_safe
```

主回测口径：

```text
策略 variant：sector_cap_2_top10
测试期：2024-01-02 到 2026-05-15
标签：未来 5 日收益
入场：信号日后 1 个交易日
持有：5 个交易日
成本：10 bps
```

当前结果：

| 指标 | 数值 |
|---|---:|
| 累计收益 | 233.42% |
| 年化收益 | 67.26% |
| 最大回撤 | -17.50% |
| 超额累计收益 | 86.50% |
| 年化 Alpha | 30.62% |
| Beta | 1.013 |
| 平均换手 | 90.17% |
| 调仓期数 | 118 |

结论先放前面：

```text
没有发现 TopK 回测函数直接使用未来收益选股。
没有发现 market rolling features 或 backtest entry/exit 的直接未来函数。
但股票池和市值口径存在高风险水分，足以让当前高收益不能被视为严谨策略结果。
```

## 审计产物

本次新增审计脚本：

```text
analysis/nasdaq_top500_score/future_leakage_audit.py
```

它生成的证据文件在：

```text
analysis/nasdaq_top500_score/runs/nasdaq_alpha158_edgar_macro_ablation_drop_credit_quality_interactions_10y_frozen_2023_top500_5d_pit_safe/future_leakage_audit/
```

核心文件：

```text
future_leakage_risk_register.csv
universe_asof_selection_sample.csv
macro_asof_sample.csv
market_feature_recalc_sample.csv
edgar_visibility_sample.csv
backtest_recalc_sample.csv
audit_summary.yaml
```

## 风险总览

| 风险 | 级别 | 状态 | 结论 |
|---|---|---|---|
| `nasdaq_public` 缺退市股票和历史证券主数据 | 高 | confirmed_risk | 存在幸存者偏差 |
| `approximate_market_cap_asof` 用当前市值反推历史市值 | 高 | confirmed_risk | 隐含当前 shares / 当前公司状态 |
| 当前 sector/industry 不是历史 PIT 分类 | 中 | confirmed_risk | 行业特征和行业约束有历史口径风险 |
| EDGAR 下一交易日生效 | 中 | partial_mitigation | 处理方向正确，但 companyfacts 是否完全 as-filed 仍需抽样核对 |
| FRED 日频序列 latest 模式 | 中 | partial_mitigation | effective date 安全，但 realtime_start 显示为当前 vintage |
| market rolling features | 低 | checked | 抽样复算没有发现未来价格 |
| backtest entry/exit | 低 | checked | 抽样复算与记录一致 |
| 收益解释 | 中 | needs_stress_test | 高收益仍需压力测试确认 |

## 最大问题：股票池不是严格 PIT

当前配置使用：

```text
universe.selection.method = approximate_market_cap_asof
as_of_date = 2023-12-31
candidate_top_n_by_current_market_cap = 1000
top_n_by_market_cap = 500
```

这比“直接用今天市值前 500”更好，但仍然不是严谨 PIT。

代码逻辑是：

```text
market_cap_asof_estimate = current_market_cap * asof_close / latest_close
```

问题在于：

```text
current_market_cap = 当前时点市值
latest_close = 当前或最近价格
asof_close = 2023-12-31 前最近价格
```

这个公式本质上假设 shares outstanding 不变，用当前市值和当前价格反推出一个近似 shares，再乘以历史价格。这会隐含：

- 当前仍然上市。
- 当前仍然在 Nasdaq public 数据里。
- 当前公司的股本结构、拆并股、增发、回购、并购状态。
- 当前能被 Nasdaq screener 看到。

抽样证据在 `universe_asof_selection_sample.csv`。例如：

```text
NVDA current_market_cap=5.387T
latest_close_for_asof_estimate=225.32
asof_close=49.522
market_cap_asof_estimate=1.184T
```

这个结果看起来像“2023 年底市值”，但它不是历史市值数据库里的真实值，而是用当前市值反推。

所以当前结果仍有两个高风险：

1. 幸存者偏差：退市、并购、破产、转板、长期失败公司不在股票池里。
2. 当前信息污染：当前证券状态和当前市值结构参与了历史股票池构造。

这一个问题足以解释为什么回测收益可能偏高。

## 价格口径风险

Nasdaq public 日线接口提供的是当前可下载的 OHLCV。当前项目没有确认：

- 是否 total return 复权。
- 是否 split adjusted。
- 是否 dividend adjusted。
- 是否对退市前价格完整。

这会影响：

- Alpha158 的价格成交量特征。
- 未来 5 日收益标签。
- 回测 entry/exit 价格。

如果价格没有正确复权，长期特征和收益会被拆股、分红、特殊公司行为污染。这个问题不一定方向性抬高收益，但会降低结论可信度。

## EDGAR 审计

当前 EDGAR 处理有一个重要安全措施：

```text
SEC acceptanceDateTime / filed
-> 顺延到下一个交易日
-> 才 merge_asof 到每日特征
```

对应代码逻辑：

```text
shift_events_to_next_trading_day(...)
pd.merge_asof(... direction="backward")
```

这可以避免“财报当天盘后披露却当天交易使用”的问题。

但还有一个中风险：

```text
companyfacts 是 SEC API 当前返回的结构化事实集合。
它按 accession 抽取，但仍需要抽样核对是否完全等价原始 as-filed XBRL。
```

所以 EDGAR 的状态是：

```text
披露日对齐：已部分缓解
as-filed 原始事实：仍需抽样核对
```

## 宏观特征审计

宏观特征使用了：

```text
effective_date <= feature date
effective_lag_trading_days = 1
```

审计样本显示：

```text
effective_after_feature_date = False
```

也就是没有看到“特征日早于生效日”的问题。

但日频市场序列，例如：

```text
DGS10
DGS2
BAA10Y
VIXCLS
DCOILWTICO
DTWEXBGS
```

配置里使用了：

```text
realtime_mode = latest
effective_date_source = observation_date
```

抽样证据里这些序列的 `realtime_start` 显示为 `2026-05-17`，晚于历史特征日。这说明它们不是严格 ALFRED vintage 口径，而是使用当前 latest 值，再按 observation date 后一交易日生效。

这对 VIX、利率、油价这类日频市场序列可能问题较小，因为它们通常修订少或不可修订；但在严谨回测里仍然应该标为中风险。

## Market Features 审计

审计脚本抽样复算了 `market_momentum_20d`：

```text
recorded_market_momentum_20d == close_today / close_20_trading_days_ago - 1
```

结果：

```text
max_market_momentum_abs_diff = 0.0
used_future_rows = 0
```

这说明行情派生特征的 20 日动量抽样没有使用未来价格。

从代码看：

- `market_history_rows_asof` 是逐日递增。
- `momentum_20d/60d/120d` 使用 `shift(window)`。
- `volatility_20d/60d` 使用历史 returns rolling。
- 行业内 percentile 是同一日期横截面排序。

当前判断：market features 低风险。

## 标签与训练切分审计

标签：

```text
Ref($close, -6) / Ref($close, -1) - 1
```

含义是预测信号日之后、从下一交易日附近开始的未来 5 日收益。它作为 Qlib label 输入 LightGBM。

当前训练切分：

```text
train: 2016-05-17 到 2021-12-31
valid: 2022-01-01 到 2023-12-31
test: 2024-01-01 到 2026-05-17
```

代码里：

```text
Alpha158 fit_end_time = train end
DatasetH train/valid/test 按日期 segment
预测只用 segment="test"
```

额外特征拼接后使用：

```text
DropnaLabel
CSZScoreNorm(fields_group="label")
```

当前没有看到标签进入特征、过滤或 TopK 选股的证据。

需要注意：如果后续增加 feature normalization，要确认 fit 只在训练段。

## TopK 回测审计

回测逻辑：

```text
signal_date = 模型预测日期
entry_date = signal_date + 1 个交易日
exit_date = entry_date + 5 个交易日
gross_return = exit_price / entry_price - 1
net_return = gross_return - turnover * cost_bps
```

抽样复算结果：

```text
max_backtest_gross_abs_diff = 9.02e-17
entry_after_signal = True
exit_after_entry = True
```

这说明回测收益计算本身没有发现明显错算。

但有两个水分点：

1. 入场价格是下一交易日 `close`，不是下一交易日 `open` 或 VWAP。
2. 成本只有 10 bps，平均换手约 90.17%，高换手策略对成本非常敏感。

所以回测函数低风险，但交易假设仍需压力测试。

## 为什么收益可能这么高

当前高收益最可能来自这些因素的叠加：

1. 股票池幸存者偏差：只看当前仍能被 Nasdaq public 看到的证券。
2. 当前市值反推历史市值：`current_market_cap * asof_close / latest_close` 隐含当前公司状态。
3. 行业分类当前快照：历史行业变化没有 PIT 化。
4. 测试期适配：2024-2026 对大型科技、AI、部分成长股非常友好。
5. 成本假设偏乐观：高换手下 10 bps 可能偏低。
6. 少数股票或行业贡献：需要后续做集中度复盘。

这不是说模型一定无效。更准确地说：

```text
当前模型可能有信号，但当前收益数字含有明显数据口径水分。
修复股票池和数据口径之前，不能把 67% 年化当成可靠策略能力。
```

## 当前结论

### 已基本排除

- TopK 回测直接用未来收益选股。
- 回测 entry/exit 日期反向。
- market momentum 抽样使用未来价格。
- 标签直接进入 TopK 选股。

### 仍有中风险

- EDGAR companyfacts 是否完全 as-filed。
- FRED 日频 latest 序列不是严格 vintage。
- 当前行业分类不是 PIT。
- 成本和入场价格假设偏乐观。

### 高风险，必须修复后重跑

- `nasdaq_public` 幸存者偏差。
- `approximate_market_cap_asof` 用当前市值和最新价格反推历史市值。

## 修复前不能作为结论的内容

在修复股票池和市值口径之前，以下说法都不能成立：

```text
策略真实年化收益约 67%
策略已经证明有稳定 alpha
默认 no-credit macro interactions 可以进入实盘候选
当前 Nasdaq Top500 frozen 结果是严格 PIT 回测
```

可以成立的是：

```text
在当前学习数据和当前回测假设下，模型能产生较高的历史回测收益。
回测函数和特征时间对齐的局部检查没有发现直接未来函数。
股票池和市值数据口径仍是主要水分来源。
```

## 下一步修复顺序

优先级 1：修复股票池。

```text
使用 Norgate / CRSP / 其他带历史成分、退市股票、历史 shares 的数据源。
不要用 current_market_cap 反推历史市值。
```

优先级 2：压力测试。

```text
entry_lag = 2
entry price = open 或 vwap
cost_bps = 25 / 50 / 100
sector/industry 不进模型，只做事后复盘
```

优先级 3：数据口径升级。

```text
确认价格复权口径
确认 EDGAR as-filed
确认 FRED 日频序列 vintage / revision 风险
接入 PIT 行业分类
```

优先级 4：重新评估策略。

```text
修复数据口径后重跑 baseline、full_interactions、default_no_credit_quality。
如果收益仍高，再讨论模型和特征。
如果收益大幅坍塌，先定位水分来源。
```

## 相关笔记

- [[PIT Safe Backtest]]
- [[Future Information Audit]]
- [[Benchmark And Excess Return Review]]
- [[Macro Interaction Ablation Review]]
- [[Data Source Upgrade Plan]]
