# Week 4 - Strategy Backtest And Custom Extension

## 学习目标

本周把预测信号接到策略和回测，并设计第一个自己的扩展方向。

完成后你应该能说清楚：

- `TopkDropoutStrategy` 如何把预测信号变成持仓。
- `Executor` 和 `Exchange` 在回测里负责什么。
- 回测指标里的 benchmark return、excess return、cost 大概代表什么。
- 自定义 handler、model、strategy 应该放在哪里，如何接入 YAML。

## 必懂概念

Qlib 回测链路可以先记成：

`Strategy -> TradeDecision/Order -> Executor -> Exchange -> Account/Reports`

最常见的学习路径是先改策略参数，而不是马上写新策略：

- `topk`：持有打分最高的多少只股票。
- `n_drop`：每期调仓时替换多少只。
- `benchmark`：用来比较超额收益的基准。
- `open_cost`、`close_cost`、`min_cost`：交易成本假设。

## 本项目对应源码/配置

- `qlib/strategy/base.py`：策略基类。
- `qlib/contrib/strategy/signal_strategy.py`：`TopkDropoutStrategy`。
- `qlib/backtest/__init__.py`：回测入口。
- `qlib/backtest/executor.py`：执行器。
- `qlib/backtest/exchange.py`：撮合、价格、交易成本。
- `qlib/backtest/decision.py`：交易决策和订单结构。
- `examples/nested_decision_execution/workflow.py`：更复杂的嵌套执行示例。
- `examples/portfolio/config_enhanced_indexing.yaml`：组合优化示例。

## 必跑命令

复制一份配置做实验，不改原 benchmark：

```bash
cp examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml /tmp/qlib_topk_experiment.yaml
```

手动调整 `/tmp/qlib_topk_experiment.yaml` 中的 `topk` 和 `n_drop`，再运行：

```bash
qrun /tmp/qlib_topk_experiment.yaml --experiment_name topk_experiment
```

查看回测产物：

```bash
find mlruns -name 'port_analysis_1day.pkl' -o -name 'indicator_analysis_1day.pkl'
```

## 输出任务

- 设计 3 组 `topk/n_drop` 参数，并记录回测结果变化。
- 阅读 `TopkDropoutStrategy`，用自己的话解释它的调仓逻辑。
- 写一个自定义扩展提案：你想先扩展 handler、model 还是 strategy，为什么。
- 在 [[Qlib Learning Log]] 总结 4 周后你最想继续深入的一个方向。

## 常见问题

- 回测结果不代表真实投资收益；先把它当成研究框架验证工具。
- 交易成本假设会明显影响超额收益，不能忽略。
- 早期扩展建议新建独立扩展包，不要直接改 `qlib/` 核心源码。

## 下一步链接

[[Qlib Source Map]]
[[Qlib Commands]]
[[Qlib Learning Log]]
