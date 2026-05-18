"""Within-sector and within-industry stock selection diagnostics."""

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
class WithinSectorReviewResult:
    daily_metrics: pd.DataFrame
    sector_summary: pd.DataFrame
    industry_summary: pd.DataFrame
    quantile_returns: pd.DataFrame
    summary: dict[str, Any]


DAILY_COLUMNS = [
    "signal_date",
    "entry_date",
    "exit_date",
    "group_level",
    "group_value",
    "candidate_count",
    "tradable_count",
    "ic",
    "rank_ic",
    "group_mean_return",
    "top_quantile_mean_return",
    "bottom_quantile_mean_return",
    "top_bottom_spread",
    "top_win_rate_vs_group",
    "skip_reason",
]
SUMMARY_COLUMNS = [
    "group_level",
    "group_value",
    "daily_count",
    "valid_ic_count",
    "valid_spread_count",
    "avg_candidate_count",
    "avg_tradable_count",
    "ic_mean",
    "rank_ic_mean",
    "group_mean_return",
    "top_quantile_mean_return",
    "bottom_quantile_mean_return",
    "top_bottom_spread_mean",
    "spread_positive_rate",
    "top_win_rate_vs_group_mean",
    "low_sample",
]
QUANTILE_COLUMNS = [
    "group_level",
    "group_value",
    "score_quantile",
    "avg_future_return",
    "observation_count",
    "period_count",
]


def run_within_sector_review(
    predictions: pd.DataFrame,
    universe: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
) -> WithinSectorReviewResult:
    review_config = config.get("within_sector_review", {})
    if not review_config.get("enabled", False):
        result = WithinSectorReviewResult(
            daily_metrics=pd.DataFrame(columns=DAILY_COLUMNS),
            sector_summary=pd.DataFrame(columns=SUMMARY_COLUMNS),
            industry_summary=pd.DataFrame(columns=SUMMARY_COLUMNS),
            quantile_returns=pd.DataFrame(columns=QUANTILE_COLUMNS),
            summary={"enabled": False},
        )
        write_within_sector_outputs(result, paths)
        return result

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
    min_group_size = int(review_config.get("min_group_size", 10))
    min_summary_periods = int(review_config.get("min_summary_periods", 20))
    quantiles = int(review_config.get("quantiles", 5))
    group_levels = list(review_config.get("group_levels", ["sector", "industry"]))

    daily_rows: list[dict[str, Any]] = []
    quantile_rows: list[dict[str, Any]] = []
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
        tradable = pd.DataFrame(build_position_returns(day, close, entry_date, exit_date))
        if tradable.empty:
            continue

        for group_level in group_levels:
            if group_level not in day.columns or group_level not in tradable.columns:
                continue
            daily_rows.extend(
                build_daily_group_metrics(
                    day=day,
                    tradable=tradable,
                    group_level=group_level,
                    signal_ts=signal_ts,
                    entry_date=entry_date,
                    exit_date=exit_date,
                    min_group_size=min_group_size,
                    quantiles=quantiles,
                )
            )
            if group_level == "sector":
                quantile_rows.extend(
                    build_quantile_return_rows(
                        tradable=tradable,
                        group_level=group_level,
                        signal_ts=signal_ts,
                        min_group_size=min_group_size,
                        quantiles=quantiles,
                    )
                )

    daily_metrics = pd.DataFrame(daily_rows, columns=DAILY_COLUMNS)
    quantile_detail = pd.DataFrame(quantile_rows)
    quantile_returns = summarize_quantile_returns(quantile_detail)
    sector_summary = summarize_group_metrics(daily_metrics, "sector", min_summary_periods)
    industry_summary = summarize_group_metrics(daily_metrics, "industry", min_summary_periods)
    summary = build_selection_summary(sector_summary, industry_summary, review_config)
    result = WithinSectorReviewResult(
        daily_metrics=daily_metrics,
        sector_summary=sector_summary,
        industry_summary=industry_summary,
        quantile_returns=quantile_returns,
        summary=summary,
    )
    write_within_sector_outputs(result, paths)
    return result


def build_daily_group_metrics(
    day: pd.DataFrame,
    tradable: pd.DataFrame,
    group_level: str,
    signal_ts: pd.Timestamp,
    entry_date: pd.Timestamp,
    exit_date: pd.Timestamp,
    min_group_size: int,
    quantiles: int,
) -> list[dict[str, Any]]:
    rows = []
    day_counts = normalized_group_series(day[group_level]).value_counts().to_dict()
    working = tradable.copy()
    working[group_level] = normalized_group_series(working[group_level])
    for group_value, group in working.dropna(subset=[group_level]).groupby(group_level, dropna=False):
        group = group.dropna(subset=["score", "gross_return"]).copy()
        tradable_count = int(len(group))
        candidate_count = int(day_counts.get(group_value, 0))
        ic = correlation_or_nan(group["score"], group["gross_return"], method="pearson")
        rank_ic = correlation_or_nan(group["score"], group["gross_return"], method="spearman")
        group_mean = float(group["gross_return"].mean()) if tradable_count else math.nan
        top_mean = math.nan
        bottom_mean = math.nan
        spread = math.nan
        top_win_rate = math.nan
        skip_reason = ""
        if tradable_count < min_group_size:
            skip_reason = f"tradable_count < {min_group_size}"
        else:
            ordered = group.sort_values("score", ascending=False).reset_index(drop=True)
            bucket_size = max(1, len(ordered) // quantiles)
            top = ordered.head(bucket_size)
            bottom = ordered.tail(bucket_size)
            top_mean = float(top["gross_return"].mean())
            bottom_mean = float(bottom["gross_return"].mean())
            spread = top_mean - bottom_mean
            top_win_rate = float((top["gross_return"] > group_mean).mean())

        rows.append(
            {
                "signal_date": signal_ts.date().isoformat(),
                "entry_date": entry_date.date().isoformat(),
                "exit_date": exit_date.date().isoformat(),
                "group_level": group_level,
                "group_value": group_value,
                "candidate_count": candidate_count,
                "tradable_count": tradable_count,
                "ic": ic,
                "rank_ic": rank_ic,
                "group_mean_return": group_mean,
                "top_quantile_mean_return": top_mean,
                "bottom_quantile_mean_return": bottom_mean,
                "top_bottom_spread": spread,
                "top_win_rate_vs_group": top_win_rate,
                "skip_reason": skip_reason,
            }
        )
    return rows


def build_quantile_return_rows(
    tradable: pd.DataFrame,
    group_level: str,
    signal_ts: pd.Timestamp,
    min_group_size: int,
    quantiles: int,
) -> list[dict[str, Any]]:
    rows = []
    working = tradable.copy()
    working[group_level] = normalized_group_series(working[group_level])
    for group_value, group in working.dropna(subset=[group_level]).groupby(group_level, dropna=False):
        group = group.dropna(subset=["score", "gross_return"]).sort_values("score", ascending=False).reset_index(drop=True)
        if len(group) < min_group_size:
            continue
        group["score_quantile"] = (group.index.to_series() * quantiles // len(group) + 1).clip(upper=quantiles).astype(int)
        for quantile, quantile_group in group.groupby("score_quantile"):
            rows.append(
                {
                    "signal_date": signal_ts.date().isoformat(),
                    "group_level": group_level,
                    "group_value": group_value,
                    "score_quantile": int(quantile),
                    "future_return": float(quantile_group["gross_return"].mean()),
                    "observation_count": int(len(quantile_group)),
                }
            )
    return rows


def summarize_group_metrics(daily_metrics: pd.DataFrame, group_level: str, min_summary_periods: int) -> pd.DataFrame:
    if daily_metrics.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)
    working = daily_metrics[daily_metrics["group_level"] == group_level].copy()
    if working.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)
    grouped = working.groupby(["group_level", "group_value"], dropna=False)
    summary = grouped.agg(
        daily_count=("signal_date", "nunique"),
        valid_ic_count=("ic", lambda series: int(series.notna().sum())),
        valid_spread_count=("top_bottom_spread", lambda series: int(series.notna().sum())),
        avg_candidate_count=("candidate_count", "mean"),
        avg_tradable_count=("tradable_count", "mean"),
        ic_mean=("ic", "mean"),
        rank_ic_mean=("rank_ic", "mean"),
        group_mean_return=("group_mean_return", "mean"),
        top_quantile_mean_return=("top_quantile_mean_return", "mean"),
        bottom_quantile_mean_return=("bottom_quantile_mean_return", "mean"),
        top_bottom_spread_mean=("top_bottom_spread", "mean"),
        spread_positive_rate=("top_bottom_spread", lambda series: float((series.dropna() > 0).mean()) if series.notna().any() else math.nan),
        top_win_rate_vs_group_mean=("top_win_rate_vs_group", "mean"),
    ).reset_index()
    summary["low_sample"] = summary["daily_count"] < min_summary_periods
    return summary.sort_values(["low_sample", "rank_ic_mean", "top_bottom_spread_mean"], ascending=[True, False, False]).reset_index(drop=True)


def summarize_quantile_returns(quantile_detail: pd.DataFrame) -> pd.DataFrame:
    if quantile_detail.empty:
        return pd.DataFrame(columns=QUANTILE_COLUMNS)
    grouped = quantile_detail.groupby(["group_level", "group_value", "score_quantile"], dropna=False)
    return (
        grouped.agg(
            avg_future_return=("future_return", "mean"),
            observation_count=("observation_count", "sum"),
            period_count=("signal_date", "nunique"),
        )
        .reset_index()
        .sort_values(["group_value", "score_quantile"])
        .reset_index(drop=True)
    )


def build_selection_summary(
    sector_summary: pd.DataFrame,
    industry_summary: pd.DataFrame,
    review_config: dict[str, Any],
) -> dict[str, Any]:
    valid_sectors = sector_summary[~sector_summary.get("low_sample", pd.Series(dtype=bool))].copy() if not sector_summary.empty else sector_summary
    return {
        "enabled": True,
        "config": review_config,
        "sector_count": int(len(sector_summary)),
        "industry_count": int(len(industry_summary)),
        "low_sample_sector_count": int(sector_summary["low_sample"].sum()) if "low_sample" in sector_summary else 0,
        "top_sectors_by_rank_ic": records_for_yaml(valid_sectors.head(5), "group_value"),
        "bottom_sectors_by_rank_ic": records_for_yaml(valid_sectors.sort_values("rank_ic_mean").head(5), "group_value"),
        "top_sectors_by_spread": records_for_yaml(valid_sectors.sort_values("top_bottom_spread_mean", ascending=False).head(5), "group_value"),
        "bottom_sectors_by_spread": records_for_yaml(valid_sectors.sort_values("top_bottom_spread_mean").head(5), "group_value"),
    }


def correlation_or_nan(left: pd.Series, right: pd.Series, method: str) -> float:
    frame = pd.concat([pd.to_numeric(left, errors="coerce"), pd.to_numeric(right, errors="coerce")], axis=1).dropna()
    if len(frame) < 2:
        return math.nan
    if frame.iloc[:, 0].nunique() < 2 or frame.iloc[:, 1].nunique() < 2:
        return math.nan
    value = frame.iloc[:, 0].corr(frame.iloc[:, 1], method=method)
    return float(value) if not pd.isna(value) else math.nan


def normalized_group_series(series: pd.Series) -> pd.Series:
    return series.map(lambda value: np.nan if pd.isna(value) or not str(value).strip() else str(value).strip())


def records_for_yaml(frame: pd.DataFrame, label_column: str) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    columns = [
        label_column,
        "daily_count",
        "avg_tradable_count",
        "rank_ic_mean",
        "ic_mean",
        "top_bottom_spread_mean",
        "spread_positive_rate",
    ]
    records = []
    for row in frame[[column for column in columns if column in frame.columns]].to_dict("records"):
        records.append({key: normalize_yaml_scalar(value) for key, value in row.items()})
    return records


def normalize_yaml_scalar(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (int, str, bool)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def write_within_sector_outputs(result: WithinSectorReviewResult, paths: dict[str, Path]) -> None:
    outputs = {
        "within_sector_daily_metrics": result.daily_metrics,
        "within_sector_summary": result.sector_summary,
        "within_industry_summary": result.industry_summary,
        "within_sector_quantile_returns": result.quantile_returns,
    }
    for key, frame in outputs.items():
        if key in paths:
            paths[key].parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(paths[key], index=False)
    if "within_sector_selection_summary" in paths:
        paths["within_sector_selection_summary"].write_text(
            yaml.safe_dump(result.summary, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
