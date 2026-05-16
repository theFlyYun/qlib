# Week 1 - Quant And Qlib Basics

## 学习目标

本周只做一件事：建立 Qlib 的全局地图，并跑通一个最小量化研究闭环。

完成后你应该能说清楚：

- 量化研究中的数据、特征、模型、信号、策略、回测各自是什么。
- `qrun` 为什么可以用一个 YAML 文件跑完整流程。
- LightGBM 示例输出的预测、IC、回测指标大概代表什么。

## 必懂概念

量化交易不是“模型预测涨跌”这么窄。一个最小研究流程通常是：

1. 准备行情数据和股票池。
2. 计算因子或特征。
3. 用历史数据训练预测模型。
4. 把模型输出变成股票打分。
5. 用策略把打分变成持仓。
6. 回测策略表现和风险。
7. 记录实验，复盘参数和结果。

Qlib 把这条链路拆成松耦合模块。你第一周不需要理解所有细节，只需要知道每个模块在链条上的位置。

## 本项目对应源码/配置

- `README.md`：项目定位、安装、数据准备和 quick start。
- `examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml`：第一条主线配置。
- `qlib/cli/run.py`：`qrun` 的入口。
- `qlib/model/trainer.py`：训练任务如何执行。
- `qlib/utils/mod.py`：配置如何动态实例化 Python 对象。
- `examples/workflow_by_code.py`：不用 YAML、用代码搭一条相似流程。

更详细的入口见 [[Qlib Source Map]]。

## 必跑命令

```bash
source .venv/bin/activate
```

```bash
qrun examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml
```

```bash
python -m pytest tests/misc/test_utils.py -q
```

如果 `qrun` 成功，你会看到模型训练、预测结果、IC 指标和组合回测指标。实验产物默认写入 `mlruns/`。

## 输出任务

- 用自己的话画出这条链路：`YAML -> qrun -> qlib.init -> task_train -> model/dataset/record -> backtest`。
- 打开 LightGBM YAML，标注这几块：`qlib_init`、`market`、`task.model`、`task.dataset`、`task.record`。
- 在 [[Qlib Learning Log]] 记录第一次跑通的命令、耗时、关键输出和不理解的指标。

## 常见问题

- CatBoost、XGBoost、PyTorch 相关提示可以先忽略；它们是可选模型。
- `Gym has been unmaintained` 是依赖提示，不影响本周 LightGBM 主流程。
- `mlruns/` 是实验记录目录，不要把它当成源码。

## 下一步链接

[[Week 2 - Data Dataset And Features]]
[[Qlib Commands]]
[[Qlib Source Map]]
[[Qlib Learning Log]]
