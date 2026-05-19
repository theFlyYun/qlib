"""Short-history stock diagnostics for bucketed TopK selections."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


@dataclass
class ShortHistoryReviewResult:
    bucket_summary: pd.DataFrame
    examples: pd.DataFrame
    feature_differences: pd.DataFrame
    sector_breakdown: pd.DataFrame
    yaml_summary: dict[str, Any]


DEFAULT_TARGET_BUCKETS = ["lt_2y", "2_5y"]
DEFAULT_COMPARISON_BUCKETS = ["full_10y", "5_10y"]
DEFAULT_BASELINE_VARIANT = "raw_score_sector_cap_2_top10"
DEFAULT_FEATURE_COLUMNS = [
    "score",
    "raw_score",
    "adjusted_score",
    "gross_return",
    "net_contribution",
    "history_rows_asof",
    "latest_close_asof",
    "avg_dollar_volume_20d_asof",
    "median_dollar_volume_60d_asof",
    "market_cap_asof_estimate",
    "market_momentum_20d",
    "market_momentum_60d",
    "market_momentum_120d",
    "market_volatility_20d",
    "market_volatility_60d",
    "market_sector_pct_log_avg_dollar_volume_20d",
    "market_sector_pct_momentum_60d",
    "market_sector_pct_volatility_20d",
    "edgar_price_to_sales",
    "edgar_price_to_book",
    "edgar_price_to_earnings",
    "edgar_gross_margin",
    "edgar_net_margin",
    "edgar_roe",
    "edgar_revenue_yoy_growth",
    "edgar_liabilities_to_assets",
    "edgar_days_since_last_10q",
    "edgar_is_recent_filing",
]
BUCKET_SUMMARY_COLUMNS = [
    "history_bucket",
    "is_target_bucket",
    "position_count",
    "symbol_count",
    "period_count",
    "avg_gross_return",
    "win_rate",
    "gross_contribution_sum",
    "net_contribution_sum",
    "avg_score",
    "avg_raw_score",
    "avg_adjusted_score",
    "worst_position_return",
    "best_position_return",
    "avg_history_rows_asof",
    "avg_latest_close_asof",
    "avg_dollar_volume_20d_asof",
    "fundamental_feature_coverage_mean",
    "market_feature_coverage_mean",
    "winner_count",
    "loser_count",
    "low_sample",
    "loser_low_liquidity_rate",
    "loser_high_valuation_rate",
    "loser_unprofitable_rate",
    "loser_recent_filing_rate",
    "loser_high_volatility_rate",
]
BREAKDOWN_COLUMNS = [
    "group_level",
    "history_bucket",
    "group_value",
    "position_count",
    "symbol_count",
    "period_count",
    "avg_gross_return",
    "win_rate",
    "gross_contribution_sum",
    "net_contribution_sum",
    "worst_position_return",
    "best_position_return",
]


def run_short_history_review(
    predictions: pd.DataFrame,
    universe: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
) -> ShortHistoryReviewResult:
    del predictions
    review_config = config.get("short_history_review", {})
    if not review_config.get("enabled", False):
        result = ShortHistoryReviewResult(
            bucket_summary=pd.DataFrame(columns=BUCKET_SUMMARY_COLUMNS),
            examples=pd.DataFrame(),
            feature_differences=pd.DataFrame(),
            sector_breakdown=pd.DataFrame(columns=BREAKDOWN_COLUMNS),
            yaml_summary={"enabled": False},
        )
        write_short_history_outputs(result, paths)
        return result

    target_buckets = normalized_list(review_config.get("target_buckets", DEFAULT_TARGET_BUCKETS))
    comparison_buckets = normalized_list(review_config.get("comparison_buckets", DEFAULT_COMPARISON_BUCKETS))
    review_buckets = [*comparison_buckets, *target_buckets]
    quantiles = int(review_config.get("quantiles", 5))
    min_bucket_samples = int(review_config.get("min_bucket_samples", 20))
    baseline_variant = str(review_config.get("baseline_variant", DEFAULT_BASELINE_VARIANT))
    feature_columns = list(review_config.get("feature_columns", DEFAULT_FEATURE_COLUMNS))

    positions = read_baseline_positions(paths, baseline_variant)
    observations = prepare_observations(positions, universe, paths, review_buckets)
    classified = classify_bucket_examples(observations, target_buckets, quantiles, min_bucket_samples)
    examples = classified[
        classified["history_bucket"].isin(target_buckets) & classified["short_history_category"].ne("")
    ].copy()
    bucket_summary = summarize_buckets(classified, target_buckets, review_buckets, min_bucket_samples)
    sector_breakdown = build_sector_breakdown(classified, review_buckets)
    feature_differences = build_feature_differences(examples, feature_columns)
    yaml_summary = build_yaml_summary(
        bucket_summary=bucket_summary,
        sector_breakdown=sector_breakdown,
        feature_differences=feature_differences,
        review_config=review_config,
        target_buckets=target_buckets,
        comparison_buckets=comparison_buckets,
        baseline_variant=baseline_variant,
    )
    result = ShortHistoryReviewResult(
        bucket_summary=bucket_summary,
        examples=examples,
        feature_differences=feature_differences,
        sector_breakdown=sector_breakdown,
        yaml_summary=yaml_summary,
    )
    write_short_history_outputs(result, paths)
    return result


def normalized_list(values: Any) -> list[str]:
    return [str(value).strip() for value in values if str(value).strip()]


def read_baseline_positions(paths: dict[str, Path], baseline_variant: str) -> pd.DataFrame:
    variant_path = paths["strategy_comparison_dir"] / baseline_variant / "backtest_positions.csv"
    fallback_path = paths["backtest_positions_csv"]
    path = variant_path if variant_path.exists() else fallback_path
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def prepare_observations(
    positions: pd.DataFrame,
    universe: pd.DataFrame,
    paths: dict[str, Path],
    review_buckets: list[str],
) -> pd.DataFrame:
    if positions.empty:
        return pd.DataFrame()
    frame = positions.copy()
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    frame["signal_date"] = pd.to_datetime(frame["signal_date"], errors="coerce").dt.normalize()
    frame["history_bucket"] = frame["history_bucket"].fillna("missing_history").astype(str)
    frame = frame[frame["history_bucket"].isin(review_buckets)].copy()
    frame = merge_universe_metadata(frame, universe)
    frame = attach_feature_frame(frame, paths.get("market_features"), "market_feature_coverage", "market_")
    frame = attach_feature_frame(frame, paths.get("fundamental_features"), "fundamental_feature_coverage", "edgar_")
    frame = add_review_flags(frame)
    return frame


def merge_universe_metadata(frame: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    if universe.empty:
        return frame
    metadata = universe.copy()
    metadata["symbol"] = metadata["symbol"].astype(str).str.upper()
    metadata_columns = ["symbol"] + [
        column
        for column in [
            "name",
            "asset_type",
            "is_adr_ads",
            "is_share_class",
            "share_class",
            "market_cap_asof_estimate",
        ]
        if column in metadata.columns and column not in frame.columns
    ]
    if len(metadata_columns) == 1:
        return frame
    return frame.merge(metadata[metadata_columns].drop_duplicates("symbol"), on="symbol", how="left")


def attach_feature_frame(
    observations: pd.DataFrame,
    path: Path | None,
    coverage_column: str,
    feature_prefix: str,
) -> pd.DataFrame:
    frame = observations.copy()
    if path is None or not path.exists() or frame.empty:
        frame[coverage_column] = 0.0
        return frame
    features = pd.read_parquet(path).reset_index()
    features["datetime"] = pd.to_datetime(features["datetime"], errors="coerce").dt.normalize()
    features["symbol"] = features["instrument"].astype(str).str.upper()
    feature_columns = [column for column in features.columns if column.startswith(feature_prefix)]
    merge_columns = ["datetime", "symbol", *feature_columns]
    working = frame.copy()
    working["datetime"] = pd.to_datetime(working["signal_date"], errors="coerce").dt.normalize()
    merged = working.merge(features[merge_columns], on=["datetime", "symbol"], how="left")
    merged[coverage_column] = merged[feature_columns].notna().mean(axis=1) if feature_columns else 0.0
    return merged.drop(columns=["datetime"])


def add_review_flags(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    working = frame.copy()
    working["is_winner"] = numeric_column(working, "gross_return") > 0
    working["is_loser"] = numeric_column(working, "gross_return") < 0
    working["is_low_liquidity"] = low_tail_flag(working, "avg_dollar_volume_20d_asof")
    working["is_high_valuation"] = high_valuation_flags(working)
    working["is_unprofitable"] = (
        (numeric_column(working, "edgar_roe") < 0)
        | (numeric_column(working, "edgar_net_margin") < 0)
    )
    working["is_recent_filing"] = numeric_column(working, "edgar_is_recent_filing").fillna(0) > 0
    working["is_high_volatility"] = high_tail_flag(working, "market_volatility_20d")
    return working


def classify_bucket_examples(
    observations: pd.DataFrame,
    target_buckets: list[str],
    quantiles: int,
    min_bucket_samples: int,
) -> pd.DataFrame:
    if observations.empty:
        return observations
    frame = observations.copy()
    frame["short_history_category"] = ""
    frame["short_history_skip_reason"] = ""
    for bucket, bucket_frame in frame.groupby("history_bucket", dropna=False):
        indexes = bucket_frame.index
        if len(bucket_frame) < min_bucket_samples:
            frame.loc[indexes, "short_history_skip_reason"] = f"bucket_count < {min_bucket_samples}"
            continue
        if bucket not in target_buckets:
            continue
        usable = bucket_frame.dropna(subset=["gross_return"]).copy()
        if usable.empty:
            continue
        bucket_size = max(1, len(usable) // quantiles)
        winners = usable.nlargest(bucket_size, "gross_return").index
        losers = usable.nsmallest(bucket_size, "gross_return").index
        frame.loc[winners, "short_history_category"] = "bucket_winners"
        frame.loc[losers, "short_history_category"] = "bucket_losers"
    return frame


def summarize_buckets(
    observations: pd.DataFrame,
    target_buckets: list[str],
    review_buckets: list[str],
    min_bucket_samples: int,
) -> pd.DataFrame:
    rows = []
    for bucket in review_buckets:
        group = observations[observations.get("history_bucket", pd.Series(dtype=object)) == bucket] if not observations.empty else pd.DataFrame()
        winners = group[group.get("short_history_category", pd.Series(dtype=object)) == "bucket_winners"] if not group.empty else pd.DataFrame()
        losers = group[group.get("short_history_category", pd.Series(dtype=object)) == "bucket_losers"] if not group.empty else pd.DataFrame()
        rows.append(
            {
                "history_bucket": bucket,
                "is_target_bucket": bucket in target_buckets,
                "position_count": int(len(group)),
                "symbol_count": int(group["symbol"].nunique()) if "symbol" in group else 0,
                "period_count": int(group["period"].nunique()) if "period" in group else 0,
                "avg_gross_return": numeric_mean(group, "gross_return"),
                "win_rate": positive_rate(group, "gross_return"),
                "gross_contribution_sum": numeric_sum(group, "gross_contribution"),
                "net_contribution_sum": numeric_sum(group, "net_contribution"),
                "avg_score": numeric_mean(group, "score"),
                "avg_raw_score": numeric_mean(group, "raw_score"),
                "avg_adjusted_score": numeric_mean(group, "adjusted_score"),
                "worst_position_return": numeric_min(group, "gross_return"),
                "best_position_return": numeric_max(group, "gross_return"),
                "avg_history_rows_asof": numeric_mean(group, "history_rows_asof"),
                "avg_latest_close_asof": numeric_mean(group, "latest_close_asof"),
                "avg_dollar_volume_20d_asof": numeric_mean(group, "avg_dollar_volume_20d_asof"),
                "fundamental_feature_coverage_mean": numeric_mean(group, "fundamental_feature_coverage"),
                "market_feature_coverage_mean": numeric_mean(group, "market_feature_coverage"),
                "winner_count": int(len(winners)),
                "loser_count": int(len(losers)),
                "low_sample": len(group) < min_bucket_samples,
                "loser_low_liquidity_rate": bool_rate(losers, "is_low_liquidity"),
                "loser_high_valuation_rate": bool_rate(losers, "is_high_valuation"),
                "loser_unprofitable_rate": bool_rate(losers, "is_unprofitable"),
                "loser_recent_filing_rate": bool_rate(losers, "is_recent_filing"),
                "loser_high_volatility_rate": bool_rate(losers, "is_high_volatility"),
            }
        )
    return pd.DataFrame(rows, columns=BUCKET_SUMMARY_COLUMNS)


def build_sector_breakdown(observations: pd.DataFrame, review_buckets: list[str]) -> pd.DataFrame:
    if observations.empty:
        return pd.DataFrame(columns=BREAKDOWN_COLUMNS)
    rows = []
    for group_level in ["sector", "industry"]:
        if group_level not in observations:
            continue
        working = observations[observations["history_bucket"].isin(review_buckets)].copy()
        working[group_level] = normalized_group_series(working[group_level])
        for (bucket, group_value), group in working.groupby(["history_bucket", group_level], dropna=False):
            rows.append(
                {
                    "group_level": group_level,
                    "history_bucket": bucket,
                    "group_value": group_value,
                    "position_count": int(len(group)),
                    "symbol_count": int(group["symbol"].nunique()) if "symbol" in group else 0,
                    "period_count": int(group["period"].nunique()) if "period" in group else 0,
                    "avg_gross_return": numeric_mean(group, "gross_return"),
                    "win_rate": positive_rate(group, "gross_return"),
                    "gross_contribution_sum": numeric_sum(group, "gross_contribution"),
                    "net_contribution_sum": numeric_sum(group, "net_contribution"),
                    "worst_position_return": numeric_min(group, "gross_return"),
                    "best_position_return": numeric_max(group, "gross_return"),
                }
            )
    if not rows:
        return pd.DataFrame(columns=BREAKDOWN_COLUMNS)
    return pd.DataFrame(rows, columns=BREAKDOWN_COLUMNS).sort_values(
        ["group_level", "history_bucket", "net_contribution_sum"],
        ascending=[True, True, True],
    )


def build_feature_differences(examples: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    if examples.empty:
        return pd.DataFrame()
    rows = []
    for bucket, bucket_examples in examples.groupby("history_bucket", dropna=False):
        winners = bucket_examples[bucket_examples["short_history_category"] == "bucket_winners"]
        losers = bucket_examples[bucket_examples["short_history_category"] == "bucket_losers"]
        for feature in feature_columns:
            if feature not in bucket_examples:
                continue
            winner_values = numeric_values(winners, feature)
            loser_values = numeric_values(losers, feature)
            if winner_values.empty and loser_values.empty:
                continue
            winner_mean = float(winner_values.mean()) if not winner_values.empty else math.nan
            loser_mean = float(loser_values.mean()) if not loser_values.empty else math.nan
            rows.append(
                {
                    "history_bucket": bucket,
                    "comparison": "bucket_winners_vs_bucket_losers",
                    "feature": feature,
                    "winner_mean": winner_mean,
                    "loser_mean": loser_mean,
                    "difference": winner_mean - loser_mean if pd.notna(winner_mean) and pd.notna(loser_mean) else math.nan,
                    "winner_coverage": float(len(winner_values) / len(winners)) if len(winners) else 0.0,
                    "loser_coverage": float(len(loser_values) / len(losers)) if len(losers) else 0.0,
                }
            )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["history_bucket", "feature"]).reset_index(drop=True)


def build_yaml_summary(
    bucket_summary: pd.DataFrame,
    sector_breakdown: pd.DataFrame,
    feature_differences: pd.DataFrame,
    review_config: dict[str, Any],
    target_buckets: list[str],
    comparison_buckets: list[str],
    baseline_variant: str,
) -> dict[str, Any]:
    target_sector = target_sector_records(sector_breakdown, target_buckets)
    top_differences = []
    if not feature_differences.empty:
        working = feature_differences.copy()
        working["abs_difference"] = pd.to_numeric(working["difference"], errors="coerce").abs()
        top_differences = records_for_yaml(working.sort_values("abs_difference", ascending=False).head(20))
    return {
        "enabled": True,
        "baseline_variant": baseline_variant,
        "target_buckets": target_buckets,
        "comparison_buckets": comparison_buckets,
        "config": review_config,
        "bucket_summary": records_for_yaml(bucket_summary),
        "largest_feature_differences": top_differences,
        "top_loss_sectors": target_sector["losses"],
        "top_gain_sectors": target_sector["gains"],
        "conclusion": infer_conclusion(bucket_summary),
    }


def target_sector_records(sector_breakdown: pd.DataFrame, target_buckets: list[str]) -> dict[str, list[dict[str, Any]]]:
    if sector_breakdown.empty:
        return {"losses": [], "gains": []}
    target = sector_breakdown[sector_breakdown["group_level"] == "sector"].copy()
    target = target[target["history_bucket"].isin(target_buckets)]
    losses = target.sort_values("net_contribution_sum", ascending=True).head(10)
    gains = target.sort_values("net_contribution_sum", ascending=False).head(10)
    return {"losses": records_for_yaml(losses), "gains": records_for_yaml(gains)}


def infer_conclusion(bucket_summary: pd.DataFrame) -> str:
    if bucket_summary.empty:
        return "no_positions"
    short = bucket_summary[bucket_summary["is_target_bucket"]]
    if short.empty:
        return "no_short_history_positions"
    short_contribution = pd.to_numeric(short["net_contribution_sum"], errors="coerce").sum()
    short_win_rate = pd.to_numeric(short["win_rate"], errors="coerce").mean()
    if short_contribution > 0 and short_win_rate >= 0.5:
        return "short_history_contributed_positive_returns"
    if short_contribution < 0:
        return "short_history_was_a_net_drag"
    return "short_history_mixed_or_noisy"


def high_valuation_flags(frame: pd.DataFrame) -> pd.Series:
    flags = pd.Series(False, index=frame.index)
    for column in ["edgar_price_to_sales", "edgar_price_to_book", "edgar_price_to_earnings"]:
        if column not in frame:
            continue
        threshold = numeric_values(frame, column).quantile(0.75)
        if pd.isna(threshold):
            continue
        flags = flags | (pd.to_numeric(frame[column], errors="coerce") >= threshold)
    return flags


def low_tail_flag(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(False, index=frame.index)
    threshold = numeric_values(frame, column).quantile(0.25)
    if pd.isna(threshold):
        return pd.Series(False, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce") <= threshold


def high_tail_flag(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(False, index=frame.index)
    threshold = numeric_values(frame, column).quantile(0.75)
    if pd.isna(threshold):
        return pd.Series(False, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce") >= threshold


def numeric_values(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty or column not in frame:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()


def numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def numeric_mean(frame: pd.DataFrame, column: str) -> float:
    values = numeric_values(frame, column)
    return float(values.mean()) if not values.empty else math.nan


def numeric_sum(frame: pd.DataFrame, column: str) -> float:
    values = numeric_values(frame, column)
    return float(values.sum()) if not values.empty else math.nan


def numeric_min(frame: pd.DataFrame, column: str) -> float:
    values = numeric_values(frame, column)
    return float(values.min()) if not values.empty else math.nan


def numeric_max(frame: pd.DataFrame, column: str) -> float:
    values = numeric_values(frame, column)
    return float(values.max()) if not values.empty else math.nan


def positive_rate(frame: pd.DataFrame, column: str) -> float:
    values = numeric_values(frame, column)
    return float((values > 0).mean()) if not values.empty else math.nan


def bool_rate(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame:
        return math.nan
    values = frame[column].dropna()
    return float(values.astype(bool).mean()) if not values.empty else math.nan


def normalized_group_series(series: pd.Series) -> pd.Series:
    return series.map(lambda value: "UNKNOWN" if pd.isna(value) or not str(value).strip() else str(value).strip())


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


def write_short_history_outputs(result: ShortHistoryReviewResult, paths: dict[str, Path]) -> None:
    outputs = {
        "short_history_bucket_summary": result.bucket_summary,
        "short_history_examples": result.examples,
        "short_history_feature_differences": result.feature_differences,
        "short_history_sector_breakdown": result.sector_breakdown,
    }
    for key, frame in outputs.items():
        if key in paths:
            paths[key].parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(paths[key], index=False)
    if "short_history_review_summary" in paths:
        paths["short_history_review_summary"].write_text(
            yaml.safe_dump(result.yaml_summary, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
