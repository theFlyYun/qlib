# Industry Neutralization

## 目标

解决 Nasdaq 股票池成分复杂、行业暴露过强的问题。

## 为什么要做

如果模型 TopK 全是某个行业，收益可能来自行业行情，而不是模型选股能力。

## 基本做法

```text
按行业分组
每个行业内排序
限制单行业权重
比较行业中性前后的 IC 和回测
```

当前阶段先完成的是模型输入层的行业相对特征，见 [[Industry Features And Relative Ranking]]。它解决“同行里谁更好”的问题。

组合层面已经开始做行业暴露对照，见 [[Industry Exposure Strategy Comparison]]。这一步不禁止买强势行业，而是把原始 TopK、行业约束 TopK 和行业增强 TopK 放在同一批模型分数下比较。

行业内部的选股能力复盘见 [[Within Sector Stock Selection Review]]。它回答的是：在同一个 sector 内，模型能不能把未来收益更好的股票排到前面。

## 当前 Nasdaq 问题

Nasdaq 总市值前 500 包含：

```text
普通股
ADR
优先股
REIT
生物科技
新上市股票
双重股权类别
```

阶段 D 需要先做股票池清洗，再做行业内排序。

## 遗留问题

- 行业分类数据源未确定。
- 双重股权类别如何处理未确定。
- ADR 是否保留需要实验设计。

## 下一阶段准备

阅读 [[Industry Features And Relative Ranking]]、[[Industry Exposure Strategy Comparison]]、[[Within Sector Stock Selection Review]] 和 [[Portfolio Risk Control]]，下一步把行业相对信号扩展到更稳定的行业权重规则。
