# Industry Exposure Strategy Comparison

## 目标

验证当前模型到底是在“选个股”，还是在“无意识押行业”。

这一步不重新训练模型，不改 Alpha158、EDGAR 或 LightGBM。我们只复用同一批测试期预测分数，改变最后 Top10 的选股规则。

## 三组策略

```text
A. unconstrained_top10
   原始 Top10，不限制行业，观察模型自然行业暴露。

B. sector_capped_top10
   行业约束 Top10，单 sector 最多 3 只，单 industry 最多 2 只。

C. sector_momentum_tilt_top10
   行业增强 Top10，先看信号日前 60 个交易日的 sector 等权收益。
   强势 sector 可以比普通 sector 多拿 1 个名额，但单 sector 最多 4 只。
```

## 为什么不是简单禁止行业暴露

行业暴露本身不是坏事。强势行业当然可以买。

问题在于我们要知道收益来自哪里：

```text
如果收益来自行业整体上涨，这是行业配置能力。
如果收益来自同业中选出更好的股票，这是个股选择能力。
如果两者都有，就应该把策略拆成“行业配置 + 行业内选股”。
```

行业对照实验的目的不是消灭行业暴露，而是把隐含押注变成可解释、可验证、可控制的策略模块。

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

## 本次结果

| 策略 | 累计收益 | 年化收益 | 最大回撤 | 超额累计收益 | 年化 Alpha | Beta | 最大平均 sector 暴露 | Sector HHI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| unconstrained_top10 | 24.77% | 9.91% | -31.47% | -30.21% | -14.17% | 1.157 | Health Care 34.55% | 0.312 |
| sector_capped_top10 | 76.79% | 27.55% | -29.58% | -1.11% | 1.87% | 1.072 | Health Care 27.89% | 0.231 |
| sector_momentum_tilt_top10 | 67.91% | 24.78% | -30.71% | -6.08% | -0.86% | 1.100 | Health Care 29.43% | 0.244 |

## 怎么理解

第一，原始 Top10 的行业集中度更高。Health Care 平均暴露达到 34.55%，某些周期里单一 sector 最高能到 80%。

第二，行业约束没有伤害收益，反而提升了收益并降低了回撤。年化收益从 9.91% 提升到 27.55%，最大回撤从 -31.47% 收窄到 -29.58%。

第三，行业增强这轮弱于普通行业约束。它仍然好于原始 Top10，但简单 60 日行业动量并没有比固定行业上限更稳。

第四，行业约束的 alpha 接近打平并略微转正，但幅度很小，还不能说模型已经有稳定超额收益。

## 当前结论

本次结果更支持这个判断：

```text
当前模型不是越自由越好。
适度限制行业集中度后，组合表现更稳。
简单行业趋势增强证据不够强。
```

也就是说，下一步不应该把行业约束删掉，而应该继续保留行业风险控制，再研究：

```text
行业内选股能力，见 [[Within Sector Stock Selection Review]]
行业权重上限
更稳定的行业趋势信号
与基准的超额收益
```

## 输出文件

```text
strategy_comparison.csv
strategy_comparison_summary.yaml
strategy_comparison/unconstrained_top10/
strategy_comparison/sector_capped_top10/
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
行业分类仍来自当前 Nasdaq public snapshot，不是历史 PIT 行业分类
NASDAQCOM 基准不是总回报复权口径
没有真实滑点、冲击成本和容量约束
没有退市股票，仍有幸存者偏差
行业动量只用 60 日等权收益，信号还很粗糙
```

## 下一步

优先做两个方向：

```text
1. 行业内选股复盘：每个 sector 内部单独看 score 排名和后续收益。
2. 行业权重规则升级：比较 max_sector=2/3/4、行业等权和行业动量权重。
```

相关笔记：

[[Industry Neutralization]]
[[Portfolio Risk Control]]
[[Position Contribution And Exposure Review]]
[[Benchmark And Excess Return Review]]
[[TopK Cost Backtest]]
