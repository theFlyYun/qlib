"""Macro interaction feature builder.

The macro variables are market-wide state variables.  This module turns them
into stock-level features by crossing them with valuation, balance-sheet,
market-relative, or sector-flag features.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from .artifact_cache import (
        artifact_cache_dir,
        artifact_cache_enabled,
        read_cached_feature_result,
        stable_hash,
        write_cached_feature_result,
    )
except ImportError:  # pragma: no cover - supports running the pipeline as a script.
    from artifact_cache import (
        artifact_cache_dir,
        artifact_cache_enabled,
        read_cached_feature_result,
        stable_hash,
        write_cached_feature_result,
    )


INTERACTION_FAILURE_COLUMNS = ["name", "left", "right", "error", "detail"]

DEFAULT_INTERACTIONS: list[dict[str, Any]] = [
    {
        "name": "macro_x_vix_zscore_momentum_20d",
        "left": "macro_vix_zscore_60d",
        "right": "market_sector_pct_momentum_20d",
    },
    {
        "name": "macro_x_vix_change_volatility_20d",
        "left": "macro_vix_change_20d",
        "right": "market_sector_pct_volatility_20d",
    },
    {
        "name": "macro_x_dgs10_price_to_sales",
        "left": "macro_dgs10",
        "right": "edgar_price_to_sales",
    },
    {
        "name": "macro_x_dgs10_change_price_to_book",
        "left": "macro_dgs10_change_20d",
        "right": "edgar_price_to_book",
    },
    {
        "name": "macro_x_credit_change_liabilities_to_assets",
        "left": "macro_baa10y_credit_spread_change_20d",
        "right": "edgar_liabilities_to_assets",
    },
    {
        "name": "macro_x_credit_spread_cash_to_assets",
        "left": "macro_baa10y_credit_spread",
        "right": "edgar_cash_to_assets",
    },
    {
        "name": "macro_x_curve_inverted_finance",
        "left": "macro_yield_curve_10y_2y_inverted",
        "sector": "Finance",
    },
    {
        "name": "macro_x_dgs10_change_technology",
        "left": "macro_dgs10_change_20d",
        "sector": "Technology",
    },
    {
        "name": "macro_x_wti_change_energy_industrials",
        "left": "macro_wti_oil_pct_change_20d",
        "sectors": ["Energy", "Industrials"],
    },
    {
        "name": "macro_x_dollar_change_technology",
        "left": "macro_broad_dollar_index_pct_change_20d",
        "sector": "Technology",
    },
]


@dataclass
class MacroInteractionResult:
    features: pd.DataFrame
    failures: pd.DataFrame
    coverage: dict[str, Any]

    @classmethod
    def empty(cls, paths: dict[str, Path]) -> "MacroInteractionResult":
        features = pd.DataFrame()
        failures = pd.DataFrame(columns=INTERACTION_FAILURE_COLUMNS)
        if "macro_interaction_features" in paths:
            features.to_parquet(paths["macro_interaction_features"])
        if "macro_interaction_failures" in paths:
            failures.to_csv(paths["macro_interaction_failures"], index=False)
        return cls(features=features, failures=failures, coverage={"enabled": False})


def build_macro_interaction_frame(
    universe: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
    *,
    macro_features: pd.DataFrame | None,
    market_features: pd.DataFrame | None,
    fundamental_features: pd.DataFrame | None,
) -> MacroInteractionResult:
    interaction_config = config.get("macro_interactions", {})
    if not interaction_config.get("enabled", False):
        return MacroInteractionResult.empty(paths)
    if macro_features is None or macro_features.empty:
        failures = pd.DataFrame(
            [
                {
                    "name": None,
                    "left": None,
                    "right": None,
                    "error": "missing_macro_features",
                    "detail": "macro_interactions require macro_features.enabled",
                }
            ],
            columns=INTERACTION_FAILURE_COLUMNS,
        )
        failures.to_csv(paths["macro_interaction_failures"], index=False)
        features = pd.DataFrame(index=macro_features.index if macro_features is not None else None)
        features.to_parquet(paths["macro_interaction_features"])
        return MacroInteractionResult(features=features, failures=failures, coverage={"enabled": True, "feature_count": 0})

    cache_paths = macro_interaction_cache_paths(universe, config, paths, macro_features, market_features, fundamental_features)
    if cache_paths:
        cached = read_cached_feature_result(
            features_path=cache_paths["features"],
            failures_path=cache_paths["failures"],
            coverage_path=cache_paths["coverage"],
            failure_columns=INTERACTION_FAILURE_COLUMNS,
        )
        if cached:
            features, failures, coverage = cached
            features.to_parquet(paths["macro_interaction_features"])
            failures.to_csv(paths["macro_interaction_failures"], index=False)
            return MacroInteractionResult(features=features, failures=failures, coverage=coverage)

    specs = interaction_config.get("interactions") or DEFAULT_INTERACTIONS
    base_frames = merge_feature_frames(macro_features, market_features, fundamental_features)
    sector_flags = build_sector_flags(universe, macro_features.index)
    output = pd.DataFrame(index=macro_features.index)
    failures: list[dict[str, Any]] = []

    for spec in specs:
        name = str(spec["name"])
        left = str(spec.get("left", ""))
        if left not in base_frames.columns:
            failures.append(failure_record(name, left, right_name(spec), "missing_left", "left feature not found"))
            continue

        right = right_series(spec, base_frames, sector_flags)
        if right is None:
            failures.append(failure_record(name, left, right_name(spec), "missing_right", "right feature or sector flag not found"))
            continue

        output[name] = pd.to_numeric(base_frames[left], errors="coerce") * pd.to_numeric(right, errors="coerce")

    output = output.apply(pd.to_numeric, errors="coerce")
    failure_frame = pd.DataFrame(failures, columns=INTERACTION_FAILURE_COLUMNS)
    output.to_parquet(paths["macro_interaction_features"])
    failure_frame.to_csv(paths["macro_interaction_failures"], index=False)
    coverage = {
        "enabled": True,
        "requested_count": len(specs),
        "feature_count": int(output.shape[1]),
        "failure_count": int(len(failure_frame)),
        "row_count": int(len(output)),
        "non_null_ratio": float(output.notna().mean().mean()) if not output.empty else None,
    }
    if cache_paths:
        write_cached_feature_result(
            features_source=paths["macro_interaction_features"],
            failures_source=paths["macro_interaction_failures"],
            coverage=coverage,
            features_path=cache_paths["features"],
            failures_path=cache_paths["failures"],
            coverage_path=cache_paths["coverage"],
        )
    return MacroInteractionResult(features=output, failures=failure_frame, coverage=coverage)


def merge_feature_frames(
    macro_features: pd.DataFrame,
    market_features: pd.DataFrame | None,
    fundamental_features: pd.DataFrame | None,
) -> pd.DataFrame:
    frames = [macro_features]
    if market_features is not None and not market_features.empty:
        frames.append(market_features.reindex(macro_features.index))
    if fundamental_features is not None and not fundamental_features.empty:
        frames.append(fundamental_features.reindex(macro_features.index))
    return pd.concat(frames, axis=1)


def build_sector_flags(universe: pd.DataFrame, index: pd.MultiIndex) -> pd.DataFrame:
    if universe.empty or "sector" not in universe.columns:
        return pd.DataFrame(index=index)
    sector_by_symbol = universe.assign(symbol=universe["symbol"].astype(str).str.upper()).drop_duplicates("symbol").set_index("symbol")[
        "sector"
    ]
    instruments = index.get_level_values("instrument").astype(str).str.upper()
    sectors = pd.Series(instruments, index=index).map(sector_by_symbol).fillna("UNKNOWN")
    unique_sectors = sorted(sectors.dropna().unique())
    flags = {
        f"sector_flag_{normalize_name(sector)}": (sectors == sector).astype(float).to_numpy()
        for sector in unique_sectors
    }
    return pd.DataFrame(flags, index=index)


def right_series(spec: dict[str, Any], base_frames: pd.DataFrame, sector_flags: pd.DataFrame) -> pd.Series | None:
    if "right" in spec:
        right = str(spec["right"])
        return base_frames[right] if right in base_frames.columns else None
    sectors = spec.get("sectors")
    if sectors is None and "sector" in spec:
        sectors = [spec["sector"]]
    if sectors is None:
        return None
    columns = [f"sector_flag_{normalize_name(str(sector))}" for sector in sectors]
    existing = [column for column in columns if column in sector_flags.columns]
    if not existing:
        return None
    return sector_flags[existing].max(axis=1)


def right_name(spec: dict[str, Any]) -> str | None:
    if "right" in spec:
        return str(spec["right"])
    if "sector" in spec:
        return f"sector:{spec['sector']}"
    if "sectors" in spec:
        return "sectors:" + ",".join(map(str, spec["sectors"]))
    return None


def normalize_name(value: Any) -> str:
    text = str(value)
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_")


def failure_record(name: str, left: str | None, right: str | None, error: str, detail: str) -> dict[str, Any]:
    return {"name": name, "left": left, "right": right, "error": error, "detail": detail}


def macro_interaction_cache_paths(
    universe: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
    macro_features: pd.DataFrame,
    market_features: pd.DataFrame | None,
    fundamental_features: pd.DataFrame | None,
) -> dict[str, Path] | None:
    default_enabled = config.get("data", {}).get("source") == "crsp"
    if not artifact_cache_enabled(config, "macro_interactions", default=default_enabled):
        return None
    payload = {
        "data": config.get("data", {}),
        "universe": {
            "symbol_count": int(universe["symbol"].nunique()) if "symbol" in universe else len(universe),
            "symbols_hash": stable_hash({"symbols": sorted(universe["symbol"].astype(str).str.upper().tolist())})
            if "symbol" in universe
            else None,
        },
        "macro_features": config.get("macro_features", {}),
        "market_features": config.get("market_features", {}),
        "fundamentals": config.get("fundamentals", {}),
        "macro_interactions": config.get("macro_interactions", {}),
        "input_shapes": {
            "macro": tuple(macro_features.shape),
            "market": None if market_features is None else tuple(market_features.shape),
            "fundamental": None if fundamental_features is None else tuple(fundamental_features.shape),
        },
    }
    key = stable_hash(payload)
    root = artifact_cache_dir(config, paths, "macro_interactions")
    return {
        "features": root / f"{key}_features.parquet",
        "failures": root / f"{key}_failures.csv",
        "coverage": root / f"{key}_coverage.yaml",
    }
