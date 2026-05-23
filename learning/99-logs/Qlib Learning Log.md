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
- 当前动作：新增 `strategy_comparison`，同一批测试期模型预测分数只改变 Top10 选股规则，分别运行 `unconstrained_top10`、`sector_cap_3_top10` 和 `sector_momentum_tilt_top10`。
- 实验口径：as-of 2023-12-31 近似冻结 Nasdaq Top500；测试期 `2024-01-02` 到 `2026-05-15`；未来 5 日收益标签；每 5 个交易日调仓；单边成本 10 bps；基准为 `NASDAQCOM`。
- 原始 Top10：累计收益 `24.77%`，年化收益 `9.91%`，最大回撤 `-31.47%`，超额累计收益 `-30.21%`，年化 alpha `-14.17%`。
- 行业约束 Top10：累计收益 `76.79%`，年化收益 `27.55%`，最大回撤 `-29.58%`，超额累计收益 `-1.11%`，年化 alpha `1.87%`。
- 行业增强 Top10：累计收益 `67.91%`，年化收益 `24.78%`，最大回撤 `-30.71%`，超额累计收益 `-6.08%`，年化 alpha `-0.86%`。
- 当前判断：适度限制行业集中度后表现更稳，说明原始 Top10 的自由行业暴露没有带来更好结果；行业动量增强弱于普通行业约束，简单 60 日行业动量还不能证明稳定有效。
- 下一步：做行业内选股复盘，按 sector 分别看模型 score 和未来收益关系；再比较 `max_sector=2/3/4`、行业等权和行业动量权重。

详细笔记：[[Industry Exposure Strategy Comparison]]

## 2026-05-18 行业内选股复盘

- 学习主题：验证模型在同一个 sector 内部是否有选股排序能力。
- 当前动作：新增 `within_sector_review`，复用测试期 `test_predictions.csv`、当前 PIT 历史长度和流动性过滤规则，按 sector / industry 计算行业内 IC、Rank IC 和 Top-Bottom spread。
- 实验口径：信号日后 1 个交易日入场，持有 5 个交易日；sector 内可交易股票少于 10 时不计算 Top/Bottom spread。
- 覆盖结果：sector 数量 `12`，industry 数量 `93`，低样本 sector 数量 `0`，测试期有效信号期数 `118`。
- Rank IC 较好 sector：`Telecommunications 0.0728`、`Health Care 0.0215`；`Miscellaneous`、`Energy`、`Basic Materials` 虽然 Rank IC 较高，但平均可交易股票数少于 10，不能只看 Rank IC 下结论。
- Top-Bottom spread 较好 sector：`Telecommunications 1.4920%`、`Industrials 0.3859%`、`Health Care 0.3350%`。
- 排序较弱 sector：`Consumer Discretionary`、`Technology`、`Finance` 的 Rank IC 和 Top-Bottom spread 均偏弱或为负。
- 当前判断：行业约束仍有必要；当前模型在部分行业有行业内排序迹象，但并不稳定。Technology 样本多但行业内排序为负，是后续重点排查对象。
- 下一步：做 `max_sector=2/3/4` 参数敏感性，并对 Technology、Health Care、Consumer Discretionary 做 sector-specific 错误复盘。

详细笔记：[[Within Sector Stock Selection Review]]

## 2026-05-18 行业约束参数敏感性

- 学习主题：比较 `max_sector=2/3/4` 的行业约束强度，判断当前 Top10 组合应该允许单个 sector 最多持仓几只。
- 当前动作：把 frozen 配置中的 `strategy_comparison` 扩展为 `unconstrained_top10`、`sector_cap_2_top10`、`sector_cap_3_top10`、`sector_cap_4_top10` 和 `sector_momentum_tilt_top10`；同一批模型分数只改变最后选股约束。
- 实验口径：as-of 2023-12-31 近似冻结 Nasdaq Top500；测试期 `2024-01-02` 到 `2026-05-15`；未来 5 日收益标签；每 5 个交易日调仓；单边成本 10 bps；基准为 `NASDAQCOM`。
- 不限制 Top10：累计收益 `24.77%`，年化收益 `9.91%`，最大回撤 `-31.47%`，超额累计收益 `-30.21%`，Sector HHI `0.312`。
- `max_sector=2`：累计收益 `62.84%`，年化收益 `23.15%`，最大回撤 `-27.38%`，超额累计收益 `-8.92%`，Sector HHI `0.176`。
- `max_sector=3`：累计收益 `76.79%`，年化收益 `27.55%`，最大回撤 `-29.58%`，超额累计收益 `-1.11%`，Sector HHI `0.231`。
- `max_sector=4`：累计收益 `52.19%`，年化收益 `19.65%`，最大回撤 `-31.05%`，超额累计收益 `-14.87%`，Sector HHI `0.266`。
- 行业动量增强：累计收益 `67.91%`，年化收益 `24.78%`，最大回撤 `-30.71%`，超额累计收益 `-6.08%`，Sector HHI `0.244`。
- 当前判断：`max_sector=3` 年化收益和超额收益最好，`max_sector=2` 回撤和行业集中度最好但收益偏保守，`max_sector=4` 偏松。当前默认保留 `max_sector=3`、`max_industry=2`。
- 下一步：对 Technology、Health Care、Consumer Discretionary 做 sector-specific 错误复盘，解释为什么模型在某些行业内排序偏弱。

详细笔记：[[Industry Constraint Sensitivity]]

## 2026-05-19 重点行业错误复盘

- 学习主题：解释模型在 `Technology`、`Health Care`、`Consumer Discretionary` 里为什么排对或排错。
- 当前动作：新增 `sector_error_review`，把每个目标 sector 内的样本分成 `high_score_winners`、`high_score_losers`、`low_score_winners`、`low_score_losers` 四类，并对估值、财务、动量、流动性、市值、历史长度做差异对比。
- 实验口径：as-of 2023-12-31 近似冻结 Nasdaq Top500；测试期 `2024-01-02` 到 `2026-05-15`；信号日后 1 个交易日入场，持有 5 个交易日；沿用 PIT 历史长度和流动性过滤。
- 重要发现：本次 5.7C 完整运行重新训练了一次 LightGBM，模型分数和 5.7A/B 记录时略有差异。后续需要固定随机种子或复用缓存的 `test_predictions.csv`，否则跨阶段比较会混入重训波动。
- Technology：Rank IC `-0.0214`，Top-Bottom spread `-0.5044%`，高分输家率 `52.63%`，低分赢家率 `50.93%`。模型漏掉了一批更大市值、更高流动性、60 日动量更强的赢家。
- Health Care：Rank IC `0.0191`，Top-Bottom spread `0.5627%`，高分输家率 `49.83%`，低分赢家率 `46.68%`。排序不是明显失效，但高分输家大量集中在高估值、亏损、短历史生物医药股。
- Consumer Discretionary：Rank IC `-0.0230`，Top-Bottom spread `-0.2560%`，高分输家率 `51.97%`，低分赢家率 `52.99%`。模型同样漏掉更大、更高流动性、估值更低的赢家。
- 当前判断：Technology 和 Consumer Discretionary 需要优先改特征或做行业专属复盘；Health Care 需要补事件数据或更严格过滤高估值亏损股；三个行业都显示短历史股票在高分输家中占比过高。
- 下一步：先固定训练随机性或缓存预测分数，再加入 size / liquidity / momentum 的行业内相对特征，并考虑 Health Care 的事件型数据。

详细笔记：[[Sector Specific Error Review]]

## 2026-05-19 训练复现控制

- 学习主题：把“重新训练模型”和“复用测试期预测分数做复盘”分开，避免跨阶段比较混入 LightGBM 重训波动。
- 当前动作：frozen 配置新增 `training.seed`、`training.deterministic`、`training.reuse_test_predictions`，并给 LightGBM 配置 `seed`、`bagging_seed`、`feature_fraction_seed`、`data_random_seed`、`drop_seed`、`deterministic` 和 `force_col_wise`。
- 工程结果：默认仍重新训练并写出新的 `test_predictions.csv`；当 `reuse_test_predictions: true` 时，流水线读取已有 `test_predictions.csv`，跳过 `model.fit()` 和 `model.predict()`，下游 TopK、回测、行业复盘继续使用同一批 score。
- 报告结果：`report.md` 会记录预测分数来源、训练随机种子和是否复用缓存分数。
- 当前判断：后续改特征或标签时重新训练；只改 TopK、行业约束、错误复盘时复用预测分数。
- 下一步：加入 size / liquidity / momentum 的行业内相对特征，属于“改模型输入”，因此会在固定 seed 的前提下重新训练。

详细笔记：[[Experiment Reproducibility And Prediction Cache]]

## 2026-05-19 行情派生行业相对特征

- 学习主题：把 5.7C 错误复盘发现的 size / liquidity / momentum 线索转成模型输入。
- 当前动作：新增 `market_features`，从日线 OHLCV 计算 `market_log_close`、成交额、20/60/120 日动量、20/60 日波动率、截至当日历史长度，并生成 sector / industry 内 percentile。
- PIT 口径：所有特征只使用当日及以前行情；例如 60 日动量等于今天收盘价除以 60 个交易日前收盘价再减 1。
- 重要边界：当前 Nasdaq public 没有历史 shares outstanding，所以没有加入真实历史市值；第一版用成交额、价格水平和历史长度作为 size / liquidity 代理，避免把未来 shares 信息放进训练集。
- 工程结果：frozen 配置启用 `market_features`，训练时会把 `market_features.parquet` 与 Alpha158、EDGAR 特征一起拼接进 LightGBM。
- 实验结果：`market_features.parquet` 生成 `1,116,570` 行、`33` 个特征，覆盖 `500` 只股票；失败记录 `3` 条，都是行业分类缺失。
- 行业结果：Technology Rank IC 从 `-0.0214` 改善到 `0.0087`，Consumer Discretionary 从 `-0.0230` 改善到 `0.0159`；两者从负数转正。
- Health Care：Rank IC 从 `0.0191` 降到 `0.0077`，说明行情相对特征不能解决它的事件驱动噪声。
- 策略结果：默认 `sector_cap_4_top10` 累计收益 `51.99%`、年化收益 `19.58%`、最大回撤 `-36.00%`；`sector_cap_2_top10` 累计收益 `94.96%`、年化收益 `33.00%`、超额累计收益 `9.05%`、年化 alpha `6.06%`。
- 当前判断：5.8B 对 Technology 和 Consumer Discretionary 有帮助；行业约束应重新偏向更紧的 `max_sector=2`；短历史股票问题仍未完全消失。
- 下一步：做短历史 score 校准，或者先把默认行业约束从 `max_sector=4/3` 调整并复用同一份 `test_predictions.csv` 做对照。

详细笔记：[[Market Derived Relative Features]]

## 2026-05-19 短历史 score 校准

- 学习主题：把短历史股票的“样本少、分数容易过度自信”问题放到选股层复盘，而不是直接重训模型。
- 当前动作：新增 `score_calibration`，保留模型原始 `raw_score`，按历史长度桶生成 `adjusted_score`，TopK 排名可选择使用校准后的分数。
- 工程结果：`strategy_comparison` 新增三组 5.8C 对照：原始 `max_sector=2`、短历史惩罚、短历史惩罚加更高流动性门槛。
- 实验口径：复用当前 frozen run 的 `test_predictions.csv`，不重新训练；测试期仍为 2024-01-02 到 2026-05-15，5 日持有、信号日后 1 个交易日入场。
- 实验结果：原始 `max_sector=2` 年化 `33.75%`、最大回撤 `-29.36%`；短历史惩罚年化 `32.85%`、最大回撤 `-28.77%`；严格版年化 `29.41%`、最大回撤 `-29.08%`。
- 当前判断：短历史惩罚没有提升收益，只轻微改善回撤；严格流动性门槛损失更多超额收益。因此短历史股票不能简单重罚，第一版更适合作为保守对照而非默认主策略。
- 下一步：保留历史长度桶名额和 `max_sector=2` 作为更稳的默认方向，再做短历史股票专项复盘，拆分哪些短历史股票贡献收益、哪些造成大亏。

详细笔记：[[Short History Score Calibration]]

## 2026-05-19 短历史股票专项复盘

- 学习主题：解释 `lt_2y` 和 `2_5y` 短历史股票到底是机会还是风险来源。
- 当前动作：新增 `short_history_review`，直接读取 `raw_score_sector_cap_2_top10/backtest_positions.csv`，按历史长度桶、sector、industry、赢家/输家类别拆解实际持仓收益。
- 复盘口径：不重新训练模型，不重新生成选股；收益来自已有回测持仓的 `gross_return`、`gross_contribution` 和 `net_contribution`。
- 实验结果：`lt_2y` 持仓 105 次，平均收益 `0.57%`，胜率 `51.43%`，净贡献 `5.25%`；`2_5y` 持仓 236 次，平均收益 `1.28%`，胜率 `48.73%`，净贡献 `28.53%`。
- 风险发现：`2_5y` 最差单票亏损 `-48.68%`，输家中亏损公司占比 `82.98%`；`lt_2y` 输家中低流动性占比 `33.33%`、高估值占比 `38.10%`。
- 行业发现：明显负贡献集中在 `2_5y / Finance`，而 `2_5y / Basic Materials`、`2_5y / Industrials`、`lt_2y / Industrials` 是正贡献来源。
- 当前判断：短历史股票整体不是净拖累，不应该统一剔除或继续加大统一惩罚；下一步更适合做 sector-specific 短历史约束。

详细笔记：[[Short History Stock Review]]

## 2026-05-19 FRED/ALFRED 宏观特征接入

- 学习主题：把利率、收益率曲线、通胀、就业、增长、信用、VIX、油价和美元指数作为宏观状态特征加入 Qlib 模型。
- 当前动作：新增 `macro_features` 配置层和 FRED/ALFRED 适配器，下载 observations 后按 `realtime_start` 重建 as-of 序列，默认顺延到下一个交易日后才进入模型。
- PIT 口径：不能用 `observation_date` 当作可见日期；月度数据发布后才能 forward fill；修订数据不能提前覆盖历史；日频市场序列统一顺延到下一个交易日。
- 工程结果：宏观特征会输出 `macro_raw_observations.parquet`、`macro_asof_observations.parquet`、`macro_features.parquet` 和 `macro_failures.csv`，并与 Alpha158、EDGAR、market_features 一起拼接进 LightGBM。
- 默认序列：`DGS10`、`DGS2`、`FEDFUNDS`、`CPIAUCSL`、`UNRATE`、`INDPRO`、`BAA10Y`、`VIXCLS`、`DCOILWTICO`、`DTWEXBGS`，并派生 `DGS10 - DGS2` 收益率曲线。
- 当前判断：宏观变量不是直接横截面排序因子，而是 regime feature；它让模型学习不同宏观状态下价格、估值、动量和行业信号是否更有效。
- 下一步：设置 `FRED_API_KEY` 后跑宏观增强配置，对比无宏观 baseline 的 IC、Rank IC、TopK 回测和行业暴露。

详细笔记：[[FRED ALFRED Macro Features Integration]]

## 2026-05-19 FRED/ALFRED 真实宏观增强实验

- 学习主题：验证宏观状态变量是否能给当前 Nasdaq/Qlib 模型带来增量 alpha。
- 当前动作：使用真实 FRED API 数据重跑宏观增强 frozen 配置，并与无宏观 baseline 对比 IC、Rank IC、TopK 回测和行业暴露。
- 数据结果：`macro_failures=0`，生成 `1,256,500` 行、`52` 列宏观特征，平均非空覆盖率约 `98.99%`。
- IC 结果：无宏观 baseline `IC=0.016978`、`Rank IC=0.003683`；宏观增强 `IC=0.012456`、`Rank IC=0.009214`。
- 回测结果：`sector_cap_2_top10` 下，无宏观累计收益 `97.56%`、年化 `33.75%`、最大回撤 `-29.36%`；宏观增强累计收益 `53.92%`、年化 `20.23%`、最大回撤 `-22.92%`。
- 当前判断：宏观增强提升了 Rank IC 并降低 beta / 回撤，但收益和超额收益弱于 baseline；第一版宏观特征更像风险状态调节器，不足以证明有稳定选股 alpha。
- 下一步：不要继续盲目堆宏观序列，优先做 `宏观状态 × 行业/估值/动量/亏损公司` 的交互或 regime 复盘。

详细笔记：[[FRED ALFRED Macro Experiment Review]]

## 2026-05-19 宏观新信息与收益下降解释

- 学习主题：解释为什么宏观特征提供了新信息，但第一版加入模型后年化收益反而下降。
- 核心判断：宏观变量是 regime information，不天然等于横截面 stock selection alpha；它更适合作为条件变量，而不是直接排序变量。
- 关键原因：宏观特征同日对所有股票相同，必须通过 `宏观状态 × 行业/估值/动量/盈利质量` 才更可能帮助选股。
- 实验解释：本次宏观增强提高 Rank IC、降低 beta 和最大回撤，但降低 TopK 收益和超额收益，说明它更像风险状态调节器，不是稳定 alpha 来源。
- 下一步：先做宏观 regime 复盘和宏观特征 ablation，再做少量经济含义明确的交互特征。

详细笔记：[[Macro Features New Information And Return Degradation]]

## 2026-05-20 宏观 Regime 复盘与交互特征设计

- 学习主题：把宏观变量从“直接输入模型”升级为“市场状态复盘 + 有经济含义的交互特征”。
- 当前动作：新增 `macro_regime_review`，按 VIX、利率、收益率曲线、信用利差、美元、油价等 regime 拆分 baseline、direct macro 和 macro interactions 的回测表现。
- PIT 口径：regime 高低阈值只使用测试期之前的历史分位数；每个 signal date 只使用当时已生成的 PIT 宏观特征。
- 当前动作：新增 `macro_interactions`，默认不把 raw macro 直接喂给模型，而是生成 `宏观状态 × 行业/估值/动量/波动率/杠杆/现金` 的横截面交互项。
- 数据结果：`macro_interaction_features.parquet` 生成 `1,256,500` 行、`10` 个交互特征，失败记录 `0`，平均非空覆盖率约 `80.73%`。
- IC 结果：baseline `IC=0.016978`、`Rank IC=0.003683`；direct macro `IC=0.012456`、`Rank IC=0.009214`；macro interactions `IC=0.022432`、`Rank IC=0.012953`。
- 回测结果：`sector_cap_2_top10` 下，macro interactions 累计收益 `133.12%`、年化 `43.55%`、最大回撤 `-24.19%`、超额累计收益 `30.39%`、年化 alpha `17.16%`、beta `0.922`。
- Regime 结果：macro interactions 在 `high_vix`、`vix_rising`、`mid_vix` 和 `curve_not_inverted` 下相对 baseline 更强，在 `low_vix` 和 `curve_inverted` 下明显变弱。
- 当前判断：raw macro 更像风险调节器；macro interactions 第一版已经显示增量选股价值，但 low VIX 和曲线倒挂状态下的拖累需要继续拆解。
- 下一步：做宏观交互 ablation，逐类移除 VIX、利率估值、信用质量、行业 flag 交互，确认增量来自哪里。

详细笔记：[[Macro Regime Review And Interaction Features]]

## 2026-05-20 宏观交互 Ablation 复盘

- 学习主题：拆解 macro interactions 的收益来源，确认哪些交互组有贡献，哪些可能是噪声。
- 当前动作：新增 `macro_ablation` 配置组和 `macro_ablation_review.py`，分别运行 `drop_vix`、`drop_rate_valuation`、`drop_credit_quality`、`drop_sector_flag`、`only_vix` 五组实验，并和 baseline、direct macro、full interactions 汇总比较。
- 实验口径：同一冻结 Nasdaq Top500、同一 10 年窗口、同一未来 5 日收益标签、同一 `sector_cap_2_top10` 回测，只改变宏观交互特征组。
- 主要结果：`full_interactions` 的 Rank IC 最高，为 `0.012953`；`drop_credit_quality_interactions` 年化收益最高，为 `67.26%`，最大回撤 `-17.50%`，年化 alpha `30.62%`。
- 关键解释：信用利差 × 负债/现金这组第一版交互可能在当前窗口拖累 TopK；行业 flag 交互不能随意删除，删掉后年化降到 `28.14%`、最大回撤扩大到 `-37.18%`。
- 当前判断：如果目标是排序稳定，`full_interactions` 更优；如果目标是本次回测收益和回撤，`drop_credit_quality_interactions` 是候选，但必须先做集中度、贡献、成本和滚动窗口验证。
- 下一步：对比 `full_interactions` 与 `drop_credit_quality_interactions` 的持仓差异，检查收益是否集中在少数股票、少数行业或少数调仓期。

详细笔记：[[Macro Interaction Ablation Review]]

## 2026-05-20 宏观交互默认策略调整

- 学习主题：把 ablation 结论转成默认实验口径，同时保留研究对照。
- 当前决策：默认主策略去掉 `credit spread × liabilities/cash` 两个信用质量交互；完整 10 交互配置继续保留，用于研究和稳健性对照。
- 工程动作：新增默认配置 `nasdaq_alpha158_edgar_macro_interactions_default_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml`，继承完整 10 交互配置，但覆盖 `macro_interactions` 为 8 个非信用质量交互。
- 当前判断：默认去掉不等于否定信用质量假设，只说明第一版原始信用质量交互在当前 Nasdaq 2024-2026 测试窗口里拖累 TopK。
- 下一步：围绕默认 no-credit 策略做收益集中度、持仓差异、换手成本和滚动窗口验证。

## 2026-05-20 未来函数与回测收益水分审计

- 学习主题：解释当前年化收益为什么这么高，系统排查未来函数、幸存者偏差、数据口径和回测假设。
- 当前动作：新增 `future_leakage_audit.py`，读取当前 no-credit 等价 run，生成风险登记表、股票池抽样、宏观 as-of 抽样、market feature 复算、EDGAR 可见性抽样和回测边界复算。
- 审计结果：当前没有发现 TopK 回测直接使用未来收益选股，也没有发现 market momentum 抽样使用未来价格；回测 entry/exit 抽样复算与记录一致。
- 高风险结论：`nasdaq_public` 缺退市股票和历史证券主数据，且 `approximate_market_cap_asof` 使用当前市值与 latest close 反推历史市值，隐含当前 shares / 当前公司状态。
- 中风险结论：sector/industry 不是历史 PIT；EDGAR companyfacts 还需要 as-filed 抽样核对；FRED 日频 latest 序列不是严格 vintage。
- 当前判断：67.26% 年化不能作为严谨策略能力结论；修复股票池和数据口径前，只能说当前学习数据下模型有较强历史表现。
- 下一步：先修复 PIT 股票池和市值数据，再做 entry_lag、交易成本、价格口径、行业分类等压力测试。

详细笔记：[[Future Leakage And Backtest Water Audit]]

## 2026-05-20 Strict PIT 修复框架与回测压力测试

- 学习主题：把未来函数审计结论落成工程护栏，防止当前快照股票池和乐观交易假设继续伪装成严格结果。
- 当前动作：新增 PIT 数据质量验收，输出 `pit_universe_validation.csv`、`security_master_validation.csv`、`market_cap_validation.csv` 和 `data_quality_summary.yaml`。
- 当前动作：新增 `strict_pit` 配置契约，严格实验禁止 `approximate_market_cap_asof`，禁止 `nasdaq_public` 冒充 PIT 数据源，且没有 PIT 行业分类时禁用行业特征和行业约束。
- 当前动作：新增 `backtest_stress`，复用同一份预测分数，比较 `entry_lag=1/2`、`close/open/vwap_proxy`、`10/25/50/100 bps` 成本。
- 当前动作：新增三份 strict 配置，默认走 Norgate S&P 500 历史成分路线；真实运行仍需要 Windows + Norgate Data Updater + 有效订阅，并补齐历史市值或股本字段。
- 当前判断：工程层面已经把“学习结果”和“严格主结论”分开；没有 PIT 数据前，高收益只能作为学习观察。
- 下一步：拿到真实 PIT 股票池和历史市值后，重跑 strict baseline、strict direct macro、strict no-credit macro interactions，再做水分归因。

详细笔记：[[Strict PIT Data Repair Plan]]、[[Backtest Stress Test Review]]、[[Strict Re-Run Result Review]]

## 2026-05-20 Sharadar Strict Launch PIT 接入

- 学习主题：把严格股票池数据源从 Windows/Norgate 路线扩展到 Mac 可落地的 Sharadar / Nasdaq Data Link 路线。
- 当前动作：新增 `data.source=sharadar`、`SharadarDataSource`、`SharadarClient` 和 provider capability probe。
- 核心护栏：先检查 `TICKERS`、`SEP`、`SF1`、`DAILY`、`INDICATORS` 字段和订阅权限；字段不足时输出 probe 报告并停止，不回退到 `nasdaq_public`。
- 股票池口径：新增 `launch_pit_2023`，使用 `2023-12-29` as-of 交易日的 PIT market cap 选 Nasdaq Top500，禁止当前市值反推。
- 当前状态：工程接口和 fake client 测试已完成；真实数据仍需要 `NASDAQ_DATA_LINK_API_KEY` 和 Sharadar 订阅验证。
- 下一步：拿到 key/订阅后先运行 strict Sharadar baseline，看 `provider_capability_summary.yaml` 是否通过，再训练模型。

详细笔记：[[Sharadar Strict Launch PIT Integration]]

## 2026-05-20 Databento Strict Launch PIT 接入

- 学习主题：把严格股票池数据源扩展到 Databento，优先解决当前 `nasdaq_public` 的幸存者偏差和历史市值口径风险。
- 当前动作：新增 `data.source=databento`、`DatabentoDataSource`、provider capability probe 和 strict Databento 配置。
- 核心护栏：必须先验证 Security Master、listing/delisting、shares outstanding、corporate actions 和 `EQUS.SUMMARY` OHLCV 权限；不通过则停止，不回退到当前快照数据。
- 股票池口径：`launch_pit_2023` 用 2023-12-29 的 `shares_outstanding × as-of close` 计算市值，禁止当前市值反推。
- 当前状态：工程接口和 fake client 测试已完成；已安装 `databento` Python 包并用真实 key 跑 capability probe。
- 真实结果：Security Master 返回 `license_reference_dataset_no_subscription`，说明当前账号缺 Reference / Security Master 订阅；strict `launch_pit_2023` 被阻断，没有下载训练数据。
- 下一步：在 Databento 账号里开通或确认 Reference API / Security Master entitlement，再重跑 strict Databento baseline。

详细笔记：[[Databento Strict Launch PIT Integration]]

## 2026-05-21 CRSP 数据源迁移计划

- 学习主题：把当前学习数据源升级到本地 CRSP 日级数据，并把策略节奏调整为每 10 个交易日调仓。
- 当前决策：默认研究窗口固定为 `2000-01-03 ~ 2025-12-31`，股票池改为 CRSP US Common Equity 月度动态市值 Top500，不再使用当前 Nasdaq Top500 作为默认对照。
- 数据口径：原始 26GB CSV 只作为归档，先流式转换为 ignored Parquet warehouse；后续训练只读 Parquet / Qlib bin。
- 模型口径：第一版先跑 CRSP Alpha158-only，标签使用 CRSP `DlyRet` 构造未来 10 个交易日总收益；EDGAR 暂不默认启用，先做 PERMNO -> CIK 和覆盖率评估。
- 回测口径：信号日后 1 个交易日 open 入场，持有 10 个交易日，保留成本和入场价格压力测试。
- 下一步：实现 CRSP warehouse builder、动态 membership、Qlib source 生成、CRSP baseline / macro 配置和 fixture 测试。

详细笔记：[[CRSP Data Source Migration Plan]]

## 2026-05-22 CRSP Alpha158-only Baseline 跑通

- 学习主题：用本地 CRSP 日级数据替换当前快照数据源，跑通 2000-2025 固定窗口、月度动态市值 Top500、未来 10 个交易日收益标签和两周调仓回测。
- 数据结果：CRSP warehouse 覆盖 `2000-01-03 ~ 2025-12-31`，共 49,886,907 行、25,306 个 instrument；月度 Top500 membership 覆盖 311 个月，每月 500 个唯一证券，历史上共有 1,702 个 PERMNO 进入过股票池。
- 工程结果：生成 1,669 个 Qlib source CSV，33 个短历史证券因 `<180` 行被跳过；Qlib bin、Alpha158、LightGBM、TopK 回测和 24 组压力测试已跑通。
- 模型结果：测试期日均 IC `-0.013744`，Rank IC `-0.007421`，说明当前 Alpha158-only 对 CRSP 10 日收益没有正向横截面预测力。
- 回测结果：2024-2025 两周调仓 Top10，次日 open 入场、10bps 成本后累计收益 `4.61%`，年化 `2.30%`，最大回撤 `-16.69%`，同期 S&P 500 累计约 `45.50%`，年化 alpha `-15.20%`。
- 压力测试：10bps 下 close/vwap/open 入场均为小幅正收益；成本提高到 25bps 后多数口径转负，50/100bps 明显恶化，说明当前换手成本对策略影响很大。
- 当前判断：CRSP 数据地基打通了，但 Alpha158-only 不是有效主策略；下一步应优先检查标签/特征口径和加入宏观增强，而不是继续调组合规则。

## 2026-05-22 CRSP + FRED/ALFRED Macro 增强实验

- 学习主题：在 CRSP 严格动态股票池上加入 FRED/ALFRED 宏观状态变量，检验宏观信息相对 Alpha158-only 是否有增量。
- 数据结果：`macro_features.parquet` 生成 11,129,378 行、52 个宏观特征列，`macro_failures=0`；测试期仍为 2024-2025，两周调仓，未来 10 日收益标签。
- 模型结果：测试期 IC 从 Alpha158-only 的 `-0.013744` 改善到 `-0.005139`，Rank IC 从 `-0.007421` 改善到 `0.007221`。
- 回测结果：次日 open 入场、10bps 成本下，累计收益 `59.74%`，年化 `26.62%`，最大回撤 `-15.52%`，相对 S&P 500 超额累计 `9.79%`。
- 风险解释：beta 从 `0.981` 升到 `1.329`，年化 alpha 只有 `0.36%`；收益改善不等于纯 alpha 很强，可能包含更高市场暴露。
- 压力测试：成本从 10bps 提到 25bps 后年化降到 `18.71%`，50bps 后降到 `6.56%`，100bps 后转为 `-14.26%`，说明换手成本仍是核心约束。
- 当前判断：宏观增强比 Alpha158-only 明显更有用，但 raw macro 仍不够理想；下一步应做 CRSP macro interactions 和换手控制。

详细笔记：[[CRSP Macro Enhanced Result Review]]

## 2026-05-22 CRSP 早停与负 IC 诊断

- 学习主题：判断 CRSP Alpha158-only 的负 IC 和第 1 轮早停，到底是数据适配错误，还是信号/模型组合问题。
- 标签检查：30x30 抽样复算最大误差 `9.8879e-17`，全量复算最大误差 `2.2204e-16`，说明 10 日未来收益标签主链路正确。
- 价格检查：adjusted close 收益与 `DlyRetx` 平均绝对误差 `9.5685e-17`，最大误差 `3.2085e-14`，说明 CRSP 复权研究价格主链路正确。
- Membership 检查：311 个月动态 Top500 全部为 500 只，生效日全部晚于月末选择日，membership 外 label 非空行数为 `0`。
- 特征检查：Alpha158 共 158 个特征，train/valid/test 平均缺失率都低于 `0.003%`，无常数列，说明不是特征大面积坏掉。
- 早停检查：当前参数 best iteration=`1`，保守模型 best iteration=`111`，tiny 模型 best iteration=`120`，说明当前参数过拟合太快。
- 标签周期检查：5 日标签 best iteration=`5`，10 日标签 best iteration=`1`，20 日标签 best iteration=`35`，说明 10 日目标并不天然更稳定。
- 当前判断：数据适配不是主要矛盾；负 IC 和早停更可能来自 Alpha158 对当前 10 日收益信号弱，以及当前 LightGBM 参数偏激进。
- 下一步：先做保守 LightGBM 参数和 5/10/20 日标签小对照，再继续宏观交互和 EDGAR。

详细笔记：[[CRSP Early Stopping And Negative IC Diagnostics]]

## 2026-05-22 CRSP 保守模型与 5/10/20 日标签对照

- 学习主题：在 CRSP Alpha158-only 主线上，验证早停是否能通过更保守的 LightGBM 缓解，并比较 5/10/20 日未来收益标签。
- 工程动作：CRSP 标签列改为 horizon-aware，新增 `label_5d_total_return`、`label_10d_total_return`、`label_20d_total_return`；新增 5/10/20 日保守配置和横向对比脚本。
- 诊断结果：三组保守实验标签复算、DlyRetx 复权、membership 生效检查均通过；非 membership 日期 label 非空行数为 `0`。
- 模型结果：旧 10 日 baseline best iteration=`1`；5 日保守=`33`，10 日保守=`180`，20 日保守=`145`，说明早停主要来自原参数过激进。
- 横向结果：10 日保守模型 Rank IC=`0.006466`、年化收益 `33.91%`、年化 alpha `10.11%`、beta `1.096`，是当前最合适的 CRSP Alpha158-only 基线。
- 风险提示：10 日保守 IC 仍为 `-0.005289`，排序优势很弱；回测收益不能直接视为强 alpha，后续还要看宏观增强、贡献集中度、换手和成本压力。
- 下一步：以 10 日保守模型作为新 baseline，重做 macro / macro interaction conservative 对照。

详细笔记：[[CRSP Conservative Model And Horizon Comparison]]

## 2026-05-22 CRSP 10 日保守宏观对照

- 学习主题：以 10 日保守 Alpha158-only 为新 baseline，公平比较 raw macro 和 macro interaction 是否有增量。
- 实验范围：不接 EDGAR，不启用行业约束，不使用行业内相对特征；macro interaction 只使用 FRED/ALFRED 宏观变量乘以 CRSP 股票自身动量/波动率。
- direct macro 结果：52 个宏观特征，failure=0；Rank IC=`-0.015064`，best iteration=`7`，年化 `17.89%`，50bps 后年化 `-1.21%`。
- macro interaction 结果：8 个交互特征，failure=0；Rank IC=`0.006653`，best iteration=`95`，年化 `21.08%`，50bps 后年化 `3.66%`。
- baseline 对照：Alpha158-only Rank IC=`0.006466`，best iteration=`180`，年化 `33.91%`，50bps 后年化 `15.70%`。
- 当前判断：raw macro 明显拖累；macro interaction 比 raw macro 更健康，但收益、alpha、成本压力都不如 Alpha158-only，暂不作为默认主策略。
- 下一步：只做 macro interaction ablation 和 regime 分段复盘；如果仍无增量，宏观先作为复盘维度，不进默认模型。

详细笔记：[[CRSP Macro Conservative Comparison]]

## 2026-05-22 CRSP 训练加速与架构优化

- 学习主题：CRSP 实验慢的主要瓶颈不是 LightGBM，而是重复生成 `qlib_source_csv`、重复生成 Qlib bin、压力测试重复读取全部股票 CSV。
- 工程动作：新增 runtime profile，输出 `runtime_profile.csv/yaml`；新增 CRSP prepared dataset cache，baseline / macro / macro interaction 可复用同一份 CRSP source CSV 和 Qlib bin；压力测试按价格口径预加载行情，避免 24 次重复扫描。
- 多核策略：保留 LightGBM `num_threads`，新增 `runtime.qlib_dump_workers` 和 `runtime.market_feature_workers`；MacBook 上默认保守并行，先减少 I/O 重复。
- 当前判断：后续慢在哪里要先看 runtime profile；若 prepared dataset 命中，第二次同口径运行不应再重建 824MB source CSV 和 202MB Qlib bin。

详细笔记：[[CRSP Training Speed Optimization]]

## 2026-05-22 CRSP 宏观交互 Ablation 与 Regime 复盘准备

- 学习主题：在 CRSP 10 日保守 baseline 上，固定股票池、切分、标签、模型和回测口径，只改变宏观交互组合。
- 工程动作：新增 CRSP 专用 macro ablation manifest，固定 9 组对照；复盘脚本支持 `main_backtest`，可直接读取 CRSP 主回测输出，不再依赖旧 Nasdaq 的 `sector_cap_2_top10` 结构。
- Regime 口径：VIX、利率、收益率曲线、信用利差、美元、油价等高低或趋势状态，阈值只用测试期之前历史计算。
- 当前判断：宏观是否进默认模型，要看 Alpha158-only、raw macro、full interactions 和 ablation 组在 Rank IC、alpha、成本压力和 regime 稳定性上的共同证据。

详细笔记：[[CRSP Macro Interaction Ablation And Regime Review]]

## 2026-05-22 CRSP 2010 主线、0bps 成本与行业恢复路径

- 学习主题：把 CRSP 主研究窗口从 `2000-2025` 收敛到 `2010-2025`，并恢复“先分桶、再行业、最后 EDGAR/宏观”的研究顺序。
- 工程动作：新增 `configs/crsp_2010/` 配置组、`cleanup_runs.py` 标准清理 dry-run、CRSP 行业字段验收模块和 2010-only prepared dataset 窗口裁剪。
- 关键修复：第一次运行发现 prepared dataset 仍把 2000 年起的 Qlib calendar 带入 2010 配置；已修复为 membership 和 qlib_source_csv 都按 `data.start_date/end_date` 裁剪。
- Baseline 结果：2010 Alpha158-only conservative 在 2024-2025 测试期 IC=`0.015469`、Rank IC=`-0.009241`，0bps 主回测累计 `85.86%`、年化 `36.67%`、最大回撤 `-17.12%`。
- 成本口径：主结果使用 `0bps`；压力测试保留 `25/50bps`，用于近似滑点、买卖价差、开盘成交不确定性和市场冲击。
- 行业验收：CRSP SIC2 测试期调仓日覆盖 `97.2%`，但训练期年度最低覆盖 `67.8%`，低于 80% 门槛；行业约束和行业相对特征暂时关闭，只做复盘。
- 下一步：先跑历史长度桶内 Top10 对照，再检查行业 UNKNOWN 集中在哪些年份和证券，确认能否恢复行业路径。

详细笔记：[[CRSP 2010 Baseline Cleanup And Industry Recovery]]

## 2026-05-23 CRSP 历史长度桶内 Top10 与行业 UNKNOWN 复盘

- 学习主题：验证 `full_10y / 5_10y / 2_5y / lt_2y` 桶内名额是否能改善 Top10，并检查 CRSP SIC/NAICS 的 `UNKNOWN` 覆盖问题。
- Bucket 结果：强制 `4/3/2/1` 后，年化从全局 Top10 的 `36.67%` 降到 `28.38%`，最大回撤从 `-17.12%` 变为 `-20.47%`，alpha 从 `5.10%` 降到约 `0%`。
- 分桶贡献：`2_5y` 和 `lt_2y` 不是主要拖累，反而有正贡献；硬性名额主要增加了较弱 `5_10y` 暴露，并减少了全局模型自然选出的更优候选。
- 当前结论：桶内 Top10 暂不作为默认策略，继续保留全局 Top10；短历史股票也不应统一剔除。
- 行业 UNKNOWN：96,000 条 membership 中 14,887 条 SIC2 UNKNOWN，总覆盖 `84.49%`；最差年份集中在 `2010-2014`，2010 年覆盖仅 `68.63%`。
- 关键发现：UNKNOWN 大多是正常 `EQTY / COM / A` 普通股，且 NAICS / ICB 也不可用；这不是证券清洗问题，而是行业字段覆盖问题。
- 下一步：先解决行业映射覆盖，再恢复行业约束和行业内相对特征；在此之前行业只做复盘，不进模型。

详细笔记：[[CRSP History Bucket Top10 And Industry Unknown Review]]

## 2026-05-23 CRSP 行业映射修复

- 学习主题：把行业分类从旧 `security_master` 回填改成 CRSP 月末 row-level PIT 行业映射。
- 工程动作：新增 `industry_master.parquet`、`industry_mapping_coverage.csv`、`industry_mapping_failures.csv`、`industry_mapping_summary.yaml`；prepared dataset key 加入 `industry_mapping.schema_version`，避免复用旧 membership。
- 关键结果：2010 baseline 重跑后，`industry_master` 共 `96,000` 行，`crsp_pit_rows=96,000`，`unknown_rows=0`，没有使用 EDGAR fallback，也没有回退到 security master。
- 覆盖结果：训练期年度最低严格 SIC2 覆盖率 `100%`，测试期调仓日最低覆盖率 `100%`，行业特征和行业约束已通过字段验收。
- 当前判断：之前行业覆盖不足主要是缓存/validation 口径问题，不是 CRSP 原始数据无法提供行业字段。
- 下一步：先做行业暴露和行业贡献复盘，再跑行业约束 Top10 与行业内 market 相对特征对照；不要直接把行业约束设为默认。

详细笔记：[[CRSP Industry Mapping Repair]]

## 2026-05-23 CRSP 行业约束与行业内相对特征恢复

- 学习主题：在 CRSP 2010 strict PIT 行业映射通过后，恢复行业约束和行业内 market 相对特征对照。
- 工程动作：非 bucket TopK 现在也支持 `max_sector / max_industry`；新增 `training.reuse_test_predictions_path`，行业约束对照直接复用 baseline `test_predictions.csv`；`market_features` 改为优先使用 `industry_master.parquet` 做 PIT 行业归属。
- 行业约束结果：`sector_cap_2_top10` 年化 `46.26%`、最大回撤 `-15.62%`、年化 alpha `13.03%`，优于 `global_top10` 的年化 `39.41%`、最大回撤 `-17.73%`、年化 alpha `6.74%`。
- 行业相对特征结果：31 个行情相对特征重新训练后，Test Rank IC=`-0.012379`，年化 `-7.89%`，最大回撤 `-24.48%`，不适合进入默认模型。
- 当前判断：行业信息目前更适合作为组合约束和风险复盘工具，而不是直接作为模型输入；候选默认改为 Alpha158-only score + `sector_cap_2_top10`。
- 下一步：对 `sector_cap_2_top10` 做持仓贡献和行业暴露复盘，确认改善不是少数调仓期偶然贡献；然后进入 EDGAR 覆盖率与 `PERMNO -> CIK` 映射评估。

详细笔记：[[CRSP Industry Constraint And Relative Feature Recovery]]

## 2026-05-23 CRSP 加入 SEC EDGAR 财报特征

- 学习主题：在 CRSP 2010 Alpha158-only conservative baseline 上加入 SEC EDGAR 10-K / 10-Q 结构化财报和估值特征。
- 当前确认：加入前的 CRSP 2010 主线只使用 Alpha158 价格成交量特征；行业约束是选股阶段规则，不是模型输入。
- 工程动作：复用旧 Nasdaq EDGAR 适配器，但新增 CRSP `P{PERMNO} -> ticker_asof -> CIK` 映射；估值因子改用 CRSP 原始 `DlyClose`，避免把 Alpha158 的研究复权价格误用于估值。
- 数据结果：EDGAR 映射 855 个 CIK，生成 `2,820,566 x 29` 日频 PIT 财报特征，覆盖 816 个 instruments。
- 失败原因：`missing_fields=573`、`missing_cik=306`、`no_effective_filing_dates=28`、`insufficient_filings=11`。
- 模型结果：Alpha158 + EDGAR 的 Test IC=`-0.004242`，Rank IC=`-0.009994`，年化 `17.43%`，最大回撤 `-19.82%`，弱于 Alpha158-only baseline。
- 当前判断：EDGAR 数据链路已经跑通，但第一版直接拼接财报特征会拖累模型；不能把 Alpha158 + EDGAR 设为默认主线。
- 下一步：做 EDGAR 覆盖率审计、估值极端值清洗、行业内财报/估值相对特征和 EDGAR ablation，再决定哪些财报字段值得进入默认模型。

详细笔记：[[CRSP EDGAR Fundamentals Integration]]

## 2026-05-23 CRSP EDGAR 覆盖审计、清洗与 Ablation

- 学习主题：把 EDGAR 从“直接拼接”改成“覆盖审计 -> 固定规则清洗 -> 行业内相对化 -> 分组 ablation”的可解释研究路径。
- 工程动作：新增 `edgar_coverage.py`、`fundamental_features_cleaned.parquet`、`fundamental_cleaning_summary.yaml`、`edgar_relative_feature_coverage.csv` 和 `crsp_edgar_ablation_review.py`。
- 覆盖结果：1,161 个 universe instruments 中，CIK 映射 855 个，EDGAR 特征覆盖 816 个，instrument 覆盖率约 `70.28%`；主要失败原因是 `missing_fields=573` 和 `missing_cik=306`。
- 清洗结果：负市盈率 / 负 FCF 估值设为 NaN `438,721` 次，静态规则裁剪低端 `302,481` 次、高端 `279,351` 次。
- 模型结果：Alpha158-only 年化 `36.67%`、alpha `5.10%` 仍最好；Clean EDGAR 年化 `22.04%`、alpha `-12.08%`；Clean EDGAR + Relative 年化 `21.34%`、alpha `-9.04%`。
- Ablation 结果：`drop_valuation` 的 Rank IC 最接近 0，说明估值组当前可能是主要排序噪声；但所有 EDGAR 组都没有超过 Alpha158-only。
- 当前判断：EDGAR 链路可用，但暂不进入默认模型；后续只保留为研究分支，优先单独研究盈利质量组和更长收益周期。

详细笔记：[[CRSP EDGAR Coverage Cleaning And Ablation]]

## 2026-05-23 CRSP EDGAR 字段级覆盖修复

- 学习主题：解释 EDGAR 覆盖不完整的原因，并验证“字段级使用上一期已披露财报”是否能改善模型。
- 工程动作：新增字段级 as-of forward fill、540 天 stale 上限、coverage-aware 特征、XBRL tag 命中报告和缺失根因报告。
- 覆盖结果：CIK mapping coverage 仍为 `73.64%`，feature instrument coverage 仍为 `70.28%`；`missing_fields` 从 `573` 降到 `519`。
- 字段改善：`fcf_margin` 缺失率从 `60.31%` 降到 `46.36%`，`operating_margin` 从 `53.73%` 降到 `45.97%`，`gross_margin` 从 `74.76%` 降到 `71.11%`。
- 模型结果：`repaired_quality_only` 的 IC=`0.014578`，Rank IC=`-0.002942`，年化 `26.88%`，最大回撤 `-18.59%`，alpha `-4.27%`；比 clean EDGAR 明显改善，但仍弱于 Alpha158-only。
- 当前判断：EDGAR 不是完全无效，盈利质量组值得保留研究；但它仍不应进入默认模型。

详细笔记：[[CRSP EDGAR Coverage Cleaning And Ablation]]

## 2026-05-23 CRSP EDGAR Quality Core 与字段有效性审计

- 学习主题：回答“EDGAR 保留哪些字段，以及如何识别有效信息再加入模型”。
- 工程动作：新增 `crsp_alpha158_edgar_quality_core_10d_conservative_2010_2025.yaml`，默认只保留 `profitability_quality`、`filing_state`、`coverage_state`，剔除估值组。
- 审计动作：新增 `edgar_effectiveness_review`，输出字段级 IC、Rank IC、按年份/行业拆分 IC，以及字段 Top/Bottom 分位未来收益差。
- 训练结果：quality core Test IC=`0.014578`、Rank IC=`-0.002942`、global Top10 年化 `26.88%`、alpha `-4.27%`；sector_cap_2 Top10 年化 `40.95%`、alpha `4.81%`。
- 对比结论：仍弱于 Alpha158-only + sector_cap_2 的年化 `46.26%`、alpha `13.03%`，所以 EDGAR quality core 不进入默认主线。
- 字段发现：`operating_margin`、`free_cash_flow_ttm`、`net_margin`、`fcf_margin`、`operating_cash_flow_ttm` 的 Rank IC 最靠前，coverage_state 直接进模型需要谨慎。
- 下一步：收缩成 EDGAR mini-core，只测试少数盈利质量字段；同时准备 20 日 / 60 日标签对照。

详细笔记：[[CRSP EDGAR Coverage Cleaning And Ablation]]

## 2026-05-23 CRSP EDGAR Mini-Core 与 20/60 日对照准备

- 学习主题：把 EDGAR 从 quality core 继续收缩成 `mini-core`，只验证少数盈利质量/现金流字段是否有边际价值。
- 工程动作：新增 `fundamentals.include_features` 白名单，mini-core 只保留 `operating_margin`、`free_cash_flow_ttm`、`net_margin`、`fcf_margin`、`operating_cash_flow_ttm`。
- 配置动作：新增 20 日、60 日 Alpha158-only 和 EDGAR mini-core 配置，标签、持有期、调仓期严格同步。
- 复盘动作：新增 `crsp_edgar_mini_core_horizon_review.py`，用于汇总 10/20/60 日的 IC、Rank IC、global Top10、sector_cap_2 Top10 和 50bps 压力结果。
- 训练结果：六组 10/20/60 日对照已完成。10 日 mini-core 的 Rank IC 从 Alpha158-only 的 `-0.009241` 改善到 `-0.000493`，global 年化从 `36.67%` 到 `38.93%`，但 global alpha 从 `5.10%` 降到 `4.16%`。
- 组合结果：10 日 mini-core + `sector_cap_2_top10` 年化 `48.84%`、alpha `11.10%`，接近但仍略弱于此前 Alpha158-only + sector_cap_2 的 alpha `13.03%`。
- 中期标签结果：20 日和 60 日 mini-core 都没有改善收益、alpha 或 Rank IC；“财报字段更适合 20/60 日收益”的假设暂时不成立。
- 当前判断：EDGAR mini-core 不进入默认主线；保留为 10 日 sector_cap_2 研究分支，下一步应复盘它替换了哪些持仓，以及改善是否来自少数股票或行业。

详细笔记：[[CRSP EDGAR Coverage Cleaning And Ablation]]

## 2026-05-23 CRSP EDGAR Mini-Core 持仓差异复盘

- 学习主题：解释 EDGAR mini-core 在 10 日 `sector_cap_2_top10` 下的边际改善来自哪里。
- 工程动作：新增 `crsp_edgar_mini_core_position_diff.py`，只读比较 Alpha158-only 与 EDGAR mini-core 的 sector_cap_2 持仓，不重训模型。
- 持仓结果：EDGAR 新增 148 个持仓行、115 只股票；移除 148 个持仓行、97 只股票；共同持仓 352 行。
- 贡献结果：EDGAR 新增持仓净贡献 `0.2308`，被移除的 Alpha158 持仓原净贡献 `0.1889`，替换差约 `+0.0419`。
- 集中度检查：Top3 新增正贡献占比 `23.71%`，最大 sector 新增正贡献占比 `17.96%`，没有触发少数股票或单一行业过度集中风险。
- 财报解释：新增持仓的 `operating_margin`、`net_margin`、`fcf_margin`、`operating_cash_flow_ttm` 均值都高于被移除持仓，说明改善有一定盈利质量和现金流解释。
- 当前判断：EDGAR mini-core 仍不进入默认主线，但可以保留为 10 日 sector_cap_2 研究分支；下一步如果继续，应做更严格的 out-of-sample/滚动窗口验证。

详细笔记：[[CRSP EDGAR Coverage Cleaning And Ablation]]

## 2026-05-23 CRSP 滚动窗口验证框架

- 学习主题：验证 `Alpha158-only + sector_cap_2_top10` 是否跨多个测试窗口稳定，同时检查 `EDGAR mini-core + sector_cap_2_top10` 是否只是 2024-2025 有效。
- 工程动作：新增 `configs/crsp_rolling_windows/`、`crsp_rolling_window_validation.py` 和滚动窗口汇总测试。
- 验证窗口：2018-2019、2020-2021、2022-2023、2024-2025。
- 对照对象：Alpha158-only 与 EDGAR mini-core，两者都使用 CRSP 动态 Top500、10 日标签、10 日调仓、次日 open 入场、sector_cap_2 Top10。
- 训练结果：8 组真实训练已完成。Alpha158-only + sector_cap_2 只有 1/4 个窗口 alpha 为正；EDGAR mini-core + sector_cap_2 在 3/4 个窗口 alpha 高于 Alpha158-only。
- 当前判断：Alpha158-only 不满足稳定默认标准；EDGAR mini-core 有跨窗口改善，但 2022-2023 仍为负，暂定为 `candidate_branch`，不能直接替代默认。

详细笔记：[[CRSP Rolling Window Validation]]

## 2026-05-23 CRSP 滚动窗口失败复盘

- 学习主题：解释 Alpha158-only + sector_cap_2 为什么不能继续作为稳定默认主线，并复盘 2022-2023 共同失效窗口。
- 工程动作：新增 `crsp_rolling_window_failure_review.py`，复用 8 个 rolling run，不重新训练；补齐每个 `sector_cap_2_top10` variant 的 0/25/50bps 压力测试。
- 失败结论：Alpha158-only + sector_cap_2 只有 1/4 个窗口 alpha 为正，继续降级为 `unstable_default_candidate`。
- EDGAR 结论：EDGAR mini-core 在 3/4 个窗口 alpha 高于 Alpha158-only，但 2022-2023 仍为负，只能保留为 `candidate_branch`。
- 压力结果：sector_cap_2 的 50bps 压力下没有一个 rolling 行为正 alpha，说明策略对换手和交易摩擦敏感。
- 当前判断：下一步不要继续堆新特征，应先复盘 2022-2023 的 beta、行业、单票贡献和回撤区间，判断是模型排序失效还是组合构建失效。

详细笔记：[[CRSP Rolling Window Failure Review]]

## 2026-05-23 CRSP 2022-2023 专项失效复盘

- 学习主题：拆解 2022-2023 为什么出现弱正 IC 但 `sector_cap_2_top10` 仍然亏损。
- 工程动作：新增 `crsp_2022_2023_failure_deep_dive.py`，只读复用 Alpha158-only 与 EDGAR mini-core 的 rolling run，不重训模型。
- IC/TopK 结果：Alpha158-only IC=`0.0166`、Rank IC=`0.0064`，但 Top10 平均收益 `-0.55%`；EDGAR mini-core IC=`0.0290`、Rank IC=`0.0123`，但 Top10 平均收益 `-0.40%`。
- 背离结果：Alpha158-only 有 `31/51` 个调仓期 Top10 跑输候选池均值；EDGAR mini-core 有 `28/51` 个调仓期跑输。
- 回撤结果：Alpha158-only 从 `2022-03-16` 到 `2023-10-18` 最大回撤 `-43.44%`；EDGAR mini-core 从 `2022-03-16` 到 `2022-06-27` 最大回撤 `-39.29%`。
- 亏损来源：Alpha158 最大回撤中亏损最重的 sector 是 `60`、`48`、`28`；最差单票包括 `P20892`、`P16140`、`P14763`。
- 当前判断：这不是模型完全无信号，而是弱信号没有撑住高集中 Top10；下一步优先做 Top10/20/30 对照、单票风险过滤和 beta 控制。

详细笔记：[[CRSP 2022 2023 Failure Deep Dive]]

## 2026-05-23 CRSP 组合构建与风险过滤修复

- 学习主题：验证弱正 IC 是否可以通过组合构建修复，重点看 TopK 宽度、持仓权重、单票风险过滤和 beta 控制。
- 工程动作：新增 `crsp_portfolio_repair.py`，复用 4 个 rolling 窗口的 Alpha158-only 与 EDGAR mini-core 预测，不重训模型。
- TopK 结果：Top10 太集中；Top30 / Top50 能明显降低最差回撤，并让 Alpha158 从 `1/4` 正 alpha 改善到 `3/4`，但 50bps 压力下仍不稳定。
- 权重结果：表现最好的观察项是 `EDGAR mini-core + Top10 + inverse_vol_weight`，平均 alpha `6.12%`、正 alpha `3/4`、平均 beta `1.35`，但 50bps 正 alpha 窗口为 `0/4`。
- 风险过滤结果：soft filter 能降低 beta 和回撤，但也过滤掉不少收益来源，更像风险削减工具，不是完整修复方案。
- beta 控制结果：beta_neutral_weight 有局部改善，但无法让跨窗口和压力测试同时通过。
- 当前判断：没有组合规则同时满足跨窗口 alpha、beta 和 50bps 压力条件；下一阶段进入 `CRSP-20 标签重设计`。

详细笔记：[[CRSP Portfolio Construction And Risk Filter Repair]]

## 2026-05-23 大型 CRSP 研究阶段收束

- 学习主题：重新审视当前研究路线是否符合个人小资金实盘目标。
- 阶段结论：CRSP + Alpha158 + EDGAR + macro + interaction 的大型 ML 路线适合学习完整量化研究流程，但不适合作为当前个人实盘主线。
- 原因一：变量过多，Alpha158 本身已有 158 个特征，再叠加财报、宏观、行业和交互后，训练慢、解释难、调参空间过大。
- 原因二：rolling window 显示结果不稳定，弱正 IC 无法稳定转化为 TopK 收益。
- 原因三：Top30 / Top50 虽能降低集中风险，但不符合小资金持仓和人工复盘需求。
- 决策：旧阶段收束为研究资料库，新阶段切换到 `Personal Quant v1`，目标是少变量、少持仓、可解释、可复盘。
- 工程动作：新增 `analysis/personal_quant_v1/` 作为干净起点，不在旧大流水线中继续叠加复杂度。

详细笔记：[[CRSP Large Research Stage Summary]]、[[Personal Quant V1 Direction]]

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
