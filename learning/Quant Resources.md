# Quant Resources

这些资料用于补足 Qlib 之外的量化知识。先按主题读，不要一上来追求读完所有书。

## Qlib 与平台型研究

- Qlib 官方文档：<https://qlib.readthedocs.io/en/stable/introduction/introduction.html>
- Qlib Workflow 文档：<https://qlib.readthedocs.io/en/stable/component/workflow.html>
- Qlib 论文：<https://arxiv.org/abs/2009.11189>

阅读目的：

- 理解 Qlib 是一个 AI-oriented quantitative investment platform。
- 理解 Qlib 的工作流覆盖数据、模型、评估和实验记录。
- 把 Qlib 当成练习平台，而不是量化知识的全部来源。

## 金融机器学习

- Marcos Lopez de Prado, `Advances in Financial Machine Learning`
- O'Reilly 页面：<https://www.oreilly.com/library/view/advances-in-financial/9781119482086/>

阅读目的：

- 理解金融数据不是 IID。
- 理解标签、过拟合、数据泄露、purged cross-validation。
- 建立“先验证，再相信模型”的习惯。

建议读法：

- 先读数据结构、标签、交叉验证、回测相关章节。
- 暂时跳过过深的数学推导。

## 主动组合管理

- Richard Grinold and Ronald Kahn, `Active Portfolio Management`
- 主题关键词：information ratio、active risk、breadth、portfolio construction、transaction costs。

阅读目的：

- 理解策略不是只选股，还要控制组合风险。
- 理解信息比率和独立下注数的重要性。
- 建立“信号 -> 组合 -> 风险预算”的框架。

## 因子投资与股票策略

建议主题：

- Value、Momentum、Quality、Low Volatility、Size、Liquidity。
- Barra 风格因子。
- Fama-French 因子模型。

阅读目的：

- 给每个因子找到经济解释。
- 不把因子当成孤立公式。
- 学会检查因子在不同市场阶段的稳定性。

## 市场微观结构

建议主题：

- Bid-ask spread。
- Market order 和 limit order。
- 滑点、冲击成本、成交量约束。
- 高频数据和日频数据的区别。

阅读目的：

- 理解为什么回测收益会被交易成本吃掉。
- 理解策略容量和流动性限制。
- 不把回测成交价当成真实成交价。

## 建议优先级

1. 先跑 Qlib 示例，建立研究闭环。
2. 学数据质量和回测偏差。
3. 学经典因子和组合管理。
4. 再进入金融机器学习。
5. 最后考虑实盘执行和监控。

## 相关笔记

[[Quant Learning Roadmap]]
[[Qlib Quant Learning Index]]
[[Week 2 - Data Dataset And Features]]
[[Week 3 - Model Workflow And Experiment Tracking]]
