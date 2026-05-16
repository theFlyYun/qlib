# Qlib 架构学习笔记

这个 fork 基于 `microsoft/qlib`，用途是学习量化交易平台架构，并在此基础上做自己的扩展。

## 本地仓库信息

- 本地路径：`/Users/file/project/qlib`
- Fork 仓库：`git@github.com:theFlyYun/qlib.git`
- 上游仓库：`https://github.com/microsoft/qlib.git`
- 默认分支：`main`

## 整体理解

Qlib 是一个模块化的量化研究平台。典型流程是：

1. 使用市场数据目录初始化 Qlib。
2. 通过 data handler 和 data loader 构建 dataset。
3. 训练模型，并生成预测信号。
4. 策略模块把预测信号转换成组合权重、交易决策或订单。
5. executor 和 exchange 执行交易决策并完成回测。
6. workflow recorder 保存预测、分析和回测产物。

配置驱动的主入口是 `qrun`，实现位置在 `qlib/cli/run.py`。它读取 YAML 配置，初始化 Qlib，然后把任务交给 `qlib.model.trainer.task_train`。

最重要的扩展机制是 `qlib/utils/mod.py` 里的 `init_instance_by_config`。大多数 YAML 配置都会通过以下字段动态实例化组件：

- `class`
- `module_path`
- `kwargs`

这意味着自定义组件通常不需要直接改 `qlib/` 核心源码。只要你的模块能被 Python import，就可以通过配置文件接入。

## 核心扩展点

### 数据层

重点文件：

- `qlib/data/data.py`
- `qlib/data/dataset/loader.py`
- `qlib/data/dataset/handler.py`
- `qlib/data/dataset/processor.py`
- `qlib/contrib/data/handler.py`

数据链路可以理解为：

`Provider -> DataLoader -> DataHandler/DataHandlerLP -> DatasetH -> Model`

默认可用的数据处理器包括 `qlib/contrib/data/handler.py` 里的 `Alpha158` 和 `Alpha360`。做自己的研究时，优先扩展 data loader、processor 或 handler，尽量不要一开始就改 provider 底层。

如果要接入自己的行情数据，建议先走官方文档中的 CSV/Parquet 到 Qlib `.bin` 的转换流程，也就是 `scripts/dump_bin.py`，然后再通过自定义 handler 或 loader 增加因子和特征。

### 模型层

重点文件：

- `qlib/model/base.py`
- `qlib/model/trainer.py`
- `qlib/contrib/model/`

自定义可训练模型通常实现 `qlib.model.base.Model`，核心接口是：

- `fit(dataset, reweighter=None)`
- `predict(dataset, segment="test")`

可参考的实现包括 `qlib/contrib/model/gbdt.py` 里的 LightGBM 模型，以及 `qlib/contrib/model/` 下的多个 PyTorch 模型。

### Workflow 与实验记录

重点文件：

- `qlib/cli/run.py`
- `qlib/workflow/record_temp.py`
- `qlib/workflow/exp.py`
- `examples/workflow_by_code.py`

Qlib 有两种常用使用方式：

- 配置驱动：`qrun some_workflow.yaml`
- 代码驱动：手动组装 model、dataset、record 和 backtest

建议先读 `examples/workflow_by_code.py`，因为它在一个脚本里串起了模型训练、预测记录、信号分析和组合回测。

### 策略与回测

重点文件：

- `qlib/strategy/base.py`
- `qlib/contrib/strategy/signal_strategy.py`
- `qlib/backtest/__init__.py`
- `qlib/backtest/executor.py`
- `qlib/backtest/exchange.py`
- `qlib/backtest/decision.py`

回测链路可以理解为：

`Strategy -> TradeDecision/Order -> Executor -> Exchange -> Account/Reports`

大多数自定义交易想法可以先从以下基类开始：

- `BaseStrategy`：适合完全自定义交易决策。
- `WeightStrategyBase`：适合目标权重型组合策略。

最简单的具体策略参考是 `TopkDropoutStrategy`。只有当执行过程本身要变化时，比如多层执行、日内执行、拆单或强化学习执行逻辑，才建议自定义 executor。

### 优先阅读的示例

- `examples/workflow_by_code.py`：完整 Python 研究流程
- `examples/benchmarks/`：模型 benchmark 配置
- `examples/highfreq/`：高频数据 handler 与 workflow
- `examples/nested_decision_execution/`：嵌套策略和 executor 设计
- `examples/portfolio/`：增强指数和组合优化

## 推荐扩展目录

为了以后更容易同步 upstream，早期实验尽量不要直接改 `qlib/`。建议创建独立扩展包，例如：

```text
qlibx_ext/
  data/
  models/
  strategies/
  workflows/
configs/
  qlibx_*.yaml
```

然后通过 YAML 的 `module_path` 引用自己的组件，或者利用 `qlib/cli/run.py` 支持的 `sys.path` / `sys.rel_path` 把扩展包加入 import 路径。

适合作为第一批扩展的方向：

1. 基于自有因子的 custom dataset handler。
2. 实现 `Model.fit` 和 `Model.predict` 的 custom model。
3. 继承 `WeightStrategyBase` 的 custom strategy。
4. 一个把自定义数据、模型、策略串起来的 workflow 配置，并接入 `SignalRecord` 和 `PortAnaRecord`。

## 环境与安装备注

- 项目元数据声明支持 Python 3.8 到 3.12。
- upstream README 推荐开发安装方式：`pip install -e .[dev]`
- macOS 上安装 LightGBM 可能需要先安装 OpenMP：`brew install libomp`
- README 里说明官方数据集下载当前临时不可用，上游文档推荐先使用社区数据源。
