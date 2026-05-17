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
