# Stock Pool Cleaning And History Buckets

## 学习目标

理解为什么模型分数出来之后，不能马上把全市场前 10 名当成候选组合。

当前 Nasdaq public 股票池里混有普通股、ADR、warrant、preferred、unit、right、notes 等证券。它们的交易属性、风险、流动性和财务字段口径不一样。如果不清洗，模型 TopN 可能被特殊证券挤占。

## 股票池清洗

第一版清洗只使用当前可获得的 `symbol` 和 `name` 文本规则，不接商业证券主数据。

默认排除：

```text
Warrant
Right
Unit
Preferred
Depositary Shares
Notes
Bond
Debenture
```

默认保留：

```text
Common Stock
Ordinary Shares
Class A / B / C Common Stock
American Depositary Shares
```

注意：`American Depositary Shares` 暂时保留，因为它仍是权益证券；但后续可以单独观察 ADR/ADS 是否需要分组或剔除。

## 历史长度分桶

固定研究窗口是：

```text
2016-05-17 到 2026-05-17
```

但不是每只股票都有完整 10 年数据。历史长度分桶就是把股票按实际可用日线数量分组：

```text
full_10y：history_rows >= 2400
5_10y：1260 <= history_rows < 2400
2_5y：504 <= history_rows < 1260
lt_2y：180 <= history_rows < 504
```

这不是为了改变模型训练目标，而是为了控制最终候选组合的样本结构。

## 桶内 Top10 名额

模型仍然输出统一的 Qlib `score`。不同历史长度桶不会训练不同模型。

最终 Top10 采用桶内排名和固定名额：

```text
full_10y：4
5_10y：3
2_5y：2
lt_2y：1
```

这样做的含义：

```text
完整历史股票仍然占主要名额
5-10 年股票有一定空间
2-5 年股票少量进入
少于 2 年股票最多 1 只，用于观察新股/新证券
```

如果某个桶不够名额，空位优先回补给更长历史的桶。

## 行业名额约束

桶内名额解决的是“历史长度结构”，但不能防止最终名单集中在单一行业。

本次在桶内 Top10 之后继续加一层行业约束：

```text
单一 sector 最多 4 只
单一 industry 最多 2 只
```

这一步不改变模型输入、标签或 `score`。它只改变最终候选组合的选股规则：

```text
先按统一 score 在桶内排序
再按 4/3/2/1 桶名额依次选择
如果候选股票会突破 sector / industry 上限，就跳过它
空余名额继续从后续候选里补足
```

所以行业约束不是“重新训练模型”，而是“把模型榜单变成更分散的候选组合”。

## 本次实验结果

运行配置：

```text
analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_clean_bucket_top10.yaml
```

本次股票池清洗剔除：

```text
总剔除：439
name:warrant：228
name:preferred：101
symbol:.*W$：45
name:notes：34
name:unit：13
name:right：5
name:depositary_shares：5
symbol:.*WT$：3
symbol:.*WS$：3
name:debenture：1
name:bond：1
```

流动性过滤后，最新日可预测股票分桶：

```text
full_10y：335
5_10y：86
2_5y：45
lt_2y：12
```

最终 Top10 分桶结果：

```text
full_10y：4
5_10y：3
2_5y：2
lt_2y：1
```

本次 Top10：

```text
AXTI
AAOI
CHTR
LBRDK
FLY
NBIS
HUT
GTX
XMTR
RKLB
```

最终 Top10 sector 分布：

```text
Technology：3
Telecommunications：2
Industrials：2
Finance：1
Consumer Discretionary：1
Real Estate：1
```

最终 Top10 industry 分布：

```text
Semiconductors：2
Cable & Other Pay Television Services：2
Military/Government/Technical：2
Computer Software: Programming Data Processing：1
Finance: Consumer Services：1
Auto Parts:O.E.M.：1
Real Estate：1
```

## 如何解读

桶内排名不是改变分数，而是改变候选组合的名额结构。

比如 `FLY` 属于 `lt_2y` 桶，它能进入最终 Top10，不是因为它和完整 10 年股票直接争到前 10，而是因为少于 2 年桶被允许保留 1 个观察名额。

这让最终列表更像一个受控研究样本，而不是无约束模型榜单。

行业名额约束进一步控制了行业集中度。上一版 Top10 里 Technology 曾经有 6 只；加入约束和流动性过滤后，Technology 为 3 只，Semiconductors 为 2 只。

## 遗留问题

第一版清洗是文本规则，不能替代专业证券主数据。

后续还需要继续处理：

```text
ADR/ADS 是否单独分组
更细的流动性分层
更可靠的证券主数据
未来 5 日标签
成本后回测
```

相关笔记：

[[Short History Evaluation And EDGAR Full Run]]
[[SEC EDGAR Fundamentals Integration]]
[[Liquidity Filtering]]
[[Industry Features And Relative Ranking]]
[[TopK Strategy]]
[[Stage Completion Records]]
