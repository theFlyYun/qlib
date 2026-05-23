# Qlib Commands

这份笔记收集学习过程中的可复制命令。默认你已经在 Qlib 项目根目录。

## 激活环境

```bash
source .venv/bin/activate
```

检查版本：

```bash
python - <<'PY'
import qlib
import lightgbm
import mlflow
print("qlib", qlib.__version__)
print("lightgbm", lightgbm.__version__)
print("mlflow", mlflow.__version__)
PY
```

## 数据准备

检查默认数据目录：

```bash
ls ~/.qlib/qlib_data/cn_data
```

下载简版 CN 1d 数据：

```bash
python scripts/get_data.py qlib_data --name qlib_data_simple --target_dir ~/.qlib/qlib_data/cn_data --interval 1d --region cn
```

检查数据健康：

```bash
python scripts/check_data_health.py check_data --qlib_dir ~/.qlib/qlib_data/cn_data
```

## 运行 workflow

运行 LightGBM Alpha158 示例：

```bash
qrun examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml
```

调试入口：

```bash
python -m pdb qlib/cli/run.py examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml
```

运行代码式 workflow：

```bash
python examples/workflow_by_code.py
```

运行 Nasdaq 配置化学习实验：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_lgbm_1d.yaml
```

运行 CRSP 本地日级数据源 baseline：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_10d_2000_2025.yaml
```

运行 CRSP + FRED/ALFRED 宏观增强实验：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_macro_10d_2000_2025.yaml
```

运行 CRSP 早停与负 IC 诊断：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_diagnostics.py \
  --config analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_10d_2000_2025.yaml
```

运行 CRSP 2010-2025 Alpha158-only conservative baseline：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_10d_conservative_2010_2025.yaml
```

运行 CRSP 2010-2025 Alpha158 + SEC EDGAR 财报估值实验：

```bash
export SEC_EDGAR_USER_AGENT="Your Name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_10d_conservative_2010_2025.yaml
```

运行 CRSP 2010-2025 EDGAR 清洗、行业相对特征和分组 ablation：

```bash
export SEC_EDGAR_USER_AGENT="Your Name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_clean_10d_conservative_2010_2025.yaml

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_relative_10d_conservative_2010_2025.yaml

for cfg in \
  analysis/nasdaq_top500_score/configs/crsp_edgar_ablation/drop_valuation.yaml \
  analysis/nasdaq_top500_score/configs/crsp_edgar_ablation/drop_profitability_quality.yaml \
  analysis/nasdaq_top500_score/configs/crsp_edgar_ablation/drop_growth.yaml \
  analysis/nasdaq_top500_score/configs/crsp_edgar_ablation/drop_balance_sheet_stability.yaml \
  analysis/nasdaq_top500_score/configs/crsp_edgar_ablation/drop_filing_state.yaml
do
  .venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
    --config "$cfg"
done

.venv/bin/python -u analysis/nasdaq_top500_score/crsp_edgar_ablation_review.py \
  --manifest analysis/nasdaq_top500_score/configs/crsp_edgar_ablation/manifest.yaml
```

CRSP EDGAR ablation 汇总优先看：

```text
analysis/nasdaq_top500_score/runs/crsp_edgar_ablation_review/crsp_edgar_ablation_summary.csv
analysis/nasdaq_top500_score/runs/crsp_edgar_ablation_review/report.md
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_clean_10d_conservative_2010_2025/edgar_coverage_summary.yaml
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_clean_10d_conservative_2010_2025/fundamental_cleaning_summary.yaml
```

运行 CRSP 2010-2025 EDGAR 字段级修复实验：

```bash
export SEC_EDGAR_USER_AGENT="Your Name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_repaired_quality_10d_conservative_2010_2025.yaml

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_repaired_no_valuation_10d_conservative_2010_2025.yaml
```

运行 CRSP 2010-2025 EDGAR quality core + 字段有效性审计：

```bash
export SEC_EDGAR_USER_AGENT="Your Name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_quality_core_10d_conservative_2010_2025.yaml
```

运行 CRSP 2010-2025 EDGAR mini-core 与 20/60 日标签对照：

```bash
export SEC_EDGAR_USER_AGENT="Your Name your-email@example.com"

for cfg in \
  analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_20d_conservative_2010_2025.yaml \
  analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_mini_core_20d_conservative_2010_2025.yaml \
  analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_60d_conservative_2010_2025.yaml \
  analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_mini_core_60d_conservative_2010_2025.yaml
do
  .venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
    --config "$cfg"
done

.venv/bin/python -u analysis/nasdaq_top500_score/crsp_edgar_mini_core_horizon_review.py
```

修复实验重点看：

```text
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_repaired_quality_10d_conservative_2010_2025/edgar_missingness_root_cause.csv
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_repaired_quality_10d_conservative_2010_2025/edgar_field_availability_by_year.csv
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_repaired_quality_10d_conservative_2010_2025/edgar_tag_resolution_report.csv
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_repaired_quality_10d_conservative_2010_2025/report.md
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_quality_core_10d_conservative_2010_2025/edgar_feature_effectiveness_summary.yaml
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_quality_core_10d_conservative_2010_2025/edgar_feature_ic_summary.csv
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_quality_core_10d_conservative_2010_2025/edgar_feature_quantile_spread.csv
analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_horizon_review/crsp_edgar_mini_core_horizon_summary.csv
analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_horizon_review/report.md
```

运行 CRSP 2010 历史长度桶内 Top10 对照：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_bucket_top10_10d_conservative_2010_2025.yaml
```

复盘 CRSP 2010 行业 `UNKNOWN` 来源：

```bash
.venv/bin/python analysis/nasdaq_top500_score/crsp_industry_unknown_review.py \
  --run-dir analysis/nasdaq_top500_score/runs/crsp_alpha158_bucket_top10_10d_conservative_2010_2025
```

运行 CRSP 2010 行业约束对照前，先看行业验收：

```bash
cat analysis/nasdaq_top500_score/runs/crsp_alpha158_10d_conservative_2010_2025/crsp_industry_validation_summary.yaml
```

查看 CRSP 2010 行业映射来源和覆盖率：

```bash
cat analysis/nasdaq_top500_score/runs/crsp_alpha158_10d_conservative_2010_2025/industry_mapping_summary.yaml
head -20 analysis/nasdaq_top500_score/runs/crsp_alpha158_10d_conservative_2010_2025/industry_mapping_coverage.csv
```

生成 runs 标准清理 dry-run 清单：

```bash
.venv/bin/python analysis/nasdaq_top500_score/cleanup_runs.py
```

运行固定 15 年窗口 baseline：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_lgbm_15y_fixed.yaml
```

运行固定 10 年窗口 baseline：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_lgbm_10y_fixed.yaml
```

运行固定 10 年窗口、短历史股票也进入评估的 baseline：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_lgbm_10y_eval_all.yaml
```

运行固定 10 年窗口、短历史股票也进入评估的 EDGAR 实验：

```bash
export SEC_EDGAR_USER_AGENT="Your Name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_eval_all.yaml
```

运行固定 10 年窗口、证券主数据、流动性过滤、历史长度分桶、桶内 Top10 和行业名额约束的 EDGAR 实验：

```bash
export SEC_EDGAR_USER_AGENT="Your Name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10.yaml
```

运行同一口径、未来 5 日收益标签和 Top10 成本后回测的 EDGAR 实验：

```bash
export SEC_EDGAR_USER_AGENT="Your Name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d.yaml
```

运行 PIT 过滤版 5 日 Top10 回测：

```bash
export SEC_EDGAR_USER_AGENT="Your Name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d_pit_safe.yaml
```

运行 as-of 2023-12-31 近似冻结股票池的 PIT 过滤版 5 日 Top10 回测：

```bash
export SEC_EDGAR_USER_AGENT="Your Name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
```

运行同一冻结股票池、加入 FRED/ALFRED 宏观特征的 5 日 Top10 回测：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_macro_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
```

运行同一冻结股票池、默认宏观交互主策略的 5 日 Top10 回测。

当前默认去掉 `credit spread × liabilities/cash` 两个信用质量交互；完整 10 交互配置保留为研究对照。

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_macro_interactions_default_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
```

运行完整 10 个宏观交互特征的研究对照：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_macro_interactions_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml
```

运行宏观交互 ablation，对比不同交互组的贡献：

```bash
for cfg in \
  analysis/nasdaq_top500_score/configs/macro_ablation/drop_vix_interactions.yaml \
  analysis/nasdaq_top500_score/configs/macro_ablation/drop_rate_valuation_interactions.yaml \
  analysis/nasdaq_top500_score/configs/macro_ablation/drop_credit_quality_interactions.yaml \
  analysis/nasdaq_top500_score/configs/macro_ablation/drop_sector_flag_interactions.yaml \
  analysis/nasdaq_top500_score/configs/macro_ablation/only_vix_interactions.yaml
do
  .venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
    --config "$cfg"
done

.venv/bin/python -u analysis/nasdaq_top500_score/macro_ablation_review.py \
  --manifest analysis/nasdaq_top500_score/configs/macro_ablation/manifest.yaml
```

ablation 汇总优先看：

```text
analysis/nasdaq_top500_score/runs/macro_interaction_ablation_review/macro_ablation_summary.csv
analysis/nasdaq_top500_score/runs/macro_interaction_ablation_review/macro_ablation_regime_summary.csv
analysis/nasdaq_top500_score/runs/macro_interaction_ablation_review/macro_ablation_review_summary.yaml
```

运行 CRSP 10 日保守模型的宏观交互 ablation 与 regime 复盘：

```bash
for cfg in \
  analysis/nasdaq_top500_score/configs/crsp_macro_ablation/drop_vix_interactions.yaml \
  analysis/nasdaq_top500_score/configs/crsp_macro_ablation/drop_rate_curve_interactions.yaml \
  analysis/nasdaq_top500_score/configs/crsp_macro_ablation/drop_credit_interaction.yaml \
  analysis/nasdaq_top500_score/configs/crsp_macro_ablation/drop_dollar_oil_interactions.yaml \
  analysis/nasdaq_top500_score/configs/crsp_macro_ablation/only_vix_interactions.yaml \
  analysis/nasdaq_top500_score/configs/crsp_macro_ablation/only_rate_curve_interactions.yaml
do
  .venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
    --config "$cfg"
done

.venv/bin/python -u analysis/nasdaq_top500_score/macro_ablation_review.py \
  --manifest analysis/nasdaq_top500_score/configs/crsp_macro_ablation/manifest.yaml
```

CRSP ablation 汇总优先看：

```text
analysis/nasdaq_top500_score/runs/crsp_macro_interaction_ablation_review/crsp_macro_ablation_summary.csv
analysis/nasdaq_top500_score/runs/crsp_macro_interaction_ablation_review/crsp_macro_ablation_regime_summary.csv
analysis/nasdaq_top500_score/runs/crsp_macro_interaction_ablation_review/crsp_macro_ablation_review_summary.yaml
analysis/nasdaq_top500_score/runs/crsp_macro_interaction_ablation_review/report.md
```

运行未来函数与回测收益水分审计：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/future_leakage_audit.py
```

审计证据输出：

```text
analysis/nasdaq_top500_score/runs/nasdaq_alpha158_edgar_macro_ablation_drop_credit_quality_interactions_10y_frozen_2023_top500_5d_pit_safe/future_leakage_audit/
```

运行 Strict PIT 配置：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/strict/strict_baseline_alpha158_edgar_5d.yaml

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/strict/strict_macro_direct_5d.yaml

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/strict/strict_macro_interactions_no_credit_5d.yaml
```

这些配置需要 PIT 数据源。当前 Mac 如果没有 Norgate Data Updater 和有效订阅，会给出数据源不可用提示，不会退回到 `nasdaq_public` 当前快照。

运行 Sharadar Strict PIT 配置：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/strict/strict_sharadar_baseline_alpha158_edgar_5d.yaml

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/strict/strict_sharadar_macro_direct_5d.yaml

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/strict/strict_sharadar_macro_interactions_no_credit_5d.yaml
```

Sharadar 配置需要 Nasdaq Data Link / Sharadar 订阅。API key 写在 ignored `.env`：

```bash
NASDAQ_DATA_LINK_API_KEY=your_key_here
```

运行后会先生成 provider capability 输出；字段验收不通过时会停止，不进入训练：

```text
provider_capability_summary.yaml
provider_table_columns.csv
provider_capability_report.md
```

运行 Databento Strict PIT 配置：

```bash
.venv/bin/python -m pip install databento

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/strict/strict_databento_baseline_alpha158_edgar_5d.yaml

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/strict/strict_databento_macro_direct_5d.yaml

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/strict/strict_databento_macro_interactions_no_credit_5d.yaml
```

Databento 配置需要 `DATABENTO_API_KEY`。API key 写在 ignored `.env`，不要写入 YAML 配置，也不要提交：

```bash
DATABENTO_API_KEY=your_key_here
```

默认 no-credit macro interactions 配置已启用回测压力测试，运行后会额外输出：

```text
pit_universe_validation.csv
security_master_validation.csv
market_cap_validation.csv
data_quality_summary.yaml
backtest_stress_matrix.csv
backtest_stress_summary.yaml
backtest_stress/
```

`FRED_API_KEY` 和 `SEC_EDGAR_USER_AGENT` 可以写在仓库根目录 `.env`，脚本会自动读取；`.env` 已被 Git ignore，不会提交。shell 环境变量优先级更高，可以临时覆盖 `.env`。

如果只是复盘行业约束、TopK 或错误样本，不想重新训练模型，可以把配置中的 `training.reuse_test_predictions` 临时改为 `true`。这会复用当前 run 目录里的 `test_predictions.csv`：

```yaml
training:
  seed: 20260519
  deterministic: true
  reuse_test_predictions: true
```

该配置已启用 `NASDAQCOM` 基准复盘，输出：

```text
backtest_nav.csv
backtest_summary.yaml
benchmark_prices.csv
benchmark_summary.yaml
contribution_by_symbol.csv
contribution_by_sector.csv
contribution_by_industry.csv
exposure_by_sector.csv
exposure_by_industry.csv
contribution_summary.yaml
strategy_comparison.csv
strategy_comparison_summary.yaml
strategy_comparison/unconstrained_top10/
strategy_comparison/sector_cap_2_top10/
strategy_comparison/sector_cap_3_top10/
strategy_comparison/sector_cap_4_top10/
strategy_comparison/sector_momentum_tilt_top10/
strategy_comparison/raw_score_sector_cap_2_top10/
strategy_comparison/short_history_penalty_sector_cap_2_top10/
strategy_comparison/short_history_strict_sector_cap_2_top10/
within_sector_daily_metrics.csv
within_sector_summary.csv
within_industry_summary.csv
within_sector_quantile_returns.csv
within_sector_selection_summary.yaml
sector_error_review_summary.csv
sector_error_examples.csv
sector_error_feature_differences.csv
sector_error_review_summary.yaml
short_history_bucket_summary.csv
short_history_examples.csv
short_history_feature_differences.csv
short_history_sector_breakdown.csv
short_history_review_summary.yaml
macro_interaction_features.parquet
macro_interaction_failures.csv
macro_regime_daily_metrics.csv
macro_regime_summary.csv
macro_regime_strategy_comparison.csv
macro_regime_sector_exposure.csv
macro_regime_contribution_summary.csv
macro_regime_review_summary.yaml
market_features.parquet
market_feature_failures.csv
report.md
```

5.8C 短历史 score 校准使用同一份 `test_predictions.csv`，只改变选股排序：

```text
raw_score = 模型原始分数
adjusted_score = raw_score - 短历史惩罚
```

主结论看 `strategy_comparison.csv` 中这三行：

```text
raw_score_sector_cap_2_top10
short_history_penalty_sector_cap_2_top10
short_history_strict_sector_cap_2_top10
```

运行真实 EDGAR smoke test 前先设置 User-Agent：

```bash
export SEC_EDGAR_USER_AGENT="Your Name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_15y_smoke.yaml
```

复盘本次实验优先看：

```bash
sed -n '1,220p' analysis/nasdaq_top500_score/runs/nasdaq_alpha158_lgbm_1d/report.md
sed -n '1,160p' analysis/nasdaq_top500_score/runs/nasdaq_alpha158_lgbm_1d/resolved_config.yaml
```

复盘 10 年窗口 EDGAR 全量实验：

```bash
sed -n '1,220p' analysis/nasdaq_top500_score/runs/nasdaq_alpha158_edgar_lgbm_10y_eval_all/report.md

.venv/bin/python - <<'PY'
from pathlib import Path
import pandas as pd
run = Path("analysis/nasdaq_top500_score/runs/nasdaq_alpha158_edgar_lgbm_10y_eval_all")
features = pd.read_parquet(run / "fundamental_features.parquet")
print(features.shape)
print(features.index.get_level_values("instrument").nunique())
PY
```

复盘证券主数据 + 流动性过滤 + 分桶 + 行业约束 Top10 实验：

```bash
sed -n '1,260p' analysis/nasdaq_top500_score/runs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10/report.md

.venv/bin/python - <<'PY'
import pandas as pd
run = "analysis/nasdaq_top500_score/runs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10"
cols = ["selected_rank", "symbol", "history_bucket", "bucket_rank", "global_rank", "score"]
print(pd.read_csv(f"{run}/selected_top10.csv").loc[:, cols])
print(pd.read_csv(f"{run}/security_master.csv")["asset_type"].value_counts())
print(pd.read_csv(f"{run}/history_buckets.csv")["history_bucket"].value_counts())
print(pd.read_csv(f"{run}/liquidity_exclusions.csv")["exclusion_reason"].value_counts())
PY
```

复盘 5 日收益标签实验：

```bash
sed -n '1,260p' analysis/nasdaq_top500_score/runs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d/report.md
```

复盘 TopK 成本后回测：

```bash
sed -n '1,120p' analysis/nasdaq_top500_score/runs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d/backtest_summary.yaml

.venv/bin/python - <<'PY'
import pandas as pd
run = "analysis/nasdaq_top500_score/runs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d"
print(pd.read_csv(f"{run}/backtest_nav.csv").tail())
print(pd.read_csv(f"{run}/backtest_positions.csv").head())
PY
```

复盘 PIT 过滤版回测：

```bash
sed -n '1,140p' analysis/nasdaq_top500_score/runs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d_pit_safe/backtest_summary.yaml
sed -n '1,280p' analysis/nasdaq_top500_score/runs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d_pit_safe/report.md
```

## CRSP 保守模型与标签周期对照

运行 5 / 10 / 20 日保守模型：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_5d_conservative_2000_2025.yaml

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_10d_conservative_2000_2025.yaml

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_20d_conservative_2000_2025.yaml
```

运行诊断：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_diagnostics.py \
  --config analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_10d_conservative_2000_2025.yaml
```

生成横向对比表：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_signal_model_comparison.py
sed -n '1,80p' analysis/nasdaq_top500_score/runs/crsp_signal_model_comparison/crsp_signal_model_comparison.csv
```

## CRSP 10 日保守宏观对照

运行 raw macro conservative：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_macro_10d_conservative_2000_2025.yaml
```

运行 macro interaction conservative：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_macro_interactions_10d_conservative_2000_2025.yaml
```

CRSP 加速后的复跑重点看：

```text
analysis/nasdaq_top500_score/runs/crsp_prepared_datasets/
analysis/nasdaq_top500_score/runs/<experiment>/runtime_profile.csv
analysis/nasdaq_top500_score/runs/<experiment>/runtime_profile.yaml
```

只重跑压力测试时，先确保目标 run 里已经有 `test_predictions.csv`，然后把配置里的 `runtime.run_mode` 临时改为 `stress_only`。

生成三组对比表：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_macro_conservative_comparison.py
sed -n '1,80p' analysis/nasdaq_top500_score/runs/crsp_macro_conservative_comparison/crsp_macro_conservative_comparison.csv
```

## CRSP 2010 行业约束与行业内相对特征

只复用 baseline 预测分数，比较不同行业约束：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_industry_strategy_comparison_10d_conservative_2010_2025.yaml

sed -n '1,80p' analysis/nasdaq_top500_score/runs/crsp_alpha158_industry_strategy_comparison_10d_conservative_2010_2025/strategy_comparison.csv
```

重新训练行业内 market 相对特征模型：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_industry_market_relative_10d_conservative_2010_2025.yaml

sed -n '1,220p' analysis/nasdaq_top500_score/runs/crsp_alpha158_industry_market_relative_10d_conservative_2010_2025/report.md
```

## CRSP EDGAR Mini-Core 持仓差异复盘

复盘 10 日 `sector_cap_2_top10` 下，Alpha158-only 和 EDGAR mini-core 的持仓替换、贡献来源和财报字段差异：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_edgar_mini_core_position_diff.py
```

查看报告：

```bash
sed -n '1,220p' analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_position_diff_review/report.md
```

核心输出：

```text
analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_position_diff_review/edgar_mini_core_position_diff.csv
analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_position_diff_review/edgar_mini_core_added_removed_summary.csv
analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_position_diff_review/edgar_mini_core_contribution_diff.csv
analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_position_diff_review/edgar_mini_core_fundamental_diff.csv
analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_position_diff_review/edgar_mini_core_position_diff_summary.yaml
analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_position_diff_review/report.md
```

## CRSP 滚动窗口验证

完整运行 4 个测试窗口、2 条特征线，一共 8 组实验：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_rolling_window_validation.py
```

只重建滚动汇总报告，不重新训练：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_rolling_window_validation.py --only-summary
```

强制重跑全部窗口：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_rolling_window_validation.py --force
```

优先查看：

```text
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/crsp_rolling_window_summary.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/crsp_rolling_window_comparison.yaml
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/report.md
```

滚动验证只比较：

```text
Alpha158-only + sector_cap_2_top10
EDGAR mini-core + sector_cap_2_top10
```

如果某个窗口已经跑完，脚本默认会跳过它；如果只想检查路径和报告格式，用 `--only-summary`。

## CRSP 滚动窗口失败复盘

复用已有 8 个 rolling run，不重新训练模型，补齐 `sector_cap_2_top10` 的 0/25/50bps 压力测试，并生成 2022-2023 失败归因：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_rolling_window_failure_review.py
```

优先查看：

```text
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/failure_review/rolling_window_failure_review.md
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/failure_review/rolling_window_failure_summary.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/failure_review/rolling_edgar_delta_by_window.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/failure_review/sector_cap_2_stress_matrix.csv
```

这一步会把每个 rolling run 的 `strategy_comparison/sector_cap_2_top10/backtest_stress_matrix.csv` 补齐，因此滚动汇总里的 `sector_cap_2_stress_annualized_return_50bps` 不应再为空。

## CRSP 2022-2023 专项失效复盘

只复用 2022-2023 的 Alpha158-only 与 EDGAR mini-core rolling run，不重新训练，分析 `IC / TopK` 背离、beta、行业贡献、单票贡献和回撤区间：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_2022_2023_failure_deep_dive.py
```

优先查看：

```text
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023_failure_deep_dive/2022_2023_failure_deep_dive_report.md
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023_failure_deep_dive/ic_topk_divergence_by_period.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023_failure_deep_dive/sector_failure_contribution.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023_failure_deep_dive/symbol_failure_contribution.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023_failure_deep_dive/edgar_vs_alpha_2022_2023_delta.csv
```

这个复盘的核心判断是：如果 IC 为弱正但 TopK 亏损，下一步优先改组合构建和风险过滤；如果 IC 也失效，再回到标签和特征设计。

## CRSP 组合构建与风险过滤修复

复用 4 个 rolling 窗口的 Alpha158-only 与 EDGAR mini-core 预测，不重新训练，做 TopK 宽度、权重、单票风险过滤和 beta 控制对照：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/crsp_portfolio_repair.py
```

优先查看：

```text
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/portfolio_repair/crsp_portfolio_repair_report.md
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/portfolio_repair/crsp_portfolio_repair_decision.yaml
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/portfolio_repair/topk_width_comparison.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/portfolio_repair/portfolio_weighting_comparison.csv
analysis/nasdaq_top500_score/runs/crsp_rolling_windows/portfolio_repair/beta_control_comparison.csv
```

这一步的核心判断是：如果组合修复仍无法同时通过跨窗口 alpha、beta 和 50bps 压力，下一阶段应进入标签重设计，而不是继续堆新特征。

## Personal Quant v1 干净起点

新阶段先不运行模型，先阅读阶段收束和新方向文档：

```bash
sed -n '1,220p' learning/05-data-expansion/CRSP\\ Large\\ Research\\ Stage\\ Summary.md
sed -n '1,220p' learning/07-personal-quant/Personal\\ Quant\\ V1\\ Direction.md
sed -n '1,160p' analysis/personal_quant_v1/README.md
```

新阶段代码目录：

```text
analysis/personal_quant_v1/
```

这个目录用于重新开始小型、可解释、适合个人实盘复盘的架构；旧的 `analysis/nasdaq_top500_score/` 保留为研究平台和资料库。

## 测试与验证

烟测：

```bash
python -m pytest tests/misc/test_utils.py -q
```

检查 Cython 扩展：

```bash
python - <<'PY'
from qlib.data._libs import rolling, expanding
print(rolling.__file__)
print(expanding.__file__)
PY
```

## 查看实验产物

```bash
find mlruns -maxdepth 3 -type f | sed -n '1,120p'
```

```bash
find mlruns -name 'pred.pkl' -o -name 'port_analysis_1day.pkl' -o -name 'indicator_analysis_1day.pkl'
```

## 常见报错

### LightGBM 找不到 libomp

现象：

```text
Library not loaded: @rpath/libomp.dylib
```

解决：

```bash
brew install libomp
```

### 缺少示例数据

现象：

```text
Invalid provider uri
```

解决：重新执行数据下载命令。

### 可选模型被跳过

现象：

```text
CatBoostModel are skipped
XGBModel is skipped
PyTorch models are skipped
```

这不影响 LightGBM 示例。只有学习对应模型时才需要额外安装依赖。

## 相关笔记

[[Qlib Quant Learning Index]]
[[Qlib Source Map]]
[[Week 1 - Quant And Qlib Basics]]
[[Qlib Learning Log]]
