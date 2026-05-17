"""Industry classification and relative feature transforms."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

INDUSTRY_FAILURE_COLUMNS = ["symbol", "error", "detail"]


@dataclass
class IndustryFeatureResult:
    features: pd.DataFrame
    failures: pd.DataFrame
    coverage: dict[str, Any]

    @classmethod
    def empty(cls, paths: dict[str, Path]) -> "IndustryFeatureResult":
        features = pd.DataFrame()
        failures = pd.DataFrame(columns=INDUSTRY_FAILURE_COLUMNS)
        coverage: dict[str, Any] = {}
        if "industry_features" in paths:
            features.to_parquet(paths["industry_features"])
        if "industry_failures" in paths:
            failures.to_csv(paths["industry_failures"], index=False)
        return cls(features=features, failures=failures, coverage=coverage)


def build_industry_features(
    universe: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
    base_features: pd.DataFrame,
) -> IndustryFeatureResult:
    builder = IndustryFeatureBuilder(config)
    result = builder.build(universe, base_features)
    result.features.to_parquet(paths["industry_features"])
    result.failures.to_csv(paths["industry_failures"], index=False)
    return result


class IndustryFeatureBuilder:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.industry_config = config["industry"]
        self.group_level = self.industry_config.get("group_level", "industry")
        self.fallback_group_level = self.industry_config.get("fallback_group_level", "sector")
        self.rank_features = list(self.industry_config.get("rank_features", []))
        self.min_group_size = int(self.industry_config.get("min_group_size", 5))

    def build(self, universe: pd.DataFrame, base_features: pd.DataFrame) -> IndustryFeatureResult:
        failures = self.validate_inputs(universe, base_features)
        if base_features.empty:
            return IndustryFeatureResult(
                features=empty_feature_frame(self.rank_features),
                failures=pd.DataFrame(failures, columns=INDUSTRY_FAILURE_COLUMNS),
                coverage=self.coverage(universe),
            )

        industry_map = build_symbol_industry_map(universe)
        working = base_features.reset_index().rename(columns={"instrument": "symbol"})
        working["symbol"] = working["symbol"].astype(str).str.upper()
        working = working.merge(industry_map, on="symbol", how="left")
        working["datetime"] = pd.to_datetime(working["datetime"])

        mapped_failures = build_missing_industry_failures(working)
        failures.extend(mapped_failures)

        working = add_group_sizes(working, self.group_level, self.fallback_group_level)
        working["effective_group"] = working[self.group_level]
        fallback_mask = working[f"{self.group_level}_group_size"] < self.min_group_size
        working.loc[fallback_mask, "effective_group"] = working.loc[fallback_mask, self.fallback_group_level]
        working["industry_used_sector_fallback"] = fallback_mask.astype(float)

        feature_frame = pd.DataFrame(index=base_features.index)
        feature_frame["industry_group_size"] = working[f"{self.group_level}_group_size"].to_numpy()
        feature_frame["sector_group_size"] = working[f"{self.fallback_group_level}_group_size"].to_numpy()
        feature_frame["industry_used_sector_fallback"] = working["industry_used_sector_fallback"].to_numpy()

        for feature in self.rank_features:
            suffix = feature.removeprefix("edgar_")
            if feature not in working.columns:
                feature_frame[f"industry_rank_{suffix}"] = pd.NA
                feature_frame[f"industry_pct_{suffix}"] = pd.NA
                feature_frame[f"sector_pct_{suffix}"] = pd.NA
                continue

            feature_frame[f"industry_rank_{suffix}"] = (
                working.groupby(["datetime", "effective_group"], dropna=True)[feature]
                .rank(method="average")
                .to_numpy()
            )
            feature_frame[f"industry_pct_{suffix}"] = (
                working.groupby(["datetime", "effective_group"], dropna=True)[feature]
                .rank(method="average", pct=True)
                .to_numpy()
            )
            feature_frame[f"sector_pct_{suffix}"] = (
                working.groupby(["datetime", self.fallback_group_level], dropna=True)[feature]
                .rank(method="average", pct=True)
                .to_numpy()
            )

        feature_frame.index = base_features.index
        feature_frame = feature_frame.sort_index()
        failure_frame = pd.DataFrame(failures, columns=INDUSTRY_FAILURE_COLUMNS).drop_duplicates()
        return IndustryFeatureResult(features=feature_frame, failures=failure_frame, coverage=self.coverage(universe))

    def validate_inputs(self, universe: pd.DataFrame, base_features: pd.DataFrame) -> list[dict[str, Any]]:
        failures: list[dict[str, Any]] = []
        for column in ["symbol", self.group_level, self.fallback_group_level]:
            if column not in universe.columns:
                failures.append({"symbol": None, "error": "missing_universe_column", "detail": column})
        for feature in self.rank_features:
            if feature not in base_features.columns:
                failures.append({"symbol": None, "error": "missing_rank_feature", "detail": feature})
        return failures

    @staticmethod
    def coverage(universe: pd.DataFrame) -> dict[str, Any]:
        sector = clean_group_series(universe.get("sector", pd.Series(index=universe.index, dtype=object)))
        industry = clean_group_series(universe.get("industry", pd.Series(index=universe.index, dtype=object)))
        return {
            "sector_missing_count": int(sector.isna().sum()),
            "industry_missing_count": int(industry.isna().sum()),
            "sector_counts": sector.fillna("UNKNOWN").value_counts().to_dict(),
            "industry_counts": industry.fillna("UNKNOWN").value_counts().head(25).to_dict(),
        }


def build_symbol_industry_map(universe: pd.DataFrame) -> pd.DataFrame:
    frame = universe.copy()
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    frame["sector"] = clean_group_series(frame.get("sector", pd.Series(index=frame.index, dtype=object)))
    frame["industry"] = clean_group_series(frame.get("industry", pd.Series(index=frame.index, dtype=object)))
    return frame[["symbol", "sector", "industry"]].drop_duplicates("symbol")


def clean_group_series(series: pd.Series) -> pd.Series:
    cleaned = series.astype("string").str.strip()
    cleaned = cleaned.replace({"": pd.NA, "nan": pd.NA, "None": pd.NA, "N/A": pd.NA})
    return cleaned


def build_missing_industry_failures(frame: pd.DataFrame) -> list[dict[str, Any]]:
    failures = []
    missing = frame[frame["sector"].isna() | frame["industry"].isna()]
    for symbol in sorted(missing["symbol"].dropna().unique()):
        failures.append(
            {"symbol": symbol, "error": "missing_industry_classification", "detail": "sector_or_industry"}
        )
    return failures


def add_group_sizes(frame: pd.DataFrame, group_level: str, fallback_group_level: str) -> pd.DataFrame:
    working = frame.copy()
    working[f"{group_level}_group_size"] = working.groupby(["datetime", group_level], dropna=True)[
        group_level
    ].transform("size")
    working[f"{fallback_group_level}_group_size"] = working.groupby(
        ["datetime", fallback_group_level], dropna=True
    )[fallback_group_level].transform("size")
    return working


def empty_feature_frame(rank_features: list[str]) -> pd.DataFrame:
    columns = ["industry_group_size", "sector_group_size", "industry_used_sector_fallback"]
    for feature in rank_features:
        suffix = feature.removeprefix("edgar_")
        columns.extend([f"industry_rank_{suffix}", f"industry_pct_{suffix}", f"sector_pct_{suffix}"])
    index = pd.MultiIndex.from_arrays([[], []], names=["datetime", "instrument"])
    return pd.DataFrame(columns=columns, index=index)
