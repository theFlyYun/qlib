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
