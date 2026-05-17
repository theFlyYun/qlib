# Fixed Window And Real EDGAR Runbook

## 本阶段目标

从现在开始，长期实验使用固定数据窗口：

```text
2011-05-17 到 2026-05-17
```

这个窗口写进 YAML 配置，不再根据运行当天自动移动。这样后续比较 Alpha158、EDGAR、行业相对特征、5 日标签和 TopK 回测时，结果才可复盘。

## 为什么必须固定时间窗口

之前 baseline 使用的是：

```yaml
data:
  lookback_days: 900
```

这表示“从运行当天往前推 900 个自然日”。如果三个月后再跑一次，数据窗口会自动移动，训练集、验证集、测试集都会变化。

固定窗口改成：

```yaml
data:
  start_date: "2011-05-17"
  end_date: "2026-05-17"
```

这样同一个配置在未来复跑时，研究问题仍然是同一个研究问题。

## 当前固定切分

第一版固定切分是：

```text
数据窗口：2011-05-17 到 2026-05-17
训练集：2011-05-17 到 2021-12-31
验证集：2022-01-01 到 2023-12-31
测试集：2024-01-01 到 2026-05-17
warmup：60 个交易日
```

注意：`2026-05-17` 是周日。真实日线数据最后一个交易日通常会落在前一个交易日，例如 `2026-05-15`。配置仍然固定写 `2026-05-17`，实际训练时会选择数据中可用的最后交易日。

## 固定窗口 baseline 配置

配置文件：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_lgbm_15y_fixed.yaml
```

运行命令：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_lgbm_15y_fixed.yaml
```

当前仍使用 Nasdaq public 数据源。它适合学习固定窗口流程，但仍有局限：

```text
股票池是当前 Nasdaq 市值前 500，不是历史动态成分
不含退市股票
行情复权口径不如 Norgate / CRSP 严谨
不同股票上市时间不同，不保证每只股票都有完整 15 年历史
```

## EDGAR 真实数据需要准备什么

SEC EDGAR 是官方免费数据源，但自动访问必须遵守 SEC Fair Access 规则。

你需要准备：

```text
1. 一个可联系的姓名或项目名
2. 一个真实邮箱
3. 稳定网络
4. 本地缓存目录
5. 先跑小股票池 smoke test，不要一上来跑 500 只
```

在 shell 里设置：

```bash
export SEC_EDGAR_USER_AGENT="Your Name your-email@example.com"
```

这里不要随便写假邮箱。SEC 官方要求请求头声明 User-Agent，并给出可联系信息。

## EDGAR smoke test

配置文件：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_15y_smoke.yaml
```

这个配置只取当前 Nasdaq 市值前 5，用于验证：

```text
ticker -> CIK 映射是否成功
submissions 是否能下载
companyfacts 是否能下载
10-K / 10-Q 是否能按披露日对齐
fundamental_features.parquet 是否生成
fundamental_failures.csv 有哪些缺失原因
```

运行命令：

```bash
export SEC_EDGAR_USER_AGENT="Your Name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_15y_smoke.yaml
```

成功后重点检查：

```text
analysis/nasdaq_top500_score/runs/nasdaq_alpha158_edgar_lgbm_15y_smoke/edgar_cik_map.csv
analysis/nasdaq_top500_score/runs/nasdaq_alpha158_edgar_lgbm_15y_smoke/fundamental_features.parquet
analysis/nasdaq_top500_score/runs/nasdaq_alpha158_edgar_lgbm_15y_smoke/fundamental_failures.csv
analysis/nasdaq_top500_score/runs/nasdaq_alpha158_edgar_lgbm_15y_smoke/report.md
```

## 为什么先 smoke test

EDGAR 的数据不是一个整齐表格。真实问题包括：

```text
ticker 和 CIK 不一定一一稳定对应
不同公司 XBRL tag 不完全一致
某些字段缺失
修正版 10-K/A、10-Q/A 需要记录
companyfacts 和 submissions 更新时间可能有延迟
全量 500 只会产生较多请求
```

先跑 5 只，是为了确认通路正确，再扩大到 50、100、500。

## 官方资料

- [SEC Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)
- [SEC data.sec.gov](https://data.sec.gov/)

## 下一步

建议顺序：

```text
1. 运行 15 年固定窗口 Alpha158 baseline。
2. 设置 SEC_EDGAR_USER_AGENT。
3. 运行 5 只股票 EDGAR smoke test。
4. 检查 CIK 映射、财报特征和 failure 文件。
5. 扩大到 50 只股票。
6. 最后再跑 Nasdaq 500 + EDGAR。
```

相关笔记：

[[SEC EDGAR Fundamentals Integration]]
[[SEC EDGAR Technical Data Flow]]
[[Industry Features And Relative Ranking]]
[[Data Source Upgrade Plan]]
