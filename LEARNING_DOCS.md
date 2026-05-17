# Qlib Quant Learning Docs

这个仓库的系统学习文档现在放在项目内的 `learning/` 目录中，推荐通过 GitHub 同步和在 iOS 端阅读。这样不占用 iCloud 空间，也能让学习文档跟代码版本保持一致。

文档主线已经调整为量化交易学习路线：重点是策略、原理、数据源、回测、组合风控和实盘约束，不以技术实现细节为主。Qlib 是练习平台，学习路线不局限于当前项目。

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

当前已按阶段分层：

- `00-start-here/`：总入口、路线、资源、命令和源码地图。
- `01-foundation/`：市场、交易和数据基础。
- `02-signals-and-labels/`：Alpha158、标签、IC 和 Rank IC。
- `03-modeling/`：LightGBM、模型训练和验证。
- `04-strategy-backtest/`：TopK、回测和交易成本。
- `05-data-expansion/`：40 年数据、多源数据和数据口径。
- `06-portfolio-risk/`：行业中性化和组合风控。
- `90-case-studies/`：四方股份、Nasdaq/Qlib 等案例。
- `99-logs/`：学习日志和阶段完成记录。

每做完一个阶段，都要更新：

```text
learning/99-logs/Stage Completion Records.md
```

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

完整学习路线请以仓库内 `learning/` 文档为准。
