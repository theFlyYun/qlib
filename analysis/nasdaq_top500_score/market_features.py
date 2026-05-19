"""Market-derived point-in-time features for Nasdaq/Qlib experiments."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    from .industry.features import build_symbol_industry_map
except ImportError:  # pragma: no cover - supports running the pipeline as a script.
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

    builder = MarketFeatureBuilder(config, paths)
    result = builder.build(universe)
    result.features.to_parquet(paths["market_features"])
    result.failures.to_csv(paths["market_feature_failures"], index=False)
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

    def build(self, universe: pd.DataFrame) -> MarketFeatureResult:
        universe_symbols = sorted(universe["symbol"].astype(str).str.upper().dropna().unique())
        frames = []
        failures: list[dict[str, Any]] = []
        for symbol in universe_symbols:
            csv_path = self.paths["source_dir"] / f"{symbol}.csv"
            if not csv_path.exists():
                failures.append({"symbol": symbol, "error": "missing_price_csv", "detail": str(csv_path)})
                continue
            symbol_frame, symbol_failures = self.build_symbol_features(csv_path, symbol)
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
        group_map = build_symbol_industry_map(universe).rename(columns={"symbol": "instrument"})
        working = frame.merge(group_map, on="instrument", how="left")
        missing = working[working["sector"].isna() | working["industry"].isna()]
        for symbol in sorted(missing["instrument"].dropna().unique()):
            failures.append({"symbol": symbol, "error": "missing_industry_classification", "detail": "sector_or_industry"})
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
        }


def feature_columns(frame: pd.DataFrame) -> pd.DataFrame:
    columns = ["datetime", "instrument"]
    columns.extend(column for column in frame.columns if column.startswith("market_"))
    return frame.loc[:, columns]


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
