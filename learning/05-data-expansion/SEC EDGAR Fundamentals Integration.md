# SEC EDGAR Fundamentals Integration

## 本阶段目标

SEC EDGAR 这一步要把财报数据变成模型能使用的基本面特征。

源数据、CIK 映射和 PIT 技术流程图见 [[SEC EDGAR Technical Data Flow]]。

它不是替代 Alpha158，而是补上 Alpha158 看不到的维度：

```text
Alpha158：价格、成交量、趋势、波动、位置
SEC EDGAR：收入、利润、现金流、资产负债、估值、披露状态
```

第一版只使用结构化 XBRL 财报数据，不做 10-K / 10-Q 全文 NLP。

## SEC EDGAR 是什么

SEC EDGAR 是美国证券交易委员会的公司申报系统。上市公司会通过 EDGAR 披露：

```text
10-K：年度报告
10-Q：季度报告
8-K：重大事项公告
Form 4：内部人交易
DEF 14A：股东大会和薪酬代理材料
```

本阶段只处理：

```text
10-K
10-Q
10-K/A
10-Q/A
```

其中 `/A` 表示 amended filing，即修正版。

## 财报如何变成特征

模型不能直接读取一份财报 PDF 或 HTML。我们需要把结构化 XBRL 字段转成数字。

当前转换链路：

```text
SEC ticker -> CIK 映射
-> submissions 获取披露日期和 accession
-> companyfacts 获取 us-gaap XBRL 字段
-> 按 accession 拼成单次披露记录
-> 按 acceptanceDateTime / filed 生效
-> forward fill 到日频交易样本
-> 与 Alpha158 按 datetime + instrument 合并
```

最终进入 LightGBM 的不是“财报文件”，而是一组 `edgar_` 开头的数字特征。

## 第一版特征

### 基础财报字段

这些字段来自 XBRL companyfacts：

```text
revenue
gross_profit
operating_income
net_income
eps_diluted
assets
liabilities
equity
cash
operating_cash_flow
capex
shares_diluted
```

### 盈利能力

回答公司“赚不赚钱、赚得好不好”：

```text
gross_margin
operating_margin
net_margin
roe
roa
```

### 成长性

回答公司“比去年同期是否变好”：

```text
revenue_yoy_growth
net_income_yoy_growth
eps_yoy_growth
assets_yoy_growth
```

### 现金流质量

回答利润是不是有现金支撑：

```text
operating_cash_flow_ttm
free_cash_flow_ttm
cfo_to_net_income
fcf_margin
```

### 负债与稳健性

回答公司财务结构是否脆弱：

```text
liabilities_to_assets
cash_to_assets
```

### 估值

估值特征必须结合行情价格，因为估值是：

```text
市场价格 / 财报基本面
```

第一版估值特征：

```text
price_to_sales
price_to_book
price_to_earnings
market_cap_to_fcf
```

### 披露状态

回答“这份财报什么时候被市场看到”：

```text
days_since_last_10q
days_since_last_10k
filing_lag_days
is_recent_filing
is_amended_filing
```

## PIT 对齐为什么重要

财报有两个关键日期：

```text
period_end：财报覆盖的会计期末
filed / acceptanceDateTime：市场真正能看到这份财报的时间
```

不能用 `period_end` 作为特征生效日期。

例子：

```text
2024-03-31：Q1 财报期末
2024-04-25：10-Q 披露
```

模型在 2024-04-10 不能看到这份财报。只有 2024-04-25 之后，相关字段才能进入样本。

这就是 PIT：point in time。

## 当前工程输出

新增配置：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_1d.yaml
```

运行入口：

```bash
export SEC_EDGAR_USER_AGENT="your-name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_1d.yaml
```

输出文件：

```text
fundamental_features.parquet
fundamental_failures.csv
edgar_cik_map.csv
predictions.csv
report.md
resolved_config.yaml
```

其中：

```text
fundamental_features.parquet：日频 PIT 财报和估值特征
fundamental_failures.csv：CIK 缺失、字段缺失、价格缺失、财报不足等问题
edgar_cik_map.csv：ticker 到 CIK 的映射
```

## 当前限制

第一版有几个必须记住的限制：

```text
没有处理 8-K、Form 4、DEF 14A
没有做 10-K / 10-Q 文本 NLP
SEC XBRL tag 存在公司差异
季度数据和 TTM 口径是学习用近似，后续需要更严谨处理累计值和重述
当前 Nasdaq public 价格数据本身仍有复权、退市和动态成分限制
```

因此，本阶段的目标不是“直接得到更好的投资模型”，而是先建立：

```text
价格成交量 baseline
-> 加入 PIT 财报估值特征
-> 对比 IC / Rank IC / TopK
-> 判断基本面信息是否提供增量
```

## 官方资料

- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)

## 下一步

完成 EDGAR 第一版后，后续可以继续分三步：

```text
1. 真实跑 5 只股票 smoke test，检查字段覆盖率。
2. 扩展到当前 Nasdaq 股票池，对比 Alpha158 baseline。
3. 再接行业分类，把财报特征改为行业内可比，详见 [[Industry Features And Relative Ranking]]。
```

相关笔记：

[[Alpha158 And Features]]
[[Norgate Data Integration]]
[[SEC EDGAR Technical Data Flow]]
[[Industry Features And Relative Ranking]]
[[Data Source Upgrade Plan]]
[[Financial Valuation Industry Macro News]]
