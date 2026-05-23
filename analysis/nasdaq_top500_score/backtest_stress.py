"""Backtest assumption stress tests that reuse model predictions."""

from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

try:
    from .backtest import load_market_data, run_topk_backtest
except ImportError:  # pragma: no cover - supports script-style imports.
    from backtest import load_market_data, run_topk_backtest


PRICE_ALIASES = {"vwap_proxy": "vwap"}


def run_backtest_stress_tests(
    predictions: pd.DataFrame,
    universe: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
) -> dict[str, Any]:
    stress_config = config.get("backtest_stress", {})
    if not stress_config.get("enabled", False):
        return {"enabled": False, "rows": []}

    rows: list[dict[str, Any]] = []
    variants: list[dict[str, Any]] = []
    market_data_by_price: dict[str, dict[str, pd.DataFrame]] = {}
    market_profile_cache_by_price: dict[str, dict[tuple[str, pd.Timestamp], dict[str, Any]]] = {}
    paths["backtest_stress_dir"].mkdir(parents=True, exist_ok=True)
    for entry_lag_days in stress_config.get("entry_lag_days", [config["backtest"].get("entry_lag_days", 1)]):
        for entry_price in stress_config.get("entry_prices", [config["backtest"].get("price", "close")]):
            for cost_bps in stress_config.get("cost_bps", [config["backtest"].get("cost_bps", 0)]):
                variant_name = stress_variant_name(entry_lag_days, entry_price, cost_bps)
                variant_paths = build_stress_paths(paths, variant_name)
                variant_config = stress_variant_config(config, entry_lag_days, entry_price, cost_bps)
                backtest_price = str(variant_config["backtest"].get("price", "close"))
                if backtest_price not in market_data_by_price:
                    market_data_by_price[backtest_price] = load_market_data(paths["source_dir"], backtest_price)
                    market_profile_cache_by_price[backtest_price] = {}
                result = run_topk_backtest(
                    predictions,
                    universe,
                    variant_config,
                    variant_paths,
                    market_data=market_data_by_price[backtest_price],
                    market_profile_cache=market_profile_cache_by_price[backtest_price],
                )
                row = summarize_stress_variant(variant_name, entry_lag_days, entry_price, cost_bps, result, variant_paths)
                rows.append(row)
                variants.append({"name": variant_name, "output_dir": row["output_dir"], "summary": result.summary})

    frame = pd.DataFrame(rows)
    frame.to_csv(paths["backtest_stress_matrix"], index=False)
    summary = {
        "enabled": True,
        "rows": rows,
        "variants": variants,
        "insights": build_stress_insights(rows, stress_config),
    }
    paths["backtest_stress_summary"].write_text(
        yaml.safe_dump(summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return summary


def stress_variant_config(config: dict[str, Any], entry_lag_days: Any, entry_price: str, cost_bps: Any) -> dict[str, Any]:
    variant = deepcopy(config)
    backtest = deepcopy(variant.get("backtest", {}))
    backtest["entry_lag_days"] = int(entry_lag_days)
    backtest["price"] = PRICE_ALIASES.get(str(entry_price), str(entry_price))
    backtest["cost_bps"] = float(cost_bps)
    variant["backtest"] = backtest
    return variant


def build_stress_paths(paths: dict[str, Path], variant_name: str) -> dict[str, Path]:
    variant_dir = paths["backtest_stress_dir"] / variant_name
    variant_dir.mkdir(parents=True, exist_ok=True)
    variant_paths = dict(paths)
    variant_paths.update(
        {
            "output_dir": variant_dir,
            "backtest_nav_csv": variant_dir / "backtest_nav.csv",
            "backtest_positions_csv": variant_dir / "backtest_positions.csv",
            "backtest_summary": variant_dir / "backtest_summary.yaml",
            "benchmark_summary": variant_dir / "benchmark_summary.yaml",
            "contribution_by_symbol": variant_dir / "contribution_by_symbol.csv",
            "contribution_by_sector": variant_dir / "contribution_by_sector.csv",
            "contribution_by_industry": variant_dir / "contribution_by_industry.csv",
            "exposure_by_sector": variant_dir / "exposure_by_sector.csv",
            "exposure_by_industry": variant_dir / "exposure_by_industry.csv",
            "contribution_summary": variant_dir / "contribution_summary.yaml",
        }
    )
    return variant_paths


def summarize_stress_variant(
    name: str,
    entry_lag_days: Any,
    entry_price: str,
    cost_bps: Any,
    result: Any,
    variant_paths: dict[str, Path],
) -> dict[str, Any]:
    summary = result.summary
    benchmark = summary.get("benchmark", {})
    return {
        "name": name,
        "entry_lag_days": int(entry_lag_days),
        "entry_price": str(entry_price),
        "backtest_price": PRICE_ALIASES.get(str(entry_price), str(entry_price)),
        "cost_bps": float(cost_bps),
        "output_dir": str(variant_paths["output_dir"]),
        "period_count": summary.get("period_count"),
        "cumulative_return": summary.get("cumulative_return"),
        "annualized_return": summary.get("annualized_return"),
        "annualized_volatility": summary.get("annualized_volatility"),
        "information_ratio": summary.get("information_ratio"),
        "max_drawdown": summary.get("max_drawdown"),
        "avg_turnover": summary.get("avg_turnover"),
        "total_cost_return": summary.get("total_cost_return"),
        "excess_cumulative_return": benchmark.get("excess_cumulative_return"),
        "alpha_annualized": benchmark.get("alpha_annualized"),
        "beta": benchmark.get("beta"),
    }


def build_stress_insights(rows: list[dict[str, Any]], stress_config: dict[str, Any]) -> dict[str, Any]:
    if not rows:
        return {"enabled": False}
    baseline = select_baseline_row(rows, stress_config)
    if not baseline:
        return {"enabled": False, "error": "missing_baseline_row"}

    lag2_rows = [row for row in rows if row["entry_lag_days"] == 2 and row["entry_price"] == baseline["entry_price"] and row["cost_bps"] == baseline["cost_bps"]]
    high_cost_rows = [row for row in rows if row["entry_lag_days"] == baseline["entry_lag_days"] and row["entry_price"] == baseline["entry_price"] and row["cost_bps"] >= 50]
    worst_lag2 = min_metric_row(lag2_rows, "annualized_return")
    worst_high_cost = min_metric_row(high_cost_rows, "annualized_return")
    lag2_drop = metric_delta(worst_lag2, baseline, "annualized_return")
    high_cost_drop = metric_delta(worst_high_cost, baseline, "annualized_return")
    contribution_large = (
        (pd.notna(lag2_drop) and lag2_drop <= -0.25)
        or (pd.notna(high_cost_drop) and high_cost_drop <= -0.25)
    )
    return {
        "enabled": True,
        "baseline": baseline["name"],
        "best_annualized_return": max_metric_record(rows, "annualized_return"),
        "worst_max_drawdown": min_metric_record(rows, "max_drawdown"),
        "worst_entry_lag_2": metric_record(worst_lag2),
        "worst_high_cost": metric_record(worst_high_cost),
        "entry_lag_2_annualized_delta": normalize_number(lag2_drop),
        "high_cost_annualized_delta": normalize_number(high_cost_drop),
        "conclusion": "交易假设贡献较大" if contribution_large else "交易假设压力下未见明显坍塌",
    }


def select_baseline_row(rows: list[dict[str, Any]], stress_config: dict[str, Any]) -> dict[str, Any] | None:
    baseline_config = stress_config.get("baseline", {})
    entry_lag = int(baseline_config.get("entry_lag_days", 1))
    entry_price = str(baseline_config.get("entry_price", "close"))
    cost_bps = float(baseline_config.get("cost_bps", 10))
    for row in rows:
        if row["entry_lag_days"] == entry_lag and row["entry_price"] == entry_price and math.isclose(row["cost_bps"], cost_bps):
            return row
    return rows[0] if rows else None


def stress_variant_name(entry_lag_days: Any, entry_price: str, cost_bps: Any) -> str:
    price = str(entry_price).replace("_", "")
    cost = int(float(cost_bps)) if float(cost_bps).is_integer() else str(cost_bps).replace(".", "p")
    return f"lag{int(entry_lag_days)}_{price}_cost{cost}bps"


def max_metric_record(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    return metric_record(max_metric_row(rows, key))


def min_metric_record(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    return metric_record(min_metric_row(rows, key))


def max_metric_row(rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    usable = [row for row in rows if pd.notna(row.get(key))]
    return max(usable, key=lambda row: float(row[key])) if usable else None


def min_metric_row(rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    usable = [row for row in rows if pd.notna(row.get(key))]
    return min(usable, key=lambda row: float(row[key])) if usable else None


def metric_delta(left: dict[str, Any] | None, right: dict[str, Any] | None, key: str) -> float:
    if not left or not right:
        return math.nan
    try:
        return float(left.get(key)) - float(right.get(key))
    except (TypeError, ValueError):
        return math.nan


def metric_record(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    keys = [
        "name",
        "entry_lag_days",
        "entry_price",
        "cost_bps",
        "cumulative_return",
        "annualized_return",
        "max_drawdown",
        "excess_cumulative_return",
        "alpha_annualized",
        "beta",
    ]
    return {key: normalize_number(row.get(key)) for key in keys}


def normalize_number(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (str, bool, int)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return value
