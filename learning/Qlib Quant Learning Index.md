# Qlib Quant Learning Index

这是用 Qlib 学习量化交易的主入口。目标不是背 API，而是逐步建立一条完整研究链路：

`数据 -> 特征 -> 模型 -> 预测信号 -> 策略 -> 回测 -> 复盘 -> 自定义扩展`

## 你要达成的能力

- 能解释一个 Qlib workflow 从 YAML 到回测结果的全过程。
- 能读懂 `Alpha158`、`DatasetH`、`LGBModel`、`SignalRecord`、`PortAnaRecord` 分别做什么。
- 能修改一个 benchmark 配置，观察模型和策略参数变化。
- 能写出自己的 handler、model 或 strategy，并通过配置接入 Qlib。
- 能把每次实验记录成可复盘的学习日志。

## 4 周学习路线

1. [[Week 1 - Quant And Qlib Basics]]
   - 先跑通项目，理解量化研究最小闭环。
2. [[Week 2 - Data Dataset And Features]]
   - 把数据层、特征、handler、dataset 关系讲清楚。
3. [[Week 3 - Model Workflow And Experiment Tracking]]
   - 理解模型训练、预测记录和 MLflow 实验产物。
4. [[Week 4 - Strategy Backtest And Custom Extension]]
   - 读策略和回测链路，完成第一个自定义扩展设计。

## 快速入口

- 常用命令：[[Qlib Commands]]
- 源码地图：[[Qlib Source Map]]
- 学习记录：[[Qlib Learning Log]]

## 当前本地基线

- 项目 fork：`theFlyYun/qlib`
- 上游项目：`microsoft/qlib`
- 本地环境：`.venv`
- 已验证数据：简版 CN 1d 数据
- 已跑通示例：`examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml`
- 已跑通烟测：`python -m pytest tests/misc/test_utils.py -q`

## 学习方法

每一周都按同一节奏推进：

1. 先跑命令，看到真实输出。
2. 再读配置，理解对象如何被实例化。
3. 再读源码，追一条主链路。
4. 最后写一段学习日志，记录你能解释什么、还卡在哪里。

## 相关笔记

[[Week 1 - Quant And Qlib Basics]]
[[Week 2 - Data Dataset And Features]]
[[Week 3 - Model Workflow And Experiment Tracking]]
[[Week 4 - Strategy Backtest And Custom Extension]]
[[Qlib Commands]]
[[Qlib Source Map]]
[[Qlib Learning Log]]
