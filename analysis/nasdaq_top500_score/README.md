# Nasdaq Top 500 Score Experiments

这个目录包含两类学习实验：

- `build_nasdaq_score.py`：透明规则打分，不经过 Qlib 模型。
- `run_qlib_alpha158_lightgbm.py`：配置驱动的 Qlib Alpha158 + LightGBM 训练流程。

## 配置化运行

默认配置文件：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_lgbm_1d.yaml
```

复跑默认实验：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_lgbm_1d.yaml
```

固定 15 年窗口 baseline 配置：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_lgbm_15y_fixed.yaml
```

这个配置把行情窗口固定为 `2011-05-17` 到 `2026-05-17`，训练/验证/测试也使用固定日期切分，不会因为以后运行日期变化而漂移：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_lgbm_15y_fixed.yaml
```

固定 10 年窗口 baseline 配置：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_lgbm_10y_fixed.yaml
```

这个配置把行情窗口固定为 `2016-05-17` 到 `2026-05-17`，使用当前 Nasdaq 市值前 500 股票池，并要求单股票至少有 2400 行日线数据：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_lgbm_10y_fixed.yaml
```

固定 10 年窗口、短历史股票也进入评估的配置：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_lgbm_10y_eval_all.yaml
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_eval_all.yaml
```

这两个配置仍使用 `2016-05-17` 到 `2026-05-17` 的固定窗口，但把 `min_history_rows` 降到 180。短历史股票不会贡献它们不存在的早期训练样本；只要测试期有足够数据，就可以进入预测和评估。

已跑通的 EDGAR 全量实验结果在：

```text
analysis/nasdaq_top500_score/runs/nasdaq_alpha158_edgar_lgbm_10y_eval_all/report.md
```

本次生成 895,760 行日频 EDGAR PIT 特征，覆盖 420 只股票；最新日可预测 480 只股票。该目录属于大型实验产物，默认不提交 Git。

固定 10 年窗口、证券主数据、流动性过滤、历史长度分桶、桶内 Top10 和行业名额约束配置：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10.yaml
```

这个配置会先生成 `security_master.csv`，把证券分类为 common stock、ordinary share、ADR/ADS、warrant、preferred、debt、unit 等，再过滤不适合普通股研究的证券；随后过滤低价、低成交额或交易不连续的股票，最后按历史长度桶内排名选出 Top10：

```text
full_10y: 4
5_10y: 3
2_5y: 2
lt_2y: 1
```

最终选择阶段还会限制单一 sector 最多 4 只、单一 industry 最多 2 只。模型训练和 `score` 不变，这个约束只影响最终候选组合的分散度。

流动性过滤第一版使用日线近似成交额：

```text
最新收盘价 >= 1 美元
近 20 日平均成交额 >= 500 万美元
近 60 日成交额中位数 >= 200 万美元
近 60 日零成交比例 <= 5%
```

运行入口：

```bash
export SEC_EDGAR_USER_AGENT="Your Name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10.yaml
```

同一口径的未来 5 日收益标签配置：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d.yaml
```

该配置把标签改为未来 5 个交易日收益，并启用第一版 Top10 成本后回测：

```text
Ref($close, -6) / Ref($close, -1) - 1
```

运行入口：

```bash
export SEC_EDGAR_USER_AGENT="Your Name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d.yaml
```

PIT 过滤版未来 5 日收益回测配置：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d_pit_safe.yaml
```

这版不在训练前使用 2026 年末流动性过滤，而是在每个回测信号日按当时可见行情重新计算：

```text
截至信号日的历史长度分桶
截至信号日的 20/60 日流动性
```

运行入口：

```bash
export SEC_EDGAR_USER_AGENT="Your Name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d_pit_safe.yaml
```

注意：这仍不是完全 PIT 回测，因为 `nasdaq_public` 股票池仍按运行日市值前 500 构建，不是历史时点的前 500。

as-of 2023-12-31 近似冻结股票池配置：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
```

这版会先按当前市值多取候选池，下载固定 10 年行情，再用 `2023-12-31` 前最近交易日收盘价近似估算当时市值，最后只保留估算前 500 进入训练、预测和回测。它用于降低“用测试期之后的运行日市值选股”的未来信息风险，但仍不是完整 PIT 股票池，因为 Nasdaq public 不提供历史 shares outstanding、退市股票和历史证券主数据。

```bash
export SEC_EDGAR_USER_AGENT="Your Name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
```

该配置已经加入训练复现控制：

```yaml
training:
  seed: 20260519
  deterministic: true
  reuse_test_predictions: true
```

如果改特征、标签或模型参数，应把 `reuse_test_predictions` 改回 `false` 并重新训练。只做行业约束、TopK、错误复盘或短历史 score 校准时，保持 `true`，流水线会复用当前 run 目录下已有的 `test_predictions.csv`。

该配置同时启用 `market_features`，从截至当日的 OHLCV 计算价格、成交额、动量、波动率、历史长度及其 sector / industry 内 percentile。当前数据源没有历史 shares outstanding，因此没有把真实历史市值作为模型输入，先用成交额和价格水平作为 size / liquidity 代理。

已跑通结果：1000 只候选股票中 500 只进入冻结股票池。最近一次 5.8C 复跑的默认 `sector_cap_4_top10` 策略成本后累计收益 `42.24%`，年化收益 `16.24%`，最大回撤 `-35.65%`。这比运行日市值股票池的 PIT 过滤版明显保守，说明股票池未来信息是旧回测收益异常高的重要来源。

该配置同时启用 FRED `NASDAQCOM` 基准复盘。当前结果：

```text
策略累计收益：42.24%
NASDAQCOM 基准累计收益：78.78%
超额累计收益：-20.44%
Beta：1.107
年化 Alpha：-7.50%
```

这说明冻结股票池后，策略虽然有绝对收益，但没有跑赢纳斯达克综合指数。

5.8C 额外加入短历史 score 校准对照，复用同一份模型分数：

```text
raw_score_sector_cap_2_top10：累计收益 97.56%，年化收益 33.75%，最大回撤 -29.36%。
short_history_penalty_sector_cap_2_top10：累计收益 94.44%，年化收益 32.85%，最大回撤 -28.77%。
short_history_strict_sector_cap_2_top10：累计收益 82.86%，年化收益 29.41%，最大回撤 -29.08%。
```

第一版结论：短历史惩罚没有提升收益，只轻微改善回撤；严格门槛明显损失超额收益。因此短历史校准先作为保守对照，不建议直接作为默认主策略。

5.9 进一步做了短历史股票专项复盘，直接读取 `raw_score_sector_cap_2_top10` 的实际持仓：

```text
lt_2y：持仓 105 次，平均收益 0.57%，胜率 51.43%，净贡献 5.25%。
2_5y：持仓 236 次，平均收益 1.28%，胜率 48.73%，净贡献 28.53%。
```

结论：短历史股票整体不是净拖累。明显负贡献集中在 `2_5y / Finance`，而 `2_5y / Basic Materials`、`2_5y / Industrials`、`lt_2y / Industrials` 是正贡献来源。下一步更适合做 sector-specific 短历史约束，而不是统一剔除或继续加大短历史惩罚。

FRED/ALFRED 宏观特征增强配置：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_macro_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
```

这版在 Alpha158、EDGAR 和 `market_features` 之外，加入利率、收益率曲线、通胀、就业、工业产出、信用利差、VIX、油价和美元指数等宏观状态特征。宏观数据按 `realtime_start` 重建 as-of 序列，并默认顺延到下一个交易日后才进入模型，避免把发布前或最终修订后的数据提前喂给模型。

```bash
export SEC_EDGAR_USER_AGENT="Your Name your-email@example.com"
export FRED_API_KEY="your-fred-api-key"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_macro_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
```

同一配置还会生成持仓贡献和行业暴露复盘：

```text
contribution_by_symbol.csv
contribution_by_sector.csv
contribution_by_industry.csv
exposure_by_sector.csv
exposure_by_industry.csv
contribution_summary.yaml
```

该配置还会生成行业暴露对照实验，复用同一批测试期模型分数，只改变 Top10 选股规则：

```text
strategy_comparison.csv
strategy_comparison_summary.yaml
strategy_comparison/unconstrained_top10/
strategy_comparison/sector_cap_2_top10/
strategy_comparison/sector_cap_3_top10/
strategy_comparison/sector_cap_4_top10/
strategy_comparison/sector_momentum_tilt_top10/
```

最近一次对照结果：

```text
unconstrained_top10：累计收益 59.18%，年化收益 21.96%，超额累计收益 -10.96%
sector_cap_2_top10：累计收益 94.96%，年化收益 33.00%，超额累计收益 9.05%，Sector HHI 0.174
sector_cap_3_top10：累计收益 79.14%，年化收益 28.27%，超额累计收益 0.20%，Sector HHI 0.224
sector_cap_4_top10：累计收益 51.99%，年化收益 19.58%，超额累计收益 -14.99%，Sector HHI 0.255
sector_momentum_tilt_top10：累计收益 66.04%，年化收益 24.18%，超额累计收益 -7.13%
```

当前判断：加入行情相对特征后，`max_sector=2` 的收益、超额收益、alpha、回撤和行业集中度综合最好；`max_sector=3` 次之；`max_sector=4` 偏松。下一步需要把默认行业约束从 4/3 重新评估到 2。

该配置还会生成行业内选股复盘，检查模型在同一个 sector 内能否把未来收益更好的股票排到前面：

```text
within_sector_daily_metrics.csv
within_sector_summary.csv
within_industry_summary.csv
within_sector_quantile_returns.csv
within_sector_selection_summary.yaml
```

最近一次行业内复盘结论：加入行情相对特征后，Technology 和 Consumer Discretionary 的行业内 Rank IC 从负数转正，排序偏差有所缓解；Health Care 仍是混合噪声，可能需要事件数据或更严格过滤。

回测口径：

```text
Top10
每 5 个交易日调仓
信号日后 1 个交易日收盘买入
持有 5 个交易日
单边交易成本 10 bps
```

Norgate S&P 500 历史成分实验配置：

```text
analysis/nasdaq_top500_score/configs/norgate_sp500_alpha158_lgbm_1d.yaml
```

运行入口：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/norgate_sp500_alpha158_lgbm_1d.yaml
```

注意：真实 Norgate API 需要 Windows、Norgate Data Updater、有效订阅和 `norgatedata` 包。当前 Mac 环境只验证了适配器和 fixture 测试。

SEC EDGAR 财报增强实验配置：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_1d.yaml
```

运行前需要设置 SEC 要求的 User-Agent：

```bash
export SEC_EDGAR_USER_AGENT="your-name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_1d.yaml
```

这个实验会把 SEC EDGAR 的 10-K / 10-Q 结构化 XBRL 字段按披露日转成日频 PIT 财报和估值特征，再与 Alpha158 合并训练。

SEC EDGAR 真实数据 smoke test 配置：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_15y_smoke.yaml
```

它同样使用 `2011-05-17` 到 `2026-05-17` 的固定窗口，但股票池先缩小到当前 Nasdaq 市值前 5，只用于验证真实 EDGAR 拉取、CIK 映射和财报特征生成：

```bash
export SEC_EDGAR_USER_AGENT="Your Name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_15y_smoke.yaml
```

行业相对特征实验配置：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_industry_lgbm_1d.yaml
```

运行入口：

```bash
export SEC_EDGAR_USER_AGENT="your-name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_industry_lgbm_1d.yaml
```

这个实验会先生成 Alpha158 和 EDGAR 财报估值特征，再用 `universe.csv` 里的 `sector` / `industry` 生成行业内 rank / percentile 特征。第一版行业分类来自当前 Nasdaq public snapshot，不是历史 PIT 行业分类。

以后要改股票池规模、数据窗口、标签表达式、切分日期、模型参数和 TopN 报告数量，优先改 YAML，不直接改脚本。

## 输出目录

每个实验输出到独立目录：

```text
analysis/nasdaq_top500_score/runs/<experiment.name>/
```

默认实验会生成：

```text
runs/nasdaq_alpha158_lgbm_1d/universe.csv
runs/nasdaq_alpha158_lgbm_1d/download_failures.csv
runs/nasdaq_alpha158_lgbm_1d/predictions.csv
runs/nasdaq_alpha158_lgbm_1d/report.md
runs/nasdaq_alpha158_lgbm_1d/resolved_config.yaml
runs/nasdaq_alpha158_lgbm_1d/qlib_source_csv/
runs/nasdaq_alpha158_lgbm_1d/qlib_data/
```

Norgate 配置会额外生成 `membership.csv`，记录每只股票在每个交易日是否属于历史指数成分。

EDGAR 配置会额外生成 `fundamental_features.parquet`、`fundamental_failures.csv` 和 `edgar_cik_map.csv`。

FRED/ALFRED 宏观配置会额外生成 `macro_raw_observations.parquet`、`macro_asof_observations.parquet`、`macro_features.parquet` 和 `macro_failures.csv`。

行业配置会额外生成 `industry_features.parquet` 和 `industry_failures.csv`。

证券主数据、流动性过滤、分桶和行业约束配置会额外生成 `security_master.csv`、`security_master_exclusions.csv`、`universe_exclusions.csv`、`liquidity_profile.csv`、`liquidity_exclusions.csv`、`history_buckets.csv`、`bucketed_predictions.csv` 和 `selected_top10.csv`。

启用回测的配置会额外生成 `test_predictions.csv`、`backtest_nav.csv`、`backtest_positions.csv` 和 `backtest_summary.yaml`。

启用基准复盘的配置会额外生成 `benchmark_prices.csv` 和 `benchmark_summary.yaml`。

启用贡献归因的配置会额外生成 `contribution_by_symbol.csv`、`contribution_by_sector.csv`、`contribution_by_industry.csv`、`exposure_by_sector.csv`、`exposure_by_industry.csv` 和 `contribution_summary.yaml`。

启用策略对照的配置会额外生成 `strategy_comparison.csv`、`strategy_comparison_summary.yaml` 和 `strategy_comparison/` 下每个 variant 的独立回测与归因文件。

启用行业内选股复盘的配置会额外生成 `within_sector_daily_metrics.csv`、`within_sector_summary.csv`、`within_industry_summary.csv`、`within_sector_quantile_returns.csv` 和 `within_sector_selection_summary.yaml`。

启用重点行业错误复盘的配置会额外生成 `sector_error_review_summary.csv`、`sector_error_examples.csv`、`sector_error_feature_differences.csv` 和 `sector_error_review_summary.yaml`。

最近一次重点行业错误复盘结论：`Technology` Rank IC 从 `-0.0214` 改善到 `0.0087`，`Consumer Discretionary` 从 `-0.0230` 改善到 `0.0159`；高分输家率和低分赢家率也下降。`Health Care` 从 `0.0191` 降到 `0.0077`，说明它更可能需要事件数据，而不是继续只加行情特征。

`resolved_config.yaml` 是复盘入口：它记录这次实验实际使用的股票池、标签、特征、切分和模型参数。

## 当前学习口径

默认实验仍然是 1 日标签：

```text
Ref($close, -2) / Ref($close, -1) - 1
```

阶段 B 只解决“实验可复现、可比较、可扩展”，不追求提升 IC。阶段 C 再新增未来 5 日收益标签做对比。

## 历史报告

目录下的 `nasdaq_top5_report.md` 和 `nasdaq_qlib_lightgbm_top5_report.md` 是早期学习报告，保留用于对照。新的 Qlib 实验报告以后看 `runs/<experiment.name>/report.md`。

生成的逐股票 CSV、Qlib bin 数据、缓存和 `runs/` 默认不提交到 Git。
