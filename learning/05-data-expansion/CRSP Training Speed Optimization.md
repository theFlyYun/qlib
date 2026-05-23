# CRSP Training Speed Optimization

## 背景

当前 CRSP 实验训练慢，主要不是 LightGBM 一轮一轮训练太慢，而是同一批底层数据被反复准备和读取。

最明显的重复成本有三类：

- 每个实验 run 都重新生成 `qlib_source_csv/`，大约 824MB、1600 多个逐股票 CSV。
- 每个实验 run 都重新生成 `qlib_data/`，大约 202MB 的 Qlib bin。
- 回测压力测试有 24 个组合，之前每个组合都会重新扫描全部逐股票 CSV。

所以优化方向不是简单把 LightGBM 线程数拉满，而是先减少重复 I/O 和重复计算。

## 本次工程优化

### 1. 运行耗时画像

主流水线现在会输出：

```text
runtime_profile.csv
runtime_profile.yaml
```

它会记录这些阶段的耗时：

```text
prepare_data
qlib_dump
alpha158_handler_init
market_features
macro_features
macro_interactions
model_fit
model_predict
backtest_main
strategy_comparison
backtest_stress
write_report
```

以后如果训练慢，先看这两个文件，而不是猜。

### 2. CRSP prepared dataset 复用

CRSP 基础数据现在会按配置生成稳定 key，把可复用产物放到：

```text
analysis/nasdaq_top500_score/runs/crsp_prepared_datasets/
```

同一个窗口、同一个动态 Top500、同一个标签周期、同一个价格口径，会复用同一份：

```text
qlib_source_csv/
qlib_data/
universe.csv
membership.csv
security_master.csv
download_failures.csv
```

这意味着 baseline、raw macro、macro interaction 不再各自重复重建底层 CRSP CSV 和 Qlib bin。

### 3. 压力测试行情复用

压力测试仍然保留 24 组：

```text
entry_lag_days: 1 / 2
entry_price: open / vwap_proxy / close
cost_bps: 10 / 25 / 50 / 100
```

但现在同一个价格口径只读取一次行情数据：

```text
open 读取一次
vwap 读取一次
close 读取一次
```

然后复用到不同成本和 entry lag 组合，避免重复扫描全部股票 CSV。

### 4. 特征 artifact cache

CRSP run 默认会缓存这些特征产物：

```text
macro_features.parquet
market_features.parquet
macro_interaction_features.parquet
```

缓存 key 由数据窗口、股票池、宏观配置、市场特征配置和交互配置共同决定。配置没变时复用，配置变了自动生成新缓存。

## 多线程如何使用

当前多线程策略偏保守：

```yaml
runtime:
  run_mode: full
  qlib_dump_workers: 8
  market_feature_workers: 4
  stress_workers: 2
```

含义：

- `qlib_dump_workers`：控制 CSV 转 Qlib bin 的 worker 数。
- `market_feature_workers`：控制逐股票市场特征生成的并行度。
- `stress_workers`：预留给压力测试并行；当前优先通过行情缓存减少重复 I/O。

MacBook 上不要盲目把 worker 开太大。CRSP 实验很多阶段是磁盘 I/O 和大 DataFrame 拼接，线程过多可能抢磁盘和内存，反而变慢。

## 运行模式

新增运行模式：

```yaml
runtime:
  run_mode: full
```

可选值：

```text
full
train_only
backtest_only
stress_only
report_only
```

推荐用法：

- 改模型或特征：用 `full`。
- 只想验证训练能不能跑通：用 `train_only`。
- 已有 `test_predictions.csv`，只想重跑回测：用 `backtest_only`。
- 已有 `test_predictions.csv`，只想重跑压力测试：用 `stress_only`。

## 复盘原则

加速不是为了跳过严谨性，而是为了让同一口径下的实验更可复现。

后续比较结果时仍然要固定：

```text
CRSP 数据窗口
月度动态 Top500 规则
标签周期
LightGBM 参数
回测入场和成本口径
```

如果这些口径变了，即使命中缓存，也不能把结果直接和旧实验混在一起解释。
