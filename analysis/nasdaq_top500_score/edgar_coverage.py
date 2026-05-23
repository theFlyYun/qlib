"""Coverage and missingness review for SEC EDGAR feature artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


@dataclass
class EdgarCoverageResult:
    summary: dict[str, Any]
    by_year: pd.DataFrame
    by_split: pd.DataFrame
    by_sector: pd.DataFrame
    by_industry: pd.DataFrame
    by_history_bucket: pd.DataFrame
    feature_missingness: pd.DataFrame
    failure_breakdown: pd.DataFrame
    missingness_root_cause: pd.DataFrame
    field_availability_by_year: pd.DataFrame


@dataclass
class EdgarEffectivenessResult:
    summary: dict[str, Any]
    by_feature: pd.DataFrame
    by_year: pd.DataFrame
    by_sector: pd.DataFrame
    quantile_spread: pd.DataFrame


def build_edgar_coverage_review(
    universe: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
    *,
    features: pd.DataFrame | None = None,
    failures: pd.DataFrame | None = None,
    cik_map: pd.DataFrame | None = None,
) -> EdgarCoverageResult:
    features = load_features(paths, features)
    failures = load_csv(paths.get("fundamental_failures"), failures)
    cik_map = load_csv(paths.get("edgar_cik_map"), cik_map)
    universe_symbols = normalize_symbols(universe.get("symbol", pd.Series(dtype=object)))
    mapped_symbols = normalize_symbols(cik_map.get("symbol", pd.Series(dtype=object)))
    feature_symbols = feature_instruments(features)

    row_frame = feature_row_frame(features, config, paths)
    by_year = summarize_group(row_frame, "year")
    by_split = summarize_group(row_frame, "split")
    by_sector = summarize_group(row_frame, "sector")
    by_industry = summarize_group(row_frame, "industry")
    by_history_bucket = summarize_group(row_frame, "history_bucket")
    feature_missingness = build_feature_missingness(features)
    failure_breakdown = build_failure_breakdown(failures)
    missingness_root_cause = build_missingness_root_cause(universe, failures, cik_map, feature_missingness)
    field_availability_by_year = build_field_availability_by_year(features)

    summary = {
        "enabled": True,
        "universe_instrument_count": int(len(universe_symbols)),
        "cik_mapped_count": int(len(mapped_symbols)),
        "feature_instrument_count": int(len(feature_symbols)),
        "feature_row_count": int(len(features)),
        "feature_column_count": int(features.shape[1]),
        "non_null_feature_row_count": int(row_frame["has_any_feature"].sum()) if "has_any_feature" in row_frame else 0,
        "cik_mapping_coverage": safe_ratio(len(mapped_symbols), len(universe_symbols)),
        "feature_instrument_coverage": safe_ratio(len(feature_symbols), len(universe_symbols)),
        "failure_count": int(len(failures)),
        "failure_counts": failure_breakdown.set_index("error")["count"].to_dict() if not failure_breakdown.empty else {},
        "top_missing_features": feature_missingness.head(10).to_dict("records"),
    }

    write_outputs(
        paths,
        summary,
        by_year,
        by_split,
        by_sector,
        by_industry,
        by_history_bucket,
        feature_missingness,
        failure_breakdown,
        missingness_root_cause,
        field_availability_by_year,
    )
    return EdgarCoverageResult(
        summary=summary,
        by_year=by_year,
        by_split=by_split,
        by_sector=by_sector,
        by_industry=by_industry,
        by_history_bucket=by_history_bucket,
        feature_missingness=feature_missingness,
        failure_breakdown=failure_breakdown,
        missingness_root_cause=missingness_root_cause,
        field_availability_by_year=field_availability_by_year,
    )


def build_edgar_effectiveness_review(
    features: pd.DataFrame,
    labels: pd.Series | pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
) -> EdgarEffectivenessResult:
    """Review field-level EDGAR signal quality against the test label.

    This is a diagnostic artifact only. It does not select features from the
    test set or mutate the model input.
    """

    settings = config.get("edgar_effectiveness_review", {})
    min_observations = int(settings.get("min_observations", 100))
    quantiles = int(settings.get("quantiles", 5))
    label_series = normalize_label_series(labels)
    frame = build_effectiveness_frame(features, label_series, config, paths)

    by_feature = build_feature_ic_summary(frame, min_observations)
    by_year = build_feature_group_ic_summary(frame, "year", min_observations)
    by_sector = build_feature_group_ic_summary(frame, "sector", min_observations)
    quantile_spread = build_feature_quantile_spread(frame, quantiles, min_observations)
    summary = build_effectiveness_summary(frame, by_feature, by_sector, quantile_spread, min_observations)

    if "edgar_feature_effectiveness_summary" in paths:
        paths["edgar_feature_effectiveness_summary"].write_text(
            yaml.safe_dump(summary, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    if "edgar_feature_ic_summary" in paths:
        by_feature.to_csv(paths["edgar_feature_ic_summary"], index=False)
    if "edgar_feature_ic_by_year" in paths:
        by_year.to_csv(paths["edgar_feature_ic_by_year"], index=False)
    if "edgar_feature_ic_by_sector" in paths:
        by_sector.to_csv(paths["edgar_feature_ic_by_sector"], index=False)
    if "edgar_feature_quantile_spread" in paths:
        quantile_spread.to_csv(paths["edgar_feature_quantile_spread"], index=False)

    return EdgarEffectivenessResult(
        summary=summary,
        by_feature=by_feature,
        by_year=by_year,
        by_sector=by_sector,
        quantile_spread=quantile_spread,
    )


def load_features(paths: dict[str, Path], features: pd.DataFrame | None) -> pd.DataFrame:
    if features is not None:
        return features
    path = paths.get("fundamental_features_cleaned")
    if path and path.exists():
        return pd.read_parquet(path)
    path = paths.get("fundamental_features")
    if path and path.exists():
        return pd.read_parquet(path)
    index = pd.MultiIndex.from_arrays([[], []], names=["datetime", "instrument"])
    return pd.DataFrame(index=index)


def load_csv(path: Path | None, frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is not None:
        return frame
    if path and path.exists():
        return pd.read_csv(path)
    return pd.DataFrame()


def normalize_symbols(series: pd.Series) -> set[str]:
    if series.empty:
        return set()
    return set(series.astype(str).str.upper().dropna().unique())


def feature_instruments(features: pd.DataFrame) -> set[str]:
    if features.empty:
        return set()
    instruments = features.index.get_level_values("instrument")
    return set(pd.Series(instruments).astype(str).str.upper().unique())


def feature_row_frame(features: pd.DataFrame, config: dict[str, Any], paths: dict[str, Path]) -> pd.DataFrame:
    if features.empty:
        return pd.DataFrame(columns=["datetime", "instrument", "has_any_feature", "year", "split", "sector", "industry", "history_bucket"])
    frame = features.reset_index()[["datetime", "instrument"]].copy()
    frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce").dt.normalize()
    frame["instrument"] = frame["instrument"].astype(str).str.upper()
    frame["has_any_feature"] = features.notna().any(axis=1).to_numpy()
    frame["year"] = frame["datetime"].dt.year.astype("Int64")
    frame["split"] = assign_split(frame["datetime"], config)
    frame = attach_industry(frame, paths.get("industry_master"))
    frame = attach_history_bucket(frame, paths.get("history_buckets_csv"))
    return frame


def assign_split(dates: pd.Series, config: dict[str, Any]) -> pd.Series:
    result = pd.Series("outside", index=dates.index, dtype=object)
    split = config.get("split", {})
    if split.get("method") != "date":
        return result
    for name in ["train", "valid", "test"]:
        segment = split.get(name, {})
        if not segment:
            continue
        start = pd.Timestamp(segment["start"]).normalize()
        end = pd.Timestamp(segment["end"]).normalize()
        result.loc[(dates >= start) & (dates <= end)] = name
    return result


def attach_industry(frame: pd.DataFrame, industry_master_path: Path | None) -> pd.DataFrame:
    working = frame.copy()
    working["sector"] = "UNKNOWN"
    working["industry"] = "UNKNOWN"
    if not industry_master_path or not industry_master_path.exists() or working.empty:
        return working
    master = pd.read_parquet(industry_master_path)
    if master.empty:
        return working
    master = master.copy()
    master["instrument"] = master["instrument"].astype(str).str.upper()
    master["effective_start"] = pd.to_datetime(master["effective_start"], errors="coerce").dt.normalize()
    master["effective_end"] = pd.to_datetime(master["effective_end"], errors="coerce").dt.normalize()
    if "is_pit" in master:
        master = master[master["is_pit"].eq(True)].copy()
    master = master.dropna(subset=["instrument", "effective_start"]).sort_values(["instrument", "effective_start"])

    frames = []
    for instrument, group in working.groupby("instrument", sort=False):
        current = group.sort_values("datetime").drop(columns=["sector", "industry"])
        symbol_master = master[master["instrument"].eq(str(instrument).upper())]
        if symbol_master.empty:
            current["sector"] = "UNKNOWN"
            current["industry"] = "UNKNOWN"
            frames.append(current)
            continue
        matched = pd.merge_asof(
            current,
            symbol_master[["effective_start", "effective_end", "sector", "industry"]].sort_values("effective_start"),
            left_on="datetime",
            right_on="effective_start",
            direction="backward",
        )
        active = matched["effective_start"].notna() & (
            matched["effective_end"].isna() | (matched["datetime"] <= matched["effective_end"])
        )
        matched.loc[~active, ["sector", "industry"]] = "UNKNOWN"
        frames.append(matched.drop(columns=["effective_start", "effective_end"]))
    return pd.concat(frames, ignore_index=True) if frames else working


def attach_history_bucket(frame: pd.DataFrame, history_buckets_path: Path | None) -> pd.DataFrame:
    working = frame.copy()
    working["history_bucket"] = "UNKNOWN"
    if not history_buckets_path or not history_buckets_path.exists():
        return working
    buckets = pd.read_csv(history_buckets_path)
    if buckets.empty or "symbol" not in buckets or "history_bucket" not in buckets:
        return working
    bucket_map = (
        buckets.assign(symbol=buckets["symbol"].astype(str).str.upper())
        .drop_duplicates("symbol", keep="last")
        .set_index("symbol")["history_bucket"]
    )
    working["history_bucket"] = working["instrument"].map(bucket_map).fillna("UNKNOWN")
    return working


def summarize_group(frame: pd.DataFrame, group_column: str) -> pd.DataFrame:
    columns = [group_column, "row_count", "non_null_feature_rows", "coverage_ratio", "instrument_count"]
    if frame.empty or group_column not in frame:
        return pd.DataFrame(columns=columns)
    summary = (
        frame.groupby(group_column, dropna=False)
        .agg(
            row_count=("instrument", "size"),
            non_null_feature_rows=("has_any_feature", "sum"),
            instrument_count=("instrument", "nunique"),
        )
        .reset_index()
    )
    summary["coverage_ratio"] = summary["non_null_feature_rows"] / summary["row_count"].replace(0, pd.NA)
    return summary[columns].sort_values(group_column).reset_index(drop=True)


def build_feature_missingness(features: pd.DataFrame) -> pd.DataFrame:
    columns = ["feature", "row_count", "missing_count", "missing_ratio", "non_null_count"]
    if features.empty:
        return pd.DataFrame(columns=columns)
    row_count = len(features)
    rows = []
    for column in features.columns:
        missing = int(features[column].isna().sum())
        rows.append(
            {
                "feature": column,
                "row_count": row_count,
                "missing_count": missing,
                "missing_ratio": safe_ratio(missing, row_count),
                "non_null_count": row_count - missing,
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values(["missing_ratio", "feature"], ascending=[False, True])


def build_failure_breakdown(failures: pd.DataFrame) -> pd.DataFrame:
    columns = ["error", "count", "symbol_count", "sample_detail"]
    if failures.empty or "error" not in failures:
        return pd.DataFrame(columns=columns)
    rows = []
    for error, group in failures.groupby("error", dropna=False):
        details = group.get("detail", pd.Series(dtype=object)).dropna().astype(str)
        rows.append(
            {
                "error": error,
                "count": int(len(group)),
                "symbol_count": int(group.get("symbol", pd.Series(dtype=object)).dropna().astype(str).nunique()),
                "sample_detail": details.iloc[0] if not details.empty else "",
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values("count", ascending=False).reset_index(drop=True)


def build_missingness_root_cause(
    universe: pd.DataFrame,
    failures: pd.DataFrame,
    cik_map: pd.DataFrame,
    feature_missingness: pd.DataFrame,
) -> pd.DataFrame:
    columns = ["symbol", "cik", "field", "root_cause", "detail"]
    rows: list[dict[str, Any]] = []
    mapped = normalize_symbols(cik_map.get("symbol", pd.Series(dtype=object)))
    if not universe.empty and "symbol" in universe:
        for symbol in sorted(normalize_symbols(universe["symbol"]) - mapped):
            rows.append(
                {
                    "symbol": symbol,
                    "cik": None,
                    "field": None,
                    "root_cause": "missing_cik_mapping",
                    "detail": "instrument is in universe but no SEC CIK mapping was produced",
                }
            )
    if not failures.empty and {"symbol", "error"}.issubset(failures.columns):
        for row in failures.to_dict("records"):
            error = str(row.get("error", ""))
            if error == "missing_fields":
                fields = [item.strip() for item in str(row.get("detail", "")).split(",") if item.strip()]
                for field in fields:
                    rows.append(
                        {
                            "symbol": row.get("symbol"),
                            "cik": row.get("cik"),
                            "field": field,
                            "root_cause": "missing_or_unrecognized_xbrl_tag",
                            "detail": "field missing for all parsed filings; may be absent or require another tag alias",
                        }
                    )
            elif error in {"insufficient_filings", "no_effective_filing_dates", "missing_price", "api_or_parse_error"}:
                rows.append(
                    {
                        "symbol": row.get("symbol"),
                        "cik": row.get("cik"),
                        "field": None,
                        "root_cause": error,
                        "detail": row.get("detail"),
                    }
                )
    if not feature_missingness.empty:
        for row in feature_missingness.head(20).to_dict("records"):
            rows.append(
                {
                    "symbol": None,
                    "cik": None,
                    "field": row.get("feature"),
                    "root_cause": "high_feature_missingness",
                    "detail": f"missing_ratio={row.get('missing_ratio')}",
                }
            )
    return pd.DataFrame(rows, columns=columns)


def build_field_availability_by_year(features: pd.DataFrame) -> pd.DataFrame:
    columns = ["year", "feature", "row_count", "non_null_count", "availability_ratio"]
    if features.empty:
        return pd.DataFrame(columns=columns)
    frame = features.copy()
    dates = pd.to_datetime(frame.index.get_level_values("datetime"), errors="coerce")
    frame = frame.assign(year=dates.year)
    rows = []
    for year, group in frame.groupby("year", dropna=True):
        row_count = len(group)
        for feature in features.columns:
            non_null = int(group[feature].notna().sum())
            rows.append(
                {
                    "year": int(year),
                    "feature": feature,
                    "row_count": int(row_count),
                    "non_null_count": non_null,
                    "availability_ratio": safe_ratio(non_null, row_count),
                }
            )
    return pd.DataFrame(rows, columns=columns).sort_values(["year", "feature"]).reset_index(drop=True)


def normalize_label_series(labels: pd.Series | pd.DataFrame) -> pd.Series:
    if isinstance(labels, pd.DataFrame):
        label_series = labels.iloc[:, 0] if labels.shape[1] else pd.Series(dtype=float)
    else:
        label_series = labels
    if label_series.empty:
        return pd.Series(dtype=float, name="label")
    normalized = pd.to_numeric(label_series, errors="coerce").copy()
    normalized.name = "label"
    return normalized


def build_effectiveness_frame(
    features: pd.DataFrame,
    labels: pd.Series,
    config: dict[str, Any],
    paths: dict[str, Path],
) -> pd.DataFrame:
    if features.empty or labels.empty:
        return pd.DataFrame(columns=["datetime", "instrument", "label", "year", "split", "sector", "industry"])
    feature_columns = [column for column in features.columns if str(column).startswith("edgar_")]
    if not feature_columns:
        return pd.DataFrame(columns=["datetime", "instrument", "label", "year", "split", "sector", "industry"])
    aligned = pd.concat([features[feature_columns], labels], axis=1, join="inner").dropna(subset=["label"])
    if aligned.empty:
        return pd.DataFrame(columns=["datetime", "instrument", "label", "year", "split", "sector", "industry"])
    frame = aligned.reset_index().copy()
    frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce").dt.normalize()
    frame["instrument"] = frame["instrument"].astype(str).str.upper()
    frame["year"] = frame["datetime"].dt.year.astype("Int64")
    frame["split"] = assign_split(frame["datetime"], config)
    frame = attach_industry(frame, paths.get("industry_master"))
    for column in feature_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["label"] = pd.to_numeric(frame["label"], errors="coerce")
    return frame.dropna(subset=["datetime", "instrument", "label"])


def build_feature_ic_summary(frame: pd.DataFrame, min_observations: int) -> pd.DataFrame:
    columns = [
        "feature",
        "feature_group",
        "observation_count",
        "date_count",
        "coverage_ratio",
        "ic_mean",
        "rank_ic_mean",
        "positive_ic_ratio",
        "positive_rank_ic_ratio",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    feature_groups = feature_group_lookup()
    row_count = len(frame)
    rows = []
    for feature in edgar_feature_columns(frame):
        rows.append(feature_ic_record(frame, feature, min_observations, row_count, feature_groups.get(feature, "other")))
    return pd.DataFrame(rows, columns=columns).sort_values(["rank_ic_mean", "ic_mean"], ascending=[False, False]).reset_index(drop=True)


def build_feature_group_ic_summary(frame: pd.DataFrame, group_column: str, min_observations: int) -> pd.DataFrame:
    columns = [
        group_column,
        "feature",
        "feature_group",
        "observation_count",
        "date_count",
        "ic_mean",
        "rank_ic_mean",
        "positive_rank_ic_ratio",
    ]
    if frame.empty or group_column not in frame:
        return pd.DataFrame(columns=columns)
    feature_groups = feature_group_lookup()
    rows = []
    for group_value, group_frame in frame.groupby(group_column, dropna=False):
        for feature in edgar_feature_columns(group_frame):
            record = feature_ic_record(group_frame, feature, min_observations, len(group_frame), feature_groups.get(feature, "other"))
            rows.append(
                {
                    group_column: group_value,
                    "feature": feature,
                    "feature_group": record["feature_group"],
                    "observation_count": record["observation_count"],
                    "date_count": record["date_count"],
                    "ic_mean": record["ic_mean"],
                    "rank_ic_mean": record["rank_ic_mean"],
                    "positive_rank_ic_ratio": record["positive_rank_ic_ratio"],
                }
            )
    return pd.DataFrame(rows, columns=columns).sort_values([group_column, "rank_ic_mean"], ascending=[True, False]).reset_index(drop=True)


def build_feature_quantile_spread(frame: pd.DataFrame, quantiles: int, min_observations: int) -> pd.DataFrame:
    columns = [
        "feature",
        "feature_group",
        "observation_count",
        "date_count",
        "bottom_quantile_label_mean",
        "top_quantile_label_mean",
        "top_bottom_spread",
        "top_beats_bottom_ratio",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    feature_groups = feature_group_lookup()
    rows = []
    for feature in edgar_feature_columns(frame):
        usable = frame[["datetime", feature, "label"]].dropna()
        if len(usable) < min_observations:
            rows.append(empty_quantile_record(feature, feature_groups.get(feature, "other"), len(usable), 0))
            continue
        daily_rows = []
        for date, group in usable.groupby("datetime", sort=True):
            if len(group) < max(quantiles, 3) or group[feature].nunique(dropna=True) < 2:
                continue
            ranks = group[feature].rank(method="first", pct=True)
            bucket = ((ranks * quantiles).clip(lower=1, upper=quantiles)).astype(int)
            bottom = group.loc[bucket.eq(1), "label"]
            top = group.loc[bucket.eq(quantiles), "label"]
            if bottom.empty or top.empty:
                continue
            bottom_mean = float(bottom.mean())
            top_mean = float(top.mean())
            daily_rows.append(
                {
                    "datetime": date,
                    "bottom": bottom_mean,
                    "top": top_mean,
                    "spread": top_mean - bottom_mean,
                }
            )
        if not daily_rows:
            rows.append(empty_quantile_record(feature, feature_groups.get(feature, "other"), len(usable), 0))
            continue
        daily = pd.DataFrame(daily_rows)
        rows.append(
            {
                "feature": feature,
                "feature_group": feature_groups.get(feature, "other"),
                "observation_count": int(len(usable)),
                "date_count": int(len(daily)),
                "bottom_quantile_label_mean": float(daily["bottom"].mean()),
                "top_quantile_label_mean": float(daily["top"].mean()),
                "top_bottom_spread": float(daily["spread"].mean()),
                "top_beats_bottom_ratio": float((daily["spread"] > 0).mean()),
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values("top_bottom_spread", ascending=False).reset_index(drop=True)


def feature_ic_record(
    frame: pd.DataFrame,
    feature: str,
    min_observations: int,
    denominator: int,
    feature_group: str,
) -> dict[str, Any]:
    usable = frame[["datetime", feature, "label"]].dropna()
    if len(usable) < min_observations:
        return {
            "feature": feature,
            "feature_group": feature_group,
            "observation_count": int(len(usable)),
            "date_count": 0,
            "coverage_ratio": safe_ratio(len(usable), denominator),
            "ic_mean": pd.NA,
            "rank_ic_mean": pd.NA,
            "positive_ic_ratio": pd.NA,
            "positive_rank_ic_ratio": pd.NA,
        }
    daily = []
    for date, group in usable.groupby("datetime", sort=True):
        if len(group) < 3:
            continue
        ic = safe_corr(group[feature], group["label"], method="pearson")
        rank_ic = safe_corr(group[feature], group["label"], method="spearman")
        if pd.isna(ic) and pd.isna(rank_ic):
            continue
        daily.append({"datetime": date, "ic": ic, "rank_ic": rank_ic})
    if not daily:
        date_count = 0
        ic_mean = rank_ic_mean = positive_ic_ratio = positive_rank_ic_ratio = pd.NA
    else:
        daily_frame = pd.DataFrame(daily)
        date_count = int(len(daily_frame))
        ic_mean = nullable_mean(daily_frame["ic"])
        rank_ic_mean = nullable_mean(daily_frame["rank_ic"])
        positive_ic_ratio = nullable_positive_ratio(daily_frame["ic"])
        positive_rank_ic_ratio = nullable_positive_ratio(daily_frame["rank_ic"])
    return {
        "feature": feature,
        "feature_group": feature_group,
        "observation_count": int(len(usable)),
        "date_count": date_count,
        "coverage_ratio": safe_ratio(len(usable), denominator),
        "ic_mean": ic_mean,
        "rank_ic_mean": rank_ic_mean,
        "positive_ic_ratio": positive_ic_ratio,
        "positive_rank_ic_ratio": positive_rank_ic_ratio,
    }


def build_effectiveness_summary(
    frame: pd.DataFrame,
    by_feature: pd.DataFrame,
    by_sector: pd.DataFrame,
    quantile_spread: pd.DataFrame,
    min_observations: int,
) -> dict[str, Any]:
    usable_features = by_feature[pd.to_numeric(by_feature.get("rank_ic_mean", pd.Series(dtype=float)), errors="coerce").notna()]
    useful = usable_features[
        (pd.to_numeric(usable_features["rank_ic_mean"], errors="coerce") > 0)
        & (pd.to_numeric(usable_features["positive_rank_ic_ratio"], errors="coerce") >= 0.5)
    ]
    return {
        "enabled": True,
        "row_count": int(len(frame)),
        "feature_count": int(len(edgar_feature_columns(frame))) if not frame.empty else 0,
        "min_observations": int(min_observations),
        "usable_feature_count": int(len(usable_features)),
        "positive_rank_ic_feature_count": int(len(useful)),
        "top_rank_ic_features": top_records(by_feature, "rank_ic_mean", 10),
        "top_quantile_spread_features": top_records(quantile_spread, "top_bottom_spread", 10),
        "weakest_rank_ic_features": top_records(by_feature, "rank_ic_mean", 10, ascending=True),
        "sector_rows": int(len(by_sector)),
        "interpretation_rule": "字段有效性是研究诊断，不会自动用 test 表现筛字段；默认字段需经 ablation 再进入主线。",
    }


def empty_quantile_record(feature: str, feature_group: str, observation_count: int, date_count: int) -> dict[str, Any]:
    return {
        "feature": feature,
        "feature_group": feature_group,
        "observation_count": int(observation_count),
        "date_count": int(date_count),
        "bottom_quantile_label_mean": pd.NA,
        "top_quantile_label_mean": pd.NA,
        "top_bottom_spread": pd.NA,
        "top_beats_bottom_ratio": pd.NA,
    }


def feature_group_lookup() -> dict[str, str]:
    lookup = {}
    for group, names in default_feature_groups().items():
        for name in names:
            lookup[f"edgar_{name}"] = group
    return lookup


def default_feature_groups() -> dict[str, list[str]]:
    return {
        "profitability_quality": [
            "gross_margin",
            "operating_margin",
            "net_margin",
            "roe",
            "roa",
            "operating_cash_flow_ttm",
            "free_cash_flow_ttm",
            "cfo_to_net_income",
            "fcf_margin",
        ],
        "growth": ["revenue_yoy_growth", "net_income_yoy_growth", "eps_yoy_growth", "assets_yoy_growth"],
        "balance_sheet_stability": [
            "revenue_ttm",
            "assets",
            "equity",
            "cash",
            "shares_diluted",
            "liabilities_to_assets",
            "cash_to_assets",
        ],
        "valuation": ["price_to_sales", "price_to_book", "price_to_earnings", "market_cap_to_fcf"],
        "filing_state": [
            "days_since_last_10q",
            "days_since_last_10k",
            "filing_lag_days",
            "is_recent_filing",
            "is_amended_filing",
        ],
        "coverage_state": [
            "has_profitability_quality",
            "has_valuation",
            "has_growth",
            "has_balance_sheet_stability",
            "days_since_revenue",
            "days_since_net_income",
            "days_since_operating_cash_flow",
            "days_since_assets",
            "days_since_equity",
        ],
    }


def edgar_feature_columns(frame: pd.DataFrame) -> list[str]:
    return [column for column in frame.columns if str(column).startswith("edgar_")]


def safe_corr(left: pd.Series, right: pd.Series, *, method: str) -> float | pd.NA:
    left_numeric = pd.to_numeric(left, errors="coerce")
    right_numeric = pd.to_numeric(right, errors="coerce")
    valid = left_numeric.notna() & right_numeric.notna()
    if int(valid.sum()) < 3:
        return pd.NA
    if left_numeric[valid].nunique(dropna=True) < 2 or right_numeric[valid].nunique(dropna=True) < 2:
        return pd.NA
    value = left_numeric[valid].corr(right_numeric[valid], method=method)
    return float(value) if not pd.isna(value) else pd.NA


def nullable_mean(series: pd.Series) -> float | pd.NA:
    numeric_series = pd.to_numeric(series, errors="coerce").dropna()
    return float(numeric_series.mean()) if not numeric_series.empty else pd.NA


def nullable_positive_ratio(series: pd.Series) -> float | pd.NA:
    numeric_series = pd.to_numeric(series, errors="coerce").dropna()
    return float((numeric_series > 0).mean()) if not numeric_series.empty else pd.NA


def top_records(frame: pd.DataFrame, column: str, limit: int, *, ascending: bool = False) -> list[dict[str, Any]]:
    if frame.empty or column not in frame:
        return []
    working = frame.copy()
    working[column] = pd.to_numeric(working[column], errors="coerce")
    working = working.dropna(subset=[column])
    if working.empty:
        return []
    return [native_record(record) for record in working.sort_values(column, ascending=ascending).head(limit).to_dict("records")]


def native_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = {}
    for key, value in record.items():
        if pd.isna(value):
            normalized[key] = None
        elif hasattr(value, "item"):
            normalized[key] = value.item()
        else:
            normalized[key] = value
    return normalized


def safe_ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def write_outputs(
    paths: dict[str, Path],
    summary: dict[str, Any],
    by_year: pd.DataFrame,
    by_split: pd.DataFrame,
    by_sector: pd.DataFrame,
    by_industry: pd.DataFrame,
    by_history_bucket: pd.DataFrame,
    feature_missingness: pd.DataFrame,
    failure_breakdown: pd.DataFrame,
    missingness_root_cause: pd.DataFrame,
    field_availability_by_year: pd.DataFrame,
) -> None:
    paths["edgar_coverage_summary"].write_text(
        yaml.safe_dump(summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    by_year.to_csv(paths["edgar_coverage_by_year"], index=False)
    by_split.to_csv(paths["edgar_coverage_by_split"], index=False)
    by_sector.to_csv(paths["edgar_coverage_by_sector"], index=False)
    by_industry.to_csv(paths["edgar_coverage_by_industry"], index=False)
    by_history_bucket.to_csv(paths["edgar_coverage_by_history_bucket"], index=False)
    feature_missingness.to_csv(paths["edgar_feature_missingness"], index=False)
    failure_breakdown.to_csv(paths["edgar_failure_breakdown"], index=False)
    if "edgar_missingness_root_cause" in paths:
        missingness_root_cause.to_csv(paths["edgar_missingness_root_cause"], index=False)
    if "edgar_field_availability_by_year" in paths:
        field_availability_by_year.to_csv(paths["edgar_field_availability_by_year"], index=False)
