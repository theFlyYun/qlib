# Backtest Stress Test Review

这篇笔记记录回测交易假设压力测试：不重新训练模型，只复用同一份 `test_predictions.csv`，改变入场延迟、入场价格和交易成本，观察收益是否对交易假设过度敏感。

## 为什么要做

当前回测使用：

```text
signal date 后 1 个交易日入场
入场/退出价格使用 close
交易成本 10 bps
平均换手约 90%
```

这套假设不一定错，但对高换手 TopK 策略偏友好。压力测试要回答：

```text
如果晚一天入场，收益是否坍塌？
如果用 open 或 vwap_proxy 入场，收益是否明显变化？
如果成本提高到 50/100 bps，策略是否还成立？
```

## 新增输出

```text
backtest_stress_matrix.csv
backtest_stress_summary.yaml
backtest_stress/
```

矩阵默认覆盖：

```text
entry_lag_days: 1 / 2
entry_price: close / open / vwap_proxy
cost_bps: 10 / 25 / 50 / 100
```

其中 `vwap_proxy` 对应项目里的 `vwap` 字段。当前数据源没有真实成交 VWAP，所以这个值通常是 OHLC 均值近似。

## 如何解释

如果 `entry_lag=2` 后收益大幅下降，说明模型可能更依赖短期价格延续或回测入场时机。

如果 `cost_bps >= 50` 后收益大幅下降，说明高收益可能主要来自高换手下的乐观成本假设。

如果 open / close / vwap_proxy 差异很大，说明执行价格口径对结论敏感，后续要使用更真实的开盘价、成交量加权价格或滑点模型。

## 当前工程口径

压力测试复用同一份预测分数：

```text
不重训模型
不改变 Alpha158
不改变 EDGAR / macro features
不改变标签
只改变 backtest.entry_lag_days / backtest.price / backtest.cost_bps
```

这样可以把“模型预测力”和“交易假设水分”拆开。

## 相关笔记

- [[Future Leakage And Backtest Water Audit]]
- [[Strict PIT Data Repair Plan]]
- [[PIT Safe Backtest]]
- [[Backtest And Costs]]
