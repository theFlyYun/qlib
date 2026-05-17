# Five Day Future Return Label

## 学习目标

理解为什么要把模型标签从未来 1 日收益改成未来 5 日收益，以及它如何影响模型、IC 和最终 Top10。

## 标签表达式

本阶段新增 5 日收益标签：

```text
Ref($close, -6) / Ref($close, -1) - 1
```

含义：

```text
t 日生成特征和模型信号
t+1 日作为建仓参考点
t+1 到 t+6 之间持有 5 个交易日
标签 = t+6 收盘价 / t+1 收盘价 - 1
```

它和当前 1 日标签的区别：

```text
1 日标签：Ref($close, -2) / Ref($close, -1) - 1
5 日标签：Ref($close, -6) / Ref($close, -1) - 1
```

两者都从 `t+1` 开始算收益，是为了避免假设模型在 `t` 日收盘后还能用 `t` 日收盘价成交。

## 为什么做 5 日标签

1 日收益受噪声影响很大：

```text
隔夜消息
短期资金流
微观结构噪声
临时流动性冲击
随机价格跳动
```

5 日收益把预测目标拉长一点，可能更接近中短期信号：

```text
趋势延续
财报后反应
估值修复
行业轮动
事件影响的逐步定价
```

但 5 日标签也有代价：

```text
调仓频率可能降低
信号反应可能变慢
持仓期间暴露更多市场波动
需要回测中处理持有期重叠和换手
```

## 本次实验口径

除标签外，其余口径保持一致：

```text
股票池：Nasdaq public 当前股票池
窗口：2016-05-17 到 2026-05-17
证券主数据：已启用
流动性过滤：已启用
EDGAR 财报估值特征：已启用
特征：Alpha158 + EDGAR
模型：Qlib LGBModel
分桶：full_10y=4, 5_10y=3, 2_5y=2, lt_2y=1
行业约束：sector<=4, industry<=2
```

运行配置：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d.yaml
```

## 1 日 vs 5 日结果

| 标签 | IC | Rank IC | IC 交易日 | Top10 |
|---|---:|---:|---:|---|
| 1 日 | -0.000519 | 0.001712 | 593 | AAOI, IBRX, LUNR, AXTI, FLEX, SNDK, CELC, QS, CORZ, LQDA |
| 5 日 | 0.036729 | 0.016211 | 589 | IBRX, LUNR, CYTK, LQDA, ONDS, BILI, KTOS, NTNX, TEM, TRI |

Top10 重叠股票：

```text
IBRX
LQDA
LUNR
```

## 如何解读

本次 5 日标签的 IC 和 Rank IC 高于 1 日标签，说明在当前数据、特征和模型口径下，模型分数和未来 5 日收益的横截面相关性更强。

但这还不是策略结论。

原因是：

```text
IC 只是预测分数和未来收益的相关性
还没有考虑交易成本
还没有考虑持有期重叠
还没有做组合净值曲线
还没有看最大回撤和换手
还没有验证不同市场阶段是否稳定
```

所以这一步的结论是：

```text
5 日标签值得进入下一步回测
不能仅凭 IC 判断它已经可交易
```

## 对 Top10 的影响

5 日标签改变了模型学习目标，最终 Top10 也明显变化。

1 日标签更像在找很短期的下一日相对收益，5 日标签则更偏向几天内的持续反应。

本次 5 日 Top10 的行业分布：

```text
Technology：4
Health Care：3
Industrials：2
Consumer Discretionary：1
```

其中 `BILI` 是 ADR/ADS，`TRI` 被当前主数据标记为 `unknown_equity_like`。这提醒我们：证券主数据虽然已经升级，但 ADR/ADS 和 unknown 类型后续仍需要单独复核。

## 下一步

进入第 5 条：TopK 成本后回测。

目标是把“模型分数 + Top10 名单”推进到“组合净值、成本、换手、最大回撤和收益风险比”。

相关笔记：

[[Labels And Future Returns]]
[[IC And Rank IC]]
[[TopK Strategy]]
[[Backtest And Costs]]
[[Stage Completion Records]]
