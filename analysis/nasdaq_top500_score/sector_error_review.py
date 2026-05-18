"""Sector-specific error review for model scores."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

try:
    from .backtest import (
        apply_point_in_time_filters,
        build_position_returns,
        enrich_predictions,
        load_market_data,
        price_matrix_from_market_data,
        read_calendar,
        read_history_buckets,
    )
except ImportError:  # pragma: no cover - supports running the pipeline as a script.
    from backtest import (
        apply_point_in_time_filters,
        build_position_returns,
        enrich_predictions,
        load_market_data,
        price_matrix_from_market_data,
        read_calendar,
        read_history_buckets,
    )


@dataclass
class SectorErrorReviewResult:
    summary: pd.DataFrame
    examples: pd.DataFrame
    feature_differences: pd.DataFrame
    yaml_summary: dict[str, Any]


CATEGORY_NAMES = [
    "high_score_winners",
    "high_score_losers",
    "low_score_winners",
    "low_score_losers",
]
DEFAULT_TARGET_SECTORS = ["Technology", "Health Care", "Consumer Discretionary"]
DEFAULT_FEATURE_COLUMNS = [
    "score",
    "future_return",
    "market_cap_asof_estimate",
    "is_adr_ads",
    "history_rows_asof",
    "latest_close_asof",
    "avg_dollar_volume_20d_asof",
    "median_dollar_volume_60d_asof",
    "momentum_20d",
    "momentum_60d",
    "momentum_120d",
    "volatility_20d",
    "volatility_60d",
    "edgar_price_to_sales",
    "edgar_price_to_book",
    "edgar_price_to_earnings",
    "edgar_gross_margin",
    "edgar_net_margin",
    "edgar_roe",
    "edgar_revenue_yoy_growth",
    "edgar_liabilities_to_assets",
    "edgar_cash_to_assets",
    "edgar_days_since_last_10q",
    "edgar_is_recent_filing",
]


def run_sector_error_review(
    predictions: pd.DataFrame,
    universe: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
) -> SectorErrorReviewResult:
    review_config = config.get("sector_error_review", {})
    if not review_config.get("enabled", False):
        result = SectorErrorReviewResult(
            summary=pd.DataFrame(),
            examples=pd.DataFrame(),
            feature_differences=pd.DataFrame(),
            yaml_summary={"enabled": False},
        )
        write_sector_error_outputs(result, paths)
        return result

    target_sectors = [str(sector).strip() for sector in review_config.get("target_sectors", DEFAULT_TARGET_SECTORS)]
    target_sectors = [sector for sector in target_sectors if sector]
    quantiles = int(review_config.get("quantiles", 5))
    min_group_size = int(review_config.get("min_group_size", 10))
    min_summary_periods = int(review_config.get("min_summary_periods", 20))
    feature_columns = list(review_config.get("feature_columns", DEFAULT_FEATURE_COLUMNS))

    price_column = str(config.get("backtest", {}).get("price", "close"))
    market_data = load_market_data(paths["source_dir"], price_column)
    close = price_matrix_from_market_data(market_data)
    history = read_history_buckets(paths["history_buckets_csv"])
    enriched = enrich_predictions(predictions, universe, history)
    calendar = read_calendar(paths["qlib_dir"])
    calendar_index = {date: index for index, date in enumerate(calendar)}
    backtest_config = config.get("backtest", {})
    rebalance_days = int(backtest_config.get("rebalance_days", 5))
    holding_days = int(backtest_config.get("holding_days", 5))
    entry_lag_days = int(backtest_config.get("entry_lag_days", 1))

    observation_rows: list[dict[str, Any]] = []
    daily_metric_rows: list[dict[str, Any]] = []
    signal_dates = sorted(pd.to_datetime(enriched["datetime"]).dt.normalize().dropna().unique())
    for signal_date in signal_dates[::rebalance_days]:
        signal_ts = pd.Timestamp(signal_date).normalize()
        if signal_ts not in calendar_index:
            continue
        signal_index = calendar_index[signal_ts]
        entry_index = signal_index + entry_lag_days
        exit_index = entry_index + holding_days
        if entry_index >= len(calendar) or exit_index >= len(calendar):
            continue

        entry_date = calendar[entry_index]
        exit_date = calendar[exit_index]
        day = enriched[enriched["datetime"] == signal_ts].copy()
        day = day.sort_values("score", ascending=False).reset_index(drop=True)
        day, _ = apply_point_in_time_filters(day, signal_ts, config, market_data)
        day["sector"] = normalized_text_series(day.get("sector", pd.Series(dtype=object)))
        day = day[day["sector"].isin(target_sectors)].copy()
        if day.empty:
            continue

        tradable = pd.DataFrame(build_position_returns(day, close, entry_date, exit_date))
        if tradable.empty:
            continue
        tradable["sector"] = normalized_text_series(tradable["sector"])
        for sector, group in tradable.groupby("sector", dropna=False):
            if sector not in target_sectors:
                continue
            group = group.dropna(subset=["score", "gross_return"]).copy()
            if group.empty:
                continue
            classified = classify_sector_period(group, sector, signal_ts, entry_date, exit_date, quantiles, min_group_size)
            observation_rows.extend(add_market_features(classified, market_data, signal_ts).to_dict("records"))
            daily_metric_rows.append(build_daily_metric(classified, sector, signal_ts, quantiles, min_group_size))

    observations = pd.DataFrame(observation_rows)
    observations = attach_fundamental_features(observations, paths)
    examples = observations[observations.get("error_category", "") != ""].copy() if not observations.empty else pd.DataFrame()
    if not examples.empty:
        examples = add_error_flags(examples, observations)
    daily_metrics = pd.DataFrame(daily_metric_rows)
    summary = summarize_sector_errors(observations, examples, daily_metrics, target_sectors, min_summary_periods)
    feature_differences = build_feature_differences(examples, feature_columns)
    yaml_summary = build_yaml_summary(summary, feature_differences, review_config, target_sectors)
    result = SectorErrorReviewResult(
        summary=summary,
        examples=examples,
        feature_differences=feature_differences,
        yaml_summary=yaml_summary,
    )
    write_sector_error_outputs(result, paths)
    return result


def classify_sector_period(
    group: pd.DataFrame,
    sector: str,
    signal_ts: pd.Timestamp,
    entry_date: pd.Timestamp,
    exit_date: pd.Timestamp,
    quantiles: int,
    min_group_size: int,
) -> pd.DataFrame:
    working = group.copy()
    working["signal_date"] = signal_ts.date().isoformat()
    working["entry_date"] = entry_date.date().isoformat()
    working["exit_date"] = exit_date.date().isoformat()
    working["sector"] = sector
    working["future_return"] = pd.to_numeric(working["gross_return"], errors="coerce")
    working["sector_candidate_count"] = int(len(working))
    working["score_rank_in_sector"] = working["score"].rank(method="first", ascending=False).astype(int)
    working["future_return_rank_in_sector"] = working["future_return"].rank(method="first", ascending=False).astype(int)
    denominator = max(1, len(working) - 1)
    working["score_rank_pct"] = (working["score_rank_in_sector"] - 1) / denominator
    working["future_return_rank_pct"] = (working["future_return_rank_in_sector"] - 1) / denominator
    working["error_category"] = ""
    working["skip_reason"] = ""
    if len(working) < min_group_size:
        working["skip_reason"] = f"tradable_count < {min_group_size}"
        return working

    bucket_size = max(1, len(working) // quantiles)
    top_score = set(working.nsmallest(bucket_size, "score_rank_in_sector")["symbol"])
    bottom_score = set(working.nlargest(bucket_size, "score_rank_in_sector")["symbol"])
    top_return = set(working.nsmallest(bucket_size, "future_return_rank_in_sector")["symbol"])
    bottom_return = set(working.nlargest(bucket_size, "future_return_rank_in_sector")["symbol"])
    categories = {
        "high_score_winners": top_score & top_return,
        "high_score_losers": top_score & bottom_return,
        "low_score_winners": bottom_score & top_return,
        "low_score_losers": bottom_score & bottom_return,
    }
    for category, symbols in categories.items():
        if symbols:
            working.loc[working["symbol"].isin(symbols), "error_category"] = category
    return working


def build_daily_metric(
    group: pd.DataFrame,
    sector: str,
    signal_ts: pd.Timestamp,
    quantiles: int,
    min_group_size: int,
) -> dict[str, Any]:
    tradable_count = int(len(group))
    rank_ic = correlation_or_nan(group["score"], group["future_return"], method="spearman")
    ic = correlation_or_nan(group["score"], group["future_return"], method="pearson")
    top_bottom_spread = math.nan
    if tradable_count >= min_group_size:
        bucket_size = max(1, tradable_count // quantiles)
        ordered = group.sort_values("score", ascending=False)
        top_bottom_spread = float(ordered.head(bucket_size)["future_return"].mean() - ordered.tail(bucket_size)["future_return"].mean())
    return {
        "signal_date": signal_ts.date().isoformat(),
        "sector": sector,
        "tradable_count": tradable_count,
        "ic": ic,
        "rank_ic": rank_ic,
        "top_bottom_spread": top_bottom_spread,
    }


def add_market_features(frame: pd.DataFrame, market_data: dict[str, pd.DataFrame], signal_ts: pd.Timestamp) -> pd.DataFrame:
    if frame.empty:
        return frame
    rows = []
    for row in frame.to_dict("records"):
        rows.append({**row, **recent_market_features(str(row["symbol"]).upper(), market_data, signal_ts)})
    return pd.DataFrame(rows)


def recent_market_features(symbol: str, market_data: dict[str, pd.DataFrame], signal_ts: pd.Timestamp) -> dict[str, Any]:
    frame = market_data.get(symbol)
    if frame is None or frame.empty:
        return {
            "momentum_20d": math.nan,
            "momentum_60d": math.nan,
            "momentum_120d": math.nan,
            "volatility_20d": math.nan,
            "volatility_60d": math.nan,
        }
    usable = frame[frame.index <= signal_ts].dropna(subset=["execution_price"])
    returns = usable["execution_price"].pct_change()
    return {
        "momentum_20d": lookback_return(usable["execution_price"], 20),
        "momentum_60d": lookback_return(usable["execution_price"], 60),
        "momentum_120d": lookback_return(usable["execution_price"], 120),
        "volatility_20d": annualized_volatility(returns.tail(20)),
        "volatility_60d": annualized_volatility(returns.tail(60)),
    }


def lookback_return(series: pd.Series, days: int) -> float:
    if len(series) <= days:
        return math.nan
    start = series.iloc[-days - 1]
    end = series.iloc[-1]
    if pd.isna(start) or pd.isna(end) or float(start) <= 0:
        return math.nan
    return float(end) / float(start) - 1.0


def annualized_volatility(returns: pd.Series) -> float:
    values = pd.to_numeric(returns, errors="coerce").dropna()
    if len(values) < 2:
        return math.nan
    return float(values.std(ddof=1) * math.sqrt(252))


def attach_fundamental_features(observations: pd.DataFrame, paths: dict[str, Path]) -> pd.DataFrame:
    if observations.empty:
        return observations
    path = paths.get("fundamental_features")
    if path is None or not path.exists():
        observations["fundamental_feature_coverage"] = 0.0
        return observations
    fundamentals = pd.read_parquet(path).reset_index()
    fundamentals["datetime"] = pd.to_datetime(fundamentals["datetime"]).dt.normalize()
    fundamentals["symbol"] = fundamentals["instrument"].astype(str).str.upper()
    working = observations.copy()
    working["datetime"] = pd.to_datetime(working["signal_date"]).dt.normalize()
    working["symbol"] = working["symbol"].astype(str).str.upper()
    merged = working.merge(fundamentals.drop(columns=["instrument"]), on=["datetime", "symbol"], how="left")
    edgar_columns = [column for column in merged.columns if column.startswith("edgar_")]
    merged["fundamental_feature_coverage"] = merged[edgar_columns].notna().mean(axis=1) if edgar_columns else 0.0
    return merged.drop(columns=["datetime"])


def add_error_flags(examples: pd.DataFrame, observations: pd.DataFrame) -> pd.DataFrame:
    enriched = examples.copy()
    for sector, sector_observations in observations.groupby("sector", dropna=False):
        mask = enriched["sector"] == sector
        sector_examples = enriched[mask]
        if sector_examples.empty:
            continue
        enriched.loc[mask, "is_high_valuation"] = high_valuation_flags(sector_examples, sector_observations).values
        enriched.loc[mask, "is_small_cap"] = low_tail_flag(sector_examples, sector_observations, "market_cap_asof_estimate").values
        enriched.loc[mask, "is_low_liquidity"] = low_tail_flag(sector_examples, sector_observations, "avg_dollar_volume_20d_asof").values
    enriched["is_short_history"] = text_column(enriched, "history_bucket").ne("full_10y")
    enriched["is_adr_ads"] = numeric_column(enriched, "is_adr_ads").fillna(0).astype(bool)
    enriched["is_unprofitable"] = (
        (numeric_column(enriched, "edgar_roe") < 0)
        | (numeric_column(enriched, "edgar_net_margin") < 0)
    )
    enriched["is_recent_filing"] = numeric_column(enriched, "edgar_is_recent_filing").fillna(0) > 0
    return enriched


def high_valuation_flags(examples: pd.DataFrame, observations: pd.DataFrame) -> pd.Series:
    flags = pd.Series(False, index=examples.index)
    for column in ["edgar_price_to_sales", "edgar_price_to_book", "edgar_price_to_earnings"]:
        if column not in observations or column not in examples:
            continue
        threshold = pd.to_numeric(observations[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna().quantile(0.75)
        if pd.isna(threshold):
            continue
        flags = flags | (pd.to_numeric(examples[column], errors="coerce") >= threshold)
    return flags


def low_tail_flag(examples: pd.DataFrame, observations: pd.DataFrame, column: str) -> pd.Series:
    if column not in observations or column not in examples:
        return pd.Series(False, index=examples.index)
    threshold = pd.to_numeric(observations[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna().quantile(0.25)
    if pd.isna(threshold):
        return pd.Series(False, index=examples.index)
    return pd.to_numeric(examples[column], errors="coerce") <= threshold


def summarize_sector_errors(
    observations: pd.DataFrame,
    examples: pd.DataFrame,
    daily_metrics: pd.DataFrame,
    target_sectors: list[str],
    min_summary_periods: int,
) -> pd.DataFrame:
    rows = []
    for sector in target_sectors:
        sector_observations = observations[observations.get("sector", pd.Series(dtype=object)) == sector] if not observations.empty else pd.DataFrame()
        sector_examples = examples[examples.get("sector", pd.Series(dtype=object)) == sector] if not examples.empty else pd.DataFrame()
        sector_daily = daily_metrics[daily_metrics.get("sector", pd.Series(dtype=object)) == sector] if not daily_metrics.empty else pd.DataFrame()
        counts = category_counts(sector_examples)
        high_score_decisions = counts["high_score_winners"] + counts["high_score_losers"]
        low_score_decisions = counts["low_score_winners"] + counts["low_score_losers"]
        rank_ic_mean = numeric_mean(sector_daily, "rank_ic")
        spread_mean = numeric_mean(sector_daily, "top_bottom_spread")
        rows.append(
            {
                "sector": sector,
                "diagnosis": diagnose_sector(rank_ic_mean, spread_mean, len(sector_daily), min_summary_periods),
                "signal_period_count": int(sector_daily["signal_date"].nunique()) if not sector_daily.empty else 0,
                "observation_count": int(len(sector_observations)),
                "classified_example_count": int(len(sector_examples)),
                "avg_tradable_count": numeric_mean(sector_daily, "tradable_count"),
                "rank_ic_mean": rank_ic_mean,
                "ic_mean": numeric_mean(sector_daily, "ic"),
                "top_bottom_spread_mean": spread_mean,
                "fundamental_coverage_mean": numeric_mean(sector_observations, "fundamental_feature_coverage"),
                **{f"{category}_count": counts[category] for category in CATEGORY_NAMES},
                **{f"{category}_avg_return": category_avg_return(sector_examples, category) for category in CATEGORY_NAMES},
                "high_score_loser_rate": counts["high_score_losers"] / high_score_decisions if high_score_decisions else math.nan,
                "low_score_winner_rate": counts["low_score_winners"] / low_score_decisions if low_score_decisions else math.nan,
                **error_concentration_rates(sector_examples, "high_score_losers"),
                **error_concentration_rates(sector_examples, "low_score_winners"),
            }
        )
    return pd.DataFrame(rows)


def category_counts(examples: pd.DataFrame) -> dict[str, int]:
    if examples.empty or "error_category" not in examples:
        return {category: 0 for category in CATEGORY_NAMES}
    counts = examples["error_category"].value_counts().to_dict()
    return {category: int(counts.get(category, 0)) for category in CATEGORY_NAMES}


def category_avg_return(examples: pd.DataFrame, category: str) -> float:
    if examples.empty:
        return math.nan
    return numeric_mean(examples[examples["error_category"] == category], "future_return")


def error_concentration_rates(examples: pd.DataFrame, category: str) -> dict[str, float]:
    subset = examples[examples.get("error_category", pd.Series(dtype=object)) == category] if not examples.empty else pd.DataFrame()
    flags = [
        "is_high_valuation",
        "is_small_cap",
        "is_short_history",
        "is_low_liquidity",
        "is_adr_ads",
        "is_unprofitable",
        "is_recent_filing",
    ]
    return {f"{category}_{flag}_rate": bool_rate(subset, flag) for flag in flags}


def build_feature_differences(examples: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    if examples.empty:
        return pd.DataFrame()
    rows = []
    comparisons = [
        ("high_score_winners", "high_score_losers"),
        ("low_score_winners", "high_score_winners"),
    ]
    for sector, sector_examples in examples.groupby("sector", dropna=False):
        for left_category, right_category in comparisons:
            left = sector_examples[sector_examples["error_category"] == left_category]
            right = sector_examples[sector_examples["error_category"] == right_category]
            for feature in feature_columns:
                if feature not in sector_examples:
                    continue
                left_values = pd.to_numeric(left[feature], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
                right_values = pd.to_numeric(right[feature], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
                if left_values.empty and right_values.empty:
                    continue
                left_mean = float(left_values.mean()) if not left_values.empty else math.nan
                right_mean = float(right_values.mean()) if not right_values.empty else math.nan
                rows.append(
                    {
                        "sector": sector,
                        "comparison": f"{left_category}_vs_{right_category}",
                        "left_category": left_category,
                        "right_category": right_category,
                        "feature": feature,
                        "left_mean": left_mean,
                        "right_mean": right_mean,
                        "difference": left_mean - right_mean if not math.isnan(left_mean) and not math.isnan(right_mean) else math.nan,
                        "left_coverage": float(left_values.size / len(left)) if len(left) else 0.0,
                        "right_coverage": float(right_values.size / len(right)) if len(right) else 0.0,
                    }
                )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["sector", "comparison", "feature"]).reset_index(drop=True)


def build_yaml_summary(
    summary: pd.DataFrame,
    feature_differences: pd.DataFrame,
    review_config: dict[str, Any],
    target_sectors: list[str],
) -> dict[str, Any]:
    sector_records = records_for_yaml(summary)
    top_differences = []
    if not feature_differences.empty:
        working = feature_differences.copy()
        working["abs_difference"] = pd.to_numeric(working["difference"], errors="coerce").abs()
        top_differences = records_for_yaml(working.sort_values("abs_difference", ascending=False).head(20))
    return {
        "enabled": True,
        "target_sectors": target_sectors,
        "config": review_config,
        "sectors": sector_records,
        "largest_feature_differences": top_differences,
    }


def diagnose_sector(rank_ic_mean: float, spread_mean: float, period_count: int, min_summary_periods: int) -> str:
    if period_count < min_summary_periods:
        return "low_sample"
    if pd.notna(rank_ic_mean) and pd.notna(spread_mean) and rank_ic_mean > 0.02 and spread_mean > 0:
        return "model_effective"
    if pd.notna(rank_ic_mean) and pd.notna(spread_mean) and rank_ic_mean < 0 and spread_mean < 0:
        return "model_weak"
    return "mixed_or_noisy"


def correlation_or_nan(left: pd.Series, right: pd.Series, method: str) -> float:
    frame = pd.concat([pd.to_numeric(left, errors="coerce"), pd.to_numeric(right, errors="coerce")], axis=1).dropna()
    if len(frame) < 2:
        return math.nan
    if frame.iloc[:, 0].nunique() < 2 or frame.iloc[:, 1].nunique() < 2:
        return math.nan
    value = frame.iloc[:, 0].corr(frame.iloc[:, 1], method=method)
    return float(value) if not pd.isna(value) else math.nan


def numeric_mean(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame:
        return math.nan
    values = pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    return float(values.mean()) if not values.empty else math.nan


def bool_rate(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame:
        return math.nan
    values = frame[column].dropna()
    return float(values.astype(bool).mean()) if not values.empty else math.nan


def normalized_text_series(series: pd.Series) -> pd.Series:
    return series.map(lambda value: np.nan if pd.isna(value) or not str(value).strip() else str(value).strip())


def numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def text_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series("", index=frame.index, dtype=object)
    return frame[column].astype(str)


def records_for_yaml(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return [
        {key: normalize_yaml_scalar(value) for key, value in row.items()}
        for row in frame.to_dict("records")
    ]


def normalize_yaml_scalar(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (bool, int, str)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def write_sector_error_outputs(result: SectorErrorReviewResult, paths: dict[str, Path]) -> None:
    outputs = {
        "sector_error_review_summary_csv": result.summary,
        "sector_error_examples_csv": result.examples,
        "sector_error_feature_differences_csv": result.feature_differences,
    }
    for key, frame in outputs.items():
        if key in paths:
            paths[key].parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(paths[key], index=False)
    if "sector_error_review_summary_yaml" in paths:
        paths["sector_error_review_summary_yaml"].write_text(
            yaml.safe_dump(result.yaml_summary, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
