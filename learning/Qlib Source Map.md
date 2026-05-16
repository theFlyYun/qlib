# Qlib Source Map

这份源码地图只保留学习 Qlib 量化流程最关键的入口。读源码时不要从目录树顶层乱翻，按主链路追。

## 主链路

`qrun -> qlib.init -> task_train -> init_instance_by_config -> model.fit -> record.generate -> backtest`

## CLI 与配置

- `qlib/cli/run.py`
  - `workflow(config_path, experiment_name, uri_folder)` 是配置驱动入口。
  - 负责读取 YAML、处理 `BASE_CONFIG_PATH`、设置 `sys.path`、初始化 Qlib、调用 `task_train`。
- `qlib/utils/mod.py`
  - `init_instance_by_config` 是扩展机制核心。
  - YAML 的 `class`、`module_path`、`kwargs` 会通过它变成真实对象。

## 初始化与配置

- `qlib/__init__.py`
  - `qlib.init(...)` 会设置全局配置、清缓存、注册数据路径。
- `qlib/config.py`
  - 全局配置对象和默认 client/server 配置。

## 数据层

- `qlib/data/data.py`
  - 数据 provider 入口。
- `qlib/data/dataset/loader.py`
  - 加载字段和表达式。
- `qlib/data/dataset/handler.py`
  - handler 组织特征、标签、处理器和切片。
- `qlib/data/dataset/processor.py`
  - 缺失处理、标准化等 processor。
- `qlib/contrib/data/handler.py`
  - `Alpha158`、`Alpha360` 等常用 handler。

## 模型与训练

- `qlib/model/base.py`
  - 自定义模型需要对齐 `fit(dataset, reweighter=None)` 和 `predict(dataset, segment="test")`。
- `qlib/model/trainer.py`
  - `task_train` 和 `_exe_task` 串起 model、dataset、record。
- `qlib/contrib/model/gbdt.py`
  - LightGBM 模型实现，是第一阶段最值得读的模型。

## Workflow 与实验记录

- `qlib/workflow/exp.py`
  - 实验上下文。
- `qlib/workflow/recorder.py`
  - 实验产物保存。
- `qlib/workflow/record_temp.py`
  - `SignalRecord`、`SigAnaRecord`、`PortAnaRecord`。

## 策略与回测

- `qlib/strategy/base.py`
  - 策略基类。
- `qlib/contrib/strategy/signal_strategy.py`
  - `TopkDropoutStrategy`。
- `qlib/backtest/executor.py`
  - 回测执行器。
- `qlib/backtest/exchange.py`
  - 交易价格、限制、成本等市场模拟。
- `qlib/backtest/decision.py`
  - 交易决策和订单对象。

## 示例优先级

1. `examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml`
2. `examples/workflow_by_code.py`
3. `examples/highfreq/workflow.py`
4. `examples/nested_decision_execution/workflow.py`
5. `examples/portfolio/config_enhanced_indexing.yaml`

## 相关笔记

[[Qlib Quant Learning Index]]
[[Qlib Commands]]
[[Week 1 - Quant And Qlib Basics]]
[[Week 2 - Data Dataset And Features]]
[[Week 3 - Model Workflow And Experiment Tracking]]
[[Week 4 - Strategy Backtest And Custom Extension]]
