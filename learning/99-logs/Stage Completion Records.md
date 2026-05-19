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

## 2026-05-19 阶段 5.8C：短历史 score 校准

目标：

```text
验证“短历史股票高分输家偏多”是否可以通过选股层 score 校准改善。
不重新训练模型，只复用同一份 test_predictions.csv。
```

为什么要做：

```text
5.7C 和 5.8B 都显示短历史股票仍是错误来源之一。
但短历史股票也可能包含真实机会，不能直接全部排除。
本阶段要区分：轻度惩罚是否更稳，严格门槛是否会过度损失收益。
```

输入数据：

```text
as-of 2023-12-31 近似冻结 Nasdaq Top500
2016-05-17 到 2026-05-17 日线数据
SEC EDGAR 财报特征
行情派生相对特征
当前 frozen run 的 test_predictions.csv
```

核心概念：

```text
raw_score：模型原始预测分数
adjusted_score：选股层校准后的分数
短历史惩罚：按 history_bucket 对 score 扣分
严格流动性门槛：仅对 lt_2y 股票增加更高可交易性要求
```

实验动作：

```text
新增 score_calibration 配置。
TopK / bucket ranking / strategy_comparison 支持使用 adjusted_score 排名。
回测持仓同时保留 score、raw_score、adjusted_score 和 score_bucket_penalty。
新增三组对照：
raw_score_sector_cap_2_top10
short_history_penalty_sector_cap_2_top10
short_history_strict_sector_cap_2_top10
```

评价指标：

```text
累计收益
年化收益
最大回撤
相对 NASDAQCOM 超额收益
年化 alpha
短历史股票持仓次数
```

结果解读：

```text
raw_score_sector_cap_2_top10：
累计收益 97.56%，年化收益 33.75%，最大回撤 -29.36%，超额累计收益 10.51%。

short_history_penalty_sector_cap_2_top10：
累计收益 94.44%，年化收益 32.85%，最大回撤 -28.77%，超额累计收益 8.76%。

short_history_strict_sector_cap_2_top10：
累计收益 82.86%，年化收益 29.41%，最大回撤 -29.08%，超额累计收益 2.28%。
```

当前判断：

```text
轻度短历史惩罚略微改善最大回撤，但没有提升收益。
严格短历史惩罚 + 更高流动性门槛明显降低超额收益。
短历史股票不能简单重罚；第一版 score 校准更适合作为保守对照，不建议设为默认主策略。
```

遗留问题：

```text
短历史股票内部仍未拆解：哪些是有效机会，哪些是主要亏损来源。
短历史有效性可能有行业差异，需要 sector-specific 复盘。
当前仍缺少真实历史 shares outstanding、退市股票和 PIT 行业历史分类。
```

下一阶段准备：

```text
建议做短历史股票专项复盘：
按 lt_2y / 2_5y 分桶拆解赢家和输家。
检查亏损是否集中于低流动性、高估值、亏损公司、财报披露附近或特定行业。
如果差异明显，再做 sector-specific 短历史名额或惩罚规则。
```

产出文件：

```text
analysis/nasdaq_top500_score/selection/history_buckets.py
analysis/nasdaq_top500_score/backtest.py
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
tests/analysis/test_stock_pool_selection.py
learning/06-portfolio-risk/Short History Score Calibration.md
learning/00-start-here/Qlib Commands.md
learning/00-start-here/Qlib Quant Learning Index.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-18 第 5.2 条：未来函数审计与 as-of 冻结股票池

目标：

继续减少 5 日 Top10 回测中的未来信息风险，重点修正 EDGAR 披露生效日，并新增 as-of 2023-12-31 的冻结股票池实验。

为什么要做：

PIT 过滤版已经修正了历史长度分桶和流动性过滤，但仍有两个明显风险：财报披露可能当天可见，股票池仍使用运行日市值前 500。两者都会让回测比真实历史更乐观。

输入数据：

```text
Nasdaq public 当前候选池
固定行情窗口：2016-05-17 到 2026-05-17
as-of 股票池日期：2023-12-31
训练期：2016-08-11 到 2021-12-31
验证期：2022-01-03 到 2023-12-29
测试期：2024-01-02 到 2026-05-15
Alpha158 价格成交量特征
SEC EDGAR 10-K / 10-Q 财报估值特征
未来 5 日收益标签
```

核心概念：

```text
EDGAR acceptanceDateTime：SEC 接收申报的具体时间
下一交易日生效：盘后披露不能被当天收盘前的模型使用
as-of frozen universe：在测试期开始前固定股票池
近似历史市值：当前市值 * as-of close / 最新 close
残余未来信息：当前数据源缺少退市、历史 shares outstanding 和历史证券主数据
```

实验动作：

```text
EDGAR 特征从披露当天可见改为下一交易日可见
新增 universe.selection.method: approximate_market_cap_asof
新增 as_of_date: 2023-12-31
新增 universe_candidates.csv 和 universe_selection.csv
新增冻结股票池配置
补充单元测试验证 EDGAR 生效日顺延和 as-of 股票池估算
新增未来函数审计学习文档
```

评价指标：

```text
EDGAR 披露日前不可见
披露后第一个交易日可见
冻结股票池只保留 as-of 估算市值前 500
as-of 日期必须早于 test.start
IC / Rank IC
TopK 成本后累计收益、年化收益、最大回撤、换手
```

结果解读：

```text
冻结股票池实验已运行完成。
1000 只候选股票中，500 只入选冻结股票池，407 只低于 as-of 前 500，52 只在 2023-12-31 前无价格，41 只下载失败或历史不足。
IC：0.010304
Rank IC：-0.007921
成本后累计收益：26.41%
年化收益：10.53%
年化波动：37.45%
信息比率：0.455
最大回撤：-31.60%
平均换手：129.98%
PIT 过滤版年化收益曾为 188.81%，冻结股票池后降到 10.53%，说明运行日当前市值前 500 是一个重要未来信息来源。
当前训练阶段选训练集时间点前的市值前 500，方向是正确的，但只有在市值、证券状态、退市和行业分类都来自历史 PIT 数据时，才能称为严格避免股票池未来信息。
当前 Nasdaq public 版本是学习级近似，不是完整 PIT。
```

遗留问题：

```text
没有退市股票，仍有幸存者偏差
没有历史 shares outstanding，as-of market cap 只能用价格近似
没有历史行业分类和历史证券主数据
Nasdaq public 行情不是专业复权数据
固定 10 bps 成本仍偏简单
```

下一阶段准备：

继续做数据源升级：历史 shares outstanding、退市股票、真实复权行情和历史行业分类。冻结股票池已经把收益压回更合理区间，此时继续调模型不如先提高数据口径。

产出文件：

```text
analysis/nasdaq_top500_score/fundamentals/sec_edgar.py
analysis/nasdaq_top500_score/data_sources/nasdaq_public.py
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
tests/analysis/test_sec_edgar_fundamentals.py
tests/analysis/test_stock_pool_selection.py
tests/analysis/test_fixed_window_config.py
learning/04-strategy-backtest/Future Information Audit.md
learning/00-start-here/Qlib Commands.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-19 阶段 5.8B：行情派生行业相对特征

目标：

把 5.7C 错误复盘中发现的 size / liquidity / momentum 问题转成模型输入。

为什么要做：

5.7C 显示模型容易给短历史、高波动股票过高分数，同时漏掉更大、更活跃、近期动量更强的赢家。当前 Nasdaq public 没有历史 shares outstanding，不能严谨生成 PIT 市值，所以第一版用价格、成交额、动量、波动率和历史长度作为更安全的代理特征。

输入数据：

```text
frozen Nasdaq Top500 股票池
2016-05-17 到 2026-05-17 日线 OHLCV
当前 Nasdaq public sector / industry
Alpha158 特征
SEC EDGAR 财报估值特征
未来 5 日收益标签
```

核心概念：

```text
market_log_close：价格水平
market_log_avg_dollar_volume_20d：20 日平均成交额
market_momentum_60d：60 日价格动量
market_volatility_20d：20 日波动率
market_history_rows_asof：截至当日历史长度
market_sector_pct_*：同一天同 sector 内 percentile
market_industry_pct_*：同一天同 industry 内 percentile
```

实验动作：

```text
新增 market_features.py
新增 market_features 配置
生成 market_features.parquet 和 market_feature_failures.csv
把 market_features 与 Alpha158、EDGAR 一起拼接进 Qlib DatasetH
重新训练 frozen 配置
报告新增行情相对特征章节
学习文档记录 PIT 口径和结果
```

评价指标：

```text
market feature 覆盖
Technology / Health Care / Consumer Discretionary 行业内 Rank IC
Top-Bottom spread
高分输家率
低分赢家率
TopK 成本后收益
行业约束策略对照
```

结果解读：

```text
market_features.parquet：
  股票数 500
  样本行数 1,116,570
  特征数 33
  失败记录 3 条，均为 sector / industry 缺失

Technology：
  Rank IC -0.0214 -> 0.0087
  Top-Bottom spread -0.5044% -> 0.0306%
  高分输家率 52.63% -> 51.15%
  低分赢家率 50.93% -> 49.58%

Health Care：
  Rank IC 0.0191 -> 0.0077
  Top-Bottom spread 0.5627% -> 0.1156%
  高分输家率 49.83% -> 49.34%
  低分赢家率 46.68% -> 49.57%

Consumer Discretionary：
  Rank IC -0.0230 -> 0.0159
  Top-Bottom spread -0.2560% -> 0.0283%
  高分输家率 51.97% -> 48.54%
  低分赢家率 52.99% -> 47.72%
```

策略结果：

```text
默认 sector_cap_4_top10：
  累计收益 51.99%
  年化收益 19.58%
  最大回撤 -36.00%
  超额累计收益 -14.99%

sector_cap_2_top10：
  累计收益 94.96%
  年化收益 33.00%
  最大回撤 -33.82%
  超额累计收益 9.05%
  年化 alpha 6.06%
```

当前判断：

```text
行情相对特征有效改善了 Technology 和 Consumer Discretionary 的行业内排序。
Health Care 没有明显改善，仍应考虑事件数据或更严格的高估值亏损股过滤。
加入行情相对特征后，更紧的 max_sector=2 表现最好，需要重新评估默认行业约束。
短历史股票问题有所缓解，但没有消失，后续仍要做短历史 score 校准。
```

遗留问题：

```text
sector / industry 仍不是历史 PIT 分类
没有真实历史 shares outstanding，不能生成严谨历史市值
成交额和价格水平只是 size / liquidity 代理
Health Care 需要临床、审批、融资等事件型数据
```

下一阶段准备：

```text
阶段 5.8C：短历史 score 校准
或先复用当前 test_predictions.csv，把默认行业约束重新对照为 max_sector=2
```

产出文件：

```text
analysis/nasdaq_top500_score/market_features.py
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
tests/analysis/test_market_features.py
learning/05-data-expansion/Market Derived Relative Features.md
learning/00-start-here/Qlib Commands.md
learning/00-start-here/Qlib Quant Learning Index.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-18 第 5.4 条：持仓贡献与行业暴露复盘

目标：

拆解冻结股票池 Top10 策略的收益和亏损来源，回答收益是否集中在少数股票或行业。

为什么要做：

基准复盘已经显示策略没有跑赢 NASDAQCOM。继续调模型前，必须先知道当前策略到底亏在哪里、赚在哪里，以及是否只是行业暴露造成的结果。

输入数据：

```text
backtest_nav.csv
backtest_positions.csv
策略每期持仓、权重、单票收益
NASDAQCOM 基准收益
sector / industry 信息
```

核心概念：

```text
毛贡献：持仓权重 * 单票收益
成本贡献：当期总交易成本 / 当期持仓数量
净贡献：毛贡献 - 成本贡献
超额贡献：净贡献 - 持仓权重 * 基准收益
行业暴露：每期同一行业持仓权重之和
贡献集中度：前几名贡献股票占全部正贡献的比例
```

实验动作：

```text
backtest_positions.csv 增加 gross_contribution、cost_contribution、net_contribution、excess_contribution
新增 contribution_by_symbol.csv
新增 contribution_by_sector.csv
新增 contribution_by_industry.csv
新增 exposure_by_sector.csv
新增 exposure_by_industry.csv
新增 contribution_summary.yaml
report.md 新增持仓贡献与行业暴露章节
新增 Position Contribution And Exposure Review 学习文档
```

评价指标：

```text
正贡献最大的股票
负贡献最大的股票
正贡献最大的 sector / industry
负贡献最大的 sector / industry
前 5 大正贡献股票占全部正贡献比例
sector 平均暴露和最大暴露
industry 平均暴露和最大暴露
```

结果解读：

```text
前 5 大正贡献股票占全部正贡献比例：30.95%
正贡献最大股票：ASST、IBRX、CAR、IOVA、OPEN
负贡献最大股票：IQ、VFS、UPST、FTRE、IRTC
正贡献最大 sector：Technology、Health Care、Basic Materials
负贡献最大 sector：Finance、Miscellaneous、Consumer Staples
平均 sector 暴露最高：Health Care 32.85%、Technology 27.03%、Consumer Discretionary 17.49%
```

遗留问题：

```text
贡献按单期简单相加，不是 Brinson 级别的专业归因
成本按持仓数平均分摊，未区分买入/卖出/换手来源
行业分类仍来自当前 Nasdaq snapshot，不是历史 PIT 行业分类
尚未按行业中性组合验证改进效果
```

下一阶段准备：

进入行业中性 TopK / 行业内排名实验。当前策略平均暴露偏向 Health Care 和 Technology，且超额收益为负，下一步应测试降低行业暴露后是否改善相对基准表现。

产出文件：

```text
analysis/nasdaq_top500_score/backtest.py
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
tests/analysis/test_topk_backtest.py
learning/04-strategy-backtest/Position Contribution And Exposure Review.md
learning/00-start-here/Qlib Commands.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-18 第 5.3 条：基准与超额收益复盘

目标：

判断 as-of 冻结股票池后的 Top10 策略是否真正跑赢市场。

为什么要做：

策略有绝对收益不代表有 alpha。2024-2026 纳斯达克本身上涨明显，如果不和基准比较，就无法判断收益来自模型能力，还是来自市场 beta。

输入数据：

```text
策略回测：nasdaq_alpha158_edgar_lgbm_10y_frozen_2023_top500_5d_pit_safe
策略入场/退出窗口：来自 backtest_nav.csv
基准：FRED NASDAQCOM
比较方式：每个策略持有窗口内，同步计算基准收益
```

核心概念：

```text
基准收益：同一入场/退出日期的 NASDAQCOM 收益
超额收益：策略收益 - 基准收益
超额累计收益：策略净值 / 基准净值 - 1
Beta：策略对市场的敏感度
Alpha：扣除 beta 后的剩余年化收益
跟踪误差：超额收益的波动
相对信息比率：平均超额收益 / 超额收益波动
```

实验动作：

```text
新增 benchmark 配置
新增 FRED NASDAQCOM 下载与缓存
在 backtest_nav.csv 中追加 benchmark_return、excess_return、benchmark_nav、relative_nav
输出 benchmark_prices.csv 和 benchmark_summary.yaml
report.md 新增基准与超额收益章节
新增 Benchmark And Excess Return Review 学习文档
```

评价指标：

```text
策略累计收益
基准累计收益
超额累计收益
基准最大回撤
跟踪误差
相对信息比率
Beta
年化 Alpha
策略/基准相关性
跑赢基准期数占比
```

结果解读：

```text
策略累计收益：26.41%
策略年化收益：10.53%
策略最大回撤：-31.60%
NASDAQCOM 基准累计收益：78.78%
NASDAQCOM 基准年化收益：28.17%
NASDAQCOM 基准最大回撤：-22.66%
超额累计收益：-29.30%
Beta：1.092
年化 Alpha：-12.25%
相对信息比率：-0.319
跑赢基准期数占比：49.15%
```

当前判断：

```text
冻结股票池后的策略有绝对收益。
但它没有跑赢纳斯达克综合指数。
当前模型还不能证明有稳定 alpha。
```

遗留问题：

```text
NASDAQCOM 不是总回报指数
仍缺少退市股票和真实历史市值
没有拆分行业暴露和个股贡献
没有计算相对基准的行业/风格风险
成本模型仍是固定 10 bps
```

下一阶段准备：

进入持仓贡献和行业暴露复盘。先回答收益和亏损来自哪些股票、哪些行业，再考虑行业中性 TopK 或行业内排名。

产出文件：

```text
analysis/nasdaq_top500_score/backtest.py
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
tests/analysis/test_topk_backtest.py
learning/04-strategy-backtest/Benchmark And Excess Return Review.md
learning/00-start-here/Qlib Commands.md
learning/99-logs/Qlib Learning Log.md
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

## 2026-05-17 阶段 E.2：SEC EDGAR 财报与估值特征

目标：

把 SEC EDGAR 的 10-K / 10-Q 结构化 XBRL 财报转成日频 PIT 特征，并与 Alpha158 合并训练。

为什么要做：

Alpha158 只描述价格和成交量，不能看到公司收入、利润、现金流、资产负债和估值。EDGAR 特征用于验证基本面信息是否能在价格技术面 baseline 之外提供增量。

输入数据：

```text
SEC company_tickers_exchange.json
SEC submissions/CIK##########.json
SEC companyfacts/CIK##########.json
当前 Nasdaq/Qlib 逐股票日线 close
```

核心概念：

```text
CIK
accession
10-K / 10-Q
XBRL us-gaap tag
PIT 披露日对齐
财报字段
估值因子
```

实验动作：

```text
新增 fundamentals 适配层
新增 SEC EDGAR client 和 feature builder
新增 nasdaq_alpha158_edgar_lgbm_1d.yaml
训练时生成 Alpha158 后合并 edgar_ 财报特征
输出 fundamental_features.parquet、fundamental_failures.csv、edgar_cik_map.csv
新增 fake SEC 单元测试验证 CIK 映射、10-K/10-Q 过滤、PIT 对齐、缺价格、缺字段
更新学习文档说明财报如何变成模型特征
```

评价指标：

```text
py_compile 通过
EDGAR fake 单元测试通过
默认 Alpha158-only 配置仍可解析
EDGAR 配置可解析
Markdown 链接和 wikilinks 无断链
EDGAR cache、parquet、Qlib bin 和大型中间产物不进入 Git
```

结果解读：

本阶段完成的是 EDGAR 第一版工程接入和学习文档。因为当前环境没有设置 `SEC_EDGAR_USER_AGENT`，没有对 SEC 官方接口做真实全量拉取。fake 测试已经验证披露日前不可见、披露日后 forward fill、估值需要价格、缺失问题进入 failure 文件。

遗留问题：

```text
尚未真实跑 5 只股票 smoke test
尚未扩展到 Nasdaq 500 股票池真实训练
TTM 和同比仍是学习基线，后续需更严谨处理季度累计值和重述
尚未接入 8-K、Form 4、行业分类和文本特征
尚未比较 Alpha158-only 与 Alpha158+EDGAR 的 IC / Rank IC
```

下一阶段准备：

先设置 SEC 要求的 User-Agent，真实跑 5 只股票 smoke test，检查字段覆盖率和 failure 原因。通过后再扩展到当前 Nasdaq 股票池，并与 Alpha158 baseline 对比。

产出文件：

```text
analysis/nasdaq_top500_score/fundamentals/
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_1d.yaml
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/README.md
tests/analysis/test_sec_edgar_fundamentals.py
learning/05-data-expansion/SEC EDGAR Fundamentals Integration.md
learning/05-data-expansion/Financial Valuation Industry Macro News.md
learning/05-data-expansion/Data Source Upgrade Plan.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-17 第 5.1 条：PIT 过滤版 TopK 回测

目标：

减少回测中的未来信息污染，先修正历史长度分桶和流动性过滤这两个明显问题。

为什么要做：

旧版成本后回测虽然训练期没有使用 2024 年以后的标签，但回测选择阶段仍然使用了未来可见信息：

```text
历史长度分桶使用完整 2016-2026 数据
流动性过滤使用 2026 年末最近 20/60 日数据
```

这会让 2024 年的选股提前知道哪些股票后来仍然存在、后来仍然有流动性。

输入数据：

```text
Nasdaq public 当前市值前 500
固定行情窗口：2016-05-17 到 2026-05-17
训练期：2016-08-11 到 2021-12-31
验证期：2022-01-03 到 2023-12-29
测试期：2024-01-02 到 2026-05-15
Alpha158 价格成交量特征
SEC EDGAR PIT 财报估值特征
未来 5 日收益标签
```

核心概念：

```text
PIT：point in time，只使用当时可见数据
history_rows_asof：截至信号日已有多少交易日历史
liquidity_asof：截至信号日前 20/60 日流动性
残余股票池偏差：当前 Nasdaq public 仍不是历史 PIT 股票池
```

实验动作：

```text
新增 backtest.point_in_time_filters
新增 nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d_pit_safe.yaml
训练前不再用 2026 年末流动性删除股票
每个回测信号日重新计算历史长度桶
每个回测信号日重新计算 20/60 日流动性
记录 PIT 过滤前后候选数
新增 PIT Safe Backtest 学习文档
```

评价指标：

```text
累计收益
年化收益
最大回撤
平均换手
PIT 过滤前候选数
PIT 过滤后候选数
PIT 历史长度通过数
PIT 流动性通过数
```

结果解读：

旧版回测：

```text
累计收益：2225.10%
年化收益：283.38%
最大回撤：-18.11%
平均换手：110.93%
```

PIT 过滤版：

```text
累计收益：1097.92%
年化收益：188.81%
最大回撤：-21.63%
平均换手：97.33%
平均 PIT 过滤前候选数：476.14
平均 PIT 过滤后候选数：454.47
```

结果下降明显，说明旧版分桶和流动性确实抬高了回测结果。但收益仍然偏高，说明最大污染源可能仍是股票池：当前 Nasdaq public 使用运行日市值前 500，不是历史时点可见股票池。

遗留问题：

```text
股票池仍不是历史 PIT top 500
没有退市股票
没有历史市值
行业分类和证券主数据仍是当前 snapshot
没有专业复权行情
没有基准超额收益和容量约束
```

下一阶段准备：

继续推进数据源升级，优先解决历史股票池、退市股票、历史市值和复权行情。当前免费 Nasdaq public 数据源不足以支持完全严谨的 PIT 回测。

产出文件：

```text
analysis/nasdaq_top500_score/backtest.py
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d_pit_safe.yaml
tests/analysis/test_topk_backtest.py
learning/04-strategy-backtest/PIT Safe Backtest.md
learning/00-start-here/Qlib Commands.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-17 阶段 E.3：行业特征与行业内相对因子

目标：

把 EDGAR 财报和估值特征从“全市场直接比较”升级为“行业内比较”，让模型看到同业相对位置。

为什么要做：

估值、毛利率、ROE、成长和负债率都有强行业属性。如果不同行业直接比较，模型可能学到行业差异，而不是公司在同行里的强弱。

输入数据：

```text
当前 Nasdaq public 股票池 universe.csv
字段：symbol、sector、industry
EDGAR 生成的 edgar_ 财报与估值特征
Alpha158 价格成交量特征
```

核心概念：

```text
行业内 rank
行业内 percentile
sector fallback
行业相对特征
行业中性化
PIT 行业分类限制
```

实验动作：

```text
新增 industry 特征层
新增 nasdaq_alpha158_edgar_industry_lgbm_1d.yaml
对 EDGAR 特征生成行业内 rank / percentile 和 sector percentile
行业样本过少时回退到 sector
输出 industry_features.parquet 和 industry_failures.csv
报告新增行业覆盖、TopN sector 分布和 TopN industry 分布
新增单元测试验证行业映射、行业内百分位、sector fallback、缺失分类记录
新增学习文档解释行业内比较和行业中性化区别
```

评价指标：

```text
py_compile 通过
行业特征单元测试通过
EDGAR 和 Norgate 既有测试仍通过
新配置可解析
Markdown 链接和 wikilinks 无断链
industry_features.parquet 等大型中间产物不进入 Git
```

结果解读：

本阶段完成的是模型输入层升级：Alpha158 仍提供价格成交量信号，EDGAR 提供财报估值信号，行业相对特征提供“同行内相对位置”。这一步还不是组合层面的行业中性策略。

第一版行业分类来自当前 Nasdaq public snapshot，不是历史 PIT 行业分类。因此它适合学习和实验，不适合作为严谨回测的最终行业口径。

遗留问题：

```text
尚未真实运行 Alpha158 + EDGAR + Industry 全量实验
尚未验证行业相对特征是否提升 IC / Rank IC
尚未做行业内 TopK 或 sector 权重限制回测
尚未接入历史 PIT 行业分类，例如 GICS、SIC、NAICS 或 vendor 分类
尚未处理行业分类变更和行业样本过少的更严谨方案
```

下一阶段准备：

进入组合层面的行业控制：先比较 Alpha158、Alpha158+EDGAR、Alpha158+EDGAR+Industry 三组模型指标，再做行业内 TopK / sector 权重限制回测，观察年化收益、最大回撤、换手率和成本后收益。

产出文件：

```text
analysis/nasdaq_top500_score/industry/
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_industry_lgbm_1d.yaml
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/README.md
tests/analysis/test_industry_features.py
learning/05-data-expansion/Industry Features And Relative Ranking.md
learning/06-portfolio-risk/Industry Neutralization.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-17 阶段 E.4：固定 15 年窗口与真实 EDGAR 准备

目标：

把长期实验的数据窗口固定为 `2011-05-17` 到 `2026-05-17`，并给真实 SEC EDGAR 拉取建立可执行指引。

为什么要做：

如果仍使用 `lookback_days`，每次运行都会以运行当天为基准向前滚动，训练集、验证集、测试集都会漂移。量化实验要比较不同标签、特征和模型，必须先固定时间窗口。

输入数据：

```text
Nasdaq public 股票池和历史日线
固定数据窗口：2011-05-17 到 2026-05-17
SEC company_tickers_exchange.json
SEC submissions
SEC companyfacts
```

核心概念：

```text
固定训练窗口
固定日期切分
warmup_days
EDGAR User-Agent
EDGAR smoke test
```

实验动作：

```text
Nasdaq public 数据源支持 data.start_date / data.end_date
训练脚本支持 split.method: date
新增 15 年固定窗口 Alpha158 baseline 配置
新增 15 年固定窗口 EDGAR smoke test 配置
新增固定窗口和真实 EDGAR 运行指引
新增测试验证固定日期下载窗口、固定切分和配置解析
```

评价指标：

```text
py_compile 通过
固定窗口单元测试通过
全部分析相关测试通过
全部 YAML 配置可解析
Markdown 链接和 wikilinks 无断链
```

结果解读：

本阶段完成的是“可复现时间边界”。以后固定窗口配置不会因为运行日期变化而改变研究样本。

注意：当前 Nasdaq public 仍是当前静态股票池，不是历史动态成分，也不含退市股票。固定窗口解决的是时间漂移，不解决幸存者偏差。

遗留问题：

```text
尚未真实下载 2011-05-17 到 2026-05-17 的 Nasdaq public 全量日线
尚未设置 SEC_EDGAR_USER_AGENT
尚未运行 EDGAR 5 只股票 smoke test
尚未把 EDGAR smoke test 扩展到 50 / 100 / 500 只股票
尚未用 Norgate 或 CRSP 解决历史成分和退市股票
```

下一阶段准备：

先运行 `nasdaq_alpha158_lgbm_15y_fixed.yaml` 建立固定窗口 baseline。然后设置 `SEC_EDGAR_USER_AGENT`，运行 `nasdaq_alpha158_edgar_lgbm_15y_smoke.yaml`，检查 CIK 映射、财报特征和 failure 文件。

产出文件：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_lgbm_15y_fixed.yaml
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_15y_smoke.yaml
analysis/nasdaq_top500_score/data_sources/nasdaq_public.py
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/README.md
tests/analysis/test_fixed_window_config.py
learning/05-data-expansion/Fixed Window And Real EDGAR Runbook.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-17 阶段 E.5：Nasdaq 当前前 500 市值 10 年数据

目标：

把固定训练窗口调整为当前 Nasdaq public 可落地的 10 年窗口，并获取当前 Nasdaq 市值前 500 股票的日线数据。

为什么要做：

真实试跑发现 Nasdaq public 对 15 年请求只返回约 10 年行情。如果继续坚持 15 年，配置看起来固定，但底层行情数据并不完整。先把窗口改成可稳定落地的 10 年，才能继续做 EDGAR、行业特征和标签对比。

输入数据：

```text
Nasdaq 当前市值前 500
固定行情窗口：2016-05-17 到 2026-05-17
字段：date, symbol, open, high, low, close, vwap, volume
```

核心概念：

```text
固定 10 年窗口
当前静态股票池
历史不足过滤
Qlib source CSV
Qlib bin
```

实验动作：

```text
新增 nasdaq_alpha158_lgbm_10y_fixed.yaml
Nasdaq public 下载后按 start_date / end_date 二次过滤
获取当前 Nasdaq 市值前 500 的 10 年日线
转换为 Qlib bin 数据
训练 Alpha158 + LightGBM baseline
生成 report.md、predictions.csv、download_failures.csv
```

评价指标：

```text
配置可解析
py_compile 通过
固定窗口测试通过
Qlib 数据日历固定在 2016-05-17 到 2026-05-15
大型 CSV、Qlib bin 和 runs 输出不进入 Git
```

结果解读：

本次下载结果：

```text
股票池：500
成功进入 Qlib source CSV：319
失败或历史不足：181
Qlib 交易日：2514
实际开始日：2016-05-17
实际结束日：2026-05-15
最新日可预测股票数：318
```

模型验证结果：

```text
Test 日均 IC：0.000299
Test 日均 Rank IC：-0.003188
```

这说明 10 年数据链路已经可用，但 Alpha158-only baseline 仍没有明显预测能力。

遗留问题：

```text
181 只当前前 500 股票没有满足 2400 行历史，主要是新上市、重组或特殊证券
股票池仍是当前静态前 500，不是历史动态成分
不含退市股票，仍有幸存者偏差
尚未接入 EDGAR 到 10 年 500 股票实验
尚未做未来 5 日标签和 TopK 成本后回测
```

下一阶段准备：

使用同一 10 年窗口扩大 EDGAR 实验：先从 50 只股票开始，检查 CIK 映射、字段缺失和请求稳定性，再扩展到 100/500 只。

产出文件：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_lgbm_10y_fixed.yaml
analysis/nasdaq_top500_score/runs/nasdaq_alpha158_lgbm_10y_fixed/
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-17 阶段 E.6：短历史股票评估与真实 EDGAR 全量接入

目标：

在固定 10 年窗口中，让不满 10 年历史但有足够近期数据的股票进入预测/评估，同时真实获取 SEC EDGAR 财报数据并接入模型。

为什么要做：

当前 Nasdaq 市值前 500 里有很多新上市、重组或特殊证券。如果要求每只股票都满 10 年历史，会排除大量测试期真实可见的股票；但如果直接放开，又必须明确它们不会贡献不存在的早期训练样本。

输入数据：

```text
股票池：当前 Nasdaq 市值前 500
固定行情窗口：2016-05-17 到 2026-05-17
最低历史行数：180
行情字段：date, symbol, open, high, low, close, vwap, volume
财报来源：SEC EDGAR company_tickers_exchange / submissions / companyfacts
财报表单：10-K, 10-Q, 10-K/A, 10-Q/A
```

核心概念：

```text
短历史股票
固定全局窗口
真实存在样本
CIK 映射
PIT 财报特征
EDGAR 字段缺失
```

实验动作：

```text
新增 nasdaq_alpha158_lgbm_10y_eval_all.yaml
新增 nasdaq_alpha158_edgar_lgbm_10y_eval_all.yaml
修复 EDGAR / 行业特征中的 pd.NA，使其在 LightGBM 输入前变成 np.nan
修复 EDGAR 同比增长 pct_change 的显式缺失处理
运行 10 年窗口 EDGAR 全量实验
生成 report.md、predictions.csv、fundamental_features.parquet、fundamental_failures.csv、edgar_cik_map.csv
```

评价指标：

```text
py_compile 通过
SEC EDGAR / industry / fixed window 单元测试通过
真实 EDGAR 全量实验跑通
报告中包含 IC、Rank IC、TopN、CIK 映射数量、财报特征数量、失败数量
大型 runs 输出继续不进入 Git
```

结果解读：

```text
股票池：500
进入 Qlib source CSV：481
下载失败或历史不足：19
最新日可预测股票数：480
EDGAR CIK 映射数量：499
EDGAR 日频特征矩阵：895,760 行 x 29 列
EDGAR 特征覆盖股票数：420
EDGAR 失败或跳过数量：340
Test 日均 IC：0.011370
Test 日均 Rank IC：0.003418
参与 IC 计算交易日：593
```

Top5 预测结果：

```text
NVAWW
FLEX
NBIS
SNDK
TSEM
```

遗留问题：

```text
Top5 中出现 warrant / 特殊证券，说明当前 Nasdaq public 的 exclude_etf / exclude_test_issue 不足以完成普通股清洗
EDGAR missing_fields 较多，不同公司 XBRL tag 和业务形态差异会影响特征质量
短历史股票和完整 10 年股票混在一起评估，后续需要按历史长度分桶观察
股票池仍是当前静态前 500，不是历史动态成分，也不含退市股票
本次仍是 1 日收益标签，尚未切换未来 5 日收益
```

下一阶段准备：

先做股票池清洗与历史长度分桶：过滤 warrant、preferred、rights、units 等特殊证券；把样本按完整 10 年、5-10 年、2-5 年、少于 2 年分组，再比较预测覆盖和 IC。随后把 EDGAR + 行业相对特征放到同一 10 年窗口中对比。

产出文件：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_lgbm_10y_eval_all.yaml
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_eval_all.yaml
analysis/nasdaq_top500_score/runs/nasdaq_alpha158_edgar_lgbm_10y_eval_all/
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-17 阶段 D.1：股票池清洗、历史长度分桶与桶内 Top10

目标：

在固定 10 年 Nasdaq + EDGAR 实验上，过滤特殊证券，并用历史长度桶控制最终 Top10 名额。

为什么要做：

上一阶段 Top5 出现 warrant，说明当前 Nasdaq public 股票池虽然过滤了 ETF 和 test issue，但仍混有 warrant、preferred、unit、right、notes 等不适合作为普通股候选的证券。模型分数本身没有证券类型常识，所以必须先清洗股票池，再做候选组合。

输入数据：

```text
股票池：当前 Nasdaq 清洗后市值前 500
固定行情窗口：2016-05-17 到 2026-05-17
财报来源：SEC EDGAR 10-K / 10-Q / companyfacts
标签：未来 1 日收益
模型：Alpha158 + EDGAR + LightGBM
```

核心概念：

```text
特殊证券过滤
历史长度分桶
桶内排名
固定桶名额
统一模型 score
```

实验动作：

```text
新增 security_filter
新增 history_buckets
新增 bucket_ranking
新增 nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10.yaml
输出 universe_exclusions.csv
输出 history_buckets.csv
输出 bucketed_predictions.csv
输出 selected_top10.csv
生成清洗和分桶报告
```

评价指标：

```text
py_compile 通过
17 个相关单元测试通过
所有 YAML 配置可解析
真实配置运行成功
最终 Top10 严格符合 4/3/2/1 桶名额
大型 runs 输出继续不进入 Git
```

结果解读：

```text
股票池清洗剔除数量：439
进入 Qlib source CSV：482
下载失败或历史不足：18
最新日可预测股票数：482
Test 日均 IC：0.015196
Test 日均 Rank IC：0.004995
参与 IC 计算交易日：593
```

清洗剔除原因：

```text
name:warrant：228
name:preferred：101
symbol:.*W$：45
name:notes：34
name:unit：13
name:right：5
name:depositary_shares：5
symbol:.*WT$：3
symbol:.*WS$：3
name:debenture：1
name:bond：1
```

最新日可预测股票分桶：

```text
full_10y：335
5_10y：86
2_5y：48
lt_2y：13
```

最终 Top10：

```text
full_10y：AMD, SIMO, PLUG, MXL
5_10y：NBIS, BILI, GTX
2_5y：LUNR, RGC
lt_2y：SNDK
```

遗留问题：

```text
清洗规则仍是文本规则，不是专业证券主数据
ADR/ADS 暂时保留，后续需要单独观察
Technology / Semiconductors 仍然偏集中
尚未做未来 5 日标签
尚未做 TopK 成本后回测
```

下一阶段准备：

在当前清洗 + 分桶 Top10 基础上加入行业内名额约束，例如单一 sector 最多 4 只、单一 industry 最多 2 只，避免候选组合过度集中在 Technology 或 Semiconductors。

产出文件：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10.yaml
analysis/nasdaq_top500_score/selection/history_buckets.py
tests/analysis/test_stock_pool_selection.py
learning/05-data-expansion/Stock Pool Cleaning And History Buckets.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-17 阶段 D.2：行业名额约束

目标：

在股票池清洗和历史长度分桶之后，继续控制最终 Top10 的行业集中度。

为什么要做：

上一版桶内 Top10 虽然解决了特殊证券和短历史股票的问题，但最终名单里 Technology 仍然偏集中。模型分数不会自动理解组合分散度，所以需要在最终选择阶段增加 sector / industry 上限。

输入数据：

```text
股票池：当前 Nasdaq 清洗后市值前 500
固定行情窗口：2016-05-17 到 2026-05-17
财报来源：SEC EDGAR 10-K / 10-Q / companyfacts
标签：未来 1 日收益
模型：Alpha158 + EDGAR + LightGBM
最终选择：历史长度桶名额 + 行业名额约束
```

核心概念：

```text
统一模型 score
历史长度桶名额
sector 上限
industry 上限
约束后回补
```

实验动作：

```text
新增 industry_constraints 配置
select_bucketed_top 支持约束选择
报告写入行业约束、sector 分布和 industry 分布
新增行业约束单元测试
复跑 clean_bucket_top10 配置
```

评价指标：

```text
py_compile 通过
10 个相关单元测试通过
所有 YAML 配置可解析
真实配置运行成功
最终 Top10 仍符合 4/3/2/1 桶名额
最终 Top10 满足 sector<=4、industry<=2
大型 runs 输出继续不进入 Git
```

结果解读：

```text
Test 日均 IC：0.015196
Test 日均 Rank IC：0.004995
参与 IC 计算交易日：593
最新日可预测股票数：482
```

最终 Top10：

```text
full_10y：AMD, SIMO, PLUG, QCOM
5_10y：NBIS, GTX, LQDA
2_5y：LUNR, RGC
lt_2y：SIRI
```

最终 sector 分布：

```text
Technology：4
Consumer Discretionary：2
Health Care：2
Energy：1
Industrials：1
```

最终 industry 分布：

```text
Semiconductors：2
Industrial Machinery/Components：2
Computer Software: Programming Data Processing：1
Radio And Television Broadcasting And Communications Equipment：1
Auto Parts:O.E.M.：1
Biotechnology: Pharmaceutical Preparations：1
Medicinal Chemicals and Botanical Products：1
Broadcasting：1
```

遗留问题：

```text
行业分类仍来自当前 Nasdaq public snapshot，不是历史 PIT 行业口径
行业约束只控制最终名单，不等于行业中性回测
尚未过滤低流动性股票
尚未使用专业证券主数据
尚未做未来 5 日标签和成本后回测
```

下一阶段准备：

进入第 2 条：流动性过滤。默认先用日线数据计算近 20 日和近 60 日成交额、零成交日、价格下限等指标，生成 `liquidity_profile.csv`，并让低流动性股票不能进入最终 Top10。

产出文件：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10.yaml
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/selection/history_buckets.py
tests/analysis/test_stock_pool_selection.py
learning/05-data-expansion/Stock Pool Cleaning And History Buckets.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-17 阶段 D.3：流动性过滤

目标：

让低价、低成交额或交易不连续的股票不进入本次 Qlib 训练、预测和最终 Top10。

为什么要做：

模型分数只说明模型认为某只股票未来收益可能更高，但它不自动考虑买卖价差、成交冲击和交易容量。低流动性股票即使分数高，也可能无法以合理成本成交。

输入数据：

```text
股票池：当前 Nasdaq 清洗后市值前 500
固定行情窗口：2016-05-17 到 2026-05-17
流动性来源：已下载日线 OHLCV
财报来源：SEC EDGAR 10-K / 10-Q / companyfacts
标签：未来 1 日收益
模型：Alpha158 + EDGAR + LightGBM
最终选择：流动性过滤 + 历史长度桶名额 + 行业名额约束
```

核心概念：

```text
日成交额
近 20 日平均成交额
近 60 日成交额中位数
零成交比例
价格下限
可交易股票池
```

实验动作：

```text
新增 liquidity_filter 配置
新增 liquidity.py 适配层
输出 liquidity_profile.csv
输出 liquidity_exclusions.csv
流动性不达标股票从 Qlib source CSV 中移除
报告写入过滤规则、剔除数量和剔除原因
新增流动性过滤单元测试
复跑 clean_bucket_top10 配置
```

评价指标：

```text
py_compile 通过
相关单元测试通过
所有 YAML 配置可解析
真实配置运行成功
生成 liquidity_profile.csv 和 liquidity_exclusions.csv
最终 Top10 仍符合 4/3/2/1 桶名额
最终 Top10 仍满足 sector<=4、industry<=2
大型 runs 输出继续不进入 Git
```

结果解读：

```text
生成流动性画像股票数：482
流动性剔除数量：4
进入 Qlib 数据股票数：478
Test 日均 IC：0.002960
Test 日均 Rank IC：0.006525
参与 IC 计算交易日：593
```

剔除股票：

```text
LBTYB：近 20 日平均成交额低于 500 万美元
MAAS：近 60 日成交额中位数低于 200 万美元
RGC：近 20 日平均成交额低于 500 万美元
VFS：近 20 日平均成交额低于 500 万美元
```

最终 Top10：

```text
full_10y：AXTI, AAOI, CHTR, LBRDK
5_10y：NBIS, GTX, RKLB
2_5y：HUT, XMTR
lt_2y：FLY
```

最终 sector 分布：

```text
Technology：3
Telecommunications：2
Industrials：2
Finance：1
Consumer Discretionary：1
Real Estate：1
```

遗留问题：

```text
当前成交额使用 vwap 近似值，不是真实交易所 VWAP
没有 bid-ask spread 和订单簿深度
没有按组合规模估算策略容量
没有把流动性作为模型特征，只作为股票池过滤
尚未使用专业证券主数据
尚未做未来 5 日标签和成本后回测
```

下一阶段准备：

进入第 3 条：证券主数据升级。目标是减少仅靠 Nasdaq public 的 `symbol` 和 `name` 文本规则判断证券类型的误差，补充更稳定的证券类型、上市状态、ADR/ADS、share class 和 primary listing 口径。

产出文件：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10.yaml
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/selection/liquidity.py
analysis/nasdaq_top500_score/selection/__init__.py
tests/analysis/test_stock_pool_selection.py
learning/05-data-expansion/Liquidity Filtering.md
learning/05-data-expansion/Stock Pool Cleaning And History Buckets.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-17 阶段 D.4：证券主数据升级

目标：

把股票池清洗从零散 `symbol/name` 文本规则升级为显式证券主数据表，让每个 symbol 的证券类型、ADR/ADS、share class、ETF/test issue 等字段可复盘。

为什么要做：

普通股、ADR、权证、优先股、债券、unit 和 right 的收益结构与交易属性不同。仅靠模型分数无法识别这些差异，必须先在股票池层面明确哪些证券可以进入普通股研究。

输入数据：

```text
Nasdaq listed：symbol、security_name、market_category、test_issue、financial_status、round_lot_size、ETF
Nasdaq screener：name、market_cap、last_sale、sector、industry
固定行情窗口：2016-05-17 到 2026-05-17
财报来源：SEC EDGAR 10-K / 10-Q / companyfacts
标签：未来 1 日收益
模型：Alpha158 + EDGAR + LightGBM
最终选择：证券主数据 + 流动性过滤 + 历史长度桶名额 + 行业名额约束
```

核心概念：

```text
证券主数据
普通股
ADR/ADS
share class
warrant
preferred
debt
unit/right
ETF/test issue
```

实验动作：

```text
新增 security_master.py
Nasdaq public 数据源合并 listed 与 screener 字段
输出 security_master.csv
输出 security_master_exclusions.csv
报告写入资产类型分布、ADR/ADS 数量、share class 数量和剔除原因
新增证券主数据单元测试
复跑 clean_bucket_top10 配置
```

评价指标：

```text
py_compile 通过
相关单元测试通过
所有 YAML 配置可解析
真实配置运行成功
生成 security_master.csv 和 security_master_exclusions.csv
最终 Top10 仍符合 4/3/2/1 桶名额
最终 Top10 仍满足 sector<=4、industry<=2
大型 runs 输出继续不进入 Git
```

结果解读：

```text
主数据记录数：3533
主数据剔除数：443
ADR/ADS 数量：162
Share class 数量：571
进入 Qlib 数据股票数：478
Test 日均 IC：-0.000519
Test 日均 Rank IC：0.001712
参与 IC 计算交易日：593
```

资产类型分布：

```text
common_stock：2332
ordinary_share：456
warrant：279
adr_ads：162
unknown_equity_like：140
preferred：104
debt：36
unit：15
right：5
depositary_share：4
```

剔除原因：

```text
warrant：279
preferred：104
debt：36
unit：15
right：5
depositary_share：4
```

最终 Top10：

```text
full_10y：AAOI, IBRX, AXTI, FLEX
5_10y：CELC, QS, LQDA
2_5y：LUNR, CORZ
lt_2y：SNDK
```

最终 sector 分布：

```text
Technology：4
Health Care：3
Industrials：1
Miscellaneous：1
Finance：1
```

遗留问题：

```text
当前证券主数据不是历史 PIT 口径
unknown_equity_like 仍需后续复核
ADR/ADS 只是保留和标记，尚未单独处理国家、汇率和会计口径
没有完整 primary listing / secondary listing 字段
尚未做未来 5 日标签和成本后回测
```

下一阶段准备：

进入第 4 条：未来 5 日收益标签。默认新增 5 日标签配置 `Ref($close, -6) / Ref($close, -1) - 1`，并与当前 1 日标签对比 IC、Rank IC、Top10 稳定性。

产出文件：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10.yaml
analysis/nasdaq_top500_score/data_sources/nasdaq_public.py
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/selection/security_master.py
analysis/nasdaq_top500_score/selection/__init__.py
tests/analysis/test_stock_pool_selection.py
learning/05-data-expansion/Security Master Data.md
learning/05-data-expansion/Stock Pool Cleaning And History Buckets.md
learning/05-data-expansion/Liquidity Filtering.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-17 阶段 C / D.5：未来 5 日收益标签

目标：

把模型预测目标从未来 1 日收益升级为未来 5 日收益，并在相同股票池、数据源、特征、模型和筛选规则下对比 IC、Rank IC 与 Top10 稳定性。

为什么要做：

1 日收益受隔夜消息、短期资金流和微观结构噪声影响很大。5 日收益可能更平滑，更适合学习中短期趋势、财报后反应和事件逐步定价。

输入数据：

```text
股票池：Nasdaq public 当前股票池
固定行情窗口：2016-05-17 到 2026-05-17
证券主数据：已启用
流动性过滤：已启用
财报来源：SEC EDGAR 10-K / 10-Q / companyfacts
特征：Alpha158 + EDGAR
模型：LightGBM
最终选择：历史长度桶名额 + 行业名额约束
```

核心概念：

```text
未来收益标签
1 日收益
5 日收益
t+1 建仓参考
t+1 到 t+6 持有 5 个交易日
IC / Rank IC
Top10 稳定性
```

实验动作：

```text
新增 nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d.yaml
标签改为 Ref($close, -6) / Ref($close, -1) - 1
复跑完整 Qlib 流水线
对比 1 日和 5 日标签的 IC、Rank IC、Top10 重叠和行业分布
更新 Labels And Future Returns 和新增 Five Day Future Return Label
```

评价指标：

```text
py_compile 通过
所有 YAML 配置可解析
真实 5 日配置运行成功
生成 report.md、predictions.csv、selected_top10.csv、resolved_config.yaml
Markdown 链接无断链
大型 runs 输出继续不进入 Git
```

结果解读：

```text
1 日标签 IC：-0.000519
1 日标签 Rank IC：0.001712
1 日标签 IC 交易日：593
5 日标签 IC：0.036729
5 日标签 Rank IC：0.016211
5 日标签 IC 交易日：589
```

1 日 Top10：

```text
AAOI, IBRX, LUNR, AXTI, FLEX, SNDK, CELC, QS, CORZ, LQDA
```

5 日 Top10：

```text
IBRX, LUNR, CYTK, LQDA, ONDS, BILI, KTOS, NTNX, TEM, TRI
```

Top10 重叠：

```text
IBRX
LQDA
LUNR
```

遗留问题：

```text
5 日 IC 更高不等于策略可交易
尚未处理持有期重叠
尚未做成本后净值曲线
尚未计算换手、最大回撤、信息比率
ADR/ADS 和 unknown_equity_like 仍需后续复核
```

下一阶段准备：

进入第 5 条：TopK 成本后回测。目标是把 5 日标签下的模型分数转成组合净值，计算成本后收益、最大回撤、换手率和收益风险比。

产出文件：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d.yaml
learning/02-signals-and-labels/Five Day Future Return Label.md
learning/02-signals-and-labels/Labels And Future Returns.md
learning/00-start-here/Qlib Commands.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-17 第 5 条：TopK 成本后回测

目标：

把未来 5 日收益标签下的模型分数转成组合净值，记录成本后收益、最大回撤、换手率和收益风险比。

为什么要做：

IC / Rank IC 只衡量模型分数和未来收益的横截面相关性，不代表组合能交易。TopK 回测把排序信号变成持仓、调仓、成本和净值，能看到策略层面的风险。

输入数据：

```text
Nasdaq public 当前市值前 500
固定行情窗口：2016-05-17 到 2026-05-17
训练期：2016-08-11 到 2021-12-31
验证期：2022-01-03 到 2023-12-29
测试期：2024-01-02 到 2026-05-15
Alpha158 价格成交量特征
SEC EDGAR PIT 财报估值特征
未来 5 日收益标签
```

核心概念：

```text
信号日：模型打分当天
入场日：信号日后 1 个交易日
退出日：入场后第 5 个交易日
TopK：按 score 排名前 K
换手率：新旧持仓权重变化之和
成本后收益：毛收益 - 交易成本
最大回撤：净值从高点回落的最大幅度
信息比率：平均收益 / 收益波动，按年化调仓期换算
```

实验动作：

```text
新增 analysis/nasdaq_top500_score/backtest.py
主流水线生成 test_predictions.csv
对测试期所有信号日做非重叠 5 日 Top10 回测
继续使用历史长度桶名额 4/3/2/1
继续使用 sector <= 4、industry <= 2 行业约束
设置单边交易成本 10 bps
输出 backtest_nav.csv、backtest_positions.csv、backtest_summary.yaml
更新 report.md 和学习文档
```

评价指标：

```text
回测期数
累计收益
年化收益
年化波动
信息比率
最大回撤
胜率
平均换手
累计成本扣减
平均持仓数量
```

结果解读：

```text
回测期数：118
起始入场日：2024-01-03
最终退出日：2026-05-12
累计收益：2225.10%
年化收益：283.38%
年化波动：49.88%
信息比率：2.966
最大回撤：-18.11%
胜率：66.95%
平均换手：110.93%
累计成本扣减：13.09%
平均持仓数量：9.31
```

这个结果说明当前学习口径下，模型排序可以形成正收益组合。但收益非常高，必须谨慎解读：它不是投资建议，也不是严谨生产级回测结论。

遗留问题：

```text
股票池仍使用当前 Nasdaq public snapshot，不是历史 PIT 成分池
没有退市股票，仍有幸存者偏差
行情不是专业复权数据
只用收盘价成交，没有真实滑点、冲击成本和成交容量
没有和 Nasdaq 100、QQQ 或 S&P 500 做基准超额收益比较
没有分析行业暴露和单票贡献
没有处理重叠持有期组合
```

下一阶段准备：

进入第 6 条：基准与风险复盘。目标是把绝对收益拆成基准收益、超额收益、行业暴露、单票贡献、换手和回撤来源。

产出文件：

```text
analysis/nasdaq_top500_score/backtest.py
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d.yaml
tests/analysis/test_topk_backtest.py
learning/04-strategy-backtest/TopK Cost Backtest.md
learning/04-strategy-backtest/Backtest And Costs.md
learning/04-strategy-backtest/TopK Strategy.md
learning/00-start-here/Qlib Commands.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-18 阶段 5.5：行业暴露对照实验

目标：

把“行业押注”和“个股选择”拆开验证。用同一批模型分数、同一训练集、同一测试期，只改变 Top10 组合构建规则。

为什么要做：

行业暴露不是坏事，但必须知道它是有意识的策略来源，还是模型无意中集中押注。如果不拆开看，就无法判断收益来自行业上涨、个股选择，还是两者混合。

输入数据：

```text
Nasdaq public as-of 2023-12-31 近似冻结 Top500
固定行情窗口：2016-05-17 到 2026-05-17
训练期：2016-08-11 到 2021-12-31
验证期：2022-01-03 到 2023-12-29
测试期：2024-01-02 到 2026-05-15
Alpha158 价格成交量特征
SEC EDGAR PIT 财报估值特征
未来 5 日收益标签
同一份 test_predictions.csv
```

核心概念：

```text
行业暴露：组合持仓集中在哪些 sector / industry
行业约束：限制单个 sector / industry 最多持仓数量
行业增强：允许近期强势 sector 多拿一点名额，但仍有上限
Sector HHI：行业权重平方和，越高代表越集中
```

实验动作：

```text
新增 strategy_comparison 配置
新增 unconstrained_top10：不限制行业
新增 sector_capped_top10：sector <= 3，industry <= 2
新增 sector_momentum_tilt_top10：强势 sector 可多 1 个名额，sector 上限 4
三组策略复用同一批模型预测分数
每组策略输出独立回测、基准和贡献归因
新增 strategy_comparison.csv 汇总三组结果
```

评价指标：

```text
累计收益
年化收益
最大回撤
超额累计收益
年化 Alpha
Beta
最大平均 sector 暴露
最大单期 sector 权重
Sector HHI
```

结果解读：

```text
unconstrained_top10：
  累计收益 24.77%
  年化收益 9.91%
  最大回撤 -31.47%
  超额累计收益 -30.21%
  年化 Alpha -14.17%
  最大平均 sector 暴露 Health Care 34.55%
  Sector HHI 0.312

sector_capped_top10：
  累计收益 76.79%
  年化收益 27.55%
  最大回撤 -29.58%
  超额累计收益 -1.11%
  年化 Alpha 1.87%
  最大平均 sector 暴露 Health Care 27.89%
  Sector HHI 0.231

sector_momentum_tilt_top10：
  累计收益 67.91%
  年化收益 24.78%
  最大回撤 -30.71%
  超额累计收益 -6.08%
  年化 Alpha -0.86%
  最大平均 sector 暴露 Health Care 29.43%
  Sector HHI 0.244
```

当前判断：

```text
行业约束明显优于原始不限制 Top10。
行业增强优于原始不限制 Top10，但弱于普通行业约束。
行业约束这轮 alpha 略微转正，但幅度仍小。
当前模型更适合保留行业风险控制，再继续验证行业内选股能力。
```

遗留问题：

```text
行业分类仍不是历史 PIT 行业分类
NASDAQCOM 不是总回报复权基准
行业动量只用 60 日等权收益，信号较粗糙
没有真实滑点、冲击成本和容量约束
没有退市股票，仍有幸存者偏差
```

下一阶段准备：

```text
做行业内选股复盘：每个 sector 内单独看 score 排名与未来收益
比较不同 max_sector 参数：2 / 3 / 4
尝试行业等权组合规则
如果行业动量继续保留，需要单独验证行业动量信号本身
```

产出文件：

```text
analysis/nasdaq_top500_score/backtest.py
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/selection/history_buckets.py
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
tests/analysis/test_topk_backtest.py
tests/analysis/test_stock_pool_selection.py
learning/06-portfolio-risk/Industry Exposure Strategy Comparison.md
learning/06-portfolio-risk/Industry Neutralization.md
learning/00-start-here/Qlib Commands.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-18 阶段 5.6：行业内选股复盘

目标：

验证模型在同一个 sector 内部，是否能把未来收益更好的股票排到更前面。

为什么要做：

行业暴露对照已经说明“限制行业集中度”有帮助，但它还不能说明模型有行业内选股能力。行业内复盘把同一个 sector 的股票放在一起比较，排除行业之间涨跌差异的影响。

输入数据：

```text
Nasdaq public as-of 2023-12-31 近似冻结 Top500
测试期 test_predictions.csv
universe.csv 的 sector / industry
qlib_source_csv 的日线行情
当前 backtest 的 PIT 历史长度和流动性过滤规则
未来 5 日实际收益
```

核心概念：

```text
行业内 IC：同一 sector 内 score 与未来收益的 Pearson 相关
行业内 Rank IC：同一 sector 内 score 排名与未来收益排名的 Spearman 相关
Top-Bottom spread：sector 内 score 前 20% 平均收益 - 后 20% 平均收益
spread_positive_rate：Top-Bottom spread 为正的交易日比例
```

实验动作：

```text
新增 within_sector_review 配置
新增 within_sector.py 复盘模块
每个信号日按 sector / industry 分组
沿用信号日后 1 个交易日入场、持有 5 个交易日的收益口径
sector 内可交易股票少于 10 时不计算 Top/Bottom spread
生成 daily metrics、sector summary、industry summary、quantile returns 和 YAML 摘要
```

评价指标：

```text
sector 覆盖数量
industry 覆盖数量
有效交易日数量
平均可交易股票数
行业内 IC
行业内 Rank IC
Top-Bottom spread
spread_positive_rate
```

结果解读：

```text
sector 数量：12
industry 数量：93
低样本 sector 数量：0
有效信号期数：118

Rank IC 较好：
  Telecommunications：0.0728，Top-Bottom spread 1.4920%
  Health Care：0.0215，Top-Bottom spread 0.3350%

Top-Bottom spread 较好：
  Telecommunications：1.4920%
  Industrials：0.3859%
  Health Care：0.3350%

排序较弱：
  Consumer Discretionary：Rank IC -0.0218，spread -0.3811%
  Technology：Rank IC -0.0128，spread -0.2904%
  Finance：Rank IC -0.0224，spread -0.2104%
```

当前判断：

```text
模型的行业内选股能力并不均匀。
Telecommunications、Health Care、Industrials 有一些正向迹象。
Technology、Consumer Discretionary、Finance 内部排序偏弱。
行业约束有必要继续保留，但下一步要看是否需要 sector-specific 特征、标签或模型。
```

遗留问题：

```text
sector / industry 仍来自当前 Nasdaq public snapshot，不是历史 PIT 分类
小行业 Rank IC 容易受少数股票影响
没有专业复权总回报行情和退市股票
没有按 sector 单独训练模型
没有比较不同行业的最佳标签周期
```

下一阶段准备：

```text
做行业参数敏感性：max_sector=2/3/4
对 Technology、Health Care、Consumer Discretionary 做错误样本复盘
考虑 sector-specific 模型或 sector-specific TopK
```

产出文件：

```text
analysis/nasdaq_top500_score/within_sector.py
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
tests/analysis/test_within_sector_review.py
learning/06-portfolio-risk/Within Sector Stock Selection Review.md
learning/06-portfolio-risk/Industry Exposure Strategy Comparison.md
learning/06-portfolio-risk/Industry Neutralization.md
learning/00-start-here/Qlib Commands.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-18 阶段 5.7A/B：行业约束参数敏感性

目标：

比较不同 `max_sector` 约束强度，判断当前 Top10 组合中单个 sector 最多持仓几只更合适。

为什么要做：

行业内选股复盘说明模型在不同行业里的排序能力不均匀。组合层面需要知道行业约束是应该更紧、更松，还是继续保留当前中等约束。

输入数据：

```text
Nasdaq public as-of 2023-12-31 近似冻结 Top500
测试期 test_predictions.csv
同一批 Qlib LightGBM score
同一套 PIT 历史长度和流动性过滤
同一套未来 5 日收益回测口径
```

核心概念：

```text
max_sector=2：强约束，降低行业集中度
max_sector=3：中等约束，收益和分散之间折中
max_sector=4：宽松约束，更接近自然行业暴露
Sector HHI：行业权重平方和，越高表示行业越集中
```

实验动作：

```text
扩展 strategy_comparison variants
新增 sector_cap_2_top10、sector_cap_3_top10、sector_cap_4_top10
保留 unconstrained_top10 作为自然暴露基线
保留 sector_momentum_tilt_top10 作为补充观察
同一模型只跑一次，五个策略复用同一批测试期预测分数
报告自动输出收益、回撤、超额收益、alpha、beta 和行业集中度
```

评价指标：

```text
累计收益
年化收益
最大回撤
超额累计收益
年化 Alpha
Beta
最大平均 sector 暴露
Sector HHI
```

结果解读：

```text
unconstrained_top10：
  累计收益 24.77%
  年化收益 9.91%
  最大回撤 -31.47%
  超额累计收益 -30.21%
  Sector HHI 0.312

sector_cap_2_top10：
  累计收益 62.84%
  年化收益 23.15%
  最大回撤 -27.38%
  超额累计收益 -8.92%
  Sector HHI 0.176

sector_cap_3_top10：
  累计收益 76.79%
  年化收益 27.55%
  最大回撤 -29.58%
  超额累计收益 -1.11%
  Sector HHI 0.231

sector_cap_4_top10：
  累计收益 52.19%
  年化收益 19.65%
  最大回撤 -31.05%
  超额累计收益 -14.87%
  Sector HHI 0.266

sector_momentum_tilt_top10：
  累计收益 67.91%
  年化收益 24.78%
  最大回撤 -30.71%
  超额累计收益 -6.08%
  Sector HHI 0.244
```

当前判断：

```text
max_sector=3 年化收益和超额收益最好。
max_sector=2 回撤和行业集中度最好，但收益偏保守。
max_sector=4 偏松，收益、回撤和集中度都弱于 max_sector=3。
简单 60 日行业动量增强没有超过固定 max_sector=3。
当前默认保留 max_sector=3、max_industry=2。
```

遗留问题：

```text
sector / industry 仍不是历史 PIT 分类
NASDAQCOM 不是总回报复权基准
没有真实滑点、冲击成本和容量约束
没有退市股票，仍有幸存者偏差
max_sector 只控制数量，不控制相对基准行业偏离
```

下一阶段准备：

```text
对 Technology、Health Care、Consumer Discretionary 做 sector-specific 错误复盘
检查模型排错股票是否集中在高估值、小市值、低流动性、亏损公司或 ADR
再决定改特征、改标签，还是做行业专属模型
```

产出文件：

```text
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
tests/analysis/test_topk_backtest.py
learning/06-portfolio-risk/Industry Constraint Sensitivity.md
learning/06-portfolio-risk/Industry Exposure Strategy Comparison.md
learning/06-portfolio-risk/Industry Neutralization.md
learning/00-start-here/Qlib Commands.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-19 阶段 5.7C：重点行业错误复盘

目标：

解释模型在 `Technology`、`Health Care`、`Consumer Discretionary` 三个行业里为什么排对或排错。

为什么要做：

行业内选股复盘告诉我们哪些 sector 的 Rank IC 和 Top-Bottom spread 偏强或偏弱，但还没有解释错误来自哪里。5.7C 把行业内样本拆成高分赢家、高分输家、低分赢家和低分输家，观察模型喜欢什么、漏掉什么。

输入数据：

```text
test_predictions.csv
fundamental_features.parquet
universe.csv
history_buckets.csv
qlib_source_csv/
backtest_positions.csv
```

核心概念：

```text
high_score_winners：模型高分，未来 5 日收益也靠前
high_score_losers：模型高分，但未来 5 日收益靠后
low_score_winners：模型低分，但未来 5 日收益靠前
low_score_losers：模型低分，未来 5 日收益也靠后
```

实验动作：

```text
新增 sector_error_review 配置
新增 sector_error_review.py 复盘模块
只分析 Technology、Health Care、Consumer Discretionary
沿用信号日后 1 个交易日入场、持有 5 个交易日收益口径
合并 EDGAR 财报估值、历史长度、市值、ADR、动量、波动率和流动性特征
生成错误样本、特征差异和 YAML 摘要
```

评价指标：

```text
行业内 Rank IC
Top-Bottom spread
高分输家率
低分赢家率
财报覆盖率
高估值、短历史、低流动性、ADR、亏损、近期披露集中度
```

结果解读：

```text
Technology：
  诊断 model_weak
  Rank IC -0.0214
  Top-Bottom spread -0.5044%
  高分输家率 52.63%
  低分赢家率 50.93%
  高分输家中短历史股票占比 91.61%
  高分输家中亏损公司占比 52.82%

Health Care：
  诊断 mixed_or_noisy
  Rank IC 0.0191
  Top-Bottom spread 0.5627%
  高分输家率 49.83%
  低分赢家率 46.68%
  高分输家中高估值占比 62.98%
  高分输家中亏损公司占比 80.81%

Consumer Discretionary：
  诊断 model_weak
  Rank IC -0.0230
  Top-Bottom spread -0.2560%
  高分输家率 51.97%
  低分赢家率 52.99%
  高分输家中短历史股票占比 84.38%
  高分输家中亏损公司占比 52.93%
```

当前判断：

```text
Technology 和 Consumer Discretionary 的行业内排序偏弱，需要优先排查特征和标签。
Health Care 有一点正向迹象，但事件驱动噪声很大，不能只靠结构化财报和价格特征。
三个行业共同问题是：短历史股票在高分输家中占比很高。
模型容易漏掉更大市值、更高流动性、近期动量更强的低分赢家。
```

额外发现：

```text
本次完整运行重新训练了一次 LightGBM，模型分数和 5.7A/B 记录时略有差异。
后续必须固定随机种子或复用缓存 test_predictions.csv，否则跨阶段比较会混入重训波动。
```

遗留问题：

```text
sector / industry 仍不是历史 PIT 分类
错误解释只用特征均值差异，没有 SHAP
Health Care 缺少临床试验、审批和融资等事件数据
Technology 和 Consumer Discretionary 还没有行业内 size / liquidity / momentum 相对特征
短历史股票是否应该继续保留 1 个名额仍需单独评估
```

下一阶段准备：

```text
固定训练随机性或缓存 test_predictions.csv
增加 size / liquidity / momentum 的行业内相对特征
对 Health Care 设计事件数据接入计划
考虑 Technology / Consumer Discretionary 的 sector-specific 模型或过滤规则
```

产出文件：

```text
analysis/nasdaq_top500_score/sector_error_review.py
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
tests/analysis/test_sector_error_review.py
learning/06-portfolio-risk/Sector Specific Error Review.md
learning/00-start-here/Qlib Commands.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-19 阶段 5.8A：训练复现控制与预测分数缓存

目标：

固定模型训练随机性，并允许后续复盘直接复用已有 `test_predictions.csv`。

为什么要做：

5.7C 发现完整运行会重新训练 LightGBM，导致模型分数和 5.7A/B 记录时略有差异。后续我们要判断新特征、短历史惩罚和行业约束是否有效，必须先减少重训波动。

输入数据：

```text
frozen 配置
当前 Nasdaq Top500 10 年窗口数据
现有 test_predictions.csv
现有 TopK / 回测 / 行业复盘模块
```

核心概念：

```text
重新训练：改特征、标签或模型参数时使用
复用预测：只改 TopK、行业约束或错误复盘时使用
seed：固定随机性，让同一实验更容易复现
prediction_source：报告中记录分数来自 trained 还是 cached_test_predictions
```

实验动作：

```text
新增 training.seed / deterministic / reuse_test_predictions 配置
给 LightGBM 增加 seed、bagging_seed、feature_fraction_seed、data_random_seed、drop_seed
在训练入口设置 Python 和 NumPy 随机种子
支持 reuse_test_predictions=true 时读取已有 test_predictions.csv
报告新增训练复现控制章节
新增学习文档说明什么时候重训、什么时候复用分数
```

评价指标：

```text
配置可解析
测试期预测缓存格式可读取
预测分数可转换回 Qlib MultiIndex Series
默认配置仍保持重新训练
report.md 可记录预测分数来源
```

结果解读：

```text
阶段 5.8A 不追求提高收益或 IC。
它解决的是实验可比性问题。
后续只改组合规则时，应复用 test_predictions.csv。
后续加入新模型输入时，应重新训练，但使用固定 seed。
```

遗留问题：

```text
LightGBM 的 deterministic 设置可以降低随机波动，但不同硬件、线程库或依赖版本仍可能有细微差异。
当前没有把模型对象本身持久化，只缓存测试期预测分数。
如果上游数据重新下载并变化，复用旧 test_predictions.csv 需要同时核对 resolved_config.yaml。
```

下一阶段准备：

```text
阶段 5.8B：加入 size / liquidity / momentum 的行业内相对特征
重新训练 frozen 配置
观察 Technology 和 Consumer Discretionary 的行业内 Rank IC 是否改善
```

产出文件：

```text
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
tests/analysis/test_fixed_window_config.py
learning/03-modeling/Experiment Reproducibility And Prediction Cache.md
learning/03-modeling/Model Validation.md
learning/00-start-here/Qlib Commands.md
learning/00-start-here/Qlib Quant Learning Index.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```
