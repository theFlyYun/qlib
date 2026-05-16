# Week 3 - Model Workflow And Experiment Tracking

## 学习目标

本周理解模型训练和实验记录。重点不是 LightGBM 的全部参数，而是 Qlib 如何从配置创建模型、训练模型、保存预测和实验产物。

完成后你应该能说清楚：

- `task.model` 如何变成 `LGBModel` 实例。
- `task_train` 做了哪些事。
- `SignalRecord`、`SigAnaRecord`、`PortAnaRecord` 分别记录什么。
- `mlruns/` 里为什么会有实验产物。

## 必懂概念

Qlib 的 workflow 是配置驱动的。YAML 里的对象一般长这样：

```yaml
class: LGBModel
module_path: qlib.contrib.model.gbdt
kwargs:
  loss: mse
```

`qlib/utils/mod.py` 里的 `init_instance_by_config` 会把它变成真实 Python 对象。这个机制是以后自定义模型、数据集、策略的关键。

训练主链路可以先记成：

`qrun -> workflow -> qlib.init -> task_train -> init model/dataset -> fit -> save params -> generate records`

## 本项目对应源码/配置

- `qlib/cli/run.py`：读取 YAML、渲染模板、初始化 Qlib。
- `qlib/model/trainer.py`：`task_train`、`_exe_task`。
- `qlib/model/base.py`：模型基类接口。
- `qlib/contrib/model/gbdt.py`：LightGBM 模型实现。
- `qlib/workflow/record_temp.py`：内置 record 模板。
- `qlib/workflow/exp.py`：实验上下文。
- `examples/workflow_by_code.py`：代码方式对照 YAML 方式。

## 必跑命令

重新跑主 workflow：

```bash
qrun examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml
```

查看实验目录：

```bash
find mlruns -maxdepth 3 -type f | sed -n '1,80p'
```

运行代码式 workflow：

```bash
python examples/workflow_by_code.py
```

## 输出任务

- 对照 `workflow_config_lightgbm_Alpha158.yaml` 和 `examples/workflow_by_code.py`，写出两者如何表达同一流程。
- 在 `qlib/model/trainer.py` 里追 `_exe_task`，记录每一步输入和输出。
- 找到 `SignalRecord` 生成的预测文件名，并解释它为什么能被策略使用。
- 在 [[Qlib Learning Log]] 记录一次实验的模型参数、IC、回测指标和你对结果的解释。

## 常见问题

- `record` 不是日志文本，而是一组会生成实验产物的对象。
- `<MODEL>`、`<DATASET>`、`<PRED>` 是配置中的占位符，用于把上一步结果交给后续 record 或 strategy。
- 先学会读实验产物，再讨论模型是否有效。

## 下一步链接

[[Week 4 - Strategy Backtest And Custom Extension]]
[[Qlib Commands]]
[[Qlib Source Map]]
[[Qlib Learning Log]]
