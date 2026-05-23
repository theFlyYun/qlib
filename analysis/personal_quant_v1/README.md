# Personal Quant v1

This directory is the clean starting point for the small, interpretable personal trading research system.

It intentionally does not reuse the large `nasdaq_top500_score` experiment pipeline as the default architecture.

## Goal

Build a small-capital-friendly research loop:

```text
CRSP data -> 10-30 interpretable factors -> factor scoring -> Top 5-10 holdings -> reviewable backtest
```

## Boundaries

- No Alpha158 as the default feature set.
- No high-dimensional macro interaction stack.
- No broad EDGAR field expansion.
- No Top30 / Top50 portfolio as the main live-trading shape.
- Prefer explainable scoring before black-box models.

## Planned Structure

```text
data/       data access and cached research inputs
features/   small interpretable factors
scoring/    factor scoring and weighting
portfolio/  Top 5-10 construction and risk rules
reports/    holding explanations and review outputs
configs/    compact strategy configs
```

Implementation starts after the Personal Quant v1 direction document is reviewed:

```text
learning/07-personal-quant/Personal Quant V1 Direction.md
```
