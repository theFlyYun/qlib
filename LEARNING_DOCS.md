# Qlib Quant Learning Docs

这个仓库的系统学习文档现在放在项目内的 `learning/` 目录中，推荐通过 GitHub 同步和在 iOS 端阅读。这样不占用 iCloud 空间，也能让学习文档跟代码版本保持一致。

## 推荐方式：GitHub

文档入口：

```text
learning/README.md
```

iOS 阅读方式：

1. 把当前分支 push 到 GitHub。
2. 在 iPhone 或 iPad 安装 GitHub App，或用 Safari 打开仓库。
3. 进入 `learning/README.md`。
4. 按 4 周路线阅读。

## 当前文档结构

仓库内路径：

```text
learning/
```

包含：

- `README.md`
- `Qlib Quant Learning Index.md`
- `Week 1 - Quant And Qlib Basics.md`
- `Week 2 - Data Dataset And Features.md`
- `Week 3 - Model Workflow And Experiment Tracking.md`
- `Week 4 - Strategy Backtest And Custom Extension.md`
- `Qlib Source Map.md`
- `Qlib Commands.md`
- `Qlib Learning Log.md`

## 已废弃方式：iCloud Obsidian Vault

之前曾创建 iCloud Obsidian vault：

```text
~/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/Qlib Quant Learning
```

因为 iCloud 空间有限，后续以仓库内 `learning/` 为准。旧 iCloud vault 可以保留作备份，也可以在确认 GitHub 版本可用后手动删除。

## 本地项目基线

当前项目已经配置好本地环境：

```bash
source .venv/bin/activate
```

已跑通主示例：

```bash
qrun examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml
```

已通过烟测：

```bash
python -m pytest tests/misc/test_utils.py -q
```

完整学习路线请以 Obsidian vault 中的文档为准。
