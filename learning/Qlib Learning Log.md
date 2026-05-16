# Qlib Learning Log

这份笔记用于记录每次学习和实验。不要只贴输出，要写下你对结果的解释。

## 记录模板

### 日期

- 学习主题：
- 运行命令：
- 修改内容：
- 关键输出：
- 我现在能解释：
- 我还不理解：
- 下一步：

## 2026-05-16 环境基线

- 已创建本地 `.venv`。
- 已安装 `pyqlib` dev 依赖。
- 已安装 macOS LightGBM 所需 `libomp`。
- 已下载简版 CN 1d 数据到默认 Qlib 数据目录。
- 已跑通 `examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml`。
- 已通过 `tests/misc/test_utils.py` 烟测。

观察到的结果：

- `qlib` 可以导入。
- `lightgbm` 可以导入。
- `qrun` 可用。
- Cython 扩展 `rolling`、`expanding` 可加载。
- LightGBM workflow 生成了预测、IC 分析和组合回测结果。

## 待补问题

- IC 和 Rank IC 如何从预测分数计算出来。
- `TopkDropoutStrategy` 的调仓细节。
- `PortAnaRecord` 保存的 pickle 如何读取和可视化。
- 自有数据接入时，什么时候用 `dump_bin.py`，什么时候自定义 loader。

## 相关笔记

[[Qlib Quant Learning Index]]
[[Qlib Commands]]
[[Qlib Source Map]]
[[Week 1 - Quant And Qlib Basics]]
