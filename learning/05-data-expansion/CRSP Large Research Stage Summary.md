# CRSP Large Research Stage Summary

## 阶段定位

这一阶段的目标是把项目从早期 Nasdaq public 学习数据，升级到更严谨的 CRSP 本地日级数据源，并验证一条看起来完整的量化研究链路：

```text
CRSP 动态股票池 -> Alpha158 -> LightGBM -> EDGAR / macro 扩展 -> rolling window -> TopK 回测 -> 风险复盘
```

这个阶段的价值不是得到一个可以直接实盘的策略，而是系统地暴露了一个问题：

```text
大型高维机器学习研究平台，不等于个人小资金可执行策略。
```

## 已完成的研究链路

### 1. 数据源升级

早期 Nasdaq public 数据只能做学习演示，存在当前股票池、幸存者偏差、当前市值反推历史市值等问题。后来迁移到 CRSP 本地日级数据，研究窗口调整为：

```text
2010-01-01 ~ 2025-12-31
```

默认股票池改成：

```text
CRSP US Common Equity monthly dynamic Top500
```

这一步显著提升了数据口径：

- 用 `PERMNO` 做稳定 instrument，避免 ticker 变更影响回测。
- 用月度动态市值 Top500，避免用当前成分回测历史。
- 用 CRSP 日收益构造标签和研究价格。
- 用 PIT 行业映射恢复 SIC2 / SIC4 行业口径。

### 2. 模型主干

主干模型是：

```text
Alpha158 -> LightGBM -> 未来 10 日收益标签
```

训练切分固定为：

```text
train: 2010-01-01 ~ 2021-12-31
valid: 2022-01-01 ~ 2023-12-31
test:  2024-01-01 ~ 2025-12-31
```

后续又做了 rolling window：

| 测试窗口 | 训练窗口 | 验证窗口 |
|---|---|---|
| 2018-2019 | 2010-2015 | 2016-2017 |
| 2020-2021 | 2010-2017 | 2018-2019 |
| 2022-2023 | 2010-2019 | 2020-2021 |
| 2024-2025 | 2010-2021 | 2022-2023 |

### 3. EDGAR 财报扩展

EDGAR 第一版接入了较多财报、估值、披露状态字段，但效果不稳定。经过覆盖率审计、字段清洗、字段有效性分析后，收缩为 `mini-core`：

```text
operating_margin
free_cash_flow_ttm
net_margin
fcf_margin
operating_cash_flow_ttm
```

结论：

- EDGAR mini-core 在部分窗口有边际价值。
- 它在 `3/4` 个 rolling 窗口 alpha 高于 Alpha158-only。
- 但它不能稳定替代主线，因为 2022-2023 仍然亏损，2024-2025 的 alpha 也低于 Alpha158-only。

### 4. FRED / ALFRED 宏观扩展

宏观数据接入重点是 PIT 和 vintage：

- 利率：`DGS10`、`DGS2`、`FEDFUNDS`
- 曲线：`T10Y2Y`
- 通胀：`CPIAUCSL`
- 就业：`UNRATE`
- 增长：`INDPRO`
- 信用：`BAA10Y`
- 风险偏好：`VIXCLS`
- 商品和美元：`DCOILWTICO`、`DTWEXBGS`

做过 raw macro、macro interaction、ablation 和 regime 复盘。结论是：

```text
宏观数据更适合作为市场状态解释和风险过滤维度，不适合作为当前小资金选股主线的默认输入。
```

原因是宏观变量对同一天所有股票基本相同，只有通过交互特征才可能影响横截面排序，而交互特征又显著增加变量数量和解释难度。

### 5. 行业路径恢复

CRSP 行业映射修复后，使用：

```text
sector = SIC2
industry = SIC4
```

行业约束做过：

- `global_top10`
- `sector_cap_2_top10`
- `sector_cap_3_top10`
- `sector_cap_4_top10`

行业约束在部分阶段有效，尤其能降低行业集中风险。但它不能解决根本问题：当模型信号很弱时，约束只能控制风险，不能创造稳定 alpha。

### 6. 滚动窗口验证

这是本阶段最重要的结论来源。

| 模型线 | rolling 结论 |
|---|---|
| Alpha158-only + sector_cap_2 | 只有 `1/4` 个窗口 alpha 为正，不稳定 |
| EDGAR mini-core + sector_cap_2 | `3/4` 个窗口优于 Alpha158-only，但仍不能替代 |

2022-2023 是共同失效窗口：

| 线 | Test IC | Rank IC | sector_cap_2 alpha | 解读 |
|---|---:|---:|---:|---|
| Alpha158-only | 0.024746 | 0.013603 | -15.05% | 排序略正，但 Top10 亏损 |
| EDGAR mini-core | 0.032535 | 0.017902 | -11.15% | 排序改善，但组合仍失败 |

这说明问题不是“模型完全没信号”，而是：

```text
弱正 IC 不足以支撑高度集中的 Top10 组合。
```

### 7. 组合构建与风险过滤修复

CRSP-19 复用了 rolling run，不重训模型，测试了：

- Top10 / Top20 / Top30 / Top50
- equal weight / score weight / inverse vol weight / beta adjusted weight
- soft / hard 单票风险过滤
- beta cap / beta neutral / beta penalty

关键结果：

| 方案 | 平均 alpha | 正 alpha 窗口 | 平均 beta | 最差回撤 | 50bps 表现 |
|---|---:|---:|---:|---:|---:|
| EDGAR Top30 等权 | 5.64% | 4/4 | 1.20 | -31.71% | 年化 1.41% |
| EDGAR Top10 inverse vol | 6.12% | 3/4 | 1.35 | -36.73% | 50bps 正 alpha 0/4 |
| EDGAR Top30 soft risk filter | 2.45% | 3/4 | 0.89 | -30.79% | 年化 -4.08% |
| EDGAR Top10 beta neutral | 3.74% | 3/4 | 1.22 | -36.76% | 年化 -2.32% |

最终决策：

```text
status: no_portfolio_rule_passed
recommended_next_stage: 标签重设计
```

## 当前问题总结

### 问题 1：变量太多

Alpha158 本身有 158 个价格成交量特征，再加入 EDGAR、macro、industry、interaction 之后，变量很快变成一个高维系统。

这带来三个问题：

- 训练慢。
- 解释难。
- 很难知道每个变量是否真的有用。

### 问题 2：效果不稳定

当前模型不是完全无效，而是信号太弱：

```text
IC / Rank IC 有时略正，但 TopK 收益不稳定。
```

这对个人实盘很危险，因为小资金通常只能持有 5-10 只股票，无法依赖 Top30 / Top50 去摊薄单票错误。

### 问题 3：策略形式不适合小资金

Top30 / Top50 能降低风险，但不适合当前目标：

- 资金分散太细。
- 执行管理复杂。
- 很难对每只持仓做人工复盘。
- 不适合建立交易直觉。

### 问题 4：大型模型掩盖了投资假设

当前研究平台能回答“模型结果怎么样”，但很难回答：

```text
为什么买这只股票？
这只股票赚的是什么钱？
这次亏损是质量、动量、估值、行业，还是市场 beta 问题？
```

这不符合个人研究者从学习走向实盘的需求。

## 阶段性结论

这一阶段应该到此收束。它给出了清晰结论：

```text
继续沿着 Alpha158 + EDGAR + macro + interaction 的大型 ML 路线推进，不符合当前个人小资金实盘目标。
```

保留价值：

- CRSP 数据仓和动态股票池能力。
- EDGAR mini-core 的财报字段经验。
- FRED / ALFRED 的 PIT 宏观处理经验。
- rolling window、压力测试和失败复盘方法。
- 行业约束、beta 控制、风险过滤的评估框架。

需要放弃或降级：

- Alpha158 作为默认主线。
- 大量宏观交互特征。
- 大规模 EDGAR 字段扩展。
- Top30 / Top50 作为个人实盘组合。
- 继续通过堆变量解决不稳定问题。

## 下一阶段方向

新阶段应切换为：

```text
Personal Quant v1：小资金可解释选股系统
```

核心原则：

```text
少变量
少持仓
可解释
可复盘
可手工执行
```

这不是退步，而是把研究目标从“建一个完整量化平台”换成“建一个个人能长期执行的策略系统”。

## 相关笔记

[[Personal Quant V1 Direction]]
[[CRSP Data Source Migration Plan]]
[[CRSP Rolling Window Validation]]
[[CRSP Rolling Window Failure Review]]
[[CRSP 2022 2023 Failure Deep Dive]]
[[CRSP Portfolio Construction And Risk Filter Repair]]
[[CRSP EDGAR Coverage Cleaning And Ablation]]
[[CRSP Macro Interaction Ablation And Regime Review]]
