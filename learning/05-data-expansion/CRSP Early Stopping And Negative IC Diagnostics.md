# CRSP Early Stopping And Negative IC Diagnostics

## 这次诊断要回答什么

CRSP Alpha158-only 模型出现两个现象：

```text
Test IC = -0.013744
Test Rank IC = -0.007421
LightGBM 第 1 轮就早停
```

这不能直接归因于“模型不好”。更合理的排查顺序是：

```text
标签是否算错 -> 价格是否复权错 -> membership 是否提前/滞后 -> 特征是否大面积缺失 -> 模型是否过拟合太快
```

## 诊断命令

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_diagnostics.py \
  --config analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_10d_2000_2025.yaml
```

输出目录：

```text
analysis/nasdaq_top500_score/runs/crsp_alpha158_10d_2000_2025/
```

核心输出：

```text
label_diagnostics.csv
label_distribution_by_year.csv
label_coverage_by_segment.csv
price_adjustment_diagnostics.csv
membership_diagnostics.csv
feature_ic_summary.csv
feature_missing_summary.csv
early_stopping_eval_history.csv
early_stopping_variants.csv
label_horizon_comparison.csv
diagnostic_summary.md
```

## 标签检查

当前标签定义：

```text
label_10d_total_return[t] = prod(1 + DlyRet[t+1 : t+10]) - 1
```

诊断结果：

```text
抽样复算最大误差: 9.8879e-17
全量复算最大误差: 2.2204e-16
非 membership 日期 label 非空行数: 0
```

结论：

```text
标签计算基本正确。
没有把 signal day 当天收益放进 label。
没有发现 membership 外日期错误参与训练。
```

因此，负 IC 和早停暂时不能归因于“10 日收益标签算错”。

## 价格复权检查

当前研究价格逻辑：

```text
用 CRSP DlyRetx 链式构造 adjusted close。
open/high/low 按 adjusted_close / raw_close 同比例缩放。
Alpha158 使用 adjusted OHLCV。
回测使用真实 open / close / vwap_proxy 执行价。
```

诊断结果：

```text
adjusted close 收益 vs DlyRetx 平均绝对误差: 9.5685e-17
最大绝对误差: 3.2085e-14
OHLC violation rate: 0.2507%
```

结论：

```text
adjusted close 与 DlyRetx 对齐，复权主链路通过。
少量 OHLC 异常存在，但比例很低，更像 CRSP 原始日线字段或同日多记录带来的边界问题。
后续可以抽样这些异常，但它不太像当前早停的主因。
```

## Membership 检查

动态股票池逻辑：

```text
每月最后一个交易日按 DlyCap 选 Top500。
membership 从下一个交易日生效。
非 membership 日期 label 置为 NaN。
```

诊断结果：

```text
月度 Top500 月数: 311
每月 Top500 唯一证券数检查: 全部通过
effective_start 晚于 month_end_date: 全部通过
非 membership 日期 label 非空行数: 0
```

结论：

```text
当前没有发现股票池生效日期提前，也没有发现 membership 外样本错误训练。
PIT 股票池主链路通过。
```

## 特征检查

Alpha158 特征诊断结果：

```text
特征数: 158
train 平均缺失率: 0.0028%
valid 平均缺失率: 0.0015%
test 平均缺失率: 0.0009%
常数列: 0
极端值比例: 约 0
```

结论：

```text
特征没有大面积缺失。
没有出现大量常数列。
特征工程没有明显“坏掉”。
```

但单因子 IC 显示，测试期有效特征主要集中在波动率、极值、上下行计数一类：

```text
STD60 / STD10 / STD5 在 test 中 Rank IC 偏正。
MIN60 / RESI30 / IMIN30 在 test 中 Rank IC 偏负。
```

这说明 Alpha158 不是完全无效，但信号很弱，而且可能只在部分特征组上有方向。

## 早停检查

三组模型对照：

| 模型 | best iteration | best valid l2 | final valid l2 |
|---|---:|---:|---:|
| current | 1 | 0.997945 | 0.999029 |
| conservative | 111 | 0.996946 | 0.997009 |
| tiny | 120 | 0.997025 | 0.997025 |

解释：

```text
current 第 1 轮早停，不代表数据一定错。
conservative 和 tiny 能训练到更后面，且 valid l2 略好。
这说明当前 LightGBM 参数对 CRSP 任务偏激进，容易很快过拟合。
```

当前参数特点：

```text
num_leaves = 64
max_depth = 8
learning_rate = 0.05
n_estimators = 300
```

对 CRSP 10 日收益这种高噪声横截面目标来说，这组参数可能太容易拟合训练集噪声。

## 标签周期对照

诊断对比：

| Horizon | train label std | valid label std | best iteration | best valid l2 |
|---:|---:|---:|---:|---:|
| 5 日 | 0.0521 | 0.0517 | 5 | 0.997730 |
| 10 日 | 0.0714 | 0.0713 | 1 | 0.999709 |
| 20 日 | 0.0988 | 0.0986 | 35 | 0.999258 |

解释：

```text
10 日标签不是明显最稳定的目标。
5 日和 20 日都比 10 日更晚早停，valid l2 也略好。
这不代表要立刻换标签，但说明 10 日收益目标需要继续复盘。
```

## 当前判断

这次诊断更支持下面的结论：

```text
CRSP 数据适配主链路基本通过。
负 IC 和早停不是由明显标签错误、复权错误或 membership 未来函数造成的。
主要问题更可能是：Alpha158 对当前 10 日收益目标信号弱，且当前 LightGBM 参数过拟合太快。
```

换句话说：

```text
早停是问题信号，但不是问题本身。
它提示我们当前“特征 + 标签 + 模型复杂度”的组合不合适。
```

## 下一步

优先顺序：

1. 做保守 LightGBM 参数的正式 CRSP baseline 对照。
2. 对 5 日、10 日、20 日标签各跑一版小对照，比较 IC、Rank IC 和回测。
3. 拆分 Alpha158 特征组，先验证波动率/动量/反转哪类特征真正有效。
4. 再做 CRSP macro interactions，而不是直接继续堆 raw macro。

后续 5 / 10 / 20 日保守模型对照已经完成，结论见 [[CRSP Conservative Model And Horizon Comparison]]。

不建议下一步直接做：

```text
继续调 TopK 规则。
继续加复杂组合约束。
直接把 EDGAR 塞进模型。
```

因为当前最核心的问题还在信号层：模型到底能不能稳定排对股票。

## 相关笔记

[[CRSP Data Source Migration Plan]]
[[CRSP Conservative Model And Horizon Comparison]]
[[CRSP Macro Enhanced Result Review]]
[[Alpha158 And Features]]
[[Labels And Future Returns]]
[[IC And Rank IC]]
