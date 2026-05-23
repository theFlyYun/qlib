# CRSP EDGAR Fundamentals Integration

## 本阶段目标

在 CRSP 2010-2025 主线中加入 SEC EDGAR 公司财报特征，验证基本面数据相对 Alpha158-only baseline 是否有增量。

本阶段回答两个问题：

```text
当前 CRSP 主线是不是只使用 Alpha158？
EDGAR 财报特征能不能作为模型输入，并改善 IC / Rank IC / TopK 回测？
```

结论先说清楚：

```text
加入前：CRSP 2010 conservative baseline 只使用 Alpha158 价格成交量特征。
加入后：EDGAR 已真实进入模型，生成 2,820,566 行 x 29 列日频 PIT 财报特征。
第一版结果：直接拼接 EDGAR 后，IC、Rank IC 和 TopK 回测均弱于 Alpha158-only。
```

这说明财报数据链路已经打通，但第一版“直接把财报特征拼到模型里”不是好的默认策略。

## 之前已经做过什么

项目里早已有 Nasdaq 版本的 EDGAR 接入：

```text
SEC ticker -> CIK
submissions -> 10-K / 10-Q 披露记录
companyfacts -> XBRL 财报字段
按披露日/接收时间生效
顺延到下一个交易日
forward fill 到日频样本
与 Alpha158 合并
```

旧版本适合 Nasdaq ticker，例如 `AAPL`、`MSFT`。

CRSP 主线不同。CRSP 的 Qlib instrument 是：

```text
P{PERMNO}
```

例如：

```text
P10104
P18572
P19455
```

SEC 不认识 `P10104`。所以 CRSP 接 EDGAR 的关键不是重新写 EDGAR 抓取，而是补上：

```text
PERMNO instrument -> ticker_asof -> CIK
```

## 本次工程改动

### 1. CRSP instrument 到 CIK 映射

新增 CRSP-aware 映射规则：

```text
如果 symbol 是 P{PERMNO}：
  不用 P{PERMNO} 直接查 SEC
  优先用 universe 中的 ticker_asof / trading_symbol_asof / TradingSymbol / Ticker 查 SEC ticker map
如果 universe 已经有 cik：
  直接使用 cik
```

映射输出：

```text
edgar_cik_map.csv
```

本次真实运行：

```text
CIK 映射数量：855
映射方法：全部为 ticker_asof
```

### 2. 估值因子使用 CRSP 原始收盘价

Alpha158 使用的是研究价格，已经按 CRSP `DlyRetx` 做过 return-adjusted 处理，适合计算动量、均线、波动率。

但 EDGAR 估值因子不应该直接用这个研究价格。估值回答的是：

```text
当前市场价格 / 财报基本面
```

所以 CRSP + EDGAR 默认使用：

```text
valuation_price_source: crsp_raw_close
```

也就是用 CRSP `DlyClose` 计算：

```text
market_cap = raw_close * shares_diluted
price_to_sales = market_cap / revenue_ttm
price_to_book = market_cap / equity
price_to_earnings = market_cap / net_income_ttm
market_cap_to_fcf = market_cap / free_cash_flow_ttm
```

这能避免把研究用复权价格误用到估值口径里。

### 3. PIT 生效规则保持不变

财报不能按财报期末日生效。

例如：

```text
2024-03-31：财报 period_end
2024-04-25：公司提交 10-Q
2024-04-26：下一个交易日才允许模型看到
```

当前规则：

```text
用 filed / acceptanceDateTime 判断披露可见时间
再顺延到下一个交易日
然后 forward fill 到后续交易日
```

这一步是为了避免未来函数。

## 第一版特征

EDGAR 进入模型的列名以 `edgar_` 开头。

主要包括：

```text
收入、资产、股东权益、现金、稀释股数
毛利率、营业利润率、净利率
ROE、ROA
收入同比、净利润同比、EPS 同比、资产同比
经营现金流 / 净利润
自由现金流率
负债 / 资产
现金 / 资产
距离最近 10-Q / 10-K 的天数
是否最近披露
是否修正版财报
市销率、市净率、市盈率、市值 / 自由现金流
```

本次输出：

```text
fundamental_features.parquet：2,820,566 行 x 29 列
覆盖 instruments：816
edgar_cik_map.csv：855 条映射
fundamental_failures.csv：918 条失败或跳过记录
```

失败原因：

```text
missing_fields：573
missing_cik：306
no_effective_filing_dates：28
insufficient_filings：11
```

这些失败大多不是单纯 bug，而是财报数据常见问题：

```text
老股票或退市股票找不到稳定 ticker -> CIK 映射
不同行业使用不同 XBRL tag
银行、保险、生物医药、壳公司、ADR 的财报结构差异很大
部分公司披露历史不足
```

## 实验配置

运行配置：

```text
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_10d_conservative_2010_2025.yaml
```

运行命令：

```bash
export SEC_EDGAR_USER_AGENT="your-name your-email@example.com"

.venv/bin/python -u analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py \
  --config analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_10d_conservative_2010_2025.yaml
```

数据口径：

```text
CRSP monthly dynamic US Common Equity Top500
2010-01-01 到 2025-12-31
Train: 2010-2021
Valid: 2022-2023
Test: 2024-2025
标签：未来 10 个交易日总收益
调仓：每 10 个交易日
入场：信号日后 1 个交易日 open
主成本：0 bps
模型：Conservative LightGBM
```

## 结果对比

### Alpha158-only baseline

```text
Test 日均 IC：0.015469
Test 日均 Rank IC：-0.009241
best_iteration：14
累计收益：85.86%
年化收益：36.67%
最大回撤：-17.12%
年化 Alpha：5.10%
Beta：1.491
```

### Alpha158 + EDGAR

```text
Test 日均 IC：-0.004242
Test 日均 Rank IC：-0.009994
best_iteration：8
累计收益：37.55%
年化收益：17.43%
最大回撤：-19.82%
年化 Alpha：-13.06%
Beta：1.652
```

行业约束 `sector_cap_2_top10` 在 EDGAR 版本中也没有改善主结论：

```text
累计收益：30.80%
年化收益：14.49%
最大回撤：-22.95%
年化 Alpha：-17.05%
```

## 如何理解结果变差

这不是“EDGAR 没用”的最终结论，而是说明第一版使用方式太粗。

可能原因：

```text
1. 财报字段缺失不是随机的
   缺字段常集中在特定行业、老公司、退市公司或特殊财报结构公司。

2. 绝对财报指标跨行业不可比
   银行、软件、制造、医药的资产、负债、现金流和利润率结构完全不同。

3. 估值特征容易被极端值污染
   亏损公司会让 P/E 失真，自由现金流为负会让 market_cap_to_fcf 很难解释。

4. EDGAR 覆盖从 2010 后才更稳定
   训练期早段可能有更多缺失和 tag 不一致问题。

5. LightGBM 更早停止
   加入 EDGAR 后 best_iteration 从 14 降到 8，说明验证集上新增特征没有带来稳定改善。

6. 直接拼接不是行业内比较
   旧 Nasdaq 路径里 EDGAR 更有效的一步，是叠加行业内相对因子，而不是直接全市场比较。
```

## 当前判断

当前默认主线不应该直接切换到 Alpha158 + EDGAR。

更稳的结论是：

```text
Alpha158-only conservative baseline 仍是当前 CRSP 主 baseline。
EDGAR 数据链路已跑通，但需要改成覆盖率审计 + 行业内相对财报/估值特征后再进入默认模型。
```

## 下一步怎么做

建议按这个顺序继续：

```text
1. 生成 EDGAR 覆盖率报告
   按年份、SIC2 sector、SIC4 industry、history bucket 看覆盖率和缺失原因。

2. 做 EDGAR 特征清洗
   对 P/E、market_cap_to_fcf、负值分母、极端值 winsorize / clip。

3. 做行业内财报/估值相对特征
   例如行业内 price_to_sales percentile、ROE percentile、gross_margin percentile。

4. 做 EDGAR ablation
   分别测试 profitability、growth、quality、leverage、valuation、filing state。

5. 再决定是否进入默认模型
   不能只看一次 TopK 收益，要同时看 IC、Rank IC、alpha、回撤和覆盖稳定性。
```

## 本阶段产物

```text
analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_10d_conservative_2010_2025.yaml
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_10d_conservative_2010_2025/fundamental_features.parquet
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_10d_conservative_2010_2025/fundamental_failures.csv
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_10d_conservative_2010_2025/edgar_cik_map.csv
analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_10d_conservative_2010_2025/report.md
```

相关笔记：

[[SEC EDGAR Fundamentals Integration]]
[[SEC EDGAR Technical Data Flow]]
[[CRSP Industry Mapping Repair]]
[[CRSP Industry Constraint And Relative Feature Recovery]]
[[Qlib Learning Log]]
[[Stage Completion Records]]
