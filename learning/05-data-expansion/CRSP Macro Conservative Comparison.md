# CRSP Macro Conservative Comparison

## 这一步要回答什么

上一阶段确定了 `crsp_alpha158_10d_conservative_2000_2025` 是当前 CRSP Alpha158-only 的新 baseline。

这一步只问一个问题：

```text
在 10 日保守模型上，FRED/ALFRED 宏观数据有没有带来稳定增量？
```

为了让对照公平，本轮只比较三组：

```text
A. Alpha158-only conservative baseline
B. Alpha158 + raw macro conservative
C. Alpha158 + macro interaction conservative
```

本轮不接 EDGAR，不用行业约束，不使用行业内相对特征。

## 三组实验

| 组别 | 模型输入 | 说明 |
|---|---|---|
| Alpha158-only | Alpha158 | 只使用 CRSP OHLCV 生成的价格成交量特征 |
| direct macro | Alpha158 + 52 个 raw macro | 把宏观状态变量直接拼进模型 |
| macro interactions | Alpha158 + 8 个 macro × market features | 不直接输入 raw macro，只输入宏观状态与股票自身动量/波动率的交互 |

macro interaction 第一版只使用 CRSP 自身行情派生特征：

```text
VIX zscore × 20日动量
VIX change × 20日波动率
10Y yield × 60日动量
10Y yield change × 20日波动率
yield curve inverted × 120日动量
credit spread change × 60日波动率
dollar change × 60日动量
oil change × 20日动量
```

它没有使用：

```text
EDGAR 财报
估值特征
sector flag
industry rank
行业约束
```

## 运行命令

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_macro_10d_conservative_2000_2025.yaml

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_macro_interactions_10d_conservative_2000_2025.yaml

.venv/bin/python -u analysis/nasdaq_top500_score/crsp_macro_conservative_comparison.py
```

核心输出：

```text
analysis/nasdaq_top500_score/runs/crsp_macro_conservative_comparison/crsp_macro_conservative_comparison.csv
analysis/nasdaq_top500_score/runs/crsp_macro_conservative_comparison/crsp_macro_conservative_comparison_summary.yaml
```

## 结果

| 实验 | IC | Rank IC | Best Iter | 年化收益 | 最大回撤 | 年化 Alpha | Beta | 50bps 年化 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Alpha158-only | -0.005289 | 0.006466 | 180 | 33.91% | -15.58% | 10.11% | 1.096 | 15.70% |
| direct macro | -0.016758 | -0.015064 | 7 | 17.89% | -12.22% | 0.52% | 0.898 | -1.21% |
| macro interactions | -0.019318 | 0.006653 | 95 | 21.08% | -14.16% | -1.67% | 1.163 | 3.66% |

特征覆盖：

```text
direct macro: 52 个 macro features，failure=0
macro interactions: 52 个 macro features + 8 个 interaction features，failure=0
```

## 怎么理解

### 1. raw macro 不适合作为当前默认增强

direct macro 的结果：

```text
Rank IC 从 0.006466 降到 -0.015064
年化收益从 33.91% 降到 17.89%
50bps 成本后年化变成 -1.21%
best iteration 只有 7
```

这说明 raw macro 直接输入后，模型很快在验证集上恶化。宏观变量本身是全市场状态变量，同一天所有股票取值相同，不天然提供横截面排序能力。

### 2. macro interactions 比 raw macro 健康，但还不够好

macro interactions 的结果：

```text
Rank IC 0.006653，略高于 Alpha158-only 的 0.006466
best iteration 95，明显比 direct macro 的 7 健康
但年化收益、年化 alpha 和 50bps 压力收益都不如 Alpha158-only
```

这说明“宏观 × 股票自身特征”的方向比 raw macro 更合理，但当前 8 个交互还没有形成足够强的增量。

### 3. Alpha158-only 仍是当前默认主基线

本轮最重要的结论不是“宏观没用”，而是：

```text
在当前 CRSP 10 日保守模型、当前 8 个宏观交互、当前 2024-2025 测试期下，
宏观特征不能替代 Alpha158-only 作为默认主策略。
```

默认主基线继续使用：

```text
crsp_alpha158_10d_conservative_2000_2025
```

macro interaction 暂时保留为研究分支。

## 需要注意的风险

```text
IC 仍然很弱，不能把 Alpha158-only 的收益解释为强稳定 alpha。
direct macro 的 beta 更低、回撤更低，但收益和 Rank IC 明显变差。
macro interactions 的 Rank IC 只略高，提升幅度太小，不足以覆盖收益和 alpha 的下降。
50bps 成本下 macro interactions 仍为正，但明显弱于 Alpha158-only。
本轮没有做 regime 分段，宏观可能只在某些市场状态下有效。
```

## 下一步

建议不要继续扩大 raw macro 特征数量，而是做更克制的两件事：

```text
1. 对 macro interactions 做单组 ablation，确认是哪几个交互拖累。
2. 做 regime 分段复盘，检查宏观交互是否只在 high VIX、利率上行、信用压力等状态下有效。
```

如果 ablation 和 regime 复盘仍不能证明增量，宏观数据应暂时作为复盘维度，而不是默认模型输入。

## 相关笔记

[[CRSP Conservative Model And Horizon Comparison]]
[[CRSP Macro Enhanced Result Review]]
[[Macro Features New Information And Return Degradation]]
[[Macro Regime Review And Interaction Features]]
[[IC And Rank IC]]
