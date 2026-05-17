# Qlib Quant Learning Index

这套文档用 Qlib 作为练习平台，但学习重点是量化交易本身：市场假设、数据源、信号、策略、回测、组合风控和实盘约束。

你不需要先懂 Qlib 的内部实现。先把一条研究链路想清楚：

`市场问题 -> 数据证据 -> 信号假设 -> 组合规则 -> 回测检验 -> 风险复盘`

## 你要达成的能力

- 能说清一个策略赚的是什么钱：趋势、反转、价值、质量、成长、波动或流动性。
- 能判断一个数据源是否适合做研究：覆盖范围、频率、复权、幸存者偏差、延迟和缺失。
- 能理解因子和机器学习模型都只是“信号生成方式”，不是策略本身。
- 能读懂回测结果中的收益、超额收益、回撤、换手和交易成本。
- 能把每次实验变成可复盘的策略假设，而不是只看收益曲线。

## 分层学习路线

完整路线先看 [[Quant Learning Roadmap]]。当前 `learning/` 已按阶段分层：

1. 基础：[[Week 1 - Quant And Qlib Basics]]、[[Week 2 - Data Dataset And Features]]
2. 信号与标签：[[Alpha158 And Features]]、[[Labels And Future Returns]]、[[IC And Rank IC]]
3. 模型：[[LightGBM Training Notes]]、[[Model Validation]]
4. 策略回测：[[TopK Strategy]]、[[Backtest And Costs]]
5. 数据扩展：[[Data Source Upgrade Plan]]、[[Norgate Data Integration]]、[[SEC EDGAR Fundamentals Integration]]、[[SEC EDGAR Technical Data Flow]]、[[Data Scope And Sources]]、[[Financial Valuation Industry Macro News]]
6. 组合风控：[[Industry Neutralization]]、[[Portfolio Risk Control]]
7. 案例复盘：[[2026-05-17 Nasdaq Qlib Model]]、[[Sifang 601126 Case Study]]

## 快速入口

- 完整路线：[[Quant Learning Roadmap]]
- 今日复盘：[[2026-05-17 Nasdaq Qlib Model]]
- 外部资料：[[Quant Resources]]
- 概念地图：[[Qlib Source Map]]
- 实验命令：[[Qlib Commands]]
- 学习记录：[[Qlib Learning Log]]
- 阶段记录：[[Stage Completion Records]]

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
[[Alpha158 And Features]]
[[Labels And Future Returns]]
[[IC And Rank IC]]
[[LightGBM Training Notes]]
[[Model Validation]]
[[TopK Strategy]]
[[Backtest And Costs]]
[[Data Source Upgrade Plan]]
[[Norgate Data Integration]]
[[SEC EDGAR Fundamentals Integration]]
[[SEC EDGAR Technical Data Flow]]
[[Data Scope And Sources]]
[[Financial Valuation Industry Macro News]]
[[Industry Neutralization]]
[[Portfolio Risk Control]]
[[Quant Learning Roadmap]]
[[2026-05-17 Nasdaq Qlib Model]]
[[Sifang 601126 Case Study]]
[[Quant Resources]]
[[Qlib Commands]]
[[Qlib Source Map]]
[[Qlib Learning Log]]
[[Stage Completion Records]]
