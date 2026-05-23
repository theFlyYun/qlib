# CRSP Conservative Model And Horizon Comparison

## 这一步要回答什么

上一轮 CRSP Alpha158-only baseline 出现两个问题：

```text
IC / Rank IC 为负
LightGBM 第 1 轮就早停
```

这一步不急着加更多特征，而是先做两个控制实验：

```text
1. 把 LightGBM 参数调得更保守，判断早停是否来自模型过拟合太快。
2. 对比 5 / 10 / 20 日未来收益标签，判断当前预测周期是否合理。
```

核心目标不是追求最高收益，而是判断当前 CRSP 数据、标签、模型是否已经可以作为下一阶段研究基线。

## 做了什么

新增三个保守配置：

```text
crsp_alpha158_5d_conservative_2000_2025.yaml
crsp_alpha158_10d_conservative_2000_2025.yaml
crsp_alpha158_20d_conservative_2000_2025.yaml
```

保守 LightGBM 的主要变化：

```text
num_leaves: 64 -> 16
max_depth: 8 -> 4
learning_rate: 0.05 -> 0.03
lambda_l1 / lambda_l2 加强
min_data_in_leaf: 500
colsample_bytree: 0.75
```

同时把 CRSP 标签改成真正的 horizon-aware：

```text
5 日标签:  label_5d_total_return
10 日标签: label_10d_total_return
20 日标签: label_20d_total_return
```

也就是说，不再用 10 日标签假装比较 5 日或 20 日实验。

## 运行命令

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_5d_conservative_2000_2025.yaml

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_10d_conservative_2000_2025.yaml

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_20d_conservative_2000_2025.yaml
```

诊断命令：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_diagnostics.py \
  --config analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_10d_conservative_2000_2025.yaml
```

横向对比命令：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_signal_model_comparison.py
```

输出目录：

```text
analysis/nasdaq_top500_score/runs/crsp_signal_model_comparison/
```

## 核心结果

| 实验 | Horizon | 参数 | IC | Rank IC | Best Iter | 年化收益 | 最大回撤 | 年化 Alpha | Beta |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 旧 baseline | 10 日 | current | -0.013744 | -0.007421 | 1 | 2.30% | -16.69% | -15.20% | 0.981 |
| 5 日保守 | 5 日 | conservative | -0.012594 | 0.005123 | 33 | 25.41% | -27.63% | -5.15% | 1.594 |
| 10 日保守 | 10 日 | conservative | -0.005289 | 0.006466 | 180 | 33.91% | -15.58% | 10.11% | 1.096 |
| 20 日保守 | 20 日 | conservative | -0.019405 | 0.003580 | 145 | 20.78% | -12.78% | -2.73% | 1.190 |

压力测试中，50bps 成本下年化收益：

| 实验 | 50bps 年化收益 | 相对 10bps 年化下降 |
|---|---:|---:|
| 旧 baseline | -12.54% | -14.84% |
| 5 日保守 | -10.38% | -35.79% |
| 10 日保守 | 15.70% | -18.21% |
| 20 日保守 | 10.96% | -9.82% |

## 怎么理解

### 1. 早停问题明显改善

旧 baseline 第 1 轮就早停，说明原参数对 CRSP 任务太激进。

保守模型后：

```text
5 日:  best_iteration = 33
10 日: best_iteration = 180
20 日: best_iteration = 145
```

这说明模型不再只是第一轮后立刻过拟合，参数已经更适合高噪声横截面收益任务。

### 2. 10 日保守模型暂时最好

10 日保守模型同时具备：

```text
最高 Rank IC
最高年化收益
最高年化 alpha
较低 beta
成本压力下仍为正收益
最大回撤没有显著恶化
```

因此，下一阶段可以把 `crsp_alpha158_10d_conservative_2000_2025` 作为 CRSP Alpha158-only 新基线。

### 3. IC 仍然为负，不能过度乐观

10 日保守模型的 Rank IC 转正，但 IC 仍为负：

```text
IC = -0.005289
Rank IC = 0.006466
```

这代表：

```text
模型整体线性相关仍弱。
排序能力只有很小的正优势。
TopK 收益改善不等于模型已经有强而稳定的全市场预测力。
```

更准确的理解是：模型可能在排序前排股票时有一点有效信息，但这种信息很弱，容易受测试期、少数股票、行业暴露和交易成本影响。

### 4. 5 日太容易受换手和噪声影响

5 日保守模型年化收益不错，但：

```text
最大回撤更深
beta 更高
50bps 成本后年化转负
```

这说明 5 日策略对交易成本和短期噪声更敏感，不适合作为当前主基线。

### 5. 20 日更稳但收益不足

20 日保守模型最大回撤较小，50bps 压力下仍为正，但：

```text
IC 更负
Rank IC 更低
年化 alpha 为负
```

它更像“低频稳一点”的观察组，而不是当前最优主线。

## 数据诊断结论

三组保守实验的诊断都支持：

```text
标签复算误差接近 0
adjusted close 与 DlyRetx 对齐
非 membership 日期 label 非空行数为 0
Alpha158 没有大面积缺失或常数列
```

以 10 日保守模型为例：

```text
Label full max absolute diff: 2.2204e-16
Adjusted close vs DlyRetx max diff: 3.2085e-14
OHLC violation rate: 0.2507%
Non-member non-null label rows: 0
```

所以目前更像是“信号弱 + 模型参数需要保守”，不是“CRSP 数据适配主链路坏了”。

## 当前结论

本阶段结论：

```text
CRSP 数据适配主链路基本通过。
旧 baseline 的第 1 轮早停主要是模型参数过激进。
10 日保守 LightGBM 是当前最合理的 Alpha158-only 基线。
但 IC 仍弱，不能把高回测收益当成最终策略结论。
```

下一步应该在 10 日保守基线上继续做：

```text
1. CRSP + FRED/ALFRED macro conservative 对照。
2. CRSP macro interaction conservative 对照。
3. 成本、换手、行业暴露和少数股票贡献复盘。
4. 如果 Rank IC 仍很低，再考虑 EDGAR、行业、质量、估值和动量改造。
```

## 相关文件

```text
analysis/nasdaq_top500_score/data_sources/crsp.py
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/crsp_diagnostics.py
analysis/nasdaq_top500_score/crsp_signal_model_comparison.py
analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_5d_conservative_2000_2025.yaml
analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_10d_conservative_2000_2025.yaml
analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_20d_conservative_2000_2025.yaml
```

## 相关笔记

[[CRSP Data Source Migration Plan]]
[[CRSP Early Stopping And Negative IC Diagnostics]]
[[CRSP Macro Enhanced Result Review]]
[[Backtest Stress Test Review]]
[[IC And Rank IC]]
