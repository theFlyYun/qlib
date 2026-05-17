# Short History Evaluation And EDGAR Full Run

## 学习目标

理解一个现实问题：固定 10 年研究窗口里，有些股票并没有完整 10 年历史，它们还能不能进入模型评估。

本阶段结论是：可以进入，但必须遵守真实存在原则。股票不存在的早期日期不能被补出来，也不能让它贡献训练样本；只有当它真实上市、有行情、有可计算特征和未来收益标签时，才进入对应日期的横截面。

## 为什么不直接剔除

如果要求每只股票都满足完整 10 年历史，模型会更干净，但会排除大量新上市或重组后的公司。这样会形成另一种偏差：测试期真实可以买到的股票，在研究里却被消失了。

如果完全不设门槛，又会引入极短历史、流动性不足、特殊证券和字段质量很差的样本。

当前折中方案：

```text
全局时间窗口固定：2016-05-17 到 2026-05-17
完整历史 baseline：min_history_rows = 2400
扩大评估覆盖：min_history_rows = 180
```

也就是说，窗口是固定的，但单只股票只在自己真实存在的数据区间里参与。

## 它如何进入模型

以一只 2022 年才有足够数据的股票为例：

```text
2016-2021：没有数据，不参与训练
2022-2023：如果有数据，可参与验证
2024-2026：如果有数据，可参与测试和最新日预测
```

这不会制造未来函数，因为模型没有看到不存在的历史。真正的风险是：短历史股票的特征稳定性和完整 10 年股票不同，所以后续必须按历史长度分桶复盘。

建议分桶：

```text
完整 10 年
5-10 年
2-5 年
少于 2 年
```

每个桶分别看覆盖数量、IC、Rank IC、TopK 行业集中度和特殊证券比例。

## 本次真实 EDGAR 获取

运行配置：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_eval_all.yaml
```

数据来源：

```text
Nasdaq public：当前 Nasdaq 市值前 500 的日线 OHLCV
SEC EDGAR：company_tickers_exchange、submissions、companyfacts
财报表单：10-K、10-Q、10-K/A、10-Q/A
```

生成结果：

```text
股票池：500
进入 Qlib source CSV：481
下载失败或历史不足：19
EDGAR CIK 映射：499
EDGAR PIT 特征矩阵：895,760 行 x 29 列
EDGAR 覆盖股票：420
最新日可预测股票：480
```

模型结果：

```text
Test 日均 IC：0.011370
Test 日均 Rank IC：0.003418
参与 IC 计算交易日：593
```

这说明真实 EDGAR 数据已经能进入模型，但目前还不能说明策略有效。它只是说明“数据链路跑通了，并且财报特征已经成为模型输入”。

## 失败和缺失怎么理解

EDGAR 失败或跳过数量是 340，其中主要原因是：

```text
missing_fields：260
insufficient_filings：74
missing_price：3
api_or_parse_error：2
missing_cik：1
```

`missing_fields` 很常见，因为不同公司会使用不同 XBRL tag，银行、保险、生物科技、ADR、特殊证券的财务报表结构也不同。

这不是简单的 bug，而是基本面数据工程的常态：字段口径、行业差异、公司自定义 tag、重述和缺失都会影响特征质量。

## 本次暴露的问题

Top5 中出现了 `NVAWW` 这类 warrant，说明当前 Nasdaq public 股票池清洗还不够。`exclude_etf` 和 `exclude_test_issue` 只能过滤一部分非普通股，不能保证剩下都是普通股。

因此下一步不能急着解读 Top5，而应该先清洗股票池：

```text
过滤 warrant
过滤 preferred
过滤 rights
过滤 units
过滤极低流动性
记录每只股票历史长度
```

## 下一步

下一阶段建议做“股票池清洗与历史长度分桶”。

目标不是提高模型分数，而是让评估对象更清楚：哪些是完整历史普通股，哪些是短历史普通股，哪些是特殊证券或数据质量不足样本。

相关笔记：

[[Data Scope And Sources]]
[[SEC EDGAR Fundamentals Integration]]
[[Industry Features And Relative Ranking]]
[[Qlib Learning Log]]
[[Stage Completion Records]]
