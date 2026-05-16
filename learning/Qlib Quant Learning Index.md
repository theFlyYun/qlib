# Qlib Quant Learning Index

这套文档用 Qlib 作为练习平台，但学习重点是量化交易本身：市场假设、数据源、信号、策略、回测和风险。

你不需要先懂 Qlib 的内部实现。先把一条研究链路想清楚：

`市场问题 -> 数据证据 -> 信号假设 -> 组合规则 -> 回测检验 -> 风险复盘`

## 你要达成的能力

- 能说清一个策略赚的是什么钱：趋势、反转、价值、质量、成长、波动或流动性。
- 能判断一个数据源是否适合做研究：覆盖范围、频率、复权、幸存者偏差、延迟和缺失。
- 能理解因子和机器学习模型都只是“信号生成方式”，不是策略本身。
- 能读懂回测结果中的收益、超额收益、回撤、换手和交易成本。
- 能把每次实验变成可复盘的策略假设，而不是只看收益曲线。

## 4 周学习路线

1. [[Week 1 - Quant And Qlib Basics]]
   - 建立量化交易框架，理解策略从哪里来。
2. [[Week 2 - Data Dataset And Features]]
   - 学数据源、数据质量和因子原理。
3. [[Week 3 - Model Workflow And Experiment Tracking]]
   - 学信号、模型和样本外验证。
4. [[Week 4 - Strategy Backtest And Custom Extension]]
   - 学组合构建、回测解释和风控边界。

## 快速入口

- 概念地图：[[Qlib Source Map]]
- 实验命令：[[Qlib Commands]]
- 学习记录：[[Qlib Learning Log]]

## 当前本地基线

- 已配置本地 `.venv` 环境。
- 已下载简版 CN 日频数据。
- 已跑通 LightGBM + Alpha158 示例。
- 已能生成预测、信号分析和组合回测结果。

这些只是学习工具。真正要关注的是：数据是否可信，信号是否有经济含义，策略是否能承受成本和风险。

## 学习方法

每一周只问四个问题：

1. 这个策略假设是什么？
2. 它依赖什么数据？
3. 它可能因为什么失效？
4. 回测结果支持还是反驳了这个假设？

## 相关笔记

[[Week 1 - Quant And Qlib Basics]]
[[Week 2 - Data Dataset And Features]]
[[Week 3 - Model Workflow And Experiment Tracking]]
[[Week 4 - Strategy Backtest And Custom Extension]]
[[Qlib Commands]]
[[Qlib Source Map]]
[[Qlib Learning Log]]
