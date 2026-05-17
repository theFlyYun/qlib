# Qlib Quant Learning

这是面向量化交易学习的中文路线文档。主线不讲技术实现细节，而是按“数据口径 -> 标签设计 -> 特征体系 -> 模型训练 -> IC 验证 -> TopK 回测 -> 风控复盘”的顺序递进。

## iOS 阅读方式

推荐使用 GitHub：

1. 把当前分支 push 到 GitHub。
2. 在 iPhone 或 iPad 打开 GitHub App 或 Safari。
3. 进入 `learning/README.md`。
4. 从下面的分层目录开始阅读。

这种方式不占 iCloud 空间，并且文档和代码版本保持一致。

## 分层目录

### 00 Start Here

- [Qlib Quant Learning Index](<00-start-here/Qlib Quant Learning Index.md>)
- [Quant Learning Roadmap](<00-start-here/Quant Learning Roadmap.md>)
- [Quant Resources](<00-start-here/Quant Resources.md>)
- [Qlib Commands](<00-start-here/Qlib Commands.md>)
- [Qlib Source Map](<00-start-here/Qlib Source Map.md>)

### 01 Foundation

- [Week 1 - Quant And Qlib Basics](<01-foundation/Week 1 - Quant And Qlib Basics.md>)
- [Week 2 - Data Dataset And Features](<01-foundation/Week 2 - Data Dataset And Features.md>)

### 02 Signals And Labels

- [Alpha158 And Features](<02-signals-and-labels/Alpha158 And Features.md>)
- [Labels And Future Returns](<02-signals-and-labels/Labels And Future Returns.md>)
- [IC And Rank IC](<02-signals-and-labels/IC And Rank IC.md>)

### 03 Modeling

- [Week 3 - Model Workflow And Experiment Tracking](<03-modeling/Week 3 - Model Workflow And Experiment Tracking.md>)
- [LightGBM Training Notes](<03-modeling/LightGBM Training Notes.md>)
- [Model Validation](<03-modeling/Model Validation.md>)

### 04 Strategy Backtest

- [Week 4 - Strategy Backtest And Custom Extension](<04-strategy-backtest/Week 4 - Strategy Backtest And Custom Extension.md>)
- [TopK Strategy](<04-strategy-backtest/TopK Strategy.md>)
- [Backtest And Costs](<04-strategy-backtest/Backtest And Costs.md>)

### 05 Data Expansion

- [Data Source Upgrade Plan](<05-data-expansion/Data Source Upgrade Plan.md>)
- [Data Scope And Sources](<05-data-expansion/Data Scope And Sources.md>)
- [Financial Valuation Industry Macro News](<05-data-expansion/Financial Valuation Industry Macro News.md>)

### 06 Portfolio Risk

- [Industry Neutralization](<06-portfolio-risk/Industry Neutralization.md>)
- [Portfolio Risk Control](<06-portfolio-risk/Portfolio Risk Control.md>)

### 90 Case Studies

- [2026-05-17 Nasdaq Qlib Model](<90-case-studies/2026-05-17 Nasdaq Qlib Model.md>)
- [Sifang 601126 Case Study](<90-case-studies/Sifang 601126 Case Study.md>)

### 99 Logs

- [Qlib Learning Log](<99-logs/Qlib Learning Log.md>)
- [Stage Completion Records](<99-logs/Stage Completion Records.md>)

## 推进规则

每完成一个阶段，都必须在 [Stage Completion Records](<99-logs/Stage Completion Records.md>) 追加记录，固定包含：

```text
目标
为什么要做
输入数据
核心概念
实验动作
评价指标
结果解读
遗留问题
下一阶段准备
```

## 当前优先级

1. 阶段 A：学习文档层级整理。
2. 阶段 B：配置化研究流水线。
3. 阶段 E：数据口径升级。
4. 阶段 C：标签升级为未来 5 日收益。
5. 阶段 D：股票池清洗与分行业。
6. 阶段 F：TopK 回测与成本后评估。
7. 阶段 G：财报、估值、行业、宏观、新闻特征扩展。
