# CRSP 2010 Baseline Cleanup And Industry Recovery

## 本阶段目标

把 CRSP 主研究线从 `2000-01-03 ~ 2025-12-31` 收敛到更快、更贴近实盘节奏的 `2010-01-01 ~ 2025-12-31`，并固定以下口径：

```text
数据源：CRSP 本地日级数据
股票池：US Common Equity 月度动态市值 Top500
标签：未来 10 个交易日总收益
调仓：每 10 个交易日一次
入场：信号日后 1 个交易日 open
主成本：0bps
压力测试：0 / 25 / 50bps
第一版模型：Alpha158-only + conservative LightGBM
```

这一步不是为了继续追高收益，而是让后续研究有一个更干净、更快、更可复查的新 baseline。

## 为什么改成 2010-2025

`2000-2025` 的优点是历史长，能覆盖更多市场状态；缺点是训练和复盘时间长，而且早期数据的行业、财报、宏观覆盖和现代市场结构差异更大。

`2010-2025` 的优势是：

- 训练更快，便于反复比较不同特征和组合规则。
- 更接近未来实盘环境，电子化交易和数据覆盖更稳定。
- EDGAR XBRL、FRED/ALFRED 宏观、CRSP 日线三者的可用性更好。
- 测试期仍固定为 `2024-2025`，便于和前面实验对齐。

代价是：少了 2000-2009 这段市场状态，长期稳健性不能只看这个窗口。后续如果 2010 主线稳定，再回头做 2000 全窗口验证。

## 标准清理策略

本阶段新增清理 dry-run，不直接盲删大型目录。

保留：

```text
crsp_daily_raw
crsp_warehouse
crsp_prepared_datasets
当前可复盘的 CRSP baseline / macro / ablation 汇总
配置、代码、学习文档、测试代码
```

可清理候选：

```text
旧 Nasdaq 大型 runs
半成品 strict provider runs
重复 macro ablation runs
过期 Qlib bin / source CSV
旧 2000 窗口中间产物
```

清理命令只生成清单：

```bash
.venv/bin/python analysis/nasdaq_top500_score/cleanup_runs.py
```

输出：

```text
analysis/nasdaq_top500_score/runs/cleanup_dry_run/cleanup_report.md
analysis/nasdaq_top500_score/runs/cleanup_dry_run/cleanup_summary.yaml
```

只有当 2010 主线跑通并确认关键报告都能复盘后，才考虑实际删除旧大型 run；原始 CRSP 数据和 warehouse 不删除。

## 本次实现结果

新增配置：

```text
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_10d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_bucket_top10_10d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_industry_constrained_10d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_industry_market_relative_10d_conservative_2010_2025.yaml
```

第一版实际运行的是 Alpha158-only baseline：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_10d_conservative_2010_2025.yaml
```

关键产物：

```text
analysis/nasdaq_top500_score/runs/crsp_alpha158_10d_conservative_2010_2025/report.md
analysis/nasdaq_top500_score/runs/crsp_alpha158_10d_conservative_2010_2025/runtime_profile.yaml
analysis/nasdaq_top500_score/runs/crsp_alpha158_10d_conservative_2010_2025/crsp_industry_validation_summary.yaml
analysis/nasdaq_top500_score/runs/crsp_alpha158_10d_conservative_2010_2025/backtest_stress_matrix.csv
```

## 重要修复

第一次运行时发现一个窗口隔离问题：2010 配置虽然写对了，但 prepared dataset 复用 CRSP warehouse 时仍把 2000 年起的 Qlib calendar 带进了训练数据。

已修复为：

- `membership.csv` 按当前配置的 `data.start_date / data.end_date` 过滤。
- `qlib_source_csv` 只写当前配置窗口内的 OHLCV。
- prepared dataset key 仍随日期窗口变化。
- 2010 run 的 Fit / All 已从 `2010-01-04` 开始，不再混入 2000-2009。

这点非常重要：训练窗口缩短不能只改 YAML，还必须确保底层 prepared dataset 也按窗口裁剪。

## 2010 Baseline 结果

本次 2010 Alpha158-only conservative baseline：

```text
Fit: 2010-01-04 ~ 2021-12-31
Train: 2010-03-31 ~ 2021-12-31
Valid: 2022-01-03 ~ 2023-12-29
Test: 2024-01-02 ~ 2025-12-31
Test IC: 0.015469
Test Rank IC: -0.009241
主回测累计收益: 85.86%
主回测年化收益: 36.67%
最大回撤: -17.12%
Beta: 约 1.5
主成本: 0bps
压力测试数量: 18 组
```

需要谨慎理解：

- 收益不错，但 Rank IC 仍为负，说明模型整体横截面排序力没有被充分确认。
- Beta 仍偏高，收益可能包含较强市场暴露。
- 50bps 压力下年化明显下降，说明虽然券商零佣金，滑点和开盘成交不确定性仍需要关注。

## 成本口径

主结果改为 `0bps`，因为用户的券商没有显式佣金。

但压力测试仍保留 `25/50bps`，原因是：

```text
成本不只等于券商佣金
还包含买卖价差
开盘成交不确定性
滑点
市场冲击
小盘股成交质量
```

所以后续报告展示顺序固定为：

```text
先看 0bps 主收益
再看 25/50bps 压力收益
```

如果 0bps 很好但 25/50bps 明显坍塌，只能说明信号理论上有收益，实盘可交易性还没有通过。

## 历史长度分桶恢复

保留原定义：

```text
full_10y >= 2520
5_10y >= 1260
2_5y >= 504
lt_2y >= 180
```

当前 2010 baseline 已经生成 `history_buckets.csv`，但第一版不直接启用桶内名额。

后续对照顺序：

1. 原始全局 Top10。
2. 桶内名额 Top10：`4/3/2/1`。
3. 比较收益、回撤、Rank IC、短历史贡献和失败样本。

桶内名额不是默认策略，只是风险控制对照。

## 行业路径恢复

第一版使用 CRSP 字段：

```text
sector = SIC 2 位
industry = SIC 4 位
UNKNOWN = 缺失 / 0 / NOAVAIL
```

本次行业验收结果：

```text
membership rows: 96000
train_min_annual_sic2_coverage: 67.8%
test_min_rebalance_sic2_coverage: 97.2%
要求 train >= 80%
要求 test >= 85%
结论：industry_review_only_until_coverage_improves
```

含义：

- 测试期行业覆盖很好。
- 训练期某些年度行业覆盖不足。
- 因此行业约束和行业内相对特征暂时不能进入默认模型。
- 目前只允许做行业暴露和贡献复盘。

后续恢复路径：

1. 先做行业暴露与行业贡献复盘。
2. 如果覆盖问题能解决，再跑行业约束 Top10：`max_sector=3`、`max_industry=2`。
3. 最后再做行业内 market 相对特征，例如动量、波动率、成交额分位。

## 后续数据加入顺序

2010 新主线的顺序固定为：

1. Alpha158-only baseline。
2. Alpha158 + 历史分桶对照。
3. Alpha158 + 行业约束 / 行业内 market 相对特征。
4. EDGAR 覆盖率与 `PERMNO -> CIK` 映射评估。
5. Alpha158 + EDGAR。
6. Alpha158 + EDGAR + 行业内财务/估值相对特征。
7. 最后再加 FRED/ALFRED macro 和 macro interactions。

原因：

- 行业和 EDGAR 更直接影响横截面选股。
- 宏观更偏市场状态和风险控制。
- 如果个股/行业信息还没稳定，过早加宏观容易把解释搞乱。

## 下一步

短期先不要继续加宏观。

下一步更合理的是：

```text
运行 bucket Top10 对照
复盘 full_10y / 5_10y / 2_5y / lt_2y 的收益贡献
检查行业 UNKNOWN 集中在哪些年份和哪些股票
决定是否能修复训练期行业覆盖
```

如果行业覆盖不能修复，就把行业继续保留为复盘维度，不进入模型和选股约束。

## 相关笔记

[[CRSP Data Source Migration Plan]]
[[CRSP Training Speed Optimization]]
[[CRSP Conservative Model And Horizon Comparison]]
[[Stock Pool Cleaning And History Buckets]]
[[Industry Features And Relative Ranking]]
[[Market Derived Relative Features]]
[[Backtest Stress Test Review]]
