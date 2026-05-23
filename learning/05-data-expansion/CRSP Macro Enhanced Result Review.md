# CRSP Macro Enhanced Result Review

## 这一步要回答什么

CRSP 数据源迁移后，我们先跑通了 `Alpha158-only` 基线。结果很清楚：在更严格的 CRSP 月度动态 Top500 股票池、未来 10 个交易日收益标签、每 10 个交易日调仓的口径下，单纯价格成交量特征没有稳定预测力。

因此这一步加入 FRED/ALFRED 宏观特征，回答一个更具体的问题：

```text
宏观状态变量能不能改善 CRSP 10 日收益模型？
改善来自横截面排序能力，还是来自更高市场 beta？
收益能不能经受更高交易成本和更慢入场的压力测试？
```

## 实验口径

输入数据：

```text
CRSP daily: 2000-01-03 到 2025-12-31
股票池: US Common Equity 月度动态市值 Top500
instrument: P{PERMNO}
特征: Alpha158 + FRED/ALFRED macro features
标签: 未来 10 个交易日 CRSP DlyRet 总收益
训练: 2000-01-03 到 2021-12-31
验证: 2022-01-03 到 2023-12-29
测试: 2024-01-02 到 2025-12-31
回测: 每 10 个交易日调仓，信号日后 1 个交易日 open 入场，持有 10 个交易日
```

宏观特征覆盖：

```text
macro_raw_observations: 40,157 行，1998-12-01 到 2025-12-31
macro_asof_observations: 65,390 行，2000-01-03 到 2025-12-31
macro_features: 11,129,378 行，52 个宏观特征列
macro_failures: 0
```

严格数据验收：

```text
data_source: crsp
strict_result_status: strict_pit_pass
survivorship_risk: low
market_cap_proxy_risk: low
pit_industry_status: not_verified
```

注意：当前宏观配置允许部分日频金融序列使用 `latest` 模式，并通过 observation date 后一交易日生效降低未来函数风险；它比直接使用最终历史值更安全，但还不是所有序列都完全 vintage 化的机构级口径。

## 核心结果

| 模型 | Test IC | Test Rank IC | 累计收益 | 年化收益 | 最大回撤 | 年化 alpha | beta |
|---|---:|---:|---:|---:|---:|---:|---:|
| CRSP Alpha158-only | -0.013744 | -0.007421 | 4.61% | 2.30% | -16.69% | -15.20% | 0.981 |
| CRSP Alpha158 + Macro | -0.005139 | 0.007221 | 59.74% | 26.62% | -15.52% | 0.36% | 1.329 |

这说明宏观特征确实改善了两个方面：

```text
Rank IC 从负值变成小幅正值
Top10 回测收益显著高于 Alpha158-only
```

但它也带来一个重要问题：

```text
beta 从 0.981 升到 1.329
年化 alpha 只有 0.36%
```

换句话说，宏观增强版的收益提升很大一部分可能来自更高的市场暴露，而不是非常稳定的纯选股 alpha。它不是坏事，但解释上必须谨慎。

## 压力测试

主口径：

```text
entry_lag_days = 1
entry_price = open
cost_bps = 10
累计收益 = 59.74%
年化收益 = 26.62%
最大回撤 = -15.52%
```

交易成本提高后的变化：

| 口径 | 年化收益 | 累计收益 | 最大回撤 | 年化 alpha |
|---|---:|---:|---:|---:|
| lag1 open 10bps | 26.62% | 59.74% | -15.52% | 0.36% |
| lag1 open 25bps | 18.71% | 40.53% | -17.69% | -6.20% |
| lag1 open 50bps | 6.56% | 13.43% | -21.20% | -17.11% |
| lag1 open 100bps | -14.26% | -26.31% | -33.59% | -38.95% |

结果非常敏感。当前平均换手约 `172%`，所以交易成本是决定策略能不能实盘化的关键变量。只看 10bps 结果会过于乐观。

## 如何理解这次改善

宏观变量本身对同一天所有股票相同，理论上它不能直接告诉模型“今天 A 股票比 B 股票更好”。它更像是在告诉模型：

```text
当前市场环境是什么？
在这种环境下，哪些价格成交量形态可能更有效？
```

所以这次 `Alpha158 + Macro` 的改善，大概率来自模型学到了某种市场状态切换。例如高波动、利率变化、信用利差变化、油价或美元变化时，价格动量、波动率、成交量结构的含义会变化。

但是，因为 raw macro 不是专门为横截面排序设计的，它的 IC 仍然很低。更自然的下一步不是继续堆更多宏观序列，而是做：

```text
宏观状态 × 股票自身特征
```

例如：

```text
VIX × 股票波动率
利率变化 × 估值
信用利差 × 杠杆/现金流
美元变化 × 海外收入暴露或行业 flag
```

这类特征更适合横截面选股。

## 当前结论

可以确认：

```text
CRSP 严格动态股票池已经跑通。
宏观增强比 Alpha158-only 明显更好。
宏观特征让 Rank IC 从负变正。
```

不能直接确认：

```text
当前策略已经有很强纯 alpha。
当前 26.62% 年化收益可以实盘复现。
当前 10bps 成本假设足够保守。
```

更准确的表述是：

```text
在 CRSP 2000-2025 训练、2024-2025 测试口径下，加入第一版宏观状态特征后，Top10 回测表现大幅改善；但收益包含更高 beta 和较强成本敏感性，仍需通过宏观交互、换手控制和更严格成本假设验证。
```

## 下一步

优先做三件事：

1. CRSP macro interaction 实验：把 raw macro 改成 `宏观状态 × 股票差异`，验证是否能提高 alpha 和 Rank IC。
2. 换手控制：引入持仓缓冲、分数稳定性或最低持有期，降低 172% 平均换手。
3. EDGAR 覆盖率评估：先做 `PERMNO -> CIK` 映射和 2000-2025 覆盖率报告，不急着把财报塞进默认模型。

## 相关笔记

[[CRSP Data Source Migration Plan]]
[[FRED ALFRED Macro Features Integration]]
[[Macro Features New Information And Return Degradation]]
[[IC And Rank IC]]
[[Backtest And Costs]]
