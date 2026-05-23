"""Market-derived point-in-time features for Nasdaq/Qlib experiments."""

from __future__ import annotations

import concurrent.futures
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    from .artifact_cache import (
        artifact_cache_dir,
        artifact_cache_enabled,
        read_cached_feature_result,
        stable_hash,
        write_cached_feature_result,
    )
    from .industry.features import build_symbol_industry_map
except ImportError:  # pragma: no cover - supports running the pipeline as a script.
    from artifact_cache import (
        artifact_cache_dir,
        artifact_cache_enabled,
        read_cached_feature_result,
        stable_hash,
        write_cached_feature_result,
    )
    from industry.features import build_symbol_industry_map


MARKET_FAILURE_COLUMNS = ["symbol", "error", "detail"]
DEFAULT_DOLLAR_VOLUME_WINDOWS = [20, 60]
DEFAULT_MOMENTUM_WINDOWS = [20, 60, 120]
DEFAULT_VOLATILITY_WINDOWS = [20, 60]
DEFAULT_RELATIVE_FEATURES = [
    "log_close",
    "log_avg_dollar_volume_20d",
    "log_median_dollar_volume_60d",
    "momentum_20d",
    "momentum_60d",
    "momentum_120d",
    "volatility_20d",
    "volatility_60d",
    "history_rows_asof",
]


@dataclass
class MarketFeatureResult:
    features: pd.DataFrame
    failures: pd.DataFrame
    coverage: dict[str, Any]

    @classmethod
    def empty(cls, paths: dict[str, Path]) -> "MarketFeatureResult":
        features = pd.DataFrame()
        failures = pd.DataFrame(columns=MARKET_FAILURE_COLUMNS)
        coverage: dict[str, Any] = {}
        if "market_features" in paths:
            features.to_parquet(paths["market_features"])
        if "market_feature_failures" in paths:
            failures.to_csv(paths["market_feature_failures"], index=False)
        return cls(features=features, failures=failures, coverage=coverage)


def build_market_feature_frame(
    universe: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
) -> MarketFeatureResult:
    feature_config = config.get("market_features", {})
    if not feature_config or not feature_config.get("enabled", False):
        return MarketFeatureResult.empty(paths)

    cache_paths = market_feature_cache_paths(universe, config, paths)
    if cache_paths:
        cached = read_cached_feature_result(
            features_path=cache_paths["features"],
            failures_path=cache_paths["failures"],
            coverage_path=cache_paths["coverage"],
            failure_columns=MARKET_FAILURE_COLUMNS,
        )
        if cached:
            features, failures, coverage = cached
            features.to_parquet(paths["market_features"])
            failures.to_csv(paths["market_feature_failures"], index=False)
            return MarketFeatureResult(features=features, failures=failures, coverage=coverage)

    builder = MarketFeatureBuilder(config, paths)
    result = builder.build(universe)
    result.features.to_parquet(paths["market_features"])
    result.failures.to_csv(paths["market_feature_failures"], index=False)
    if cache_paths:
        write_cached_feature_result(
            features_source=paths["market_features"],
            failures_source=paths["market_feature_failures"],
            coverage=result.coverage,
            features_path=cache_paths["features"],
            failures_path=cache_paths["failures"],
            coverage_path=cache_paths["coverage"],
        )
    return result


class MarketFeatureBuilder:
    def __init__(self, config: dict[str, Any], paths: dict[str, Path]) -> None:
        self.config = config
        self.paths = paths
        self.feature_config = config.get("market_features", {})
        self.dollar_volume_windows = positive_ints(
            self.feature_config.get("dollar_volume_windows", DEFAULT_DOLLAR_VOLUME_WINDOWS)
        )
        self.momentum_windows = positive_ints(self.feature_config.get("momentum_windows", DEFAULT_MOMENTUM_WINDOWS))
        self.volatility_windows = positive_ints(
            self.feature_config.get("volatility_windows", DEFAULT_VOLATILITY_WINDOWS)
        )
        self.group_levels = list(self.feature_config.get("group_levels", ["sector", "industry"]))
        self.relative_features = list(self.feature_config.get("relative_features", DEFAULT_RELATIVE_FEATURES))
        self.min_group_size = int(self.feature_config.get("min_group_size", 5))
        self.workers = int(config.get("runtime", {}).get("market_feature_workers", self.feature_config.get("workers", 1)))

    def build(self, universe: pd.DataFrame) -> MarketFeatureResult:
        universe_symbols = sorted(universe["symbol"].astype(str).str.upper().dropna().unique())
        frames = []
        failures: list[dict[str, Any]] = []
        tasks = [(symbol, self.paths["source_dir"] / f"{symbol}.csv") for symbol in universe_symbols]
        if self.workers > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as executor:
                futures = {
                    executor.submit(self.build_symbol_features_from_task, task): task[0]
                    for task in tasks
                }
                for future in concurrent.futures.as_completed(futures):
                    symbol_frame, symbol_failures = future.result()
                    failures.extend(symbol_failures)
                    if not symbol_frame.empty:
                        frames.append(symbol_frame)
        else:
            for task in tasks:
                symbol_frame, symbol_failures = self.build_symbol_features_from_task(task)
                failures.extend(symbol_failures)
                if not symbol_frame.empty:
                    frames.append(symbol_frame)

        if not frames:
            features = empty_market_frame(self.relative_features, self.group_levels)
            failure_frame = pd.DataFrame(failures, columns=MARKET_FAILURE_COLUMNS).drop_duplicates()
            return MarketFeatureResult(features=features, failures=failure_frame, coverage=self.coverage(universe, features))

        working = pd.concat(frames, ignore_index=True)
        working = self.attach_groups(working, universe, failures)
        working = self.add_relative_features(working, failures)
        features = feature_columns(working).copy()
        features = features.set_index(["datetime", "instrument"]).sort_index()
        features = features.apply(pd.to_numeric, errors="coerce")
        failure_frame = pd.DataFrame(failures, columns=MARKET_FAILURE_COLUMNS).drop_duplicates()
        return MarketFeatureResult(features=features, failures=failure_frame, coverage=self.coverage(universe, features))

    def build_symbol_features(self, csv_path: Path, symbol: str) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        failures = []
        frame = pd.read_csv(csv_path)
        required = ["date", "close", "volume"]
        missing = [column for column in required if column not in frame.columns]
        if missing:
            return pd.DataFrame(), [
                {"symbol": symbol, "error": "missing_price_column", "detail": ",".join(missing)}
            ]

        price_column = "vwap" if "vwap" in frame.columns else "close"
        working = frame.copy()
        working["datetime"] = pd.to_datetime(working["date"], errors="coerce").dt.normalize()
        working["close"] = pd.to_numeric(working["close"], errors="coerce")
        working[price_column] = pd.to_numeric(working[price_column], errors="coerce")
        working["volume"] = pd.to_numeric(working["volume"], errors="coerce")
        working = working.dropna(subset=["datetime", "close", price_column, "volume"]).sort_values("datetime")
        working = working[working["close"] > 0].copy()
        if working.empty:
            return pd.DataFrame(), [{"symbol": symbol, "error": "no_usable_price_rows", "detail": csv_path.name}]

        working["instrument"] = symbol
        working["market_log_close"] = np.log(working["close"])
        working["market_dollar_volume"] = working[price_column] * working["volume"]
        working["market_history_rows_asof"] = np.arange(1, len(working) + 1, dtype=float)
        working["market_age_years_asof"] = working["market_history_rows_asof"] / 252.0
        returns = working["close"].pct_change()
        for window in self.dollar_volume_windows:
            avg = working["market_dollar_volume"].rolling(window, min_periods=window).mean()
            median = working["market_dollar_volume"].rolling(window, min_periods=window).median()
            working[f"market_log_avg_dollar_volume_{window}d"] = np.log1p(avg)
            working[f"market_log_median_dollar_volume_{window}d"] = np.log1p(median)
        for window in self.momentum_windows:
            working[f"market_momentum_{window}d"] = working["close"] / working["close"].shift(window) - 1.0
        for window in self.volatility_windows:
            working[f"market_volatility_{window}d"] = returns.rolling(window, min_periods=window).std() * math.sqrt(252)
        return working, failures

    def attach_groups(
        self,
        frame: pd.DataFrame,
        universe: pd.DataFrame,
        failures: list[dict[str, Any]],
    ) -> pd.DataFrame:
        industry_master = read_industry_master(self.paths.get("industry_master"))
        if not industry_master.empty:
            return self.attach_pit_groups(frame, industry_master, failures)

        group_map = build_symbol_industry_map(universe).rename(columns={"symbol": "instrument"})
        working = frame.merge(group_map, on="instrument", how="left")
        missing = working[working["sector"].isna() | working["industry"].isna()]
        for symbol in sorted(missing["instrument"].dropna().unique()):
            failures.append({"symbol": symbol, "error": "missing_industry_classification", "detail": "sector_or_industry"})
        return working

    def attach_pit_groups(
        self,
        frame: pd.DataFrame,
        industry_master: pd.DataFrame,
        failures: list[dict[str, Any]],
    ) -> pd.DataFrame:
        master = industry_master.copy()
        master["instrument"] = master["instrument"].astype(str).str.upper()
        master["effective_start"] = pd.to_datetime(master["effective_start"], errors="coerce").dt.normalize()
        master["effective_end"] = pd.to_datetime(master["effective_end"], errors="coerce").dt.normalize()
        if "is_pit" in master:
            master = master[master["is_pit"].eq(True)].copy()
        master = master.dropna(subset=["instrument", "effective_start"])
        if master.empty:
            failures.append({"symbol": None, "error": "empty_industry_master", "detail": "no_pit_rows"})
            return self.attach_groups_without_pit(frame, failures)

        frames = []
        for symbol, symbol_frame in frame.groupby("instrument", sort=False):
            symbol_text = str(symbol).upper()
            symbol_master = master[master["instrument"].eq(symbol_text)].sort_values("effective_start")
            if symbol_master.empty:
                failures.append({"symbol": symbol_text, "error": "missing_pit_industry_mapping", "detail": "industry_master"})
                current = symbol_frame.copy()
                current["sector"] = pd.NA
                current["industry"] = pd.NA
                frames.append(current)
                continue
            current = symbol_frame.sort_values("datetime").copy()
            matched = pd.merge_asof(
                current,
                symbol_master[["effective_start", "effective_end", "sector", "industry"]],
                left_on="datetime",
                right_on="effective_start",
                direction="backward",
            )
            active = matched["effective_start"].notna() & (
                matched["effective_end"].isna() | (matched["datetime"] <= matched["effective_end"])
            )
            matched.loc[~active, ["sector", "industry"]] = pd.NA
            frames.append(matched.drop(columns=["effective_start", "effective_end"]))
        return pd.concat(frames, ignore_index=True) if frames else frame

    def attach_groups_without_pit(self, frame: pd.DataFrame, failures: list[dict[str, Any]]) -> pd.DataFrame:
        working = frame.copy()
        working["sector"] = pd.NA
        working["industry"] = pd.NA
        return working

    def add_relative_features(
        self,
        frame: pd.DataFrame,
        failures: list[dict[str, Any]],
    ) -> pd.DataFrame:
        working = frame.copy()
        for feature in self.relative_features:
            column = f"market_{feature}"
            if column not in working.columns:
                failures.append({"symbol": None, "error": "missing_relative_feature", "detail": column})
                continue
            for group_level in self.group_levels:
                size_column = f"market_{group_level}_group_size"
                if group_level not in working.columns:
                    failures.append({"symbol": None, "error": "missing_group_level", "detail": group_level})
                    continue
                if size_column not in working:
                    working[size_column] = working.groupby(["datetime", group_level], dropna=True)[group_level].transform("size")
                pct_column = f"market_{group_level}_pct_{feature}"
                rank = working.groupby(["datetime", group_level], dropna=True)[column].rank(method="average", pct=True)
                working[pct_column] = rank.where(working[size_column] >= self.min_group_size)
        return working

    def coverage(self, universe: pd.DataFrame, features: pd.DataFrame) -> dict[str, Any]:
        return {
            "enabled": True,
            "symbol_count": int(features.index.get_level_values("instrument").nunique()) if not features.empty else 0,
            "row_count": int(len(features)),
            "feature_count": int(features.shape[1]),
            "group_levels": self.group_levels,
            "relative_features": self.relative_features,
            "min_group_size": self.min_group_size,
            "universe_count": int(len(universe)),
            "workers": self.workers,
        }

    def build_symbol_features_from_task(self, task: tuple[str, Path]) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        symbol, csv_path = task
        if not csv_path.exists():
            return pd.DataFrame(), [{"symbol": symbol, "error": "missing_price_csv", "detail": str(csv_path)}]
        return self.build_symbol_features(csv_path, symbol)


def feature_columns(frame: pd.DataFrame) -> pd.DataFrame:
    columns = ["datetime", "instrument"]
    columns.extend(column for column in frame.columns if column.startswith("market_"))
    return frame.loc[:, columns]


def read_industry_master(path: Path | None) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame()
    try:
        frame = pd.read_parquet(path)
    except (OSError, ValueError):
        return pd.DataFrame()
    required = {"instrument", "effective_start", "effective_end", "sector", "industry"}
    if frame.empty or not required.issubset(frame.columns):
        return pd.DataFrame()
    return frame


def positive_ints(values: list[Any]) -> list[int]:
    output = sorted({int(value) for value in values})
    if any(value <= 0 for value in output):
        raise ValueError("market feature windows must be positive")
    return output


def empty_market_frame(relative_features: list[str], group_levels: list[str]) -> pd.DataFrame:
    columns = [
        "market_log_close",
        "market_dollar_volume",
        "market_history_rows_asof",
        "market_age_years_asof",
    ]
    for group_level in group_levels:
        columns.append(f"market_{group_level}_group_size")
        for feature in relative_features:
            columns.append(f"market_{group_level}_pct_{feature}")
    index = pd.MultiIndex.from_arrays([[], []], names=["datetime", "instrument"])
    return pd.DataFrame(columns=columns, index=index)


def market_feature_cache_paths(
    universe: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
) -> dict[str, Path] | None:
    default_enabled = config.get("data", {}).get("source") == "crsp"
    if not artifact_cache_enabled(config, "market_features", default=default_enabled):
        return None
    payload = {
        "data": config.get("data", {}),
        "universe": {
            "symbol_count": int(universe["symbol"].nunique()) if "symbol" in universe else len(universe),
            "symbols_hash": stable_hash({"symbols": sorted(universe["symbol"].astype(str).str.upper().tolist())})
            if "symbol" in universe
            else None,
        },
        "crsp": {
            key: config.get("crsp", {}).get(key)
            for key in ["label_horizon_days", "label_only_member_dates", "major_exchanges", "exclude_name_terms"]
        },
        "market_features": config.get("market_features", {}),
        "industry_mapping": market_industry_mapping_cache_fingerprint(paths),
    }
    key = stable_hash(payload)
    root = artifact_cache_dir(config, paths, "market_features")
    return {
        "features": root / f"{key}_features.parquet",
        "failures": root / f"{key}_failures.csv",
        "coverage": root / f"{key}_coverage.yaml",
    }


def market_industry_mapping_cache_fingerprint(paths: dict[str, Path]) -> dict[str, Any]:
    summary_path = paths.get("industry_mapping_summary")
    master_path = paths.get("industry_master")
    fingerprint: dict[str, Any] = {
        "summary_exists": bool(summary_path and summary_path.exists()),
        "master_exists": bool(master_path and master_path.exists()),
    }
    if summary_path and summary_path.exists():
        fingerprint["summary_hash"] = stable_hash({"summary": summary_path.read_text(encoding="utf-8")})
    if master_path and master_path.exists():
        stat = master_path.stat()
        fingerprint["master_size"] = int(stat.st_size)
    return fingerprint
