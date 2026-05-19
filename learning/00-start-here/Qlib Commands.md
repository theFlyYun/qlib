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
