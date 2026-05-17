# Stage Completion Records

每完成一个阶段，都在这里追加记录。记录要服务于复盘，而不是贴命令输出。

## 记录模板

```text
## YYYY-MM-DD 阶段 X：阶段名称

目标：
为什么要做：
输入数据：
核心概念：
实验动作：
评价指标：
结果解读：
遗留问题：
下一阶段准备：
产出文件：
```

## 2026-05-17 阶段 A：整理学习文档层级

目标：

把 `learning/` 从平铺笔记整理成可长期维护的分层知识库。

为什么要做：

后续学习会持续增加标签、特征、模型、回测、数据源和风控内容。如果继续平铺，iOS 阅读和复盘都会越来越困难。

输入数据：

```text
learning/ 下已有学习文档
analysis/ 下已有四方股份与 Nasdaq/Qlib 实验报告
```

核心概念：

```text
数据口径 -> 标签设计 -> 特征体系 -> 模型训练 -> IC 验证 -> TopK 回测 -> 风控复盘
```

实验动作：

```text
重新划分 learning/ 目录
移动已有文档
新增信号、标签、IC、LightGBM、TopK、数据扩展、组合风控主题笔记
建立阶段完成记录模板
```

评价指标：

```text
README 入口可读
旧文档没有丢失
Markdown 链接可跳转
Obsidian wikilinks 无断链
后续阶段有固定记录位置
```

结果解读：

阶段 A 完成后，学习资料从“单层资料堆”变成“分阶段知识库”。后续可以按阶段 B-G 继续推进。

遗留问题：

```text
尚未实现配置化研究流水线
尚未改成未来 5 日收益标签
尚未做股票池清洗和行业分组
尚未做 TopK 成本后回测
```

下一阶段准备：

阶段 B 需要把 Nasdaq/Qlib 实验脚本改造成配置驱动，避免每次修改代码。

产出文件：

```text
learning/README.md
learning/00-start-here/
learning/01-foundation/
learning/02-signals-and-labels/
learning/03-modeling/
learning/04-strategy-backtest/
learning/05-data-expansion/
learning/06-portfolio-risk/
learning/90-case-studies/
learning/99-logs/
```

## 2026-05-17 阶段 B：配置化研究流水线

目标：

把 Nasdaq/Qlib 实验从“改脚本才能换参数”改成“改 YAML 配置即可复跑”。

为什么要做：

量化研究需要可复现和可比较。股票池、数据窗口、标签、切分比例、模型参数只要有一个变化，结果就不能直接比较；所以每次实验必须有稳定配置和稳定输出目录。

输入数据：

```text
Nasdaq public screener 股票池信息
Nasdaq historical endpoint 近 900 自然日日线 OHLCV
股票池规则：NASDAQ、非 ETF、非测试证券、总市值前 500、最少 180 行历史
```

核心概念：

```text
配置文件
实验名
独立输出目录
resolved_config.yaml
IC / Rank IC
TopN 模型分数
```

实验动作：

```text
新增默认配置 analysis/nasdaq_top500_score/configs/nasdaq_alpha158_lgbm_1d.yaml
改造 run_qlib_alpha158_lightgbm.py 支持 --config
把股票池、数据窗口、标签、切分、模型参数和报告 TopN 全部配置化
每次实验输出到 analysis/nasdaq_top500_score/runs/<experiment.name>/
生成 universe.csv、download_failures.csv、predictions.csv、report.md、resolved_config.yaml
把逐股票 CSV 和 Qlib bin 放入本次实验目录下的 qlib_source_csv/ 与 qlib_data/
```

评价指标：

```text
脚本可编译
默认配置可运行
输出文件齐全
报告字段与配置一致
大型 CSV、Qlib bin 和缓存不进入 Git
```

结果解读：

默认 1 日标签实验已跑通。结果仍是学习样例，不是投资建议。

```text
可预测股票数：480
下载失败或历史不足：19
最新预测日：2026-05-15
Test 日均 IC：-0.009905
Test 日均 Rank IC：-0.003036
Top 5：AXTI、LUNR、NBIS、MXL、FTNT
```

这说明阶段 B 完成的是“研究流水线可复现”，不是“模型已经有效”。IC 仍然偏弱，后续要通过标签周期、股票池清洗、行业分组、数据口径和回测继续改善。

遗留问题：

```text
仍使用 1 日未来收益标签，噪声较大
股票池仍按当前 Nasdaq 总市值静态选择，未处理动态成分
尚未过滤低流动性、特殊证券类型和复杂行业差异
尚未接入复权、PIT 财报、估值、行业、宏观、新闻数据
尚未完成 TopK 成本后回测
```

下一阶段准备：

阶段 C 新增未来 5 日收益标签配置：

```text
Ref($close, -6) / Ref($close, -1) - 1
```

然后用同一条流水线对比 1 日标签和 5 日标签的 IC、Rank IC、TopN 结果差异。

产出文件：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_lgbm_1d.yaml
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/README.md
analysis/nasdaq_top500_score/runs/nasdaq_alpha158_lgbm_1d/report.md
analysis/nasdaq_top500_score/runs/nasdaq_alpha158_lgbm_1d/resolved_config.yaml
learning/03-modeling/Model Validation.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-17 阶段 E：数据口径升级

目标：

为后续 40 年历史数据、多源特征、行业分组和严谨回测建立数据验收标准。

为什么要做：

当前 `nasdaq_public` 数据源适合学习 Qlib 流水线，但不能解决复权、退市、动态股票池、PIT 财报和数据版本追溯问题。如果这些口径不先定清楚，后续提升 IC 或做 TopK 回测都可能只是数据偏差。

输入数据：

```text
当前 Nasdaq/Qlib 实验结果
Qlib 官方数据与 PIT 文档
WRDS CRSP / Compustat 官方说明
Norgate、SEC EDGAR、FRED、Nasdaq Data Link 官方说明
```

核心概念：

```text
学习数据 vs 严谨研究数据
复权
退市股票
动态成分
PIT 财报
数据版本
可审计复盘
```

实验动作：

```text
新增 Data Source Upgrade Plan
补充 Data Scope And Sources 的验收标准
补充 Financial Valuation Industry Macro News 的特征接入顺序
把数据源升级加入学习入口
明确短期、中期、长期数据路线
```

评价指标：

```text
能区分学习数据和严谨研究数据
每类数据都有字段、口径风险和接入优先级
明确 Qlib 负责研究框架，不负责提供完整美股 40 年数据库
给出下一阶段可执行建议
```

结果解读：

阶段 E 不追求立刻接入所有数据，而是先建立数据验收表。当前建议是双轨路线：

```text
短期：继续用 nasdaq_public 学习流水线
中期：个人可落地路线用 Norgate / Nasdaq Data Link / SEC EDGAR / FRED
长期：严谨研究路线用 WRDS CRSP + Compustat + FRED/ALFRED
```

遗留问题：

```text
尚未选择实际付费或机构数据源
尚未实现 data.source 的多数据源适配
尚未接入退市股票和动态成分
尚未把 PIT 财报转换为 Qlib 可训练特征
尚未验证 40 年数据的本地存储和运行成本
```

下一阶段准备：

先选一个价格和股票池数据源路线。确认是否能覆盖退市和动态成分后，再回到阶段 C，对比 1 日标签和 5 日标签。

产出文件：

```text
learning/05-data-expansion/Data Source Upgrade Plan.md
learning/05-data-expansion/Data Scope And Sources.md
learning/05-data-expansion/Financial Valuation Industry Macro News.md
learning/README.md
learning/00-start-here/Qlib Quant Learning Index.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-17 阶段 E.1：Norgate 可测试适配器

目标：

先从 Norgate 接入价格行情、退市股票和历史 S&P 500 成分，建立更严谨的 Alpha158 底层数据输入。

为什么要做：

当前 `nasdaq_public` 只能证明 Qlib 流水线能跑通，但它没有解决复权口径、退市股票、动态成分和幸存者偏差。Norgate 的作用是把“今天能看到的静态股票池”升级为“历史上当时真实属于指数的股票池”。

输入数据：

```text
当前 Mac 本地使用 fake Norgate client / fixture 数据
真实运行目标为 Norgate US Equities + US Equities Delisted
首个股票池为 S&P 500 / $SPX 历史成分
价格口径为 TOTALRETURN
padding 为 NONE
```

核心概念：

```text
复权
总回报价格
退市股票
历史指数成分
幸存者偏差
Alpha158 的底层 OHLCV 输入
```

实验动作：

```text
新增 data_sources 适配层
保留 nasdaq_public 原行为
新增 data.source: norgate
新增 Norgate S&P 500 配置文件
新增 membership.csv 输出路径
新增 fixture 单元测试验证当前上市和退市候选池
验证 membership 过滤非成分日期
验证 download_failures.csv 记录无价格和无历史成分原因
在 Mac 环境下验证无 norgatedata 时给出可读错误
```

评价指标：

```text
py_compile 通过
Norgate adapter 单元测试通过
YAML 配置可解析
Markdown 链接和 wikilinks 无断链
大型 CSV、Qlib bin 和缓存仍不进入 Git
```

结果解读：

本阶段完成的是“可测试工程接口”，不是“真实 Norgate 数据已跑通”。真实运行仍需要 Windows、Norgate Data Updater、有效订阅和 `norgatedata` 包。

Norgate 在当前模型中只负责升级底层行情和股票池。模型输入仍然是 Alpha158；区别是 Alpha158 将基于更长、更干净、包含退市和历史成分约束的 OHLCV 生成。

遗留问题：

```text
尚未在 Windows + Norgate Data Updater 环境真实拉取数据
尚未确认订阅级别是否包含 US Equities Delisted 和历史指数成分
尚未用 Norgate 数据训练一次完整 Alpha158 + LightGBM
尚未做 5 日标签和 TopK 成本后回测
尚未接入 PIT 财报、估值、行业、宏观、新闻特征
```

下一阶段准备：

建议下一步接入 SEC EDGAR，先补 10-K / 10-Q 披露日、财报字段和公告事件。目标是学习 PIT 财报如何按披露日对齐到日频样本，避免未来函数。

产出文件：

```text
analysis/nasdaq_top500_score/data_sources/
analysis/nasdaq_top500_score/configs/norgate_sp500_alpha158_lgbm_1d.yaml
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/README.md
tests/analysis/test_norgate_data_source.py
learning/05-data-expansion/Norgate Data Integration.md
learning/05-data-expansion/Data Source Upgrade Plan.md
learning/05-data-expansion/Data Scope And Sources.md
learning/README.md
learning/00-start-here/Qlib Quant Learning Index.md
```
