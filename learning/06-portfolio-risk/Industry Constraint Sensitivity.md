# Industry Constraint Sensitivity

## 目标

比较不同 `max_sector` 约束强度，判断当前 Top10 组合里每个 sector 最多放几只股票比较合适。

这一步不重新训练模型，不改 Alpha158、EDGAR、LightGBM 或标签。它只复用同一批测试期模型分数，改变最后选股时的行业约束。

## 为什么要做

行业约束不是越紧越好，也不是越松越好：

```text
max_sector=2：更分散，行业风险低，但可能错过强势行业里的高分股票。
max_sector=3：中等约束，在分散和信号利用之间折中。
max_sector=4：更宽松，允许强势行业多拿名额，但可能重新行业扎堆。
```

所以这一步的核心不是找收益最高的单点，而是同时看：

```text
收益
回撤
超额收益
alpha
行业集中度
```

## 实验口径

```text
股票池：as-of 2023-12-31 近似冻结 Nasdaq Top500
数据窗口：2016-05-17 到 2026-05-17
训练期：2016-08-11 到 2021-12-31
验证期：2022-01-03 到 2023-12-29
测试期：2024-01-02 到 2026-05-15
标签：未来 5 个交易日收益
调仓：每 5 个交易日
入场：信号日后 1 个交易日
持有：5 个交易日
成本：单边 10 bps
基准：FRED NASDAQCOM
```

## 对照组

```text
unconstrained_top10：
  不限制 sector / industry，观察自然行业暴露。

sector_cap_2_top10：
  单 sector 最多 2 只，单 industry 最多 2 只。

sector_cap_3_top10：
  单 sector 最多 3 只，单 industry 最多 2 只。

sector_cap_4_top10：
  单 sector 最多 4 只，单 industry 最多 2 只。

sector_momentum_tilt_top10：
  补充观察。以 max_sector=3 为基础，强势 sector 最多可到 4 只。
```

## 本次结果

| 策略 | Max Sector | 累计收益 | 年化收益 | 最大回撤 | 超额累计收益 | 年化 Alpha | Beta | 最大平均 sector 暴露 | Sector HHI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| unconstrained_top10 | N/A | 24.77% | 9.91% | -31.47% | -30.21% | -14.17% | 1.157 | Health Care 34.55% | 0.312 |
| sector_cap_2_top10 | 2 | 62.84% | 23.15% | -27.38% | -8.92% | -3.49% | 1.138 | Health Care 20.11% | 0.176 |
| sector_cap_3_top10 | 3 | 76.79% | 27.55% | -29.58% | -1.11% | 1.87% | 1.072 | Health Care 27.89% | 0.231 |
| sector_cap_4_top10 | 4 | 52.19% | 19.65% | -31.05% | -14.87% | -5.90% | 1.150 | Health Care 30.81% | 0.266 |
| sector_momentum_tilt_top10 | 3 + tilt | 67.91% | 24.78% | -30.71% | -6.08% | -0.86% | 1.100 | Health Care 29.43% | 0.244 |

## 怎么理解

第一，完全不限制行业表现最差。它的 Health Care 平均暴露最高，Sector HHI 也最高，说明模型自然会出现明显行业集中。

第二，`max_sector=2` 最分散，最大回撤最小，行业集中度最低。但它的年化收益和超额收益弱于 `max_sector=3`，说明约束过紧会牺牲一部分高分股票。

第三，`max_sector=3` 本次综合表现最好。它的年化收益最高、超额收益最好、年化 alpha 略微转正，同时行业集中度仍显著低于不限制组合。

第四，`max_sector=4` 已经偏松。它比 `max_sector=3` 收益更低、回撤更深、行业集中度更高，说明放宽到 4 没有带来更好的信号利用。

第五，简单 60 日行业动量增强没有超过固定 `max_sector=3`。它可以作为补充观察，但当前不适合作为默认规则。

## 当前结论

```text
当前默认保留 max_sector=3、max_industry=2。
max_sector=2 更稳但偏保守。
max_sector=4 偏松，不建议作为当前默认。
```

这个结论只适用于当前学习实验口径，不代表真实投资建议。

## 输出文件

```text
strategy_comparison.csv
strategy_comparison_summary.yaml
strategy_comparison/unconstrained_top10/
strategy_comparison/sector_cap_2_top10/
strategy_comparison/sector_cap_3_top10/
strategy_comparison/sector_cap_4_top10/
strategy_comparison/sector_momentum_tilt_top10/
```

每个子目录都有独立的：

```text
backtest_nav.csv
backtest_positions.csv
backtest_summary.yaml
benchmark_summary.yaml
contribution_by_symbol.csv
contribution_by_sector.csv
contribution_by_industry.csv
exposure_by_sector.csv
exposure_by_industry.csv
contribution_summary.yaml
```

## 遗留问题

```text
sector / industry 仍来自当前 Nasdaq public snapshot，不是历史 PIT 分类。
NASDAQCOM 不是总回报复权基准。
没有真实滑点、冲击成本和容量约束。
没有退市股票，仍有幸存者偏差。
max_sector 只控制行业数量，不控制行业权重相对基准的偏离。
```

## 下一步

```text
对 Technology、Health Care、Consumer Discretionary 做 sector-specific 错误复盘。
检查模型在这些行业里排错的股票有什么共同特征。
再决定是改特征、改标签，还是做行业专属模型。
```

相关笔记：

[[Industry Exposure Strategy Comparison]]
[[Within Sector Stock Selection Review]]
[[Industry Neutralization]]
[[Portfolio Risk Control]]
