# Nasdaq Top 500 Score Experiments

这个目录包含两类学习实验：

- `build_nasdaq_score.py`：透明规则打分，不经过 Qlib 模型。
- `run_qlib_alpha158_lightgbm.py`：真正走 Qlib 数据格式、Alpha158 特征和 LightGBM 训练流程。

## 关键结果

规则打分报告：

```text
nasdaq_top5_report.md
```

Qlib 模型报告：

```text
nasdaq_qlib_lightgbm_top5_report.md
```

当前 Qlib 模型的测试期指标较弱：

```text
Test 日均 IC:      -0.009905
Test 日均 Rank IC: -0.003036
```

这说明当前流程可以作为学习样例，但不能作为买入建议。

## 复跑

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py
```

脚本会重新下载 Nasdaq 历史日线、转换 Qlib 数据并训练模型。生成的逐股票 CSV、Qlib bin 数据和缓存默认不提交到 Git。
