# PIT Safe Backtest

## 目标

把回测中最明显的未来信息先去掉：历史长度分桶和流动性过滤不能使用回测结束日的数据，而要按每个信号日当时可见的数据重新计算。

## 什么是 PIT-safe

PIT 是 point in time，意思是“站在当时那个时间点，只能看到当时已经发生、已经披露、已经上市、已经交易的数据”。

一个更安全的回测应该满足：

```text
信号日 t
只使用 t 日及以前行情
只使用 t 日及以前已披露财报
只使用 t 日当时可交易股票池
只使用 t 日以前流动性
只使用 t 日以前历史长度
预测 t+1 到 t+6 的未来收益
```

## 本次修正了什么

第一版 TopK 回测存在两个明显问题：

```text
历史长度分桶用了 2016-2026 全窗口数据
流动性过滤用了 2026 年末最近 20/60 日数据
```

这会让 2024 年的回测提前知道：

```text
某只股票后来是否继续存在到 2026
某只股票到 2026 年是否仍然有足够流动性
```

本次新增 `point_in_time_filters`：

```text
每个信号日重新统计 history_rows_asof
每个信号日重新计算 latest_close_asof
每个信号日重新计算 avg_dollar_volume_20d_asof
每个信号日重新计算 median_dollar_volume_60d_asof
每个信号日重新计算 zero_volume_ratio_60d_asof
每个信号日重新计算 recent_trading_days_60d_asof
```

只有通过当日历史长度和当日流动性筛选的股票，才进入当期 Top10。

## 本次仍未修正什么

当前 `nasdaq_public` 数据源仍然不是严格 PIT。

最大残余问题是：

```text
股票池仍按运行日 Nasdaq 市值前 500 构建
不是 2024 年每个信号日当时的 Nasdaq 前 500
不包含退市股票
证券主数据和行业分类仍来自当前 snapshot
```

所以这次只能叫做：

```text
PIT-filtered backtest
```

还不能叫：

```text
fully PIT-safe backtest
```

## 新旧结果对比

旧版回测：

```text
历史分桶：全窗口
流动性过滤：2026 年末
累计收益：2225.10%
年化收益：283.38%
最大回撤：-18.11%
平均换手：110.93%
```

PIT 过滤版：

```text
历史分桶：按信号日
流动性过滤：按信号日
累计收益：1097.92%
年化收益：188.81%
最大回撤：-21.63%
平均换手：97.33%
平均 PIT 过滤前候选数：476.14
平均 PIT 过滤后候选数：454.47
```

结果下降明显，说明之前确实存在未来信息抬高收益的问题。

但收益仍然很高，说明还必须继续处理股票池层面的未来信息。

## 当前配置

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d_pit_safe.yaml
```

运行命令：

```bash
export SEC_EDGAR_USER_AGENT="Your Name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10_5d_pit_safe.yaml
```

## 下一步

要真正杜绝未来函数，下一步必须升级股票池数据：

```text
历史市值
历史指数成分
退市股票
历史证券类型
历史行业分类
复权行情
```

当前最现实路线是接入 Norgate 或 CRSP 类数据源。继续看 [[Data Source Upgrade Plan]] 和 [[Norgate Data Integration]]。
