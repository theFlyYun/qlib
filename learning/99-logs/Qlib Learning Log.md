# Qlib Learning Log

这份笔记用于记录学习和实验。重点不是贴命令输出，而是记录策略假设、数据来源和你对结果的判断。

## 记录模板

### 日期

- 学习主题：
- 策略假设：
- 使用数据：
- 信号来源：
- 交易规则：
- 回测结果：
- 成本后是否仍有效：
- 最大风险：
- 我现在相信什么：
- 我还不确定什么：
- 下一步验证：

## 2026-05-16 环境基线

- 已创建本地 `.venv`。
- 已安装 `pyqlib` dev 依赖。
- 已安装 macOS LightGBM 所需 `libomp`。
- 已下载简版 CN 日频数据。
- 已跑通 LightGBM + Alpha158 示例。
- 已生成预测、IC 分析和组合回测结果。

这条基线说明环境可用，但不说明策略可实盘。

## 当前重点问题

- 示例数据来自哪里，是否足够可靠？
- Alpha158 里的信号更偏趋势、反转、波动还是流动性？
- IC 为正是否能稳定转化为扣成本后的超额收益？
- Topk 策略的持仓数量和换手率如何影响结果？
- 这个策略在哪些市场阶段可能失效？

## 2026-05-17 Nasdaq 与 Qlib 模型复盘

- 学习主题：从规则打分升级到 Qlib Alpha158 + LightGBM 模型。
- 策略假设：价格和成交量特征可能预测股票未来短期横截面收益。
- 使用数据：Nasdaq-listed 非 ETF 股票，按总市值取前 500，下载近 2 年日线 OHLCV。
- 信号来源：Alpha158 技术面特征。
- 标签设计：当前默认预测 `t+1` 到 `t+2` 的 1 日收益；后续应改成未来 5 日收益。
- 模型结果：最新预测日 Top5 为 AXTI、LUNR、NBIS、MXL、FTNT。
- 验证结果：Test 日均 IC 为 -0.009905，Rank IC 为 -0.003036。
- 当前判断：流程跑通，但信号暂未证明有效，不能作为买入建议。
- 遗留问题：数据历史太短、股票池复杂、缺少财报/估值/行业/宏观/新闻、未做成本后 TopK 回测。
- 下一步验证：配置化流水线、40 年数据方案、5 日收益标签、行业内排序、PIT 财报与估值特征、完整组合回测。

详细笔记：[[2026-05-17 Nasdaq Qlib Model]]

## 2026-05-17 Alpha158 特征生成复盘

- 学习主题：当前模型的数据如何变成 Alpha158 特征。
- 策略假设：价格和成交量的形态、趋势、波动、位置和量价关系，可能对短期横截面收益排序有解释力。
- 使用数据：Nasdaq public 近 900 个自然日的日线 `open/high/low/close/volume/vwap`。
- 信号来源：Qlib Alpha158，从少量 OHLCV 字段派生 158 个技术面特征。
- 核心理解：Alpha158 不是 158 个原始字段，而是 `9 个 K 线形态 + 4 个价格比例 + 29 类滚动指标 * 5 个窗口`。
- 当前判断：它适合作为价格成交量 baseline，但没有财报、估值、行业、宏观、新闻和退市数据。
- 下一步验证：后续加入更长历史、行业分组、PIT 财报和估值特征时，必须和 Alpha158 baseline 对比。

详细笔记：[[Alpha158 And Features]]

## 2026-05-17 Norgate 数据源接入

- 学习主题：用 Norgate 升级价格行情、退市股票和历史指数成分。
- 策略假设：只有把历史股票池、复权和退市样本处理清楚，Alpha158 和 LightGBM 的验证结果才更接近真实可交易环境。
- 当前动作：新增 `data.source: norgate` 的可测试适配器，默认股票池为 S&P 500 历史成分。
- 核心理解：Norgate 不替代 Alpha158，而是给 Alpha158 提供更可靠的 OHLCV 和历史可交易范围。
- 当前限制：Mac 本地没有 Windows/Norgate Data Updater/订阅，只完成 fake client 测试；真实数据拉取留到 Windows 环境。
- 下一步：接入 SEC EDGAR，补财报披露日和 PIT 财报字段。

详细笔记：[[Norgate Data Integration]]

## 2026-05-17 SEC EDGAR 财报特征接入

- 学习主题：把 SEC EDGAR 10-K / 10-Q 结构化财报转成模型输入。
- 策略假设：Alpha158 只看价格成交量，加入 PIT 财报、盈利质量、成长、现金流、负债和估值特征后，可能提供基本面增量信息。
- 当前动作：新增 `fundamentals.source: sec_edgar`，按披露日生成日频 `edgar_` 特征，再与 Alpha158 合并训练。
- 核心理解：财报不能按财报期末日生效，必须按 `filed` / `acceptanceDateTime` 生效，避免未来函数。
- 当前限制：第一版不做 NLP，不处理 8-K，只做结构化 XBRL 字段；TTM 和同比口径仍是学习用基线。
- 下一步：设置 `SEC_EDGAR_USER_AGENT` 后先做 5 只股票 smoke test，再扩大到当前 Nasdaq 股票池。

详细笔记：[[SEC EDGAR Fundamentals Integration]]

## 2026-05-17 行业特征与行业内相对因子

- 学习主题：把 EDGAR 财报和估值特征改成行业内可比的 rank / percentile。
- 策略假设：估值、ROE、毛利率、成长和负债率不能直接跨行业比较；行业内相对位置可能比绝对数值更稳定。
- 使用数据：当前 Nasdaq public 股票池 `universe.csv` 中的 `sector` / `industry`，以及 EDGAR 生成的 `edgar_` 财报估值特征。
- 信号来源：行业内 rank、行业内 percentile、sector fallback percentile。
- 当前动作：新增行业特征配置和适配层，输出 `industry_features.parquet` 与 `industry_failures.csv`，并合并进同一个 Qlib LightGBM 模型。
- 当前判断：这一步完成的是模型输入升级，不等于已经完成行业中性策略。
- 当前限制：行业分类来自当前 Nasdaq snapshot，不是历史 PIT 行业分类。
- 下一步：做行业内 TopK / sector 权重限制回测，验证行业相对信号是否能转化为成本后收益。

详细笔记：[[Industry Features And Relative Ranking]]

## 2026-05-17 固定 15 年窗口与真实 EDGAR 准备

- 学习主题：把训练数据窗口固定为 `2011-05-17` 到 `2026-05-17`，并准备真实 SEC EDGAR 拉取。
- 策略假设：后续比较不同特征和标签时，必须先固定训练/验证/测试时间段，否则结果会随运行日期漂移。
- 使用数据：Nasdaq public 日线固定窗口；EDGAR smoke test 使用当前 Nasdaq 市值前 5。
- 当前动作：新增固定窗口 baseline 配置，支持 `data.start_date/end_date` 和 `split.method: date`。
- EDGAR 准备：真实拉取需要设置 `SEC_EDGAR_USER_AGENT`，先跑 5 只股票 smoke test，再扩大股票池。
- 当前限制：Nasdaq public 股票池仍是当前静态市值前 500，不是历史动态成分，也不含退市股票。
- 下一步：运行固定窗口 baseline，再设置 User-Agent 跑 EDGAR smoke test。

详细笔记：[[Fixed Window And Real EDGAR Runbook]]

## 2026-05-17 Nasdaq 当前前 500 市值 10 年数据

- 学习主题：把可落地训练窗口从 15 年调整为 Nasdaq public 当前可获取的 10 年窗口。
- 使用数据：当前 Nasdaq 市值前 500，窗口固定为 `2016-05-17` 到 `2026-05-17`。
- 当前结果：500 只股票中，319 只满足至少 2400 行日线并进入 Qlib 数据集，181 只历史不足或下载失败。
- 实际日历：`2016-05-17` 到 `2026-05-15`，共 2514 个交易日。
- 训练切分：Train 到 `2021-12-31`，Valid 为 2022-2023，Test 为 2024 到 2026-05。
- 当前判断：10 年窗口已可用于 baseline 训练；但股票池仍是当前静态前 500，不含退市股票和历史动态成分。
- 下一步：用同一 10 年窗口扩大 EDGAR 特征实验，先 50 只，再 100/500 只。

## 2026-05-17 短历史股票进入评估

- 学习主题：处理当前前 500 股票里不满 10 年历史的股票。
- 策略假设：短历史股票不能贡献它们不存在的早期训练样本，但如果在测试期有足够数据，仍可进入预测和横截面评估。
- 当前动作：新增 `nasdaq_alpha158_lgbm_10y_eval_all.yaml` 和 `nasdaq_alpha158_edgar_lgbm_10y_eval_all.yaml`。
- 关键规则：固定窗口仍是 `2016-05-17` 到 `2026-05-17`，但 `min_history_rows` 从 2400 降到 180。
- 当前判断：这会扩大测试期覆盖面，但样本结构更复杂，需要在报告中同时看股票数、失败数和历史长度分布。
- 风险：新股/短历史股票的训练历史更少，模型分数稳定性可能弱，不能和完整 10 年历史股票完全等同解读。

## 2026-05-17 10 年窗口真实 EDGAR 全量实验

- 学习主题：在当前 Nasdaq 市值前 500 的固定 10 年窗口中，真实获取 SEC EDGAR 财报数据并接入 Qlib 模型。
- 使用数据：Nasdaq public 日线 `2016-05-17` 到 `2026-05-17`，SEC EDGAR `10-K / 10-Q / 10-K/A / 10-Q/A` 结构化 XBRL。
- 当前动作：运行 `nasdaq_alpha158_edgar_lgbm_10y_eval_all.yaml`，把短历史股票最低门槛降为 180 行，并启用 EDGAR 财报估值特征。
- EDGAR 结果：CIK 映射 499 只，生成日频 PIT 财报特征 895,760 行、29 列，覆盖 420 只股票。
- 训练结果：最新日可预测股票 480 只，Test 日均 IC 为 0.011370，Rank IC 为 0.003418，参与 IC 计算 593 个交易日。
- Top5：`NVAWW`、`FLEX`、`NBIS`、`SNDK`、`TSEM`。
- 当前判断：真实 EDGAR 数据链路已经跑通，但字段缺失较多，且 Top5 出现 warrant / 特殊证券，说明后续必须做证券类型清洗。
- 下一步：先做股票池清洗和历史长度分桶，再把 EDGAR + 行业相对特征放到同一 10 年窗口里对比。

## 2026-05-17 股票池清洗、历史长度分桶与桶内 Top10

- 学习主题：把无约束模型榜单改成“清洗后股票池 + 历史长度桶名额”的受控候选组合。
- 策略假设：warrant、preferred、unit、right、notes 等特殊证券不应和普通股混在同一个 TopK 候选池里。
- 当前动作：新增股票池清洗、历史长度分桶、桶内 Top10 选择，默认名额为 `full_10y=4`、`5_10y=3`、`2_5y=2`、`lt_2y=1`。
- 本次清洗：剔除特殊证券 439 条，其中 `name:warrant` 228 条、`name:preferred` 101 条。
- 最新日分桶：`full_10y=335`、`5_10y=86`、`2_5y=48`、`lt_2y=13`。
- 最终 Top10：`AMD`、`SNDK`、`SIMO`、`NBIS`、`PLUG`、`MXL`、`BILI`、`LUNR`、`GTX`、`RGC`。
- 当前判断：桶内名额生效，少于 2 年历史桶保留 1 个观察名额，特殊证券污染明显下降。
- 下一步：加入行业内名额约束，避免 Top10 过度集中在 Technology / Semiconductors。

详细笔记：[[Stock Pool Cleaning And History Buckets]]

## 2026-05-17 行业名额约束

- 学习主题：在桶内 Top10 基础上继续控制行业集中度。
- 策略假设：即使所有股票都来自同一个模型 `score`，最终候选名单也不应过度集中在单一 sector 或 industry。
- 当前动作：在 `nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10.yaml` 中启用 `industry_constraints`，默认单一 sector 最多 4 只、单一 industry 最多 2 只。
- 关键规则：模型训练、标签、Alpha158、EDGAR 特征都不变；行业约束只发生在最终 Top10 选择阶段。
- 本次结果：最终 Top10 的 sector 分布为 `Technology=4`、`Consumer Discretionary=2`、`Health Care=2`、`Energy=1`、`Industrials=1`。
- 本次结果：最终 Top10 的 industry 分布中，`Semiconductors=2`、`Industrial Machinery/Components=2`，其余行业各 1 只。
- 当前判断：行业约束能降低榜单集中度，但仍不是成本后回测，也不是历史 PIT 行业分类。
- 下一步：加入流动性过滤，避免低成交额、低换手或交易不连续的股票进入候选组合。

详细笔记：[[Stock Pool Cleaning And History Buckets]]

## 2026-05-17 流动性过滤

- 学习主题：在进入 Qlib 训练和最终 Top10 之前，过滤低价、低成交额或交易不连续的股票。
- 策略假设：模型分数只回答“相对看好”，不回答“能不能低成本买卖”；低流动性股票需要先从候选池中剔除。
- 当前动作：新增 `liquidity_filter` 配置和流动性画像，输出 `liquidity_profile.csv` 与 `liquidity_exclusions.csv`。
- 默认规则：最新收盘价不低于 1 美元，近 20 日平均成交额不低于 500 万美元，近 60 日成交额中位数不低于 200 万美元，近 60 日零成交比例不超过 5%。
- 本次结果：482 只有可下载行情的股票生成流动性画像，4 只被剔除，478 只进入 Qlib 训练与预测。
- 被剔除股票：`LBTYB`、`MAAS`、`RGC`、`VFS`。
- 最终 Top10：`AXTI`、`AAOI`、`CHTR`、`LBRDK`、`FLY`、`NBIS`、`HUT`、`GTX`、`XMTR`、`RKLB`。
- 当前判断：流动性过滤改变了股票池和横截面样本，不应把 IC 变化直接理解为模型能力提升。
- 下一步：做证券主数据升级，减少仅靠 symbol / name 文本规则判断证券类型的误差。

详细笔记：[[Liquidity Filtering]]

## 2026-05-17 证券主数据升级

- 学习主题：把证券类型判断从隐含文本规则升级为显式 `security_master.csv`。
- 策略假设：普通股、ADR、权证、优先股、债券和 unit 不能混在同一个普通股模型候选池里。
- 当前动作：合并 Nasdaq listed 元数据和 Nasdaq screener 字段，生成 `security_master.csv` 与 `security_master_exclusions.csv`。
- 当前分类：`common_stock`、`ordinary_share`、`adr_ads`、`unknown_equity_like` 允许进入；`warrant`、`preferred`、`debt`、`unit`、`right`、`depositary_share` 剔除。
- 本次结果：主数据记录 3533 条，剔除 443 条，其中 warrant 279 条、preferred 104 条、debt 36 条。
- 本次结果：识别 ADR/ADS 162 条，share class 571 条。
- 最终 Top10：`AAOI`、`IBRX`、`LUNR`、`AXTI`、`FLEX`、`SNDK`、`CELC`、`QS`、`CORZ`、`LQDA`。
- 当前判断：这一步改善的是股票池口径，不是新增模型特征，也不是历史 PIT 主数据。
- 下一步：做未来 5 日收益标签，对比 1 日标签和 5 日标签的 IC、Rank IC 与 Top10 稳定性。

详细笔记：[[Security Master Data]]

## 2026-05-17 未来 5 日收益标签

- 学习主题：把模型预测目标从未来 1 日收益改成未来 5 日收益。
- 策略假设：1 日收益噪声很大，5 日收益可能更贴近中短期趋势、财报后反应和事件逐步定价。
- 当前动作：新增 `nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d.yaml`，除标签外保持证券主数据、流动性、EDGAR、模型参数、分桶和行业约束不变。
- 标签表达式：`Ref($close, -6) / Ref($close, -1) - 1`，含义是从 t+1 收盘到 t+6 收盘的 5 个交易日收益。
- 1 日结果：IC `-0.000519`，Rank IC `0.001712`，Top10 为 `AAOI`、`IBRX`、`LUNR`、`AXTI`、`FLEX`、`SNDK`、`CELC`、`QS`、`CORZ`、`LQDA`。
- 5 日结果：IC `0.036729`，Rank IC `0.016211`，Top10 为 `IBRX`、`LUNR`、`CYTK`、`LQDA`、`ONDS`、`BILI`、`KTOS`、`NTNX`、`TEM`、`TRI`。
- Top10 重叠：`IBRX`、`LQDA`、`LUNR`。
- 当前判断：5 日标签在当前口径下更有预测相关性，但还不是可交易结论，下一步必须做成本后回测。
- 下一步：做 TopK 成本后回测，观察净值、换手、最大回撤和成本后收益。

详细笔记：[[Five Day Future Return Label]]

## 2026-05-17 TopK 成本后回测

- 学习主题：把 5 日标签模型分数转成可复盘的 Top10 组合净值。
- 策略假设：如果模型对未来 5 个交易日收益有排序能力，那么每 5 个交易日选出 Top10、等权持有 5 个交易日，扣除交易成本后应仍有正收益。
- 当前动作：在 `nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d.yaml` 中启用 `backtest`，生成 `test_predictions.csv`、`backtest_nav.csv`、`backtest_positions.csv` 和 `backtest_summary.yaml`。
- 回测口径：测试期 `2024-01-02` 到 `2026-05-15`；信号日后 1 个交易日收盘买入；持有 5 个交易日；单边成本 10 bps；Top10 继续使用历史长度桶名额和行业约束。
- 本次结果：回测 118 期，累计收益 `2225.10%`，年化收益 `283.38%`，年化波动 `49.88%`，信息比率 `2.966`，最大回撤 `-18.11%`。
- 成本与换手：平均换手 `110.93%`，累计成本扣减 `13.09%`，平均持仓数量 `9.31`。
- 当前判断：这一步完成了从 IC 到组合净值的第一版闭环，但结果仍受免费行情、非 PIT 股票池、缺少退市股票、无真实滑点和无基准超额收益影响。
- 下一步：加入基准收益、超额收益、行业暴露复盘和更真实的成本/容量约束。

详细笔记：[[TopK Cost Backtest]]

## 2026-05-17 PIT 过滤版回测

- 学习主题：减少回测中的未来信息污染。
- 问题来源：旧版回测的历史长度分桶使用 2016-2026 全窗口，流动性过滤使用 2026 年末最近 20/60 日数据，这会让 2024 年回测提前知道未来。
- 当前动作：新增 `point_in_time_filters`，每个信号日按当时可见行情重新计算历史长度分桶和 20/60 日流动性。
- 新配置：`nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d_pit_safe.yaml`。
- 新结果：累计收益从 `2225.10%` 降到 `1097.92%`，年化收益从 `283.38%` 降到 `188.81%`，最大回撤从 `-18.11%` 扩大到 `-21.63%`。
- 当前判断：PIT 过滤确实削弱了收益，证明旧版回测有未来信息抬高的问题；但收益仍高，主要残余风险是股票池仍用运行日 Nasdaq 市值前 500，不是历史 PIT 股票池。
- 下一步：接入历史股票池、历史市值、退市股票和复权行情，优先继续推进 Norgate / CRSP 类数据源。

详细笔记：[[PIT Safe Backtest]]

## 2026-05-18 未来函数审计与冻结股票池

- 学习主题：继续压低回测里的未来信息风险，重点处理 EDGAR 披露生效日和测试期股票池选择。
- 问题来源 1：EDGAR `acceptanceDateTime` 之前被归一成披露当天日期，盘后披露可能在当天模型打分时提前可见。
- 修正 1：EDGAR 事件现在顺延到该股票价格日历中的下一个交易日才生效，再 forward fill 成日频 PIT 特征。
- 问题来源 2：`nasdaq_public` 股票池原来按运行日市值前 500 构建，回测 2024-2026 时仍带有当前幸存者和当前市值信息。
- 修正 2：新增 `nasdaq_alpha158_edgar_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml`，用 as-of 2023-12-31 的近似估算市值冻结股票池。
- 本次冻结实验：1000 只候选股票中，500 只入选冻结股票池，407 只低于 as-of 前 500，52 只在 2023-12-31 前无价格，41 只下载失败或历史不足。
- 本次结果：IC `0.010304`，Rank IC `-0.007921`，成本后累计收益 `26.41%`，年化收益 `10.53%`，最大回撤 `-31.60%`，平均换手 `129.98%`。
- 当前判断：冻结股票池后，收益从 PIT 过滤版的年化 `188.81%` 大幅降到 `10.53%`，说明运行日当前市值前 500 是一个很大的未来信息来源。
- 下一步：不要急着调参；优先继续升级数据源，补历史 shares outstanding、退市股票、真实复权行情和历史行业分类。

详细笔记：[[Future Information Audit]]

## 2026-05-18 基准与超额收益复盘

- 学习主题：判断冻结股票池后的 Top10 策略是否真的跑赢市场。
- 当前动作：在回测阶段加入 FRED `NASDAQCOM` 基准，按同一组入场日和退出日计算基准收益、超额收益、beta、alpha、跟踪误差和相对信息比率。
- 策略结果：成本后累计收益 `26.41%`，年化收益 `10.53%`，最大回撤 `-31.60%`。
- 基准结果：NASDAQCOM 累计收益 `78.78%`，年化收益 `28.17%`，最大回撤 `-22.66%`。
- 超额结果：超额累计收益 `-29.30%`，年化 alpha `-12.25%`，beta `1.092`，相对信息比率 `-0.319`。
- 当前判断：冻结股票池后的模型有绝对收益，但没有跑赢纳斯达克综合指数；当前还不能证明有稳定 alpha。
- 下一步：做持仓贡献和行业暴露复盘，判断收益/亏损来自哪些股票和行业，再考虑行业中性 TopK。

详细笔记：[[Benchmark And Excess Return Review]]

## 2026-05-18 持仓贡献与行业暴露复盘

- 学习主题：拆解冻结股票池 Top10 策略的收益来源和亏损来源。
- 当前动作：在回测阶段为每个持仓计算 `gross_contribution`、`cost_contribution`、`net_contribution` 和 `excess_contribution`，并按股票、sector、industry 聚合。
- 新增输出：`contribution_by_symbol.csv`、`contribution_by_sector.csv`、`contribution_by_industry.csv`、`exposure_by_sector.csv`、`exposure_by_industry.csv`、`contribution_summary.yaml`。
- 贡献口径：单票净贡献 = 持仓权重 × 单票收益 - 当期交易成本按持仓数平均分摊。
- 本次结果：前 5 大正贡献股票占全部正贡献 `30.95%`；正贡献最大股票为 `ASST`、`IBRX`、`CAR`、`IOVA`、`OPEN`；负贡献最大股票为 `IQ`、`VFS`、`UPST`、`FTRE`、`IRTC`。
- 行业结果：正贡献最大的 sector 是 `Technology`、`Health Care`、`Basic Materials`；负贡献最大的 sector 是 `Finance`、`Miscellaneous`、`Consumer Staples`。
- 暴露结果：平均 sector 暴露最高的是 `Health Care 32.85%`、`Technology 27.03%`、`Consumer Discretionary 17.49%`。
- 当前判断：策略收益并非完全靠一两只股票，但行业暴露偏向 Health Care 和 Technology；下一步应做行业中性 TopK 或行业内排名，而不是直接加模型复杂度。
- 下一步：实现行业中性 TopK，对比当前桶内 Top10 是否能改善超额收益和回撤。

详细笔记：[[Position Contribution And Exposure Review]]

## 2026-05-18 行业暴露对照实验

- 学习主题：拆开验证“行业押注”和“个股选择”，判断行业暴露是否应该被限制或显式利用。
- 当前动作：新增 `strategy_comparison`，同一批测试期模型预测分数只改变 Top10 选股规则，分别运行 `unconstrained_top10`、`sector_capped_top10` 和 `sector_momentum_tilt_top10`。
- 实验口径：as-of 2023-12-31 近似冻结 Nasdaq Top500；测试期 `2024-01-02` 到 `2026-05-15`；未来 5 日收益标签；每 5 个交易日调仓；单边成本 10 bps；基准为 `NASDAQCOM`。
- 原始 Top10：累计收益 `29.72%`，年化收益 `11.76%`，最大回撤 `-31.36%`，超额累计收益 `-27.44%`，年化 alpha `-9.83%`。
- 行业约束 Top10：累计收益 `57.38%`，年化收益 `21.37%`，最大回撤 `-28.69%`，超额累计收益 `-11.97%`，年化 alpha `-1.24%`。
- 行业增强 Top10：累计收益 `57.85%`，年化收益 `21.53%`，最大回撤 `-29.78%`，超额累计收益 `-11.71%`，年化 alpha `-1.10%`。
- 当前判断：适度限制行业集中度后表现更稳，说明原始 Top10 的自由行业暴露没有带来更好结果；行业动量增强略优于行业约束，但差距很小，还不能证明行业趋势模块稳定有效。
- 下一步：做行业内选股复盘，按 sector 分别看模型 score 和未来收益关系；再比较 `max_sector=2/3/4`、行业等权和行业动量权重。

详细笔记：[[Industry Exposure Strategy Comparison]]

## 复盘原则

- 先写假设，再看结果。
- 先问数据质量，再讨论模型。
- 先看成本后收益，再看成本前收益。
- 先看回撤和稳定性，再看最高收益。

## 相关笔记

[[Qlib Quant Learning Index]]
[[Qlib Commands]]
[[Qlib Source Map]]
[[Week 1 - Quant And Qlib Basics]]
[[2026-05-17 Nasdaq Qlib Model]]
[[Stage Completion Records]]
