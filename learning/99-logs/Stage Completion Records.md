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

## 2026-05-21 CRSP 数据源迁移工程骨架

目标：

```text
把默认研究数据源从当前快照式学习数据，迁移到本地 CRSP daily 数据。
建立 2000-01-03 到 2025-12-31 固定窗口。
股票池改为 US Common Equity 月度动态市值 Top500。
策略调仓改为每 10 个交易日一次。
```

为什么要做：

```text
当前 nasdaq_public 股票池存在幸存者偏差、当前市值反推和当前证券状态污染历史的问题。
CRSP 提供 PERMNO、DlyCap、DlyRet、DlyRetx 和退市/状态字段，更适合做严格研究回测。
```

输入数据：

```text
analysis/nasdaq_top500_score/runs/crsp_daily_raw/crsp0025.csv
CRSP daily columns: PERMNO, DlyCap, DlyRet, DlyRetx, DlyOpen, DlyHigh, DlyLow, DlyClose, DlyVol 等
```

核心概念：

```text
PERMNO：CRSP 永久证券 ID，用作 Qlib instrument
monthly dynamic Top500：每月月末按当时 DlyCap 选市值前 500
membership effective_start：从下一交易日生效，避免当日收盘信息提前使用
CRSP return label：用 DlyRet 构造未来 10 个交易日总收益
research-adjusted OHLCV：用 DlyRetx 构造拆股调整后的研究价格
```

实验动作：

```text
新增 CRSP 数据源迁移学习文档
新增 data.source=crsp 适配器
新增 raw CSV -> Parquet warehouse 构建逻辑
新增月度动态 Top500 membership 生成逻辑
新增 Qlib source CSV 生成逻辑，包含 label_10d_total_return
回测选股层接入 dynamic membership 过滤
新增 CRSP baseline 和 CRSP macro 配置
新增 CRSP fixture 单元测试
```

评价指标：

```text
先看工程验收，不看收益。
配置可解析。
fixture 能生成 warehouse、membership、source CSV。
membership 只在有效期内参与选股。
10 日标签只使用未来收益，且非 membership 日期置为 NaN。
```

结果解读：

```text
CRSP warehouse 已完成真实构建。
覆盖 2000-01-03 到 2025-12-31，共 49,886,907 行、25,306 个 instrument。
月度动态 Top500 覆盖 311 个月，每月 500 个唯一证券，历史上共有 1,702 个 PERMNO 进入过股票池。
生成 1,669 个 Qlib source CSV，33 个短历史证券因历史行数不足被跳过。
Alpha158-only baseline 已完整跑通，但测试期 IC=-0.013744、Rank IC=-0.007421。
两周调仓 Top10 成本后累计收益 4.61%，年化 2.30%，最大回撤 -16.69%，明显跑输同期 S&P 500。
```

遗留问题：

```text
Alpha158-only 在 CRSP 10 日标签上没有正向预测力。
模型早停在第 1 轮，说明当前特征/标签/样本口径需要复盘。
EDGAR 暂未接入 CRSP PERMNO -> CIK 映射。
宏观增强配置已准备，但尚未运行。
行业分类暂用 CRSP SIC/NAICS sidecar，不进入默认行业约束。
成本敏感性较强，25bps 后多数压力测试口径转负。
```

下一阶段准备：

```text
运行 crsp_alpha158_macro_10d_2000_2025.yaml 做宏观增量比较。
复盘 Alpha158-only 为什么 IC 为负：按年份、行业、持仓贡献和标签分布拆解。
考虑建立 CRSP label/feature diagnostics：10 日收益分布、membership 覆盖、短历史/低流动性样本影响。
后续再做 EDGAR PERMNO -> CIK 映射覆盖率评估。
```

产出文件：

```text
learning/05-data-expansion/CRSP Data Source Migration Plan.md
analysis/nasdaq_top500_score/data_sources/crsp.py
analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_10d_2000_2025.yaml
analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_macro_10d_2000_2025.yaml
tests/analysis/test_crsp_data_source.py
```

## 2026-05-22 CRSP 宏观增强对照实验

目标：

```text
在 CRSP 月度动态 Top500 股票池上加入 FRED/ALFRED 宏观特征。
比较 Alpha158-only 和 Alpha158 + macro 的 IC、Rank IC、TopK 回测和压力测试。
```

为什么要做：

```text
Alpha158-only 在 CRSP 10 日收益标签上 IC 和 Rank IC 都为负。
需要验证宏观状态是否能改善模型对不同市场环境下价格成交量信号的理解。
```

输入数据：

```text
CRSP daily warehouse: 2000-01-03 到 2025-12-31
CRSP 月度动态 US Common Equity 市值 Top500 membership
FRED/ALFRED macro raw observations: 1998-12-01 到 2025-12-31
macro_features: 11,129,378 行，52 个特征列
训练: 2000-01-03 到 2021-12-31
验证: 2022-01-03 到 2023-12-29
测试: 2024-01-02 到 2025-12-31
```

核心概念：

```text
raw macro：同一天对所有股票相同的宏观状态变量
Rank IC：横截面排序能力，比收益曲线更能反映模型是否排对股票
beta：策略对市场涨跌的暴露；beta 升高会提高牛市收益，但不等于纯 alpha
压力测试：提高成本、改变入场价格和入场延迟，检查收益是否稳健
```

实验动作：

```text
运行 crsp_alpha158_macro_10d_2000_2025.yaml
构建 PIT 宏观特征并合并到 Alpha158 特征矩阵
训练 LightGBM
生成 predictions、test_predictions、TopK 回测、benchmark 对比和 24 组压力测试
新增 CRSP macro 增强结果复盘笔记
```

评价指标：

```text
IC / Rank IC
累计收益 / 年化收益 / 最大回撤
相对 S&P 500 超额收益
alpha / beta
成本压力测试下的收益衰减
```

结果解读：

```text
Alpha158-only：IC=-0.013744，Rank IC=-0.007421，累计收益 4.61%，年化 2.30%，alpha=-15.20%，beta=0.981
Alpha158 + macro：IC=-0.005139，Rank IC=0.007221，累计收益 59.74%，年化 26.62%，alpha=0.36%，beta=1.329
```

宏观增强显著改善了 TopK 回测和 Rank IC，但年化 alpha 接近 0，beta 明显升高。因此当前改善不能简单解释为纯选股 alpha，而更像“宏观状态帮助模型提高了风险暴露和部分排序质量”。

遗留问题：

```text
部分日频金融宏观序列仍是 latest 模式，只做 observation_date 后一交易日生效，不是完整 vintage。
平均换手约 172%，成本从 10bps 提高到 50bps 后年化收益降到 6.56%。
raw macro 对同一天所有股票相同，不一定是最适合横截面选股的输入形式。
EDGAR 仍未接入 CRSP PERMNO -> CIK 覆盖率评估。
```

下一阶段准备：

```text
做 CRSP macro interaction 实验，把 raw macro 转成 宏观状态 × 股票差异。
做换手控制，避免收益完全依赖低成本假设。
做 EDGAR PERMNO -> CIK 覆盖率报告，再决定是否接入财报特征。
```

产出文件：

```text
analysis/nasdaq_top500_score/runs/crsp_alpha158_macro_10d_2000_2025/report.md
analysis/nasdaq_top500_score/runs/crsp_alpha158_macro_10d_2000_2025/backtest_stress_matrix.csv
analysis/nasdaq_top500_score/runs/crsp_alpha158_macro_10d_2000_2025/macro_features.parquet
learning/05-data-expansion/CRSP Macro Enhanced Result Review.md
learning/README.md
learning/00-start-here/Qlib Quant Learning Index.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-22 阶段 CRSP-3：10 日保守宏观对照

目标：

以 10 日保守 Alpha158-only 模型作为新 baseline，比较 raw macro 和 macro interaction 是否真正带来增量。

为什么要做：

旧宏观实验继承的是激进参数，不能和新的 10 日保守 baseline 直接比较。本阶段固定股票池、标签、切分、模型参数和回测口径，只改变宏观输入方式。

输入数据：

```text
CRSP 2000-2025 日级动态 Top500
Alpha158 价格成交量特征
FRED/ALFRED 宏观特征
CRSP market-derived 动量/波动率特征
2024-2025 测试期
```

核心概念：

```text
raw macro：同一天所有股票相同的市场状态变量
macro interaction：宏观状态 × 股票自身动量/波动率
公平对照：只改变特征输入，不改变股票池、标签、模型参数和回测口径
```

实验动作：

```text
新增 raw macro conservative 配置
新增 macro interaction conservative 配置
新增 crsp_macro_conservative_comparison.py
运行两组真实训练、回测、压力测试和 diagnostics
生成三组对比表
```

评价指标：

```text
IC / Rank IC
best iteration / best valid l2
年化收益 / 最大回撤 / 年化 alpha / beta
50bps 成本压力收益
宏观特征和交互特征 failure count
```

结果解读：

```text
Alpha158-only：Rank IC=0.006466，年化 33.91%，alpha 10.11%，50bps 后 15.70%
direct macro：Rank IC=-0.015064，年化 17.89%，alpha 0.52%，50bps 后 -1.21%
macro interactions：Rank IC=0.006653，年化 21.08%，alpha -1.67%，50bps 后 3.66%
```

raw macro 明显拖累。macro interaction 的 Rank IC 略好于 baseline，但收益、alpha、成本压力都不如 baseline，因此暂时不能作为默认主策略。

遗留问题：

```text
宏观交互是否只在特定 regime 下有效尚未验证
8 个交互中可能有少数有效、少数拖累
IC 仍然很弱，不能把收益改善或下降过度解释
```

下一阶段准备：

```text
做 CRSP macro interaction ablation
做 high VIX / rate up / credit stress 等 regime 复盘
如果仍无稳定增量，宏观只保留为复盘维度
```

产出文件：

```text
analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_macro_10d_conservative_2000_2025.yaml
analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_macro_interactions_10d_conservative_2000_2025.yaml
analysis/nasdaq_top500_score/crsp_macro_conservative_comparison.py
tests/analysis/test_crsp_macro_conservative_comparison.py
learning/05-data-expansion/CRSP Macro Conservative Comparison.md
```

## 2026-05-22 CRSP 早停与负 IC 诊断

目标：

```text
判断 CRSP Alpha158-only 负 IC 和第 1 轮早停来自数据适配错误、标签设计问题、特征无效、训练切分变化，还是模型参数过强。
```

为什么要做：

```text
早停本身不是 bug，但第 1 轮早停是强烈诊断信号。
如果标签、复权或 membership 有错，后续调模型没有意义。
```

输入数据：

```text
CRSP warehouse: 2000-01-03 到 2025-12-31
CRSP Alpha158-only run: crsp_alpha158_10d_2000_2025
Qlib source CSV / Qlib bin / membership.csv
```

核心概念：

```text
标签复算：用 DlyRet[t+1:t+10] 重算 label_10d_total_return
复权一致性：adjusted close 日收益必须接近 DlyRetx
membership mask：非动态 Top500 生效期内样本不能参与训练
早停对照：同一数据下改变模型复杂度，观察是否仍立即停止
```

实验动作：

```text
新增 crsp_diagnostics.py 只读诊断模块
新增 label、price adjustment、membership、Alpha158 feature IC、early stopping、label horizon 对照输出
运行真实 CRSP baseline 诊断
新增诊断学习文档
```

评价指标：

```text
标签复算误差
adjusted close vs DlyRetx 误差
非 membership 日期 label 非空数量
Alpha158 缺失率、常数列、单因子 IC
current / conservative / tiny 模型 best iteration
5/10/20 日标签 best iteration
```

结果解读：

```text
标签抽样复算最大误差 9.8879e-17，全量最大误差 2.2204e-16。
adjusted close vs DlyRetx 平均绝对误差 9.5685e-17，最大误差 3.2085e-14。
311 个月动态 Top500 全部通过，每月 500 只，membership 外 label 非空行数为 0。
Alpha158 平均缺失率低于 0.003%，常数列为 0。
current best_iteration=1，conservative best_iteration=111，tiny best_iteration=120。
```

当前更支持的结论是：CRSP 数据适配主链路通过；早停和负 IC 更像是 Alpha158 对当前 10 日收益目标信号弱，以及当前 LightGBM 参数过拟合太快。

遗留问题：

```text
OHLC violation rate 约 0.25%，比例低但后续可以抽样核对。
10 日标签相比 5 日和 20 日更早早停，需要进一步对照。
当前只诊断 Alpha158-only；宏观增强和后续交互模型也应复用这套诊断口径。
```

下一阶段准备：

```text
做保守 LightGBM 参数正式 baseline。
做 5 日、10 日、20 日标签对照。
拆 Alpha158 特征组，验证波动率、动量、反转、量价特征哪类有效。
```

产出文件：

```text
analysis/nasdaq_top500_score/crsp_diagnostics.py
tests/analysis/test_crsp_diagnostics.py
analysis/nasdaq_top500_score/runs/crsp_alpha158_10d_2000_2025/diagnostic_summary.md
analysis/nasdaq_top500_score/runs/crsp_alpha158_10d_2000_2025/feature_ic_summary.csv
analysis/nasdaq_top500_score/runs/crsp_alpha158_10d_2000_2025/early_stopping_variants.csv
analysis/nasdaq_top500_score/runs/crsp_alpha158_10d_2000_2025/label_horizon_comparison.csv
learning/05-data-expansion/CRSP Early Stopping And Negative IC Diagnostics.md
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

## 2026-05-20 阶段 E.5：Sharadar Strict Launch PIT 数据源接口

目标：

```text
用 Sharadar / Nasdaq Data Link 替代当前 nasdaq_public 近似冻结股票池，
构建 2023-12-31 当时可见的 launch PIT 股票池。
```

为什么要做：

```text
当前 nasdaq_public 缺退市股票和历史证券主数据。
approximate_market_cap_asof 使用当前市值反推历史市值，存在高风险未来信息。
Norgate 需要 Windows/Data Updater/订阅，Mac 本地不方便真实验证。
Sharadar 通过 API 提供 active + delisted、价格、基本面和元数据，适合作为个人可落地路线。
```

输入数据：

```text
SHARADAR/TICKERS
SHARADAR/SEP
SHARADAR/SF1
SHARADAR/DAILY
SHARADAR/INDICATORS
```

核心概念：

```text
capability probe：先验收字段和订阅权限，再允许训练
launch_pit_2023：用 2023-12-29 当时可见数据构建测试启动股票池
PIT market cap：使用 as-of 当时的市值或股本，不使用当前市值反推
strict headline：只有通过数据验收的结果才可作为严格主结论
```

实验动作：

```text
新增 SharadarDataSource
新增 SharadarClient
新增 provider capability 输出
新增 strict_sharadar_* 配置
扩展 strict_pit 和 data_quality 对 sharadar 的识别
新增 fake Sharadar client 单元测试
```

评价指标：

```text
provider_capability_summary.yaml strict_capability_pass
pit_universe_validation.csv blocking checks
market_cap_validation.csv 是否存在当前市值反推
security_master_validation.csv 是否具备 first/last quoted date
```

结果解读：

```text
当前完成的是工程接口和验收框架，不代表真实 Sharadar 数据已经下载。
没有 Nasdaq Data Link / Sharadar API key 和订阅时，会明确失败并输出缺失原因。
如果 capability probe 不通过，不允许继续训练严格模型。
```

遗留问题：

```text
真实 API key / 订阅尚未验证
PIT Nasdaq exchange 口径需根据 TICKERS 字段进一步确认
PIT 行业分类仍未启用，strict headline 暂不使用行业约束
```

下一阶段准备：

```text
配置 NASDAQ_DATA_LINK_API_KEY
运行 strict_sharadar_baseline_alpha158_edgar_5d
先看 provider_capability_summary.yaml
通过后再跑 baseline / direct macro / no-credit macro interactions 三组严格实验
```

产出文件：

```text
analysis/nasdaq_top500_score/data_sources/sharadar.py
analysis/nasdaq_top500_score/configs/strict/strict_base_sharadar_launch_pit_2023_5d.yaml
analysis/nasdaq_top500_score/configs/strict/strict_sharadar_baseline_alpha158_edgar_5d.yaml
analysis/nasdaq_top500_score/configs/strict/strict_sharadar_macro_direct_5d.yaml
analysis/nasdaq_top500_score/configs/strict/strict_sharadar_macro_interactions_no_credit_5d.yaml
tests/analysis/test_sharadar_data_source.py
learning/05-data-expansion/Sharadar Strict Launch PIT Integration.md
```

## 2026-05-20 阶段 E.6：Databento Strict Launch PIT 数据源接口

目标：

```text
把 Databento 接入为 strict launch_pit_2023 数据源，
替换 nasdaq_public 的股票池、证券主数据、OHLCV 和历史市值口径。
```

为什么要做：

```text
当前 nasdaq_public 缺退市股票、历史证券主数据和 PIT 市值。
Sharadar 注册/订阅路线不稳定时，Databento 是另一个个人可落地候选。
Databento Security Master + EQUS.SUMMARY 能为 Qlib 提供更严格的日频行情底座。
```

输入数据：

```text
Databento Reference API / Security Master
Databento Corporate Actions / Adjustment Factors
Databento EQUS.SUMMARY ohlcv-1d
```

核心概念：

```text
capability probe：先验收 key、Python client 和 entitlement
launch_pit_2023：用 2023-12-29 当时可见股票池启动 2024-2026 测试
shares × as-of close：严格实验使用当时股本和当时收盘价算市值
不回退原则：Databento probe 失败时停止，不回退到 nasdaq_public
```

实验动作：

```text
新增 DatabentoDataSource
新增 DatabentoClient lazy import
新增 provider capability 输出
新增 strict_databento_* 配置
扩展 strict_pit 和 data_quality 对 databento 的识别
新增 fake Databento client 单元测试
新增 Databento 学习笔记和命令入口
```

评价指标：

```text
provider_capability_summary.yaml strict_capability_pass
provider_table_columns.csv 是否发现必需字段
pit_universe_validation.csv 是否通过退市/成员/价格口径检查
market_cap_validation.csv 是否没有 current market cap proxy
```

结果解读：

```text
当前完成的是工程接口、验收框架和一次真实 capability probe。
已经安装 databento Python 包，并把 DATABENTO_API_KEY 写入 ignored .env。
真实 probe 返回 license_reference_dataset_no_subscription，说明当前账号缺 Reference / Security Master 订阅。
因此本次没有下载训练数据，也没有进入模型训练。
如果 capability probe 不通过，不允许进入 strict headline 训练。
```

遗留问题：

```text
真实 Databento key 已在本机触达 API，但 Security Master entitlement 缺失
PIT Nasdaq primary listing 口径需要根据真实字段进一步确认
PIT 行业分类仍未启用，strict headline 暂不使用行业约束
价格复权和 corporate actions audit 需要真实数据后继续验收
```

下一阶段准备：

```text
在 ignored .env 设置 DATABENTO_API_KEY
安装 databento Python client
运行 strict_databento_baseline_alpha158_edgar_5d
先看 provider_capability_summary.yaml
通过后再跑 baseline / direct macro / no-credit macro interactions 三组严格实验
```

产出文件：

```text
analysis/nasdaq_top500_score/data_sources/databento.py
analysis/nasdaq_top500_score/configs/strict/strict_base_databento_launch_pit_2023_5d.yaml
analysis/nasdaq_top500_score/configs/strict/strict_databento_baseline_alpha158_edgar_5d.yaml
analysis/nasdaq_top500_score/configs/strict/strict_databento_macro_direct_5d.yaml
analysis/nasdaq_top500_score/configs/strict/strict_databento_macro_interactions_no_credit_5d.yaml
tests/analysis/test_databento_data_source.py
learning/05-data-expansion/Databento Strict Launch PIT Integration.md
```

## 2026-05-20 阶段 E.4M：Strict PIT 修复框架与回测压力测试

目标：

把未来函数与水分审计后的修复顺序落成工程护栏：先阻断非 PIT 股票池冒充严格结果，再用压力测试检查交易假设水分。

为什么要做：

当前高收益最大的风险来自股票池幸存者偏差和当前市值反推历史市值。即使回测函数本身没有直接未来函数，数据源和交易假设仍可能夸大收益。

输入数据：

```text
当前 Nasdaq public 学习配置
当前 no-credit macro interactions 默认配置
未来 Norgate / CRSP / 同级 PIT 数据源
```

核心概念：

```text
strict_pit：严格 PIT 实验契约
strict_headline_allowed：是否允许作为严格主结论
data_quality_summary：股票池、市值、证券主数据验收摘要
backtest_stress：复用预测分数的交易假设压力测试
```

实验动作：

```text
新增 data_quality.py
新增 backtest_stress.py
主流水线接入数据质量验收和压力测试
默认 no-credit 配置启用压力测试
新增 strict 三组配置
新增学习文档和测试
```

评价指标：

```text
pit_universe_validation.csv 是否存在 HIGH fail
market_cap_validation.csv 是否仍使用 market_cap_asof_estimate
backtest_stress_matrix.csv 中 entry_lag / entry_price / cost_bps 敏感性
严格配置是否拒绝 nasdaq_public / approximate_market_cap_asof
```

结果解读：

```text
当前学习配置仍可运行，但 data_quality_summary 会标记 not_strict_pit。
strict 配置默认走 Norgate，不允许 nasdaq_public 当前快照冒充严格 PIT。
没有 PIT 行业分类前，strict headline 禁用行业特征和行业约束。
压力测试不重训模型，只改变交易假设。
```

遗留问题：

```text
真实 Norgate 环境尚未验证
历史 market cap / shares outstanding 仍需要补齐
PIT 行业分类仍未接入
EDGAR as-filed 抽样和 FRED 日频 vintage 风险仍需后续处理
```

下一阶段准备：

```text
拿到真实 PIT 数据源后跑 strict 配置
补历史市值 / shares 字段
运行 backtest_stress，确认收益是否依赖 entry_lag=1 或低成本
重新运行 future_leakage_audit.py，确认 R1/R2 是否消失
```

产出文件：

```text
analysis/nasdaq_top500_score/data_quality.py
analysis/nasdaq_top500_score/backtest_stress.py
analysis/nasdaq_top500_score/configs/strict/strict_baseline_alpha158_edgar_5d.yaml
analysis/nasdaq_top500_score/configs/strict/strict_macro_direct_5d.yaml
analysis/nasdaq_top500_score/configs/strict/strict_macro_interactions_no_credit_5d.yaml
tests/analysis/test_pit_data_quality.py
tests/analysis/test_backtest_stress.py
learning/05-data-expansion/Strict PIT Data Repair Plan.md
learning/04-strategy-backtest/Backtest Stress Test Review.md
learning/04-strategy-backtest/Strict Re-Run Result Review.md
```

## 2026-05-20 阶段 E.4J：宏观交互 Ablation 复盘

目标：

拆解 macro interactions 的收益来源，判断 VIX、利率估值、信用质量、行业 flag 交互分别贡献了什么。

为什么要做：

完整宏观交互模型的收益、IC 和 Rank IC 都提升了，但如果不知道哪一组交互在起作用，就无法判断下一步应该保留、删除还是重设特征。

输入数据：

```text
baseline frozen run
direct macro frozen run
full macro interactions frozen run
五组 macro ablation run
同一 as-of 2023-12-31 冻结 Nasdaq Top500
同一未来 5 日收益标签
同一 sector_cap_2_top10 回测口径
```

核心概念：

```text
ablation：在完整模型基础上删除一组特征，观察指标变化
drop group：删掉某类交互后效果变差，说明该组大概率有贡献
only group：只保留某类交互，观察它单独是否足够稳定
Rank IC vs TopK：Rank IC 看整体排序，TopK 看最终组合收益
```

实验动作：

```text
新增 configs/macro_ablation/*.yaml
新增 macro_ablation_review.py
运行 drop_vix、drop_rate_valuation、drop_credit_quality、drop_sector_flag、only_vix 五组实验
汇总 macro_ablation_summary.csv、macro_ablation_regime_summary.csv、macro_ablation_review_summary.yaml
新增学习笔记 Macro Interaction Ablation Review
```

评价指标：

```text
IC / Rank IC
sector_cap_2_top10 年化收益、最大回撤、超额收益、alpha、beta
相对 full_interactions 的收益差、Rank IC 差、alpha 差
不同 regime 下相对 baseline 的收益差和 alpha 差
```

结果解读：

```text
full_interactions：Rank IC=0.012953，年化 43.55%，最大回撤 -24.19%，alpha 17.16%
drop_vix_interactions：年化 42.53%，但 Rank IC 降到 0.007859，回撤扩大到 -29.85%
drop_rate_valuation_interactions：年化 34.08%，回撤改善到 -19.00%，alpha 降到 9.06%
drop_credit_quality_interactions：年化 67.26%，回撤 -17.50%，alpha 30.62%，但 Rank IC 降到 0.007062
drop_sector_flag_interactions：年化 28.14%，回撤 -37.18%，超额收益接近 0
only_vix_interactions：年化 46.31%，但 Rank IC 0.005085，回撤 -34.98%
```

核心判断：

```text
完整交互模型的整体排序最好
信用质量交互在本窗口可能拖累 TopK，需要重新设计或暂时下线
行业 flag 交互非常重要，删除后收益和风险明显变差
VIX 交互有助于风险和排序稳定，但不能单独作为主模型
利率估值交互贡献收益，但也带来一定风险暴露
```

遗留问题：

```text
drop_credit_quality_interactions 收益最高，但可能依赖少数股票或少数行业
当前测试期仍只有 2024-2026，需要滚动窗口或其他时间段验证
信用质量特征可能需要改成行业内分位，而不是原始负债/现金比率
行业分类仍不是历史 PIT 行业分类
```

下一阶段准备：

```text
对比 full_interactions 和 drop_credit_quality_interactions 的持仓差异
检查收益集中度、行业贡献、单票贡献、换手率和成本敏感性
如果 drop_credit 仍稳，再把它作为候选默认配置
如果收益集中度过高，则保留 full_interactions 作为更稳的排序模型
```

产出文件：

```text
analysis/nasdaq_top500_score/macro_ablation_review.py
analysis/nasdaq_top500_score/configs/macro_ablation/manifest.yaml
analysis/nasdaq_top500_score/configs/macro_ablation/drop_vix_interactions.yaml
analysis/nasdaq_top500_score/configs/macro_ablation/drop_rate_valuation_interactions.yaml
analysis/nasdaq_top500_score/configs/macro_ablation/drop_credit_quality_interactions.yaml
analysis/nasdaq_top500_score/configs/macro_ablation/drop_sector_flag_interactions.yaml
analysis/nasdaq_top500_score/configs/macro_ablation/only_vix_interactions.yaml
tests/analysis/test_macro_ablation_review.py
learning/05-data-expansion/Macro Interaction Ablation Review.md
learning/00-start-here/Qlib Commands.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-20 阶段 E.4K：宏观交互默认策略调整

目标：

把 macro ablation 的研究结论落实到默认实验配置。

为什么要做：

`drop_credit_quality_interactions` 在本次测试窗口中收益、alpha 和回撤都优于完整交互模型，但完整交互模型的 Rank IC 更高。因此需要明确默认口径和研究口径，避免后续实验混用。

输入数据：

```text
macro ablation 汇总结果
full_interactions 研究配置
drop_credit_quality_interactions ablation 结果
```

核心概念：

```text
默认主策略：后续优先运行和比较的候选策略
研究保留：不作为默认，但保留配置与结果用于对照和复盘
```

实验动作：

```text
新增 default no-credit macro interactions 配置
默认配置去掉 credit spread × liabilities/cash 两个交互
完整 10 交互配置不改名、不删除，继续保留为 research reference
更新 Qlib Commands、Qlib Learning Log 和 ablation 学习笔记
```

评价指标：

```text
默认配置可解析
信用质量交互不在默认配置里
完整研究配置仍保留信用质量交互
```

结果解读：

```text
默认配置包含 8 个宏观交互特征
研究配置包含完整 10 个宏观交互特征
默认去掉 credit quality 是阶段性工程决策，不是永久否定信用质量因子
```

遗留问题：

```text
默认 no-credit 策略还需要集中度、持仓差异、换手成本和滚动窗口验证
信用质量交互后续应改成行业内分位或更稳定的质量因子，而不是直接原始比率相乘
```

下一阶段准备：

```text
比较 default no-credit 与 full_interactions 的持仓差异
检查收益是否集中在少数股票、少数行业或少数调仓期
```

产出文件：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_macro_interactions_default_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
tests/analysis/test_macro_ablation_review.py
learning/00-start-here/Qlib Commands.md
learning/05-data-expansion/Macro Interaction Ablation Review.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-20 阶段 E.4L：未来函数与回测收益水分审计

目标：

系统检查当前高收益是否来自真实可交易信号，还是混入未来信息、幸存者偏差、数据口径错误或回测假设过宽。

为什么要做：

当前 no-credit macro interactions 等价 run 的 `sector_cap_2_top10` 年化收益达到 `67.26%`，明显偏高。必须先审计数据和回测口径，再决定策略是否有真实 alpha。

输入数据：

```text
当前 no-credit 等价 ablation run
universe_selection.csv
macro_asof_observations.parquet
market_features.parquet
fundamental_features.parquet
strategy_comparison/sector_cap_2_top10/backtest_positions.csv
strategy_comparison/sector_cap_2_top10/backtest_nav.csv
```

核心概念：

```text
未来函数：训练或选股时使用当时不可见的信息
幸存者偏差：只保留现在仍存在的股票，漏掉失败样本
PIT：point-in-time，当时真实可见的数据口径
回测水分：不是代码偷看未来，但数据或交易假设让收益虚高
```

实验动作：

```text
新增 future_leakage_audit.py
生成 future_leakage_risk_register.csv
抽样检查 universe as-of selection、macro as-of、market rolling features、EDGAR visibility
抽样复算 10 个回测调仓期的 entry/exit 和 gross return
新增审计学习报告
```

评价指标：

```text
风险等级：HIGH / MEDIUM / LOW
风险状态：confirmed_risk / partial_mitigation / checked / needs_stress_test
market momentum 抽样复算误差
backtest gross return 抽样复算误差
macro effective_date 是否晚于 feature date
```

结果解读：

```text
高风险 confirmed_risk：2 个，均来自股票池与市值口径
中风险：4 个，来自行业分类、EDGAR as-filed、FRED latest、收益压力测试
低风险 checked：2 个，来自 market rolling features 和 backtest entry/exit
market momentum 最大复算误差：0.0
backtest gross return 最大复算误差：约 9.0e-17
```

核心判断：

```text
没有发现 TopK 回测直接使用未来收益选股
没有发现 market rolling features 或 backtest entry/exit 的直接未来函数
但当前股票池和市值口径存在高风险水分，足以让 67.26% 年化不能作为严谨策略结论
```

遗留问题：

```text
nasdaq_public 缺退市股票和历史证券主数据
approximate_market_cap_asof 使用 current_market_cap 和 latest close 反推历史市值
当前 sector/industry 不是历史 PIT
FRED 日频 latest 序列不是严格 vintage
EDGAR companyfacts 是否完全 as-filed 仍需抽样核对
```

下一阶段准备：

```text
先修复 PIT 股票池和历史市值口径
再做 entry_lag=2、open/vwap 入场、25/50/100 bps 成本压力测试
修复前不把当前年化收益当作策略能力结论
```

产出文件：

```text
analysis/nasdaq_top500_score/future_leakage_audit.py
tests/analysis/test_future_leakage_audit.py
learning/04-strategy-backtest/Future Leakage And Backtest Water Audit.md
learning/00-start-here/Qlib Commands.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-19 阶段 5.9：短历史股票专项复盘

目标：

```text
解释 lt_2y 和 2_5y 短历史股票到底是机会来源还是风险来源。
不重新训练模型，不改变 TopK 规则，只读取已有基线策略的实际持仓结果。
```

为什么要做：

```text
5.8C 显示短历史统一惩罚没有提升收益，严格门槛还损失超额收益。
所以问题不再是继续加大惩罚，而是拆开看短历史赢家和输家到底有什么不同。
```

输入数据：

```text
raw_score_sector_cap_2_top10/backtest_positions.csv
universe.csv
fundamental_features.parquet
market_features.parquet
```

核心概念：

```text
lt_2y：180 到 503 个交易日历史
2_5y：504 到 1259 个交易日历史
bucket_winners：桶内实际回测收益最高的一组
bucket_losers：桶内实际回测收益最低的一组
```

实验动作：

```text
新增 short_history_review 模块。
按历史长度桶汇总持仓收益、胜率、贡献和风险特征。
按 sector / industry 拆解短历史贡献。
比较短历史赢家和输家的流动性、估值、盈利能力、动量和波动率。
报告新增“短历史股票专项复盘”章节。
```

评价指标：

```text
持仓次数
股票数
平均收益
胜率
净贡献
最差单票收益
输家低流动性占比
输家高估值占比
输家亏损公司占比
```

结果解读：

```text
lt_2y：
持仓 105 次，股票 10 只，平均收益 0.57%，胜率 51.43%，净贡献 5.25%，最差单票 -17.74%。

2_5y：
持仓 236 次，股票 26 只，平均收益 1.28%，胜率 48.73%，净贡献 28.53%，最差单票 -48.68%。

2_5y / Finance：
持仓 12 次，平均收益 -5.97%，胜率 16.67%，净贡献 -7.27%，是最明显的短历史负贡献来源。

2_5y / Basic Materials、2_5y / Industrials、lt_2y / Industrials：
都是短历史正贡献来源。
```

当前判断：

```text
短历史股票整体不是净拖累。
lt_2y 和 2_5y 都是正净贡献。
问题集中在特定行业和基本面状态，而不是“历史短”本身。
不建议统一剔除短历史股票，也不建议继续加大统一短历史惩罚。
```

遗留问题：

```text
短历史行业差异还没有转化成新的选股约束。
当前行业分类仍不是历史 PIT 分类。
2_5y 输家中亏损公司占比很高，但还没有做亏损公司名额限制。
```

下一阶段准备：

```text
阶段 5.10：短历史行业约束对照。
建议先测试：限制 2_5y / Finance 名额，或限制短历史亏损公司进入 Top10 的数量。
观察是否降低最差单票亏损和最大回撤，同时不牺牲 Basic Materials / Industrials 的短历史正贡献。
```

产出文件：

```text
analysis/nasdaq_top500_score/short_history_review.py
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
tests/analysis/test_short_history_review.py
learning/06-portfolio-risk/Short History Stock Review.md
learning/00-start-here/Qlib Commands.md
learning/00-start-here/Qlib Quant Learning Index.md
learning/99-logs/Qlib Learning Log.md
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

## 2026-05-19 阶段 E.4：FRED/ALFRED 宏观特征接入

目标：

把宏观经济状态作为模型输入，并按严格 PIT 口径控制未来函数。

为什么要做：

当前模型主要依赖价格成交量、财报估值、行业和行情相对特征。它还不知道市场处在高利率、曲线倒挂、通胀上行、信用压力扩大或风险偏好恶化等宏观状态。加入宏观特征可以帮助模型学习不同市场环境下哪些个股信号更可靠。

输入数据：

```text
FRED/ALFRED observations
FRED realtime_start / realtime_end
当前 frozen Nasdaq Top500 交易日历
现有 Alpha158 / EDGAR / market_features 特征矩阵
```

核心概念：

```text
FRED：当前宏观序列数据库
ALFRED：历史 vintage / real-time 宏观数据库
observation_date：数据对应的经济时期
realtime_start：数据当时可见的日期
effective_date：顺延到下一个交易日后的模型可用日期
forward fill：已公开宏观数据在下一次发布前继续沿用
```

实验动作：

```text
新增 macro_features 配置层
新增 FRED/ALFRED 宏观适配器
按 realtime_start 重建 as-of 宏观状态
生成 macro_raw_observations.parquet / macro_asof_observations.parquet / macro_features.parquet
把 macro_features 与 Alpha158、EDGAR、market_features 拼接进 LightGBM
新增宏观增强 frozen 配置和学习文档
```

评价指标：

```text
单元测试验证披露日前不可见
单元测试验证旧观察值修订不会覆盖更新观察期
单元测试验证日频数据也至少滞后一交易日
单元测试验证 max_staleness_days 会阻止过旧数据继续 forward fill
配置可解析，脚本可编译
```

结果解读：

```text
本阶段先完成工程接入和 PIT 口径验证。
尚未真实下载 FRED/ALFRED 并训练完整模型，因为需要 FRED_API_KEY。
宏观特征不是直接排序因子，而是市场状态变量。
```

遗留问题：

```text
需要用户设置 FRED_API_KEY 后跑真实宏观增强实验
第一版没有区分盘前、盘中、盘后发布时间
低频统计序列默认 output_type=4 initial release only，日频市场序列使用 output_type=1 并顺延到下一个交易日；后续可进一步扩展更完整的 vintage 查询
```

下一阶段准备：

```text
设置 FRED_API_KEY
运行宏观增强 frozen 配置
对比无宏观 baseline 的 IC、Rank IC、TopK 回测和行业暴露
如果宏观变量有效，再做“宏观状态 × 行业/估值/动量”的交互特征
```

产出文件：

```text
analysis/nasdaq_top500_score/macro_features.py
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_macro_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
tests/analysis/test_macro_features.py
learning/05-data-expansion/FRED ALFRED Macro Features Integration.md
learning/00-start-here/Qlib Commands.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-19 阶段 E.4R：FRED/ALFRED 真实宏观增强实验

目标：

用真实 FRED/ALFRED 宏观数据跑完整 frozen 实验，和无宏观 baseline 对比，判断宏观状态变量是否有增量价值。

为什么要做：

宏观特征接入完成后，只有通过同股票池、同训练期、同测试期、同回测规则的对照实验，才能区分“工程上能接入”和“策略上有价值”。

输入数据：

```text
无宏观 baseline frozen run
真实 FRED/ALFRED observations
当前 frozen Nasdaq Top500 股票池
Alpha158 + EDGAR + industry + market relative features
测试期 2024-01-02 到 2026-05-15
```

核心概念：

```text
宏观状态变量：同一天对所有股票相同，用来描述市场 regime
增量 alpha：加入新特征后，在同等约束下能否提高排序、收益或风险调整表现
Rank IC：看模型横截面排序是否更接近未来收益排序
TopK 回测：看模型分数经过组合规则后是否真的变成策略收益
```

实验动作：

```text
修正日频市场宏观序列口径：output_type=1 + realtime_mode=latest + observation_date 后一交易日生效
保留低频统计序列 initial release / realtime_start 口径
重新运行宏观增强 frozen 配置
生成 macro_features.parquet、macro_failures.csv、report.md 和 strategy_comparison.csv
新增真实实验复盘文档
```

评价指标：

```text
macro_failures 数量
macro_features 覆盖率
IC / Rank IC
sector_cap_2_top10 收益、超额收益、最大回撤、信息比率、alpha、beta
行业暴露和 sector HHI
```

结果解读：

```text
macro_failures=0
macro_features=1,256,500 行 x 52 列，平均非空覆盖率约 98.99%
无宏观 baseline：IC=0.016978，Rank IC=0.003683
宏观增强：IC=0.012456，Rank IC=0.009214
无宏观 sector_cap_2_top10：累计收益 97.56%，年化 33.75%，最大回撤 -29.36%，超额累计收益 10.51%
宏观 sector_cap_2_top10：累计收益 53.92%，年化 20.23%，最大回撤 -22.92%，超额累计收益 -13.90%
```

宏观特征提高了 Rank IC，也降低了 beta 和最大回撤，但没有提高 TopK 收益和超额收益。当前不能证明第一版宏观特征有稳定增量 alpha。

遗留问题：

```text
日频市场序列没有使用完整 vintage，只做 observation_date 后一交易日滞后
低频宏观数据没有精确到盘前、盘中、盘后发布时间
宏观变量同日对所有股票相同，直接拼接可能不如交互特征有效
单次 2024-2026 测试期不足以证明长期稳健性
```

下一阶段准备：

```text
做宏观状态交互特征，而不是继续堆更多宏观序列
优先验证：宏观状态 × 行业、宏观状态 × 估值、宏观状态 × 动量、宏观状态 × 亏损公司
如果交互仍无效，把宏观数据保留为风险复盘维度，而不是默认模型输入
```

产出文件：

```text
analysis/nasdaq_top500_score/macro_features.py
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_macro_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
learning/05-data-expansion/FRED ALFRED Macro Features Integration.md
learning/05-data-expansion/FRED ALFRED Macro Experiment Review.md
learning/00-start-here/Qlib Quant Learning Index.md
learning/README.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-20 阶段 E.4I：宏观 Regime 复盘与交互特征实验

目标：

把宏观变量从“直接输入模型”升级为“regime 复盘 + 宏观交互特征”，判断宏观信息是否能转成横截面选股增量。

为什么要做：

第一版 direct macro 提高 Rank IC 并降低 beta，但收益下降。原因可能是 raw macro 同一天对所有股票相同，更像市场状态变量，而不是个股排序因子。因此需要把宏观状态和股票差异相乘。

输入数据：

```text
无宏观 baseline frozen run
direct macro frozen run
macro interactions frozen run
真实 FRED/ALFRED PIT 宏观特征
Alpha158 + EDGAR + market relative features
测试期 2024-01-02 到 2026-05-15
```

核心概念：

```text
regime：市场状态，如 high VIX、利率上行、曲线倒挂、信用压力、美元走强、油价上涨
宏观交互：宏观状态 × 股票差异，使市场状态变量变成横截面特征
低样本过滤：regime 摘要至少需要 5 个调仓期，避免 1 个周期年化失真
```

实验动作：

```text
新增 macro_interactions.py
新增 macro_regime_review.py
新增 macro interactions frozen 配置
训练 macro interactions 模型
生成 macro_regime_* 复盘输出
更新报告、命令和学习笔记
```

评价指标：

```text
IC / Rank IC
sector_cap_2_top10 累计收益、年化收益、最大回撤、超额收益、alpha、beta
macro_interaction_features 覆盖率
不同 regime 下相对 baseline 的收益差、alpha 差、beta 差、回撤差
```

结果解读：

```text
macro_interaction_features=1,256,500 行 x 10 列，失败记录 0，平均非空覆盖率约 80.73%
baseline：IC=0.016978，Rank IC=0.003683，年化 33.75%，alpha 7.88%，beta 1.042
direct macro：IC=0.012456，Rank IC=0.009214，年化 20.23%，alpha 1.20%，beta 0.813
macro interactions：IC=0.022432，Rank IC=0.012953，年化 43.55%，alpha 17.16%，beta 0.922
```

macro interactions 第一版明显优于 baseline 和 direct macro，说明宏观信息通过“宏观状态 × 股票差异”更容易变成选股信息。它在 high VIX、VIX rising、mid VIX、curve not inverted 下更强，但在 low VIX 和 curve inverted 下明显变弱。

遗留问题：

```text
当前行业分类仍不是历史 PIT 行业分类
交互特征只有 10 个，尚未确认哪一类贡献最大
low VIX 和 curve inverted 状态下存在拖累
单一 2024-2026 测试期仍需更长历史或滚动窗口验证
```

下一阶段准备：

```text
做 macro interaction ablation
逐类移除 VIX、利率估值、信用质量、行业 flag 交互
确认收益提升来自哪些交互，而不是偶然拟合
如果 VIX 交互贡献最大，再设计更细的 high/low VIX 选股规则
```

产出文件：

```text
analysis/nasdaq_top500_score/macro_interactions.py
analysis/nasdaq_top500_score/macro_regime_review.py
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_macro_interactions_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
tests/analysis/test_macro_interactions.py
tests/analysis/test_macro_regime_review.py
learning/05-data-expansion/Macro Regime Review And Interaction Features.md
learning/00-start-here/Qlib Commands.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-22 阶段 CRSP-2：保守 LightGBM 与标签周期对照

目标：

确认 CRSP Alpha158-only 的负 IC 和第 1 轮早停，是否来自数据适配错误，还是来自模型参数过激进和信号弱。

为什么要做：

旧 baseline 第 1 轮早停，不能直接进入宏观/EDGAR 增强。必须先把 CRSP 基线本身调到可复盘状态，否则后续增强实验会建立在不稳的对照上。

输入数据：

```text
CRSP 2000-01-03 到 2025-12-31 日级数据
CRSP US Common Equity 月度动态市值 Top500
Alpha158 价格成交量特征
5 / 10 / 20 日 CRSP DlyRet 总收益标签
2024-2025 测试期
```

核心概念：

```text
horizon-aware label：不同预测周期使用不同标签列
early stopping：验证集不再改善时停止训练
Rank IC：模型分数排序和未来收益排序的相关性
压力测试：用更高成本和不同入场价检查收益脆弱性
```

实验动作：

```text
新增 CRSP 动态标签列生成
新增 5/10/20 日保守模型配置
运行三组训练、回测和 24 组压力测试
运行三组 CRSP diagnostics
生成 crsp_signal_model_comparison.csv
更新学习文档和命令入口
```

评价指标：

```text
IC / Rank IC
best_iteration / best_valid_l2
累计收益 / 年化收益 / 最大回撤
年化 alpha / beta
50bps 成本压力下年化收益
标签、价格、membership 诊断是否通过
```

结果解读：

```text
旧 10 日 baseline：Rank IC=-0.007421，best_iteration=1，年化收益 2.30%
5 日保守：Rank IC=0.005123，best_iteration=33，年化收益 25.41%，但 50bps 成本后转负
10 日保守：Rank IC=0.006466，best_iteration=180，年化收益 33.91%，alpha 10.11%，50bps 后仍为 15.70%
20 日保守：Rank IC=0.003580，best_iteration=145，年化收益 20.78%，最大回撤较低
```

10 日保守模型是当前最合适的 CRSP Alpha158-only 基线。但 IC 仍为负，Rank IC 也很小，所以只能说“基线更稳”，不能说“策略已经可靠”。

遗留问题：

```text
IC 仍弱，需要继续检查收益是否集中于少数股票或特定时期
5 日策略对成本太敏感
20 日策略更稳但 alpha 不足
当前还没有把 macro/EDGAR 用保守参数重跑
OHLC violation rate 约 0.2507%，后续可抽样复核
```

下一阶段准备：

```text
以 crsp_alpha158_10d_conservative_2000_2025 作为新 baseline
重跑 CRSP macro conservative
重跑 CRSP macro interaction conservative
继续检查贡献集中度、换手、成本和行业暴露
```

产出文件：

```text
analysis/nasdaq_top500_score/crsp_signal_model_comparison.py
analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_5d_conservative_2000_2025.yaml
analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_10d_conservative_2000_2025.yaml
analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_20d_conservative_2000_2025.yaml
tests/analysis/test_crsp_signal_model_comparison.py
learning/05-data-expansion/CRSP Conservative Model And Horizon Comparison.md
learning/00-start-here/Qlib Commands.md
learning/99-logs/Qlib Learning Log.md
learning/99-logs/Stage Completion Records.md
```

## 2026-05-22 阶段 CRSP-4：训练加速与架构优化

目标：

减少 CRSP baseline / macro / macro interaction 实验之间的重复数据准备和重复行情读取，让后续研究更快复跑。

为什么要做：

CRSP 训练慢的主要瓶颈不在 LightGBM，而在重复 I/O：

```text
每个 run 重建约 824MB qlib_source_csv
每个 run 重建约 202MB qlib_data
压力测试 24 个组合重复扫描全部股票 CSV
macro interaction run 还会生成较大的 market_features 和 macro_interaction_features
```

输入数据：

```text
CRSP 2000-01-03 到 2025-12-31 日级数据
CRSP US Common Equity 月度动态市值 Top500
当前 10 日保守 baseline / macro / macro interaction 配置
```

核心概念：

```text
prepared dataset：同一底层数据口径下可复用的数据准备产物
runtime profile：每个阶段耗时画像
artifact cache：特征 parquet 级别缓存
market data preload：回测前一次性读取行情，避免每个 variant 重扫 CSV
```

实验动作：

```text
新增 runtime_profile.csv / runtime_profile.yaml
新增 CRSP prepared dataset cache
Qlib bin 写回 prepared dataset 后供后续 run 复用
backtest 和 stress test 支持预加载 market_data
strategy comparison 和 stress test 按 price 口径复用行情
market / macro / macro interaction 特征支持 artifact cache
新增 run_mode：full / train_only / backtest_only / stress_only / report_only
```

评价指标：

```text
第二次同口径 run 是否命中 prepared dataset
是否不再重建 per-symbol source CSV
是否不再重建 Qlib bin
压力测试是否仍输出 24 组结果
预加载行情与旧版回测结果是否一致
runtime_profile 是否能定位最慢阶段
```

结果解读：

本阶段没有重新训练模型，也不改变策略结论。它解决的是研究工程效率问题：同一 CRSP 口径下，后续比较 Alpha158-only、raw macro、macro interaction 时，应复用底层数据和 Qlib bin，把时间主要花在真正变化的模型或特征上。

遗留问题：

```text
stress_workers 仍偏保守，当前优先通过行情复用减少 I/O
Alpha158 handler 自身仍会加载全窗口数据，后续可继续研究 Qlib 层缓存
feature cache key 依赖配置，改配置后会生成新缓存，需要定期清理 runs/feature_cache
```

下一阶段准备：

```text
用 runtime_profile 对真实 CRSP run 做一次耗时画像
确认 prepared dataset 第二次运行命中
如果仍慢，再继续优化 Alpha158 初始化和 DatasetH 构造
```

产出文件：

```text
analysis/nasdaq_top500_score/runtime_profile.py
analysis/nasdaq_top500_score/artifact_cache.py
analysis/nasdaq_top500_score/data_sources/crsp.py
analysis/nasdaq_top500_score/backtest.py
analysis/nasdaq_top500_score/backtest_stress.py
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
learning/05-data-expansion/CRSP Training Speed Optimization.md
```

## 2026-05-22 阶段 CRSP-6：2010 主线、清理 dry-run 与行业路径恢复

目标：

把 CRSP 主研究窗口切到 `2010-01-01 ~ 2025-12-31`，主回测成本改为 `0bps`，并在恢复行业约束前先做 CRSP SIC/NAICS 覆盖验收。

为什么要做：

```text
2000-2025 训练和复盘较慢
用户计划两周调仓，2010-2025 更贴近未来实盘环境
零佣金券商下主结果应先看 0bps
行业约束和行业内相对特征之前有效，但 CRSP 下必须先验证行业字段覆盖
```

输入数据：

```text
CRSP 本地日级 Parquet warehouse
CRSP US Common Equity 月度动态市值 Top500
2010-01-01 到 2025-12-31
未来 10 个交易日收益标签
Alpha158-only conservative LightGBM
```

核心概念：

```text
prepared dataset window isolation
0bps headline result
25/50bps stress as slippage/spread proxy
SIC2 sector / SIC4 industry
industry validation gate
```

实验动作：

```text
新增 configs/crsp_2010 配置组
新增 cleanup_runs.py dry-run 清理清单
新增 crsp_industry_validation.py
修复 prepared dataset 复用旧 warehouse 时未按 2010 窗口裁剪的问题
重跑 crsp_alpha158_10d_conservative_2010_2025
```

评价指标：

```text
Qlib calendar 是否从 2010 开始
主回测 cost_bps 是否为 0
压力测试是否为 18 组：2 entry_lag x 3 price x 3 cost
行业训练期年度 SIC2 覆盖是否 >= 80%
测试期调仓日 SIC2 覆盖是否 >= 85%
```

结果解读：

```text
Fit: 2010-01-04 到 2021-12-31
Test: 2024-01-02 到 2025-12-31
Test IC: 0.015469
Test Rank IC: -0.009241
0bps 主回测累计收益: 85.86%
0bps 主回测年化收益: 36.67%
最大回撤: -17.12%
压力测试: 18 组
runtime total: 约 345 秒
```

行业验收：

```text
train_min_annual_sic2_coverage: 67.8%
test_min_rebalance_sic2_coverage: 97.2%
industry_features_allowed: false
industry_constraints_allowed: false
结论：行业字段先只做复盘，不进入模型和选股约束
```

遗留问题：

```text
Rank IC 仍为负，不能只凭回测收益认定强横截面 alpha
训练期行业覆盖不足，需要查 UNKNOWN 集中年份和证券类型
高 beta 仍需要关注
25/50bps 压力仍会明显降低收益
```

下一阶段准备：

```text
先跑历史长度桶内 Top10 对照
复盘 full_10y / 5_10y / 2_5y / lt_2y 的收益贡献
检查 CRSP SIC UNKNOWN 的来源
行业覆盖修复后再跑行业约束和行业内 market 相对特征
```

产出文件：

```text
analysis/nasdaq_top500_score/cleanup_runs.py
analysis/nasdaq_top500_score/crsp_industry_validation.py
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_10d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_bucket_top10_10d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_industry_constrained_10d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_industry_market_relative_10d_conservative_2010_2025.yaml
learning/05-data-expansion/CRSP 2010 Baseline Cleanup And Industry Recovery.md
```

## 2026-05-23 阶段 CRSP-7：历史长度桶内 Top10 与行业 UNKNOWN 复盘

目标：

验证历史长度桶内名额是否应该恢复为默认策略，并定位 CRSP 行业字段 `UNKNOWN` 的主要来源。

为什么要做：

```text
Nasdaq 旧实验里短历史分桶曾经用于控制新股/短历史股票风险
CRSP 新主线换成动态 Top500 后，需要重新验证桶内名额是否仍有价值
行业约束和行业内相对特征恢复前，必须弄清 CRSP SIC/NAICS 覆盖不足来自哪里
```

输入数据：

```text
CRSP 2010-2025 prepared dataset
crsp_alpha158_10d_conservative_2010_2025 baseline
crsp_alpha158_bucket_top10_10d_conservative_2010_2025 bucket 对照
CRSP membership.csv
CRSP security_master.csv
```

核心概念：

```text
全局 Top10：直接按模型 score 选前 10
桶内 Top10：按 full_10y / 5_10y / 2_5y / lt_2y 分配名额
SIC2：CRSP 行业大类
UNKNOWN：SIC/NAICS/ICB 缺失或无效
```

实验动作：

```text
运行 crsp_alpha158_bucket_top10_10d_conservative_2010_2025
生成 bucket_vs_global_comparison.csv
生成 bucket_vs_global_bucket_contribution.csv
新增 crsp_industry_unknown_review.py
生成 crsp_industry_unknown_by_year/security/type/examples/summary
```

评价指标：

```text
累计收益
年化收益
最大回撤
alpha / beta
25/50bps 压力年化
各历史桶净贡献和超额贡献
SIC2 年度覆盖率
UNKNOWN 是否集中在特殊证券类型
```

结果解读：

```text
global_top10 年化收益: 36.67%
bucket_4_3_2_1 年化收益: 28.38%
global_top10 最大回撤: -17.12%
bucket_4_3_2_1 最大回撤: -20.47%
global_top10 alpha: 5.10%
bucket_4_3_2_1 alpha: 约 0%
```

分桶贡献：

```text
2_5y 和 lt_2y 均为正贡献
5_10y 在 bucket quota 下贡献较弱
硬性名额提高换手并降低 alpha
```

行业 UNKNOWN：

```text
membership_rows: 96000
unknown_rows: 14887
sic2_coverage: 84.49%
worst year: 2010, coverage 68.63%
unknown_security_count: 336
unknown_naics_valid_share: 0%
unknown_icb_valid_share: 0%
UNKNOWN 主要仍是 EQTY / COM / A 普通股
```

遗留问题：

```text
桶内名额不适合作为默认，但短历史股票仍需要专项复盘
行业 UNKNOWN 不是清洗能解决，需要外部行业映射或更完整的行业数据源
CRSP 行业约束和行业内相对特征继续关闭
```

下一阶段准备：

```text
保留全局 Top10 为当前 2010 baseline 主策略
先做短历史赢家/输家复盘
再做行业映射补全方案
行业覆盖修复后再恢复行业约束和行业内 market 相对特征
```

产出文件：

```text
analysis/nasdaq_top500_score/crsp_industry_unknown_review.py
analysis/nasdaq_top500_score/runs/crsp_alpha158_bucket_top10_10d_conservative_2010_2025/report.md
analysis/nasdaq_top500_score/runs/crsp_alpha158_bucket_top10_10d_conservative_2010_2025/bucket_vs_global_comparison.csv
analysis/nasdaq_top500_score/runs/crsp_alpha158_bucket_top10_10d_conservative_2010_2025/bucket_vs_global_bucket_contribution.csv
analysis/nasdaq_top500_score/runs/crsp_alpha158_bucket_top10_10d_conservative_2010_2025/crsp_industry_unknown_review_summary.yaml
learning/06-portfolio-risk/CRSP History Bucket Top10 And Industry Unknown Review.md
```

## 2026-05-23 阶段 CRSP-8：行业映射补齐与行业路径恢复准备

目标：

```text
把 CRSP 行业分类从旧 security_master 回填升级为 CRSP 月末 row-level PIT 行业映射。
```

为什么要做：

```text
旧行业验收显示 2010-2014 覆盖不足，但问题可能来自 prepared dataset 复用旧 membership，而不是 CRSP 原始行缺少行业字段。
行业约束和行业内相对特征必须先通过 PIT 字段验收，不能直接从 Nasdaq 旧路径搬过来。
```

输入数据：

```text
CRSP 2010-2025 monthly dynamic Top500 membership
CRSP 月末 daily row 的 SICCD / NAICS / ICBIndustry
可选 SEC EDGAR SIC fallback
```

实验动作：

```text
新增 industry_master.parquet
新增 industry_mapping_coverage.csv
新增 industry_mapping_failures.csv
新增 industry_mapping_summary.yaml
prepared dataset key 加入 industry_mapping.schema_version
crsp_industry_validation 优先读取 industry_master，不再优先 security_master 回填
重跑 crsp_alpha158_10d_conservative_2010_2025
```

评价指标：

```text
crsp_pit_rows
edgar_fallback_rows
unknown_rows
non_pit_or_unverified_rows
训练期年度最低 strict sector coverage
测试期调仓日最低 strict sector coverage
fallback_to_security_master
```

结果解读：

```text
industry_master rows: 96000
crsp_pit_rows: 96000
edgar_fallback_rows: 0
unknown_rows: 0
non_pit_or_unverified_rows: 0
train_min_annual_strict_sector_coverage: 100%
test_min_strict_sector_coverage: 100%
fallback_to_security_master: false
conclusion: industry_pit_validation_pass
```

结论：

```text
CRSP 月末 row-level SIC 已足够覆盖当前 2010 动态 Top500。
之前行业 UNKNOWN 覆盖不足主要来自旧 membership 缺字段和 validation fallback 路径，不是 CRSP 原始数据不支持行业分类。
行业字段验收已通过，可以恢复行业暴露复盘、行业约束和行业内相对特征的对照实验。
```

遗留问题：

```text
SIC 不是 GICS，行业经济含义和投资组合常用行业口径不完全一致。
EDGAR fallback 还没有实际使用，后续只能在 evidence date 可验证时进入 PIT 路径。
行业字段可用不等于行业约束一定提升策略，需要单独回测验证。
```

下一阶段准备：

```text
先做 CRSP 2010 行业暴露和行业贡献复盘。
再跑 global_top10 vs sector_capped_top10 对照。
覆盖和回测都通过后，再恢复行业内 market 相对特征。
```

产出文件：

```text
analysis/nasdaq_top500_score/industry_mapping.py
analysis/nasdaq_top500_score/runs/crsp_alpha158_10d_conservative_2010_2025/industry_master.parquet
analysis/nasdaq_top500_score/runs/crsp_alpha158_10d_conservative_2010_2025/industry_mapping_coverage.csv
analysis/nasdaq_top500_score/runs/crsp_alpha158_10d_conservative_2010_2025/industry_mapping_summary.yaml
analysis/nasdaq_top500_score/runs/crsp_alpha158_10d_conservative_2010_2025/crsp_industry_validation_summary.yaml
learning/05-data-expansion/CRSP Industry Mapping Repair.md
```

## 2026-05-23 阶段 CRSP-9：行业约束与行业内相对特征恢复

目标：

```text
在 CRSP PIT 行业映射通过后，先验证行业约束是否改善 Top10，再验证行业内 market 相对特征是否应该进入模型输入。
```

为什么要做：

```text
Nasdaq 旧主线中行业约束曾明显改善组合表现，但 CRSP 换数据源后必须重新验证。
行业字段可用不等于行业特征有效；组合约束和模型输入要分开测试。
```

输入数据：

```text
CRSP 2010-2025 prepared dataset
CRSP monthly dynamic Top500
industry_master.parquet
crsp_alpha158_10d_conservative_2010_2025/test_predictions.csv
```

核心概念：

```text
SIC2 sector：CRSP 行业大类
SIC4 industry：CRSP 行业细分
行业约束：只限制最终 Top10 名额
行业内 market 相对特征：把行业内动量、波动、成交额、历史长度分位作为模型输入
```

实验动作：

```text
新增非 bucket TopK 行业约束选择逻辑
新增 training.reuse_test_predictions_path
market_features 优先按 industry_master 做 PIT 行业归属
运行 global_top10 / sector_cap_2 / sector_cap_3 / sector_cap_4 四组行业约束对照
运行行业内 market 相对特征重新训练实验
```

评价指标：

```text
累计收益
年化收益
最大回撤
年化 alpha
beta
最大单 sector 权重
Sector HHI
IC / Rank IC
best_iteration
```

结果解读：

```text
global_top10: 年化 39.41%, 最大回撤 -17.73%, alpha 6.74%, 最大单 sector 60%
sector_cap_2_top10: 年化 46.26%, 最大回撤 -15.62%, alpha 13.03%, 最大单 sector 20%
sector_cap_3_top10: 年化 40.47%, 最大回撤 -17.63%, alpha 7.51%, 最大单 sector 30%
sector_cap_4_top10: 年化 40.21%, 最大回撤 -17.27%, alpha 7.36%, 最大单 sector 40%
market relative model: Rank IC -0.012379, 年化 -7.89%, 最大回撤 -24.48%, best_iteration 5
```

结论：

```text
行业约束有效，尤其 sector_cap_2。
行业内 market 相对特征本轮无效，不进入默认模型。
行业信息当前更适合做组合风控，而不是直接作为模型输入。
```

遗留问题：

```text
sector_cap_2 只在 2024-2025 测试期验证过，需要后续滚动窗口复查。
SIC 不是 GICS，行业解释要保持谨慎。
行业相对特征失败不代表所有行业特征无效，只说明当前这组 market relative features 不适合默认。
```

下一阶段准备：

```text
把 Alpha158-only score + sector_cap_2_top10 作为候选默认。
做 sector_cap_2 的持仓贡献和行业暴露复盘。
随后进入 EDGAR 覆盖率与 PERMNO -> CIK 映射评估。
```

产出文件：

```text
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_industry_strategy_comparison_10d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_industry_market_relative_10d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/runs/crsp_alpha158_industry_strategy_comparison_10d_conservative_2010_2025/strategy_comparison.csv
analysis/nasdaq_top500_score/runs/crsp_alpha158_industry_market_relative_10d_conservative_2010_2025/report.md
learning/06-portfolio-risk/CRSP Industry Constraint And Relative Feature Recovery.md
```

## 2026-05-23 阶段 CRSP-10：SEC EDGAR 财报特征接入

目标：

```text
在 CRSP 2010 Alpha158-only conservative baseline 上加入 SEC EDGAR 公司财报和估值特征，验证基本面数据是否带来增量。
```

为什么要做：

```text
Alpha158 只看价格成交量，无法直接表达收入、利润、现金流、负债、估值和披露状态。
旧 Nasdaq 主线已经实现 EDGAR 接入，但 CRSP 主线使用 P{PERMNO} instrument，需要重新解决 PERMNO -> CIK 映射和估值价格口径。
```

输入数据：

```text
CRSP 2010-2025 monthly dynamic Top500
CRSP DlyClose 原始收盘价
SEC EDGAR company_tickers_exchange.json
SEC EDGAR submissions
SEC EDGAR companyfacts
```

核心概念：

```text
CIK：SEC 公司唯一编号
ticker_asof：CRSP 月度股票池当时的交易代码
PIT 财报：只能在 filed / acceptanceDateTime 之后、并顺延到下一个交易日生效
估值口径：price_to_sales / price_to_book 等必须使用市场原始价格，不使用 Alpha158 研究复权价格
```

实验动作：

```text
新增 CRSP-aware CIK 映射
新增 crsp_raw_close 估值价格源
新增 crsp_alpha158_edgar_10d_conservative_2010_2025.yaml
运行 Alpha158 + EDGAR conservative 模型
对比 Alpha158-only baseline
```

评价指标：

```text
EDGAR 覆盖 instruments
fundamental_features 行数和列数
missing_fields / missing_cik / insufficient_filings
IC / Rank IC
best_iteration
Top10 回测收益
alpha / beta / 最大回撤
```

结果解读：

```text
EDGAR 特征矩阵：2,820,566 行 x 29 列
覆盖 instruments：816
CIK 映射：855
失败或跳过：918
Alpha158-only: IC 0.015469, Rank IC -0.009241, 年化 36.67%, 最大回撤 -17.12%, alpha 5.10%
Alpha158 + EDGAR: IC -0.004242, Rank IC -0.009994, 年化 17.43%, 最大回撤 -19.82%, alpha -13.06%
```

结论：

```text
EDGAR 真实接入成功，但第一版直接拼接财报和估值特征没有带来增量，反而拖累模型。
当前默认主线仍应保留 Alpha158-only conservative baseline。
EDGAR 下一步应该先做覆盖率审计、字段清洗、行业内相对特征和分组 ablation，而不是直接作为默认模型输入。
```

遗留问题：

```text
PERMNO -> CIK 仍有 306 个 missing_cik。
missing_fields 说明 XBRL tag 和行业口径差异明显。
估值因子可能受亏损公司、负自由现金流和极端值影响。
跨行业直接比较财报指标不合理，需要行业内相对化。
```

下一阶段准备：

```text
做 EDGAR 覆盖率报告：按年份、SIC2 sector、SIC4 industry、历史长度桶统计覆盖和失败原因。
做 EDGAR 特征清洗：处理极端估值、负分母、缺失字段。
做行业内财报/估值相对特征：先比较 ROE、gross margin、price_to_sales、liabilities_to_assets 的行业内 percentile。
做 EDGAR ablation：盈利、成长、质量、负债、估值、披露状态分组验证。
```

产出文件：

```text
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_10d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_10d_conservative_2010_2025/fundamental_features.parquet
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_10d_conservative_2010_2025/fundamental_failures.csv
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_10d_conservative_2010_2025/edgar_cik_map.csv
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_10d_conservative_2010_2025/report.md
learning/05-data-expansion/CRSP EDGAR Fundamentals Integration.md
```

## 2026-05-23 阶段 CRSP-11：EDGAR 覆盖审计、清洗、行业相对特征与 Ablation

目标：

```text
确认 CRSP 主线中的 EDGAR 覆盖质量，清洗极端财报/估值特征，恢复基于 PIT 行业映射的财报相对特征，并用 ablation 判断哪些 EDGAR 信息有用。
```

为什么要做：

```text
第一版 Alpha158 + EDGAR 直接拼接后显著弱于 Alpha158-only。
在决定是否继续使用 EDGAR 前，必须先确认覆盖、缺失、极端值和特征组贡献。
```

输入数据：

```text
CRSP 2010-2025 monthly dynamic Top500
SEC EDGAR companyfacts / submissions
CRSP PIT industry_master.parquet
Alpha158-only conservative baseline
```

核心概念：

```text
覆盖审计：看哪些股票、年份、行业真正有可用财报特征
固定规则清洗：不用全样本分位数，避免未来函数
行业内相对化：财报和估值应优先同业比较
Ablation：删除某组特征后如果表现变好，说明该组可能是噪声
```

实验动作：

```text
新增 EDGAR 覆盖率审计输出
新增 fundamental_features_cleaned.parquet 和 cleaning summary
新增基于 industry_master 的 EDGAR 行业相对特征
新增 8 组 EDGAR ablation manifest 和汇总脚本
运行 clean、relative、5 个 drop 组并汇总
```

评价指标：

```text
CIK 映射覆盖率
EDGAR 特征 instrument 覆盖率
字段缺失率
清洗 set_nan / clip 次数
IC / Rank IC
Top10 年化收益 / alpha / beta / 最大回撤
best iteration
```

结果解读：

```text
CIK mapping coverage: 73.64%
feature instrument coverage: 70.28%
failure count: 918
Clean EDGAR: IC 0.001496, Rank IC -0.004580, 年化 22.04%, alpha -12.08%
Clean EDGAR + Relative: IC -0.003471, Rank IC -0.009711, 年化 21.34%, alpha -9.04%
drop_valuation: Rank IC -0.002181, 年化 25.90%，是 EDGAR 组里排序最接近 0 的版本
Alpha158-only: 年化 36.67%, alpha 5.10%，仍然是最好基线
```

结论：

```text
EDGAR 数据链路和复盘工具已经可用，但当前 10 日收益标签下，EDGAR 不应进入默认模型。
估值组当前可能是最明显的排序噪声；盈利质量组不能简单删除，但需要单独研究。
行业内财报相对特征受 EDGAR 缺失率和 SIC4 样本不足影响，暂未证明有效。
```

遗留问题：

```text
PERMNO -> CIK 覆盖仍不完整。
EDGAR 字段缺失集中在 gross margin、FCF、负债率、成长和估值字段。
SIC4 行业组样本不足，relative features 大量 fallback 到 SIC2。
10 日标签可能太短，未必适合财报基本面。
```

下一阶段准备：

```text
短期不把 EDGAR 设为默认。
后续若继续研究 EDGAR，应先单独测试盈利质量组，并把收益标签拉长到 20/60 日。
当前默认主线仍以 Alpha158-only score + sector_cap_2_top10 作为候选策略。
```

产出文件：

```text
analysis/nasdaq_top500_score/edgar_coverage.py
analysis/nasdaq_top500_score/crsp_edgar_ablation_review.py
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_clean_10d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_relative_10d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/configs/crsp_edgar_ablation/manifest.yaml
analysis/nasdaq_top500_score/runs/crsp_edgar_ablation_review/crsp_edgar_ablation_summary.csv
learning/05-data-expansion/CRSP EDGAR Coverage Cleaning And Ablation.md
```

## 2026-05-23 阶段 CRSP-12：EDGAR 字段级覆盖修复

目标：

```text
在不扩大训练窗口的前提下，修复 EDGAR 覆盖不完整中最明显的工程问题：字段级缺失不能沿用上一期已披露值。
```

为什么要做：

```text
旧版已经按最近一份 filing 做 as-of forward fill，但如果最新 filing 缺某个字段，不会单独沿用上一期同字段。
这会让低频财报数据出现不必要缺口。
```

输入数据：

```text
CRSP 2010-2025 monthly dynamic Top500
SEC EDGAR submissions / companyfacts
已有 Alpha158-only baseline
```

核心概念：

```text
字段级 as-of forward fill：每个财报字段只从过去已经披露过的记录向后续用
stale 上限：字段太久没更新后失效，不再继续填
coverage-aware 特征：让模型知道某类财报字段是否可用，以及距上次披露多久
```

实验动作：

```text
扩展 XBRL tag alias
新增 edgar_tag_resolution_report.csv
新增 edgar_missingness_root_cause.csv
新增 edgar_field_availability_by_year.csv
新增 repaired_quality_only 和 repaired_no_valuation 两组配置
运行两组真实实验
```

评价指标：

```text
CIK mapping coverage
feature instrument coverage
missing_fields 数量
字段缺失率
IC / Rank IC
Top10 年化收益 / alpha / beta / 最大回撤
```

结果解读：

```text
CIK mapping coverage: 73.64%，未变化
feature instrument coverage: 70.28%，未变化
missing_fields: 573 -> 519
fcf_margin missing: 60.31% -> 46.36%
operating_margin missing: 53.73% -> 45.97%
gross_margin missing: 74.76% -> 71.11%
repaired_quality_only: IC 0.014578, Rank IC -0.002942, 年化 26.88%, alpha -4.27%, 最大回撤 -18.59%
repaired_no_valuation: IC -0.000555, Rank IC -0.002331, 年化 9.26%, alpha -22.40%, 最大回撤 -21.82%
```

结论：

```text
字段级修复有效改善了缺失率，也让盈利质量组明显优于 clean EDGAR。
但 EDGAR 仍未超过 Alpha158-only，所以默认主线仍不启用 EDGAR。
后续 EDGAR 研究应聚焦 profitability_quality + coverage_state，而不是全量财报特征。
```

遗留问题：

```text
CIK 映射没有改善，因为当前 CRSP warehouse 没有额外 CIK 字段可用。
早期年份结构化 XBRL 覆盖仍很弱。
部分 tag alias 仍可能需要逐字段核对。
10 日标签对财报基本面可能仍偏短。
```

下一阶段准备：

```text
暂不继续扩展 EDGAR。
如果继续研究财报，先做盈利质量组在 sector_cap_2 组合约束下的边际候选复盘。
默认策略仍保持 Alpha158-only score + sector_cap_2_top10 候选。
```

产出文件：

```text
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_repaired_quality_10d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_repaired_no_valuation_10d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_repaired_quality_10d_conservative_2010_2025/report.md
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_repaired_quality_10d_conservative_2010_2025/edgar_missingness_root_cause.csv
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_repaired_quality_10d_conservative_2010_2025/edgar_tag_resolution_report.csv
```

## 2026-05-23 阶段 CRSP-13：EDGAR Quality Core 与字段有效性审计

目标：

```text
把 EDGAR 从全量拼接改成字段筛选研究：先保留盈利质量、披露状态和覆盖状态，再用字段级 IC / Rank IC / 分位收益诊断识别有效信息。
```

为什么要做：

```text
前序 clean / repaired 实验说明 EDGAR 不是完全无效，但全量加入会拖累 alpha。
需要知道是哪些字段有用，哪些字段只是缺失噪声或估值噪声。
```

输入数据：

```text
CRSP 2010-2025 monthly dynamic Top500
Alpha158 10 日 conservative baseline
SEC EDGAR cleaned + repaired quality features
CRSP PIT SIC2/SIC4 industry_master
```

核心概念：

```text
quality core：只保留 profitability_quality、filing_state、coverage_state
字段有效性：字段值和未来 10 日收益在同一交易日横截面上的 IC / Rank IC
分位收益差：字段高分组和低分组未来收益是否有稳定差异
```

实验动作：

```text
新增 edgar_effectiveness_review
新增 crsp_alpha158_edgar_quality_core_10d_conservative_2010_2025.yaml
扩展 CRSP EDGAR ablation manifest
更新学习文档和命令入口
```

评价指标：

```text
字段 IC / Rank IC
按年份和 sector 的字段 IC
Top/Bottom quantile spread
TopK 年化收益 / alpha / beta / 最大回撤
```

结果解读：

```text
quality core Test IC: 0.014578
quality core Test Rank IC: -0.002942
global Top10 年化收益: 26.88%
global Top10 alpha: -4.27%
global Top10 最大回撤: -18.59%
sector_cap_2_top10 年化收益: 40.95%
sector_cap_2_top10 alpha: 4.81%
sector_cap_2_top10 最大回撤: -19.67%
Alpha158-only + sector_cap_2_top10 年化收益: 46.26%
Alpha158-only + sector_cap_2_top10 alpha: 13.03%
```

结论：

```text
quality core 比 clean EDGAR 更合理，但仍弱于 Alpha158-only + sector_cap_2。
EDGAR 不进入默认主线。
盈利质量字段中 operating_margin、free_cash_flow_ttm、net_margin、fcf_margin、operating_cash_flow_ttm 更值得单独研究。
coverage_state 不应直接默认入模，先作为复盘诊断。
```

遗留问题：

```text
字段筛选不能只看测试期表现，否则会形成二次过拟合。
估值组暂时剔除，但仍保留在研究 ablation 中。
更长标签周期 20/60 日仍待单独验证。
edgar_effectiveness_review 本次耗时约 219 秒，应改成可选或缓存复用。
```

下一阶段准备：

```text
新增 EDGAR mini-core 配置，只保留少数盈利质量字段。
做 20 日 / 60 日标签对照，验证财报字段是否更适合中期收益。
默认策略继续保持 Alpha158-only score + sector_cap_2_top10。
```

产出文件：

```text
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_quality_core_10d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/configs/crsp_edgar_ablation/manifest.yaml
analysis/nasdaq_top500_score/edgar_coverage.py
analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
```

## 2026-05-23 阶段 CRSP-14：EDGAR Mini-Core 与 Horizon 对照准备

目标：

```text
把 EDGAR 入模字段收缩到 5 个盈利质量/现金流字段，并准备 20 日、60 日标签对照。
```

为什么要做：

```text
quality core 仍弱于 Alpha158-only + sector_cap_2，但字段审计显示少数盈利质量字段 Rank IC 为正。
财报数据可能不适合 10 日收益，更可能适合 20 日或 60 日中期收益。
```

输入数据：

```text
CRSP 2010-2025 monthly dynamic Top500
Alpha158-only conservative baseline
SEC EDGAR repaired quality features
```

核心概念：

```text
mini-core：只保留 operating_margin、free_cash_flow_ttm、net_margin、fcf_margin、operating_cash_flow_ttm
horizon 对照：label_horizon_days、holding_days、rebalance_days 必须同步为 20 或 60
```

实验动作：

```text
新增 fundamentals.include_features 白名单
新增 10/20/60 日 EDGAR mini-core 配置
新增 20/60 日 Alpha158-only 配置
新增 crsp_edgar_mini_core_horizon_review.py 汇总脚本
```

评价指标：

```text
IC / Rank IC
best iteration
global Top10 年化收益 / alpha / 最大回撤
sector_cap_2_top10 年化收益 / alpha / 最大回撤
50bps 压力年化收益
```

结果解读：

```text
六组真实训练已完成。
10 日 mini-core：IC=0.013347，Rank IC=-0.000493，global 年化=38.93%，global alpha=4.16%。
10 日 Alpha158-only：IC=0.015469，Rank IC=-0.009241，global 年化=36.67%，global alpha=5.10%。
10 日 mini-core + sector_cap_2：年化=48.84%，alpha=11.10%。
20 日 mini-core：年化=27.62%，alpha=-10.26%，弱于 20 日 Alpha158-only。
60 日 mini-core：年化=22.67%，alpha=-13.44%，弱于 60 日 Alpha158-only。
结论是 mini-core 对 10 日组合收益有边际帮助，但不足以进入默认主线；20/60 日不支持继续沿 EDGAR 中期标签方向推进。
```

遗留问题：

```text
10 日 mini-core 的改善可能来自 sector_cap_2 组合约束下的持仓替换，需要进一步拆解。
Rank IC 改善接近 0，但没有转正，不能说横截面排序能力已经确认增强。
20/60 日标签下 EDGAR 表现更弱，说明当前五个财报字段不能简单迁移到更长周期。
```

下一阶段准备：

```text
做 10 日 mini-core vs Alpha158-only + sector_cap_2 的持仓差异复盘。
重点看新增/移除股票、行业分布、贡献来源、财报字段水平，以及收益是否由少数样本贡献。
如果改善不稳定，EDGAR 继续留在研究分支，不进入默认策略。
```

产出文件：

```text
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_mini_core_10d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_20d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_mini_core_20d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_60d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_mini_core_60d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/crsp_edgar_mini_core_horizon_review.py
```

## 2026-05-23 阶段 CRSP-15：EDGAR Mini-Core 持仓差异复盘

目标：

```text
解释 EDGAR mini-core + sector_cap_2_top10 的组合改善来自哪些持仓替换，而不是只看年化收益。
```

为什么要做：

```text
10 日 mini-core 的 sector_cap_2 年化达到 48.84%，但 Rank IC 仍未转正。
必须判断改善是否来自少数股票、单一行业或偶然调仓期。
```

输入数据：

```text
Alpha158-only + sector_cap_2_top10 backtest_positions.csv
EDGAR mini-core + sector_cap_2_top10 backtest_positions.csv
EDGAR mini-core fundamental_features_cleaned.parquet
```

实验动作：

```text
新增 crsp_edgar_mini_core_position_diff.py
逐调仓日标记 common / added_by_edgar / removed_by_edgar
汇总新增/移除股票、sector、industry、历史长度桶和财报字段差异
输出中文 report.md 和 summary yaml
```

评价指标：

```text
新增持仓净贡献
被移除持仓原净贡献
Top3 新增正贡献占比
最大 sector 新增正贡献占比
新增 vs 移除的 mini-core 财报字段均值/中位数/缺失率
```

结果解读：

```text
共同持仓 352 行。
EDGAR 新增 148 个持仓行，涉及 115 只股票，净贡献 0.2308。
EDGAR 移除 148 个持仓行，涉及 97 只股票，原 Alpha158 净贡献 0.1889。
替换贡献差约 +0.0419。
Top3 新增正贡献占比 23.71%，最大 sector 新增正贡献占比 17.96%，未触发集中风险。
新增持仓的 operating_margin、net_margin、fcf_margin 和 operating_cash_flow_ttm 均值高于被移除持仓。
```

结论：

```text
EDGAR mini-core 的改善有一定经济解释，且不是明显由少数股票或单一行业贡献。
但因为 global alpha 没改善、Rank IC 未转正，它仍不进入默认主线。
保留为 10 日 sector_cap_2 研究分支。
```

下一阶段准备：

```text
如果继续 EDGAR，下一步做滚动窗口或更早测试期复盘，验证 mini-core 是否只适配 2024-2025。
如果回到主线，默认仍使用 Alpha158-only + sector_cap_2_top10。
```

产出文件：

```text
analysis/nasdaq_top500_score/crsp_edgar_mini_core_position_diff.py
analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_position_diff_review/report.md
analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_position_diff_review/edgar_mini_core_position_diff_summary.yaml
analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_position_diff_review/edgar_mini_core_position_diff.csv
analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_position_diff_review/edgar_mini_core_contribution_diff.csv
analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_position_diff_review/edgar_mini_core_fundamental_diff.csv
```

## 2026-05-23 阶段 CRSP-16：滚动窗口验证框架

目标：

```text
确认当前默认研究主线 Alpha158-only + sector_cap_2_top10 是否跨多个市场阶段稳定，并把 EDGAR mini-core + sector_cap_2_top10 作为候选分支一起验证。
```

为什么要做：

```text
此前主要结果来自 2024-2025 单一测试窗口。
如果更早窗口失效，当前高收益只能作为局部观察，不能作为默认主线结论。
```

输入数据：

```text
CRSP 2010-2025 monthly dynamic Top500
10 日未来收益标签
10 日调仓、次日 open 入场
Alpha158-only conservative 配置
EDGAR mini-core conservative 配置
CRSP PIT SIC2/SIC4 行业映射
```

实验动作：

```text
新增 configs/crsp_rolling_windows/manifest.yaml
新增 4 个测试窗口 x 2 条特征线 = 8 个配置
新增 crsp_rolling_window_validation.py
支持跳过已完成 run、--only-summary 汇总和 --force 强制重跑
新增 fake run 汇总测试
```

评价指标：

```text
IC
Rank IC
best iteration
sector_cap_2 年化收益
sector_cap_2 alpha / beta
sector_cap_2 最大回撤
50bps 压力结果
跨窗口通过数量
```

当前结果：

```text
8 组真实训练全部完成，状态均为 ok。
Alpha158-only + sector_cap_2：1/4 个窗口 alpha 为正。
EDGAR mini-core + sector_cap_2：3/4 个窗口 alpha 高于 Alpha158-only。
最佳窗口：2020-2021 EDGAR mini-core，sector_cap_2 alpha=13.05%，Rank IC=0.019793。
最弱窗口：2022-2023，Alpha158 sector_cap_2 alpha=-15.05%，EDGAR mini-core sector_cap_2 alpha=-11.15%。
滚动汇总分类：candidate_branch。
```

结论：

```text
滚动窗口验证是当前最重要的稳定性审计。
Alpha158-only + sector_cap_2 未通过稳定默认标准，不能只凭 2024-2025 的高收益作为主线结论。
EDGAR mini-core 有跨窗口边际价值，但还不能替代默认，因为 2022-2023 仍明显失效，2024-2025 的 alpha 也低于 Alpha158-only。
```

下一阶段准备：

```text
优先复盘 2022-2023 失效窗口：行业暴露、beta、持仓贡献、回撤来源、市场 regime。
复盘 2018-2021 中 EDGAR 改善来自哪些字段和持仓替换。
暂不继续堆宏观或更多 EDGAR 字段，先解释跨窗口不稳定来源。
```

产出文件：

```text
analysis/nasdaq_top500_score/configs/crsp_rolling_windows/manifest.yaml
analysis/nasdaq_top500_score/configs/crsp_rolling_windows/*_alpha158_only.yaml
analysis/nasdaq_top500_score/configs/crsp_rolling_windows/*_edgar_mini_core.yaml
analysis/nasdaq_top500_score/crsp_rolling_window_validation.py
tests/analysis/test_crsp_rolling_window_validation.py
learning/05-data-expansion/CRSP Rolling Window Validation.md
```

## 2026-05-23 阶段 CRSP-17：滚动窗口失败复盘与主线修正

目标：

```text
复盘 Alpha158-only + sector_cap_2 和 EDGAR mini-core + sector_cap_2 的 rolling window 结果，解释跨窗口不稳定来源，并补齐 sector_cap_2 的压力测试。
```

为什么要做：

```text
滚动验证显示原默认主线只在 2024-2025 明显有效。
如果不解释 2022-2023 的共同失效，就不能继续把高收益窗口当成策略结论。
```

输入数据：

```text
8 个已完成 rolling run
sector_cap_2_top10 backtest_nav.csv
sector_cap_2_top10 backtest_positions.csv
strategy_comparison.csv
benchmark_summary.yaml
EDGAR mini-core fundamental_features_cleaned.parquet
```

实验动作：

```text
新增 crsp_rolling_window_failure_review.py
不重新训练模型，只复用已有持仓和净值
补齐 sector_cap_2_top10 的 0/25/50bps 压力测试
生成 rolling_window_failure_summary.csv
生成 rolling_window_drawdown_events.csv
生成 rolling_edgar_delta_by_window.csv
刷新 crsp_rolling_window_summary.csv
```

评价指标：

```text
年化收益
alpha / beta
最大回撤
50bps 压力年化和压力 alpha
行业贡献
单票贡献
EDGAR 新增/移除持仓贡献差
最大回撤区间
```

当前结果：

```text
Alpha158-only + sector_cap_2：1/4 个窗口 alpha 为正，状态 unstable_default_candidate。
EDGAR mini-core + sector_cap_2：3/4 个窗口 alpha 高于 Alpha158-only，状态 candidate_branch。
2022-2023 Alpha158：年化 -18.30%，alpha -15.05%，beta 1.64，最大回撤 -43.44%。
2022-2023 EDGAR：年化 -14.16%，alpha -11.15%，beta 1.50，最大回撤 -39.29%。
sector_cap_2 50bps 压力下没有一个 rolling 行为正 alpha。
```

结果解读：

```text
2022-2023 是共同失效窗口，问题不是单纯增加或删除 EDGAR 字段能解决。
EDGAR mini-core 的改善更多表现为“亏得少”和部分窗口替换持仓有效，不足以替代默认策略。
50bps 压力结果说明当前 Top10 + sector_cap_2 对换手和交易摩擦敏感。
```

遗留问题：

```text
2022-2023 的亏损到底来自 beta 暴露、行业暴露、单票极端亏损，还是模型排序本身失效。
EDGAR mini-core 的改善是否集中在少数行业或少数调仓期。
如果 IC 仍有信号但 TopK 亏损，应优先改组合构建；如果 IC 也失效，应回到标签和特征设计。
```

下一阶段准备：

```text
做 2022-2023 专项失效复盘。
按回撤区间拆行业贡献、单票贡献、beta 暴露和持仓集中度。
暂不继续堆新特征，先判断失效类型。
```

产出文件：

```text
analysis/nasdaq_top500_score/crsp_rolling_window_failure_review.py
tests/analysis/test_crsp_rolling_window_failure_review.py
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/failure_review/rolling_window_failure_review.md
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/failure_review/rolling_window_failure_summary.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/failure_review/rolling_edgar_delta_by_window.csv
learning/05-data-expansion/CRSP Rolling Window Failure Review.md
```

## 2026-05-23 阶段 CRSP-18：2022-2023 专项失效复盘

目标：

```text
解释 2022-2023 中为什么两条线 Test IC / Rank IC 弱正，但 sector_cap_2 Top10 组合仍然亏损。
```

为什么要做：

```text
滚动窗口失败复盘确认 2022-2023 是共同失效窗口。
如果不拆清 IC/TopK 背离，就无法判断下一步应该改模型特征、组合构建还是风险过滤。
```

输入数据：

```text
2022_2023/alpha158_only/test_predictions.csv
2022_2023/edgar_mini_core/test_predictions.csv
prepared qlib_source_csv 中的 label_10d_total_return
sector_cap_2_top10/backtest_nav.csv
sector_cap_2_top10/backtest_positions.csv
EDGAR mini-core fundamental_features_cleaned.parquet
```

实验动作：

```text
新增 crsp_2022_2023_failure_deep_dive.py
按 signal_date 计算每日 IC / Rank IC
把每日 IC 映射到对应 Top10 调仓收益
识别 positive IC but negative TopK 的调仓期
计算 rolling beta、上/下行捕获
拆最大回撤区间内 sector / industry / symbol 贡献
比较 EDGAR 相对 Alpha158 的新增/移除/共同持仓
```

评价指标：

```text
IC / Rank IC
Top10 gross return
候选池平均 label
Top10 - 候选池均值
最大回撤区间
rolling beta
sector / symbol 净贡献
EDGAR 持仓替换贡献差
```

当前结果：

```text
Alpha158-only IC=0.0166，Rank IC=0.0064，Top10 平均收益=-0.55%。
EDGAR mini-core IC=0.0290，Rank IC=0.0123，Top10 平均收益=-0.40%。
Alpha158-only 有 31/51 个调仓期 Top10 跑输候选池均值。
EDGAR mini-core 有 28/51 个调仓期 Top10 跑输候选池均值。
Alpha158-only 最大回撤 -43.44%，持续 41 个调仓期。
EDGAR mini-core 最大回撤 -39.29%，持续 8 个调仓期。
```

结果解读：

```text
模型不是完全无信号，而是信号太弱，无法支撑高度集中的 Top10 组合。
EDGAR mini-core 改善了排序和部分持仓替换，但新增持仓整体仍亏，只是比被替换的 Alpha158 持仓亏得少。
当前更像是组合构建和风险过滤问题，而不是继续堆新特征能直接解决的问题。
```

遗留问题：

```text
Top10 是否过于集中，需要 Top20 / Top30 对照验证。
高 beta 和高波动股票是否解释主要回撤。
单票 P20892、P16140 等是否需要冷却期或极端亏损过滤。
sector_cap_2 是否只限制数量而没有限制行业风险贡献。
```

下一阶段准备：

```text
先做 TopK 宽度对照：Top10 / Top20 / Top30。
再做单票风险过滤：近期高波动、近期大回撤、连续亏损入选。
再做 beta 控制：历史 beta 过滤或降权。
暂不继续加入宏观或更多 EDGAR 字段。
```

产出文件：

```text
analysis/nasdaq_top500_score/crsp_2022_2023_failure_deep_dive.py
tests/analysis/test_crsp_2022_2023_failure_deep_dive.py
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023_failure_deep_dive/2022_2023_failure_deep_dive_report.md
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023_failure_deep_dive/ic_topk_divergence_by_period.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023_failure_deep_dive/sector_failure_contribution.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023_failure_deep_dive/symbol_failure_contribution.csv
learning/05-data-expansion/CRSP 2022 2023 Failure Deep Dive.md
```

## 2026-05-23 阶段 CRSP-19：组合构建与风险过滤修复

目标：

```text
验证弱正 IC 是否可以通过组合构建修复，而不是继续加入 EDGAR / macro / 新特征。
```

为什么要做：

```text
2022-2023 专项复盘显示，模型 IC / Rank IC 弱正，但 sector_cap_2 Top10 仍亏损。
这说明问题可能在 TopK 太窄、单票风险过高、beta 暴露过大或等权组合放大错误股票。
```

输入数据：

```text
4 个 rolling 窗口：2018-2019、2020-2021、2022-2023、2024-2025。
两条线：Alpha158-only、EDGAR mini-core。
每条线复用 test_predictions.csv、rolling run 的配置、CRSP prepared dataset、membership、history bucket、benchmark 和 qlib_source_csv label。
```

实验动作：

```text
新增 crsp_portfolio_repair.py。
固化 sector_cap_2_top10 基准。
跑 Top10 / Top20 / Top30 / Top50 宽度对照。
跑 equal / score / inverse_vol / beta_adjusted 权重对照。
跑 soft / hard 单票风险过滤。
跑 beta_cap_1.5 / beta_cap_1.2 / beta_neutral_weight / beta_penalty_score。
所有实验不重训模型，只改组合构建。
```

评价指标：

```text
IC / Rank IC
年化收益
alpha / beta
最大回撤
TopK - 候选池均值
50bps 压力年化
50bps 正 alpha 窗口数
换手率
```

当前结果：

```text
EDGAR Top30 等权：平均 alpha 5.64%，正 alpha 4/4，平均 beta 1.20，最差回撤 -31.71%，50bps 平均年化 1.41%。
EDGAR Top10 inverse_vol_weight：平均年化 24.32%，平均 alpha 6.12%，正 alpha 3/4，平均 beta 1.35，最差回撤 -36.73%，50bps 正 alpha 0/4。
EDGAR Top30 soft risk filter：平均 alpha 2.45%，正 alpha 3/4，平均 beta 0.89，最差回撤 -30.79%，50bps 平均年化 -4.08%。
EDGAR Top10 beta_neutral_weight：平均 alpha 3.74%，正 alpha 3/4，平均 beta 1.22，最差回撤 -36.76%，50bps 平均年化 -2.32%。
```

结果解读：

```text
Top10 确实太窄，Top30 / Top50 可以降低集中风险和最大回撤。
inverse_vol 权重是本轮最好观察项，但交易压力下仍不稳。
风险过滤和 beta 控制能降低风险暴露，但会牺牲收益。
组合修复有价值，但不足以让当前标签下的策略成为稳定默认主线。
```

遗留问题：

```text
当前未来 10 日总收益标签天然偏向高 beta、高波动和顺风行业。
组合规则只能缓解风险暴露，不能从根上改变模型学习目标。
50bps 压力下没有候选规则稳定通过，说明换手和交易摩擦仍是关键约束。
```

下一阶段准备：

```text
进入 CRSP-20 标签重设计。
优先做未来 10 日超额收益、sector-neutral return、beta-adjusted return、risk-adjusted return。
目标是让模型预测更接近个股 alpha 的收益，而不是绝对总收益。
```

产出文件：

```text
analysis/nasdaq_top500_score/crsp_portfolio_repair.py
tests/analysis/test_crsp_portfolio_repair.py
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/portfolio_repair/crsp_portfolio_repair_report.md
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/portfolio_repair/crsp_portfolio_repair_decision.yaml
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/portfolio_repair/topk_width_comparison.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/portfolio_repair/portfolio_weighting_comparison.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/portfolio_repair/beta_control_comparison.csv
learning/06-portfolio-risk/CRSP Portfolio Construction And Risk Filter Repair.md
```

## 2026-05-23 阶段 CRSP-20：大型研究阶段收束与 Personal Quant v1 启动

目标：

```text
对 CRSP / Alpha158 / EDGAR / macro 大型研究路线做阶段性收束，并为个人小资金实盘研究启动干净的新方向。
```

为什么要做：

```text
当前路线变量过多、训练慢、解释难，且 rolling window 不稳定。
Top30 / Top50 的组合形态不适合小资金实盘，继续在旧架构中堆特征会进一步偏离用户目标。
```

输入数据：

```text
CRSP 2010-2025 动态 Top500 实验结果。
Alpha158-only、EDGAR mini-core、macro interaction、rolling window、2022-2023 deep dive、CRSP-19 组合修复结果。
```

核心概念：

```text
研究平台 vs 实盘策略雏形。
高维模型 vs 可解释小型系统。
TopK 分散 vs 小资金集中持仓。
绝对收益预测 vs 可复盘的个股 alpha 假设。
```

实验动作：

```text
新增 CRSP Large Research Stage Summary.md。
新增 Personal Quant V1 Direction.md。
新增 analysis/personal_quant_v1/README.md 作为干净代码起点。
更新 learning/README.md、Qlib Quant Learning Index、Qlib Commands 和学习日志。
```

评价指标：

```text
是否清楚总结旧阶段结论。
是否明确哪些能力保留、哪些方向降级或停止。
是否为下一阶段定义清晰能力边界。
是否给出适合个人小资金的持仓、变量、数据和复盘范围。
```

结果解读：

```text
旧阶段不失败，它完成了研究流程学习和风险识别。
但旧阶段不应继续作为实盘主线。
新阶段应从少变量、少持仓、可解释打分开始，而不是继续沿用 Alpha158 高维模型。
```

遗留问题：

```text
Personal Quant v1 的第一版因子权重如何定。
Top5 还是 Top10 更适合当前资金规模。
宏观风险开关如何影响仓位，而不是直接影响股票排序。
EDGAR mini-core 是否进入第一版，还是先做纯价格质量因子。
```

下一阶段准备：

```text
在 analysis/personal_quant_v1/ 中实现最小链路：
CRSP 数据读取 -> 10-15 个可解释因子 -> 因子打分 -> Top5/Top10 -> 两周回测 -> 持仓解释报告。
```

产出文件：

```text
learning/05-data-expansion/CRSP Large Research Stage Summary.md
learning/07-personal-quant/Personal Quant V1 Direction.md
analysis/personal_quant_v1/README.md
```
