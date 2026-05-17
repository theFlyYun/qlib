# Norgate Data Integration

## 本阶段目标

Norgate 这一步不是为了替代 Alpha158，也不是立刻加入财报因子。

它的定位是：

```text
用更可靠的历史行情和股票池
生成更可信的 Alpha158 底层输入
```

当前 Nasdaq public 数据只能作为学习样例。Norgate 的价值在于：它能让我们更接近真实历史研究所需要的价格口径、退市股票和历史指数成分。

## Norgate 在模型中的位置

模型链路是：

```text
Norgate 历史行情
-> 历史 S&P 500 成分过滤
-> Qlib source CSV
-> Qlib bin 数据
-> Alpha158 技术面特征
-> LightGBM 预测未来收益
-> IC / Rank IC / TopK 回测
```

所以 Norgate 提供的是更好的“地基”：

```text
open
high
low
close
volume
vwap 近似
历史可交易日期
```

Alpha158 仍然负责把这些 OHLCV 字段派生成模型输入。

## 什么是复权

股票历史价格会被公司行为打断，例如：

```text
拆股
合股
现金分红
特别分红
配股
并购或其他资本事件
```

如果不复权，历史价格会出现机械断层。

例如一只股票 1 拆 2：

```text
拆股前价格：100
拆股后价格：50
```

如果模型直接看到 `100 -> 50`，会误以为股票暴跌 50%。实际上股东持有的股数翻倍，总资产没有这样下跌。

复权的目标是让历史价格序列更适合计算收益和特征。

常见口径：

```text
未复权：保留交易所原始成交价格。
拆股复权：处理拆股、合股等资本结构变化。
总回报复权：同时考虑分红再投资，更接近持有者总收益。
```

本项目 Norgate 默认使用：

```text
StockPriceAdjustmentType.TOTALRETURN
```

这意味着标签 `未来收益` 和 Alpha158 的趋势、波动、均线等特征，都基于总回报调整后的价格序列。

## 什么是退市股票

退市股票是历史上曾经上市交易、后来不再交易的证券。

它们可能因为：

```text
破产
被并购
长期低价
私有化
不满足交易所要求
```

如果只用今天仍然活着的股票回测过去，就会发生幸存者偏差。

直觉上说：

```text
只看活下来的公司
等于提前排除了很多失败样本
```

这样训练出来的模型和回测结果会过于乐观。

Norgate 的 `US Equities Delisted` 可以帮助我们把退市股票放回历史样本里，但官方也明确说明，退市数据需要 Platinum 或 Diamond 级别的美股订阅。

## 什么是历史指数成分

历史指数成分回答的问题是：

```text
某只股票在某一天，是否属于某个指数？
```

这和“今天的 S&P 500 成分”不是一回事。

错误做法：

```text
拿今天的 S&P 500 股票
回测 2000 年以来的策略
```

问题是：今天的成分股本身就是历史竞争后的结果。很多过去属于指数、后来表现差、退市或被替换的公司，会被这种做法漏掉。

本项目 Norgate 默认股票池：

```text
候选证券：US Equities + US Equities Delisted
历史成分：S&P 500 / $SPX
```

适配器会对每只候选股票查询每日是否为 S&P 500 成分，只保留 `is_member == 1` 的交易日进入 Qlib。

## 当前已经完成什么

本阶段已经完成 Mac 可测试工程接口：

```text
新增 data.source: norgate
新增 Norgate S&P 500 配置文件
新增 Norgate 数据源适配器
新增 fixture 单元测试
保留 nasdaq_public 原行为
输出 membership.csv 记录历史成分日级标记
```

新增配置：

```text
analysis/nasdaq_top500_score/configs/norgate_sp500_alpha158_lgbm_1d.yaml
```

运行入口：

```bash
.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/norgate_sp500_alpha158_lgbm_1d.yaml
```

在当前 Mac 环境下，这个命令会给出可读错误，因为真实 Norgate Python API 依赖：

```text
Microsoft Windows
Norgate Data Updater 正在运行
有效 Norgate 订阅
pip install norgatedata
```

这不是失败，而是本阶段刻意设计的边界：先把接口和测试做好，真实数据验证留到 Windows + Norgate 环境。

## 输出文件

真实 Norgate 环境跑通后，实验目录会生成：

```text
runs/norgate_sp500_alpha158_lgbm_1d/universe.csv
runs/norgate_sp500_alpha158_lgbm_1d/membership.csv
runs/norgate_sp500_alpha158_lgbm_1d/download_failures.csv
runs/norgate_sp500_alpha158_lgbm_1d/qlib_source_csv/
runs/norgate_sp500_alpha158_lgbm_1d/qlib_data/
runs/norgate_sp500_alpha158_lgbm_1d/predictions.csv
runs/norgate_sp500_alpha158_lgbm_1d/report.md
runs/norgate_sp500_alpha158_lgbm_1d/resolved_config.yaml
```

其中最重要的是：

```text
resolved_config.yaml：复盘本次实验到底用了什么配置
membership.csv：复盘每只股票哪些日期属于 S&P 500
download_failures.csv：复盘哪些股票因为无价格、无成分记录、历史太短或 API 问题被跳过
```

## 数据验收重点

Windows 环境真实运行后，必须检查：

```text
是否同时包含 US Equities 和 US Equities Delisted
是否只保留历史上真实属于 S&P 500 的日期
价格是否使用 TOTALRETURN 口径
padding 是否为 NONE
退市股票是否能生成最后交易日前的历史样本
失败股票是否有明确原因
Qlib source CSV 是否只有 date,symbol,open,high,low,close,vwap,volume
```

## Norgate 的限制

Norgate 很适合作为个人学习和较严谨美股日频研究的数据源，但它不是“无限制免费数据库”。

限制包括：

```text
Python API 依赖 Windows 和 Norgate Data Updater
历史指数成分需要 Platinum 或更高级别订阅
退市股票同样依赖订阅级别
current fundamentals 不是完整 PIT 历史财报
不能直接替代 SEC EDGAR / Compustat 这类财报数据源
```

所以本项目第一步只使用 Norgate 做：

```text
价格行情
复权口径
退市股票
历史指数成分
```

财报和公告事件下一步走 SEC EDGAR。

## 官方资料

- [Norgate Data Python package](https://pypi.org/project/norgatedata/)
- [Norgate Data content tables](https://norgatedata.com/data-content-tables.php)
- [Norgate Data accessibility](https://norgatedata.com/accessibility.php)
- [Norgate Data package FAQ](https://norgatedata.com/data-package-faq.php)

## 下一步

Norgate 之后建议接入 [[Financial Valuation Industry Macro News]] 中的第一类基本面来源：SEC EDGAR。

下一阶段的目标不是马上堆很多财报字段，而是先解决：

```text
10-K / 10-Q 什么时候披露
模型在某个交易日能看到哪些财报
如何把财报字段按披露日对齐到日频样本
如何避免未来函数和重述污染
```

相关笔记：

[[Data Source Upgrade Plan]]
[[Data Scope And Sources]]
[[Alpha158 And Features]]
[[Labels And Future Returns]]
