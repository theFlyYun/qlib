"""Liquidity profile and filtering helpers for downloaded OHLCV data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

LIQUIDITY_PROFILE_COLUMNS = [
    "symbol",
    "rows",
    "first_date",
    "last_date",
    "latest_close",
    "avg_dollar_volume_20d",
    "avg_dollar_volume_60d",
    "median_dollar_volume_60d",
    "zero_volume_days_60d",
    "zero_volume_ratio_60d",
    "recent_trading_days_60d",
    "liquidity_pass",
    "exclusion_reason",
]
LIQUIDITY_EXCLUSION_COLUMNS = [
    "symbol",
    "exclusion_reason",
    "latest_close",
    "avg_dollar_volume_20d",
    "median_dollar_volume_60d",
    "zero_volume_ratio_60d",
]


def apply_liquidity_filter(
    universe: pd.DataFrame,
    source_dir: Path,
    config: dict[str, Any],
    paths: dict[str, Path],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    filter_config = config.get("liquidity_filter", {})
    profile_path = paths["liquidity_profile_csv"]
    exclusions_path = paths["liquidity_exclusions_csv"]

    if not filter_config.get("enabled", False):
        empty_profile = pd.DataFrame(columns=LIQUIDITY_PROFILE_COLUMNS)
        empty_exclusions = pd.DataFrame(columns=LIQUIDITY_EXCLUSION_COLUMNS)
        empty_profile.to_csv(profile_path, index=False)
        empty_exclusions.to_csv(exclusions_path, index=False)
        return universe.copy(), {
            "liquidity_filter_enabled": False,
            "liquidity_profile_count": 0,
            "liquidity_exclusion_count": 0,
            "liquidity_exclusion_reasons": {},
            "liquidity_filter": {},
        }

    rows = []
    keep_symbols: set[str] = set()
    for csv_path in sorted(source_dir.glob("*.csv")):
        profile = build_liquidity_profile(csv_path)
        reason = liquidity_exclusion_reason(profile, filter_config)
        profile["liquidity_pass"] = reason is None
        profile["exclusion_reason"] = reason
        rows.append(profile)
        if reason is None:
            keep_symbols.add(profile["symbol"])
        else:
            csv_path.unlink(missing_ok=True)

    profile = pd.DataFrame(rows, columns=LIQUIDITY_PROFILE_COLUMNS)
    exclusions = profile[~profile["liquidity_pass"]].copy() if not profile.empty else profile.head(0).copy()
    exclusions = exclusions.reindex(columns=LIQUIDITY_EXCLUSION_COLUMNS)
    profile.to_csv(profile_path, index=False)
    exclusions.to_csv(exclusions_path, index=False)

    filtered_universe = universe[universe["symbol"].astype(str).str.upper().isin(keep_symbols)].copy()
    filtered_universe.to_csv(paths["universe_csv"], index=False)
    if filtered_universe.empty and not universe.empty:
        raise RuntimeError("liquidity_filter removed all downloaded symbols")

    return filtered_universe, {
        "liquidity_filter_enabled": True,
        "liquidity_profile_count": int(len(profile)),
        "liquidity_exclusion_count": int(len(exclusions)),
        "liquidity_exclusion_reasons": exclusions["exclusion_reason"].value_counts().to_dict()
        if not exclusions.empty
        else {},
        "liquidity_filter": filter_config,
    }


def build_liquidity_profile(csv_path: Path) -> dict[str, Any]:
    frame = pd.read_csv(csv_path)
    symbol = csv_path.stem.upper()
    required = ["date", "close", "volume"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        return empty_profile(symbol, f"missing column(s): {', '.join(missing)}")

    working = frame.copy()
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working["close"] = pd.to_numeric(working["close"], errors="coerce")
    working["volume"] = pd.to_numeric(working["volume"], errors="coerce")
    price_column = "vwap" if "vwap" in working.columns else "close"
    working[price_column] = pd.to_numeric(working[price_column], errors="coerce")
    working = working.dropna(subset=["date", "close", "volume", price_column]).sort_values("date")
    if working.empty:
        return empty_profile(symbol, "no usable rows")

    working["dollar_volume"] = working[price_column] * working["volume"]
    recent_20 = working.tail(20)
    recent_60 = working.tail(60)
    zero_volume_days = int((recent_60["volume"] <= 0).sum())
    recent_60_count = int(len(recent_60))

    return {
        "symbol": symbol,
        "rows": int(len(working)),
        "first_date": working["date"].iloc[0].date().isoformat(),
        "last_date": working["date"].iloc[-1].date().isoformat(),
        "latest_close": float(working["close"].iloc[-1]),
        "avg_dollar_volume_20d": float(recent_20["dollar_volume"].mean()),
        "avg_dollar_volume_60d": float(recent_60["dollar_volume"].mean()),
        "median_dollar_volume_60d": float(recent_60["dollar_volume"].median()),
        "zero_volume_days_60d": zero_volume_days,
        "zero_volume_ratio_60d": zero_volume_days / recent_60_count if recent_60_count else 1.0,
        "recent_trading_days_60d": recent_60_count,
        "liquidity_pass": True,
        "exclusion_reason": None,
    }


def empty_profile(symbol: str, reason: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "rows": 0,
        "first_date": None,
        "last_date": None,
        "latest_close": pd.NA,
        "avg_dollar_volume_20d": pd.NA,
        "avg_dollar_volume_60d": pd.NA,
        "median_dollar_volume_60d": pd.NA,
        "zero_volume_days_60d": pd.NA,
        "zero_volume_ratio_60d": pd.NA,
        "recent_trading_days_60d": 0,
        "liquidity_pass": False,
        "exclusion_reason": reason,
    }


def liquidity_exclusion_reason(profile: dict[str, Any], filter_config: dict[str, Any]) -> str | None:
    if profile.get("exclusion_reason"):
        return str(profile["exclusion_reason"])

    checks = [
        ("latest_close", "min_latest_close", "<"),
        ("avg_dollar_volume_20d", "min_avg_dollar_volume_20d", "<"),
        ("median_dollar_volume_60d", "min_median_dollar_volume_60d", "<"),
        ("recent_trading_days_60d", "min_recent_trading_days_60d", "<"),
        ("zero_volume_ratio_60d", "max_zero_volume_ratio_60d", ">"),
    ]
    for metric, config_key, direction in checks:
        threshold = filter_config.get(config_key)
        if threshold is None:
            continue
        value = profile.get(metric)
        if pd.isna(value):
            return f"{metric}:missing"
        numeric_value = float(value)
        numeric_threshold = float(threshold)
        if direction == "<" and numeric_value < numeric_threshold:
            return f"{metric} < {format_threshold(numeric_threshold)}"
        if direction == ">" and numeric_value > numeric_threshold:
            return f"{metric} > {format_threshold(numeric_threshold)}"
    return None


def format_threshold(value: float) -> str:
    if float(value).is_integer():
        return f"{value:.0f}"
    return f"{value:g}"
