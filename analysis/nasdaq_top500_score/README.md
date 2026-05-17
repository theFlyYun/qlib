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

以后要改股票池规模、数据回看天数、标签表达式、切分比例、模型参数和 TopN 报告数量，优先改 YAML，不直接改脚本。

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
