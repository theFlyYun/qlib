# Experiment Reproducibility And Prediction Cache

## 为什么先做这一步

5.7C 错误复盘发现一个问题：完整运行会重新训练一次 LightGBM。即使数据、标签和参数大体不变，模型分数也可能因为随机抽样、特征采样、线程调度等细节轻微变化。

如果我们下一步要判断“行业内相对特征是否改善了模型”，或者“短历史股票惩罚是否有效”，就必须先把实验口径固定住。

## 两种运行模式

### 1. 重新训练

适用场景：

```text
改了特征
改了标签
改了模型参数
改了训练/验证/测试切分
需要生成新的 test_predictions.csv
```

配置：

```yaml
training:
  seed: 20260519
  deterministic: true
  reuse_test_predictions: false
```

含义：

```text
seed：固定 Python / NumPy / LightGBM 随机性
deterministic：声明本次实验要求可复现
reuse_test_predictions=false：重新训练模型并覆盖 test_predictions.csv
```

### 2. 复用预测分数

适用场景：

```text
只改 TopK 选股规则
只改行业约束
只做行业内复盘
只做错误样本解释
不希望模型重新训练
```

配置：

```yaml
training:
  seed: 20260519
  deterministic: true
  reuse_test_predictions: true
```

含义：

```text
直接读取当前 run 目录下已有的 test_predictions.csv
跳过 LightGBM 训练和预测
后续 TopK、回测、行业复盘继续使用同一批 score
```

## 为什么不能每次都重训

如果每次复盘都重训，那么结果变化可能来自两种来源：

```text
模型本身的随机波动
新规则或新特征真的有效
```

这会让结论变得不干净。比如 `max_sector=3` 比 `max_sector=2` 好，到底是行业约束更合适，还是这次重训出来的 score 更幸运？复用 `test_predictions.csv` 可以把这个问题切开。

## 当前项目如何落地

当前 frozen 配置已经加入：

```yaml
model:
  kwargs:
    seed: 20260519
    bagging_seed: 20260519
    feature_fraction_seed: 20260519
    data_random_seed: 20260519
    drop_seed: 20260519
    deterministic: true
    force_col_wise: true

training:
  seed: 20260519
  deterministic: true
  reuse_test_predictions: false
```

每次报告会记录：

```text
预测分数来源：trained 或 cached_test_predictions
训练随机种子
是否复用 test_predictions.csv
```

## 后续实验规则

后续我会按这个规则推进：

```text
改模型输入：重新训练
改标签：重新训练
改 LightGBM 参数：重新训练
只改 TopK 规则：复用预测分数
只做复盘解释：复用预测分数
```

这能保证每个阶段的变化都尽量只有一个原因。

## 和下一步的关系

下一步要加入 size / liquidity / momentum 的行业内相对特征。那属于“改模型输入”，所以应该重新训练，但因为 seed 已固定，重训结果更容易复现。

等这个新模型输出新的 `test_predictions.csv` 后，再做短历史惩罚或行业约束参数对比时，就应该设置：

```yaml
training:
  reuse_test_predictions: true
```

相关笔记：

[[Model Validation]]
[[LightGBM Training Notes]]
[[Sector Specific Error Review]]
[[Industry Constraint Sensitivity]]
