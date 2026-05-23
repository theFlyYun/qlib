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
- [Five Day Future Return Label](<02-signals-and-labels/Five Day Future Return Label.md>)
- [IC And Rank IC](<02-signals-and-labels/IC And Rank IC.md>)

### 03 Modeling

- [Week 3 - Model Workflow And Experiment Tracking](<03-modeling/Week 3 - Model Workflow And Experiment Tracking.md>)
- [LightGBM Training Notes](<03-modeling/LightGBM Training Notes.md>)
- [Model Validation](<03-modeling/Model Validation.md>)
- [Experiment Reproducibility And Prediction Cache](<03-modeling/Experiment Reproducibility And Prediction Cache.md>)

### 04 Strategy Backtest

- [Week 4 - Strategy Backtest And Custom Extension](<04-strategy-backtest/Week 4 - Strategy Backtest And Custom Extension.md>)
- [TopK Strategy](<04-strategy-backtest/TopK Strategy.md>)
- [Backtest And Costs](<04-strategy-backtest/Backtest And Costs.md>)
- [TopK Cost Backtest](<04-strategy-backtest/TopK Cost Backtest.md>)
- [PIT Safe Backtest](<04-strategy-backtest/PIT Safe Backtest.md>)
- [Future Information Audit](<04-strategy-backtest/Future Information Audit.md>)
- [Future Leakage And Backtest Water Audit](<04-strategy-backtest/Future Leakage And Backtest Water Audit.md>)
- [Backtest Stress Test Review](<04-strategy-backtest/Backtest Stress Test Review.md>)
- [Strict Re-Run Result Review](<04-strategy-backtest/Strict Re-Run Result Review.md>)
- [Benchmark And Excess Return Review](<04-strategy-backtest/Benchmark And Excess Return Review.md>)
- [Position Contribution And Exposure Review](<04-strategy-backtest/Position Contribution And Exposure Review.md>)

### 05 Data Expansion

- [Data Source Upgrade Plan](<05-data-expansion/Data Source Upgrade Plan.md>)
- [Strict PIT Data Repair Plan](<05-data-expansion/Strict PIT Data Repair Plan.md>)
- [CRSP Data Source Migration Plan](<05-data-expansion/CRSP Data Source Migration Plan.md>)
- [CRSP Early Stopping And Negative IC Diagnostics](<05-data-expansion/CRSP Early Stopping And Negative IC Diagnostics.md>)
- [CRSP Conservative Model And Horizon Comparison](<05-data-expansion/CRSP Conservative Model And Horizon Comparison.md>)
- [CRSP Macro Conservative Comparison](<05-data-expansion/CRSP Macro Conservative Comparison.md>)
- [CRSP Training Speed Optimization](<05-data-expansion/CRSP Training Speed Optimization.md>)
- [CRSP Macro Interaction Ablation And Regime Review](<05-data-expansion/CRSP Macro Interaction Ablation And Regime Review.md>)
- [CRSP Macro Enhanced Result Review](<05-data-expansion/CRSP Macro Enhanced Result Review.md>)
- [CRSP 2010 Baseline Cleanup And Industry Recovery](<05-data-expansion/CRSP 2010 Baseline Cleanup And Industry Recovery.md>)
- [CRSP Industry Mapping Repair](<05-data-expansion/CRSP Industry Mapping Repair.md>)
- [CRSP EDGAR Fundamentals Integration](<05-data-expansion/CRSP EDGAR Fundamentals Integration.md>)
- [CRSP EDGAR Coverage Cleaning And Ablation](<05-data-expansion/CRSP EDGAR Coverage Cleaning And Ablation.md>)
- [CRSP Rolling Window Validation](<05-data-expansion/CRSP Rolling Window Validation.md>)
- [CRSP Rolling Window Failure Review](<05-data-expansion/CRSP Rolling Window Failure Review.md>)
- [CRSP 2022 2023 Failure Deep Dive](<05-data-expansion/CRSP 2022 2023 Failure Deep Dive.md>)
- [CRSP Large Research Stage Summary](<05-data-expansion/CRSP Large Research Stage Summary.md>)
- [Databento Strict Launch PIT Integration](<05-data-expansion/Databento Strict Launch PIT Integration.md>)
- [Sharadar Strict Launch PIT Integration](<05-data-expansion/Sharadar Strict Launch PIT Integration.md>)
- [Fixed Window And Real EDGAR Runbook](<05-data-expansion/Fixed Window And Real EDGAR Runbook.md>)
- [Norgate Data Integration](<05-data-expansion/Norgate Data Integration.md>)
- [SEC EDGAR Fundamentals Integration](<05-data-expansion/SEC EDGAR Fundamentals Integration.md>)
- [SEC EDGAR Technical Data Flow](<05-data-expansion/SEC EDGAR Technical Data Flow.md>)
- [FRED ALFRED Macro Features Integration](<05-data-expansion/FRED ALFRED Macro Features Integration.md>)
- [FRED ALFRED Macro Experiment Review](<05-data-expansion/FRED ALFRED Macro Experiment Review.md>)
- [Macro Features New Information And Return Degradation](<05-data-expansion/Macro Features New Information And Return Degradation.md>)
- [Macro Regime Review And Interaction Features](<05-data-expansion/Macro Regime Review And Interaction Features.md>)
- [Macro Interaction Ablation Review](<05-data-expansion/Macro Interaction Ablation Review.md>)
- [Short History Evaluation And EDGAR Full Run](<05-data-expansion/Short History Evaluation And EDGAR Full Run.md>)
- [Stock Pool Cleaning And History Buckets](<05-data-expansion/Stock Pool Cleaning And History Buckets.md>)
- [Security Master Data](<05-data-expansion/Security Master Data.md>)
- [Liquidity Filtering](<05-data-expansion/Liquidity Filtering.md>)
- [Industry Features And Relative Ranking](<05-data-expansion/Industry Features And Relative Ranking.md>)
- [Market Derived Relative Features](<05-data-expansion/Market Derived Relative Features.md>)
- [Data Scope And Sources](<05-data-expansion/Data Scope And Sources.md>)
- [Financial Valuation Industry Macro News](<05-data-expansion/Financial Valuation Industry Macro News.md>)

### 06 Portfolio Risk

- [Industry Neutralization](<06-portfolio-risk/Industry Neutralization.md>)
- [Industry Exposure Strategy Comparison](<06-portfolio-risk/Industry Exposure Strategy Comparison.md>)
- [Industry Constraint Sensitivity](<06-portfolio-risk/Industry Constraint Sensitivity.md>)
- [Within Sector Stock Selection Review](<06-portfolio-risk/Within Sector Stock Selection Review.md>)
- [Sector Specific Error Review](<06-portfolio-risk/Sector Specific Error Review.md>)
- [Short History Score Calibration](<06-portfolio-risk/Short History Score Calibration.md>)
- [Short History Stock Review](<06-portfolio-risk/Short History Stock Review.md>)
- [CRSP History Bucket Top10 And Industry Unknown Review](<06-portfolio-risk/CRSP History Bucket Top10 And Industry Unknown Review.md>)
- [CRSP Industry Constraint And Relative Feature Recovery](<06-portfolio-risk/CRSP Industry Constraint And Relative Feature Recovery.md>)
- [CRSP Portfolio Construction And Risk Filter Repair](<06-portfolio-risk/CRSP Portfolio Construction And Risk Filter Repair.md>)
- [Portfolio Risk Control](<06-portfolio-risk/Portfolio Risk Control.md>)

### 07 Personal Quant

- [Personal Quant V1 Direction](<07-personal-quant/Personal Quant V1 Direction.md>)

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

1. 大型 CRSP / Alpha158 / EDGAR / macro 研究阶段先收束，结论见 [CRSP Large Research Stage Summary](<05-data-expansion/CRSP Large Research Stage Summary.md>)。
2. 当前判断：这条大型高维 ML 路线适合学习研究流程，但不适合作为个人小资金实盘主线。
3. 下一阶段切换到 [Personal Quant V1 Direction](<07-personal-quant/Personal Quant V1 Direction.md>)：少变量、少持仓、可解释、可复盘、可手工执行。
4. 新代码从 `analysis/personal_quant_v1/` 干净开始，旧 `analysis/nasdaq_top500_score/` 保留为研究资料库。
