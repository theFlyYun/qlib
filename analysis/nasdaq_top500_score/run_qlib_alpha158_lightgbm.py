"""Run a config-driven Qlib Alpha158 + LightGBM Nasdaq experiment.

The output is a model-scored ranking for the latest available date. This is a
research artifact for learning Qlib, not investment advice.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import shutil
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

try:
    from backtest import run_topk_backtest
    from data_sources import DataSourceUnavailable, create_data_source
    from fundamentals import build_fundamental_features
    from industry import build_industry_feature_frame
    from macro_features import build_macro_feature_frame
    from market_features import build_market_feature_frame
    from sector_error_review import run_sector_error_review
    from selection import apply_bucket_ranking, apply_liquidity_filter, build_history_buckets
    from short_history_review import run_short_history_review
    from within_sector import run_within_sector_review
except ImportError:  # pragma: no cover - supports importing this script as a module in tests.
    from analysis.nasdaq_top500_score.backtest import run_topk_backtest
    from analysis.nasdaq_top500_score.data_sources import DataSourceUnavailable, create_data_source
    from analysis.nasdaq_top500_score.fundamentals import build_fundamental_features
    from analysis.nasdaq_top500_score.industry import build_industry_feature_frame
    from analysis.nasdaq_top500_score.macro_features import build_macro_feature_frame
    from analysis.nasdaq_top500_score.market_features import build_market_feature_frame
    from analysis.nasdaq_top500_score.sector_error_review import run_sector_error_review
    from analysis.nasdaq_top500_score.selection import apply_bucket_ranking, apply_liquidity_filter, build_history_buckets
    from analysis.nasdaq_top500_score.short_history_review import run_short_history_review
    from analysis.nasdaq_top500_score.within_sector import run_within_sector_review

WORKSPACE = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "configs" / "nasdaq_alpha158_lgbm_1d.yaml"
LOCAL_SECRET_FILES = [WORKSPACE / ".env", ROOT / "configs" / "local_secrets.env"]
SECRET_ENV_KEYS = {"FRED_API_KEY", "SEC_EDGAR_USER_AGENT"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"YAML experiment config. Defaults to {DEFAULT_CONFIG}",
    )
    return parser.parse_args()


def resolve_path(path_text: str | Path) -> Path:
    path = Path(path_text).expanduser()
    if path.is_absolute():
        return path
    return WORKSPACE / path


def load_local_secret_env() -> None:
    """Load ignored local credentials without overriding explicit shell env vars."""
    for path in LOCAL_SECRET_FILES:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            if key not in SECRET_ENV_KEYS:
                continue
            os.environ.setdefault(key, value.strip().strip("\"'"))


def load_config(config_path: Path) -> dict[str, Any]:
    load_local_secret_env()
    resolved_path = resolve_path(config_path)
    with resolved_path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    required_sections = [
        "experiment",
        "universe",
        "data",
        "label",
        "features",
        "split",
        "model",
        "report",
    ]
    missing = [section for section in required_sections if section not in config]
    if missing:
        raise ValueError(f"missing config section(s): {', '.join(missing)}")

    config["_config_path"] = str(resolved_path)
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    source = config["data"]["source"]
    if source not in {"nasdaq_public", "norgate"}:
        raise ValueError("supported data.source values: nasdaq_public, norgate")
    if source == "nasdaq_public" and config["universe"]["exchange"] != "NASDAQ":
        raise ValueError("nasdaq_public currently supports universe.exchange: NASDAQ")
    security_master = config["universe"].get("security_master", {})
    if security_master:
        if security_master.get("enabled") and source != "nasdaq_public":
            raise ValueError("universe.security_master currently supports data.source: nasdaq_public")
        if security_master.get("enabled") and not security_master.get("allowed_asset_types"):
            raise ValueError("enabled universe.security_master requires allowed_asset_types")
    if source == "nasdaq_public":
        validate_universe_selection(config)
        fixed_window = bool(config["data"].get("start_date") or config["data"].get("end_date"))
        if fixed_window:
            missing = [key for key in ["start_date", "end_date"] if key not in config["data"]]
            if missing:
                raise ValueError(f"nasdaq_public fixed window missing data key(s): {', '.join(missing)}")
            validate_date_order(config["data"]["start_date"], config["data"]["end_date"], "data")
        elif "lookback_days" not in config["data"]:
            raise ValueError("nasdaq_public requires either data.lookback_days or data.start_date/data.end_date")
    if source == "norgate":
        required_universe_keys = ["index_name", "index_symbol", "candidate_databases", "min_history_rows"]
        required_data_keys = ["start_date", "price_adjustment", "padding", "vwap_method"]
        missing = [key for key in required_universe_keys if key not in config["universe"]]
        missing.extend(key for key in required_data_keys if key not in config["data"])
        if missing:
            raise ValueError(f"norgate config missing key(s): {', '.join(missing)}")
    if config["data"]["freq"] != "day":
        raise ValueError("currently supports data.freq: day")
    if config["data"]["vwap_method"] != "ohlc_mean":
        raise ValueError("currently supports data.vwap_method: ohlc_mean")
    if config["features"]["handler"] != "Alpha158":
        raise ValueError("currently supports features.handler: Alpha158")
    if config["model"]["class"] != "LGBModel":
        raise ValueError("currently supports model.class: LGBModel")
    if config["split"]["method"] not in {"ratio", "date"}:
        raise ValueError("currently supports split.method: ratio, date")
    fundamentals = config.get("fundamentals", {})
    if fundamentals:
        if fundamentals.get("source") != "sec_edgar":
            raise ValueError("currently supports fundamentals.source: sec_edgar")
        if fundamentals.get("enabled") and not fundamentals.get("cache_dir"):
            raise ValueError("enabled fundamentals require fundamentals.cache_dir")
    industry = config.get("industry", {})
    if industry:
        if industry.get("source") != "universe":
            raise ValueError("currently supports industry.source: universe")
        if industry.get("enabled") and not fundamentals.get("enabled", False):
            raise ValueError("enabled industry features require fundamentals.enabled: true")
        if industry.get("enabled") and not industry.get("rank_features"):
            raise ValueError("enabled industry features require industry.rank_features")

    if config["split"]["method"] == "ratio":
        train_ratio = float(config["split"]["train_ratio"])
        valid_ratio = float(config["split"]["valid_ratio"])
        test_ratio = float(config["split"]["test_ratio"])
        if not math.isclose(train_ratio + valid_ratio + test_ratio, 1.0, rel_tol=0, abs_tol=1e-6):
            raise ValueError("split train_ratio + valid_ratio + test_ratio must equal 1.0")
    else:
        validate_date_split(config["split"])
    validate_bucket_ranking(config)
    validate_industry_constraints(config)
    validate_liquidity_filter(config)
    validate_backtest(config)
    validate_benchmark(config)
    validate_attribution(config)
    validate_market_features(config)
    validate_macro_features(config)
    validate_strategy_comparison(config)
    validate_within_sector_review(config)
    validate_sector_error_review(config)
    validate_short_history_review(config)
    validate_training_control(config)


def validate_universe_selection(config: dict[str, Any]) -> None:
    selection = config["universe"].get("selection", {})
    if not selection:
        return
    method = selection.get("method", "current_market_cap")
    if method not in {"current_market_cap", "approximate_market_cap_asof"}:
        raise ValueError("universe.selection.method must be current_market_cap or approximate_market_cap_asof")
    if method == "current_market_cap":
        return
    if "as_of_date" not in selection:
        raise ValueError("approximate_market_cap_asof requires universe.selection.as_of_date")
    missing_data_dates = [key for key in ["start_date", "end_date"] if key not in config["data"]]
    if missing_data_dates:
        raise ValueError("approximate_market_cap_asof requires fixed data.start_date and data.end_date")
    top_n = int(config["universe"]["top_n_by_market_cap"])
    candidate_top_n = int(selection.get("candidate_top_n_by_current_market_cap", top_n))
    if candidate_top_n < top_n:
        raise ValueError("candidate_top_n_by_current_market_cap must be >= top_n_by_market_cap")
    validate_date_order(config["data"]["start_date"], selection["as_of_date"], "universe.selection")
    validate_date_order(selection["as_of_date"], config["data"]["end_date"], "universe.selection")
    if config["split"]["method"] == "date" and date_value(selection["as_of_date"]) >= date_value(config["split"]["test"]["start"]):
        raise ValueError("as-of universe selection date must be before split.test.start")


def validate_bucket_ranking(config: dict[str, Any]) -> None:
    ranking = config.get("bucket_ranking", {})
    if not ranking or not ranking.get("enabled", False):
        return
    if not config.get("history_buckets", {}).get("enabled", False):
        raise ValueError("enabled bucket_ranking requires history_buckets.enabled: true")
    quotas = ranking.get("quotas", {})
    missing = [bucket for bucket in ["full_10y", "5_10y", "2_5y", "lt_2y"] if bucket not in quotas]
    if missing:
        raise ValueError(f"bucket_ranking.quotas missing bucket(s): {', '.join(missing)}")
    top_n = int(config["report"]["top_n"])
    quota_total = sum(int(value) for value in quotas.values())
    if quota_total != top_n:
        raise ValueError("bucket_ranking quota total must equal report.top_n")


def validate_industry_constraints(config: dict[str, Any]) -> None:
    constraints = config.get("industry_constraints", {})
    if not constraints or not constraints.get("enabled", False):
        return
    if not config.get("bucket_ranking", {}).get("enabled", False):
        raise ValueError("enabled industry_constraints requires bucket_ranking.enabled: true")
    for key in ["max_sector", "max_industry"]:
        if key not in constraints:
            raise ValueError(f"enabled industry_constraints requires {key}")
        if int(constraints[key]) <= 0:
            raise ValueError(f"industry_constraints.{key} must be positive")


def validate_liquidity_filter(config: dict[str, Any]) -> None:
    liquidity = config.get("liquidity_filter", {})
    if not liquidity or not liquidity.get("enabled", False):
        return
    positive_keys = [
        "min_latest_close",
        "min_avg_dollar_volume_20d",
        "min_median_dollar_volume_60d",
        "min_recent_trading_days_60d",
    ]
    for key in positive_keys:
        if key in liquidity and float(liquidity[key]) < 0:
            raise ValueError(f"liquidity_filter.{key} must be non-negative")
    if "max_zero_volume_ratio_60d" in liquidity:
        value = float(liquidity["max_zero_volume_ratio_60d"])
        if value < 0 or value > 1:
            raise ValueError("liquidity_filter.max_zero_volume_ratio_60d must be between 0 and 1")


def validate_backtest(config: dict[str, Any]) -> None:
    backtest = config.get("backtest", {})
    if not backtest or not backtest.get("enabled", False):
        return
    positive_int_keys = ["top_n", "holding_days", "rebalance_days", "min_positions"]
    for key in positive_int_keys:
        if int(backtest.get(key, 0)) <= 0:
            raise ValueError(f"backtest.{key} must be positive")
    if int(backtest.get("entry_lag_days", 1)) < 0:
        raise ValueError("backtest.entry_lag_days must be non-negative")
    if float(backtest.get("cost_bps", 0.0)) < 0:
        raise ValueError("backtest.cost_bps must be non-negative")
    if backtest.get("price", "close") not in {"close", "vwap"}:
        raise ValueError("backtest.price must be close or vwap")
    if config.get("bucket_ranking", {}).get("enabled", False) and int(backtest["top_n"]) != int(config["report"]["top_n"]):
        raise ValueError("bucketed backtest requires backtest.top_n to equal report.top_n")
    pit_filters = backtest.get("point_in_time_filters", {})
    if pit_filters.get("enabled", False) and int(pit_filters.get("min_history_rows", config["universe"].get("min_history_rows", 1))) <= 0:
        raise ValueError("backtest.point_in_time_filters.min_history_rows must be positive")


def validate_benchmark(config: dict[str, Any]) -> None:
    benchmark = config.get("benchmark", {})
    if not benchmark or not benchmark.get("enabled", False):
        return
    if not config.get("backtest", {}).get("enabled", False):
        raise ValueError("enabled benchmark requires backtest.enabled: true")
    source = benchmark.get("source", "nasdaq_public")
    if source not in {"nasdaq_public", "fred", "csv"}:
        raise ValueError("benchmark.source must be nasdaq_public, fred, or csv")
    if source == "csv" and not benchmark.get("path"):
        raise ValueError("benchmark.source=csv requires benchmark.path")
    if not benchmark.get("symbol"):
        raise ValueError("enabled benchmark requires benchmark.symbol")


def validate_attribution(config: dict[str, Any]) -> None:
    attribution = config.get("attribution", {})
    if not attribution or not attribution.get("enabled", False):
        return
    if not config.get("backtest", {}).get("enabled", False):
        raise ValueError("enabled attribution requires backtest.enabled: true")
    if int(attribution.get("top_n", 10)) <= 0:
        raise ValueError("attribution.top_n must be positive")


def validate_strategy_comparison(config: dict[str, Any]) -> None:
    comparison = config.get("strategy_comparison", {})
    if not comparison or not comparison.get("enabled", False):
        return
    if not config.get("backtest", {}).get("enabled", False):
        raise ValueError("enabled strategy_comparison requires backtest.enabled: true")
    variants = comparison.get("variants", [])
    if not variants:
        raise ValueError("enabled strategy_comparison requires variants")
    names = [str(variant.get("name", "")).strip() for variant in variants]
    if any(not name for name in names):
        raise ValueError("strategy_comparison variants require non-empty name")
    if len(set(names)) != len(names):
        raise ValueError("strategy_comparison variant names must be unique")
    for variant in variants:
        constraints = variant.get("industry_constraints", {})
        if constraints.get("enabled", False):
            for key in ["max_sector", "max_industry"]:
                if key not in constraints or int(constraints[key]) <= 0:
                    raise ValueError(f"enabled strategy_comparison industry_constraints requires positive {key}")
            tilt = constraints.get("sector_momentum_tilt", {})
            if tilt.get("enabled", False):
                for key in ["lookback_days", "top_sector_count"]:
                    if int(tilt.get(key, 0)) <= 0:
                        raise ValueError(f"sector_momentum_tilt.{key} must be positive")
                if int(tilt.get("extra_max_sector", 1)) < 0:
                    raise ValueError("sector_momentum_tilt.extra_max_sector must be non-negative")


def validate_within_sector_review(config: dict[str, Any]) -> None:
    review = config.get("within_sector_review", {})
    if not review or not review.get("enabled", False):
        return
    if not config.get("backtest", {}).get("enabled", False):
        raise ValueError("enabled within_sector_review requires backtest.enabled: true")
    if int(review.get("min_group_size", 10)) <= 1:
        raise ValueError("within_sector_review.min_group_size must be greater than 1")
    if int(review.get("min_summary_periods", 20)) <= 0:
        raise ValueError("within_sector_review.min_summary_periods must be positive")
    if int(review.get("quantiles", 5)) < 2:
        raise ValueError("within_sector_review.quantiles must be at least 2")
    invalid_levels = set(review.get("group_levels", ["sector", "industry"])) - {"sector", "industry"}
    if invalid_levels:
        raise ValueError("within_sector_review.group_levels can only include sector and industry")


def validate_sector_error_review(config: dict[str, Any]) -> None:
    review = config.get("sector_error_review", {})
    if not review or not review.get("enabled", False):
        return
    if not config.get("backtest", {}).get("enabled", False):
        raise ValueError("enabled sector_error_review requires backtest.enabled: true")
    target_sectors = review.get("target_sectors", [])
    if not target_sectors:
        raise ValueError("enabled sector_error_review requires target_sectors")
    if any(not str(sector).strip() for sector in target_sectors):
        raise ValueError("sector_error_review.target_sectors cannot include empty values")
    if int(review.get("quantiles", 5)) < 2:
        raise ValueError("sector_error_review.quantiles must be at least 2")
    if int(review.get("min_group_size", 10)) <= 1:
        raise ValueError("sector_error_review.min_group_size must be greater than 1")
    if int(review.get("min_summary_periods", 20)) <= 0:
        raise ValueError("sector_error_review.min_summary_periods must be positive")


def validate_short_history_review(config: dict[str, Any]) -> None:
    review = config.get("short_history_review", {})
    if not review or not review.get("enabled", False):
        return
    if not config.get("backtest", {}).get("enabled", False):
        raise ValueError("enabled short_history_review requires backtest.enabled: true")
    if not review.get("baseline_variant"):
        raise ValueError("enabled short_history_review requires baseline_variant")
    if not review.get("target_buckets"):
        raise ValueError("enabled short_history_review requires target_buckets")
    if not review.get("comparison_buckets"):
        raise ValueError("enabled short_history_review requires comparison_buckets")
    if int(review.get("quantiles", 5)) < 2:
        raise ValueError("short_history_review.quantiles must be at least 2")
    if int(review.get("min_bucket_samples", 20)) <= 0:
        raise ValueError("short_history_review.min_bucket_samples must be positive")


def validate_training_control(config: dict[str, Any]) -> None:
    training = config.get("training", {})
    if not training:
        return
    if "seed" in training and int(training["seed"]) < 0:
        raise ValueError("training.seed must be non-negative")
    if "reuse_test_predictions" in training and not isinstance(training["reuse_test_predictions"], bool):
        raise ValueError("training.reuse_test_predictions must be true or false")
    if training.get("deterministic", False) and "seed" not in training:
        raise ValueError("training.deterministic requires training.seed")


def validate_market_features(config: dict[str, Any]) -> None:
    market_features = config.get("market_features", {})
    if not market_features or not market_features.get("enabled", False):
        return
    if market_features.get("source", "qlib_source_csv") != "qlib_source_csv":
        raise ValueError("market_features.source currently supports qlib_source_csv")
    group_levels = set(market_features.get("group_levels", ["sector", "industry"]))
    if not group_levels.issubset({"sector", "industry"}):
        raise ValueError("market_features.group_levels can only include sector and industry")
    for key in ["dollar_volume_windows", "momentum_windows", "volatility_windows"]:
        for value in market_features.get(key, []):
            if int(value) <= 0:
                raise ValueError(f"market_features.{key} values must be positive")
    if int(market_features.get("min_group_size", 5)) <= 0:
        raise ValueError("market_features.min_group_size must be positive")


def validate_macro_features(config: dict[str, Any]) -> None:
    macro_features = config.get("macro_features", {})
    if not macro_features or not macro_features.get("enabled", False):
        return
    if macro_features.get("source", "fred_alfred") != "fred_alfred":
        raise ValueError("macro_features.source currently supports fred_alfred")
    if not macro_features.get("series"):
        raise ValueError("enabled macro_features requires series")
    if int(macro_features.get("effective_lag_trading_days", 1)) < 1:
        raise ValueError("macro_features.effective_lag_trading_days must be at least 1")
    if int(macro_features.get("history_buffer_days", 370)) < 0:
        raise ValueError("macro_features.history_buffer_days must be non-negative")
    if int(macro_features.get("output_type", 4)) not in {1, 2, 3, 4}:
        raise ValueError("macro_features.output_type must be one of 1, 2, 3, or 4")
    known_transforms = {
        "level",
        "change_20d",
        "change_60d",
        "change_3m",
        "pct_change_20d",
        "pct_change_60d",
        "yoy",
        "zscore_60d",
    }
    for spec in macro_features.get("series", []):
        if not spec.get("id"):
            raise ValueError("macro_features.series entries require id")
        transforms = set(spec.get("transforms", ["level", "change_20d", "change_60d"]))
        invalid = transforms - known_transforms
        if invalid:
            raise ValueError(f"macro_features.series {spec.get('id')} unsupported transform(s): {', '.join(sorted(invalid))}")
        if int(spec.get("max_staleness_days", 370)) <= 0:
            raise ValueError(f"macro_features.series {spec.get('id')} max_staleness_days must be positive")
        if spec.get("realtime_mode", "period") not in {"period", "latest"}:
            raise ValueError(f"macro_features.series {spec.get('id')} realtime_mode must be period or latest")
        if spec.get("effective_date_source", "realtime_start") not in {"realtime_start", "observation_date"}:
            raise ValueError(
                f"macro_features.series {spec.get('id')} effective_date_source must be realtime_start or observation_date"
            )
    for spec in macro_features.get("derived", []):
        if spec.get("operation") != "subtract":
            raise ValueError("macro_features.derived currently supports operation: subtract")
        if not spec.get("name") or not spec.get("left") or not spec.get("right"):
            raise ValueError("macro_features.derived entries require name, left, and right")
        invalid = set(spec.get("transforms", ["level"])) - known_transforms
        if invalid:
            raise ValueError(f"macro_features.derived {spec.get('name')} unsupported transform(s): {', '.join(sorted(invalid))}")


def date_value(value: Any) -> pd.Timestamp:
    if isinstance(value, str) and value == "latest":
        return pd.Timestamp.today().normalize()
    return pd.Timestamp(value).normalize()


def validate_date_order(start: Any, end: Any, label: str) -> None:
    if date_value(start) > date_value(end):
        raise ValueError(f"{label} start date must be before or equal to end date")


def validate_date_split(split: dict[str, Any]) -> None:
    missing_segments = [segment for segment in ["train", "valid", "test"] if segment not in split]
    if missing_segments:
        raise ValueError(f"date split missing segment(s): {', '.join(missing_segments)}")
    for segment in ["train", "valid", "test"]:
        missing = [key for key in ["start", "end"] if key not in split[segment]]
        if missing:
            raise ValueError(f"date split {segment} missing key(s): {', '.join(missing)}")
        validate_date_order(split[segment]["start"], split[segment]["end"], f"split.{segment}")
    if date_value(split["train"]["end"]) >= date_value(split["valid"]["start"]):
        raise ValueError("date split train.end must be before valid.start")
    if date_value(split["valid"]["end"]) >= date_value(split["test"]["start"]):
        raise ValueError("date split valid.end must be before test.start")


def build_paths(config: dict[str, Any]) -> dict[str, Path]:
    output_dir = resolve_path(config["experiment"]["output_dir"])
    paths = {
        "output_dir": output_dir,
        "source_dir": output_dir / "qlib_source_csv",
        "qlib_dir": output_dir / "qlib_data",
        "universe_csv": output_dir / "universe.csv",
        "universe_candidates_csv": output_dir / "universe_candidates.csv",
        "universe_selection_csv": output_dir / "universe_selection.csv",
        "universe_exclusions_csv": output_dir / "universe_exclusions.csv",
        "security_master_csv": output_dir / "security_master.csv",
        "security_master_exclusions_csv": output_dir / "security_master_exclusions.csv",
        "failures_csv": output_dir / "download_failures.csv",
        "membership_csv": output_dir / "membership.csv",
        "history_buckets_csv": output_dir / "history_buckets.csv",
        "liquidity_profile_csv": output_dir / "liquidity_profile.csv",
        "liquidity_exclusions_csv": output_dir / "liquidity_exclusions.csv",
        "fundamental_features": output_dir / "fundamental_features.parquet",
        "fundamental_failures": output_dir / "fundamental_failures.csv",
        "edgar_cik_map": output_dir / "edgar_cik_map.csv",
        "market_features": output_dir / "market_features.parquet",
        "market_feature_failures": output_dir / "market_feature_failures.csv",
        "macro_raw_observations": output_dir / "macro_raw_observations.parquet",
        "macro_asof_observations": output_dir / "macro_asof_observations.parquet",
        "macro_features": output_dir / "macro_features.parquet",
        "macro_failures": output_dir / "macro_failures.csv",
        "industry_features": output_dir / "industry_features.parquet",
        "industry_failures": output_dir / "industry_failures.csv",
        "predictions_csv": output_dir / "predictions.csv",
        "bucketed_predictions_csv": output_dir / "bucketed_predictions.csv",
        "selected_top10_csv": output_dir / "selected_top10.csv",
        "test_predictions_csv": output_dir / "test_predictions.csv",
        "backtest_nav_csv": output_dir / "backtest_nav.csv",
        "backtest_positions_csv": output_dir / "backtest_positions.csv",
        "backtest_summary": output_dir / "backtest_summary.yaml",
        "benchmark_prices_csv": output_dir / "benchmark_prices.csv",
        "benchmark_summary": output_dir / "benchmark_summary.yaml",
        "contribution_by_symbol": output_dir / "contribution_by_symbol.csv",
        "contribution_by_sector": output_dir / "contribution_by_sector.csv",
        "contribution_by_industry": output_dir / "contribution_by_industry.csv",
        "exposure_by_sector": output_dir / "exposure_by_sector.csv",
        "exposure_by_industry": output_dir / "exposure_by_industry.csv",
        "contribution_summary": output_dir / "contribution_summary.yaml",
        "strategy_comparison_dir": output_dir / "strategy_comparison",
        "strategy_comparison_csv": output_dir / "strategy_comparison.csv",
        "strategy_comparison_summary": output_dir / "strategy_comparison_summary.yaml",
        "within_sector_daily_metrics": output_dir / "within_sector_daily_metrics.csv",
        "within_sector_summary": output_dir / "within_sector_summary.csv",
        "within_industry_summary": output_dir / "within_industry_summary.csv",
        "within_sector_quantile_returns": output_dir / "within_sector_quantile_returns.csv",
        "within_sector_selection_summary": output_dir / "within_sector_selection_summary.yaml",
        "sector_error_review_summary_csv": output_dir / "sector_error_review_summary.csv",
        "sector_error_examples_csv": output_dir / "sector_error_examples.csv",
        "sector_error_feature_differences_csv": output_dir / "sector_error_feature_differences.csv",
        "sector_error_review_summary_yaml": output_dir / "sector_error_review_summary.yaml",
        "short_history_bucket_summary": output_dir / "short_history_bucket_summary.csv",
        "short_history_examples": output_dir / "short_history_examples.csv",
        "short_history_feature_differences": output_dir / "short_history_feature_differences.csv",
        "short_history_sector_breakdown": output_dir / "short_history_sector_breakdown.csv",
        "short_history_review_summary": output_dir / "short_history_review_summary.yaml",
        "report_md": output_dir / "report.md",
        "resolved_config": output_dir / "resolved_config.yaml",
    }
    fundamentals = config.get("fundamentals", {})
    cache_dir = fundamentals.get("cache_dir") if fundamentals else None
    paths["edgar_cache_dir"] = resolve_path(cache_dir) if cache_dir else output_dir / "edgar_cache"
    macro_features = config.get("macro_features", {})
    macro_cache_dir = macro_features.get("cache_dir") if macro_features else None
    paths["macro_cache_dir"] = resolve_path(macro_cache_dir) if macro_cache_dir else output_dir / "fred_alfred_cache"
    return paths


def write_resolved_config(config: dict[str, Any], paths: dict[str, Path]) -> None:
    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    resolved = {key: value for key, value in config.items() if not key.startswith("_")}
    resolved["_metadata"] = {
        "config_path": config["_config_path"],
        "output_dir_absolute": str(paths["output_dir"]),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    paths["resolved_config"].write_text(
        yaml.safe_dump(resolved, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def set_training_seed(config: dict[str, Any]) -> int | None:
    seed = config.get("training", {}).get("seed")
    if seed is None:
        return None
    seed = int(seed)
    random.seed(seed)
    np.random.seed(seed)
    return seed


def use_cached_test_predictions(config: dict[str, Any]) -> bool:
    return bool(config.get("training", {}).get("reuse_test_predictions", False))


def read_test_predictions(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"training.reuse_test_predictions is true but {path} does not exist")
    frame = pd.read_csv(path)
    required = {"datetime", "instrument", "score"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"cached test_predictions.csv missing column(s): {', '.join(missing)}")
    frame = frame[["datetime", "instrument", "score"]].copy()
    frame["datetime"] = pd.to_datetime(frame["datetime"]).dt.normalize()
    frame["instrument"] = frame["instrument"].astype(str).str.upper()
    frame["score"] = pd.to_numeric(frame["score"], errors="coerce")
    return frame.dropna(subset=["datetime", "instrument", "score"])


def prediction_frame_to_series(frame: pd.DataFrame) -> pd.Series:
    working = frame[["datetime", "instrument", "score"]].copy()
    working["datetime"] = pd.to_datetime(working["datetime"]).dt.normalize()
    working["instrument"] = working["instrument"].astype(str).str.upper()
    index = pd.MultiIndex.from_frame(working[["datetime", "instrument"]])
    index.names = ["datetime", "instrument"]
    return pd.Series(pd.to_numeric(working["score"], errors="coerce").to_numpy(), index=index, name="score")


def dump_qlib_bin(config: dict[str, Any], paths: dict[str, Path]) -> None:
    qlib_dir = paths["qlib_dir"]
    if qlib_dir.exists():
        shutil.rmtree(qlib_dir)
    sys.path.insert(0, str(WORKSPACE))
    from scripts.dump_bin import DumpDataAll

    print("Dumping CSV files into Qlib bin format...")
    dumper = DumpDataAll(
        data_path=str(paths["source_dir"]),
        qlib_dir=str(qlib_dir),
        freq=config["data"]["freq"],
        max_workers=8,
        date_field_name="date",
        symbol_field_name="symbol",
        exclude_fields="date,symbol",
        file_suffix=".csv",
    )
    dumper.dump()


def choose_segments(config: dict[str, Any], paths: dict[str, Path]) -> dict[str, tuple[str, str]]:
    calendar = pd.read_csv(paths["qlib_dir"] / "calendars/day.txt", header=None)[0]
    dates = pd.to_datetime(calendar).sort_values().reset_index(drop=True)
    warmup_days = int(config["split"]["warmup_days"])
    if len(dates) < max(300, warmup_days + 30):
        raise RuntimeError(f"not enough trading dates for model training: {len(dates)}")

    if config["split"]["method"] == "date":
        return choose_date_segments(config, dates, warmup_days)

    train_ratio = float(config["split"]["train_ratio"])
    valid_ratio = float(config["split"]["valid_ratio"])
    train_end_idx = int(len(dates) * train_ratio)
    valid_end_idx = int(len(dates) * (train_ratio + valid_ratio))
    if train_end_idx <= warmup_days or valid_end_idx <= train_end_idx + 1 or valid_end_idx >= len(dates) - 1:
        raise RuntimeError("split ratios leave an invalid train/valid/test segment")

    train_end = dates.iloc[train_end_idx].strftime("%Y-%m-%d")
    valid_start = dates.iloc[train_end_idx + 1].strftime("%Y-%m-%d")
    valid_end = dates.iloc[valid_end_idx].strftime("%Y-%m-%d")
    test_start = dates.iloc[valid_end_idx + 1].strftime("%Y-%m-%d")
    return {
        "fit": (dates.iloc[0].strftime("%Y-%m-%d"), train_end),
        "all": (dates.iloc[0].strftime("%Y-%m-%d"), dates.iloc[-1].strftime("%Y-%m-%d")),
        "train": (dates.iloc[warmup_days].strftime("%Y-%m-%d"), train_end),
        "valid": (valid_start, valid_end),
        "test": (test_start, dates.iloc[-1].strftime("%Y-%m-%d")),
    }


def choose_date_segments(
    config: dict[str, Any],
    dates: pd.Series,
    warmup_days: int,
) -> dict[str, tuple[str, str]]:
    split = config["split"]
    train = calendar_segment(dates, split["train"]["start"], split["train"]["end"], "train")
    valid = calendar_segment(dates, split["valid"]["start"], split["valid"]["end"], "valid")
    test = calendar_segment(dates, split["test"]["start"], split["test"]["end"], "test")
    warmup_start = dates.iloc[warmup_days]
    train_start = max(pd.Timestamp(train[0]), warmup_start).strftime("%Y-%m-%d")
    if pd.Timestamp(train_start) > pd.Timestamp(train[1]):
        raise RuntimeError("warmup_days leave no dates in the configured train segment")
    return {
        "fit": (dates.iloc[0].strftime("%Y-%m-%d"), train[1]),
        "all": (dates.iloc[0].strftime("%Y-%m-%d"), dates.iloc[-1].strftime("%Y-%m-%d")),
        "train": (train_start, train[1]),
        "valid": valid,
        "test": test,
    }


def calendar_segment(dates: pd.Series, start: Any, end: Any, label: str) -> tuple[str, str]:
    start_ts = date_value(start)
    end_ts = date_value(end)
    selected = dates[(dates >= start_ts) & (dates <= end_ts)]
    if selected.empty:
        raise RuntimeError(f"no trading dates available for configured {label} segment")
    return selected.iloc[0].strftime("%Y-%m-%d"), selected.iloc[-1].strftime("%Y-%m-%d")


def train_and_predict(
    universe: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    sys.path.insert(0, str(WORKSPACE))

    import qlib
    from qlib.constant import REG_US
    from qlib.contrib.data.handler import Alpha158
    from qlib.contrib.model.gbdt import LGBModel
    from qlib.data.dataset import DatasetH
    from qlib.data.dataset.handler import DataHandlerLP
    from qlib.data.dataset.loader import StaticDataLoader

    qlib.init(
        provider_uri=str(paths["qlib_dir"]),
        region=REG_US,
        expression_cache=None,
        dataset_cache=None,
    )
    segments = choose_segments(config, paths)
    print(f"Segments: {segments}")

    handler = Alpha158(
        instruments=config["features"]["instruments"],
        start_time=segments["all"][0],
        end_time=segments["all"][1],
        fit_start_time=segments["fit"][0],
        fit_end_time=segments["fit"][1],
        freq=config["data"]["freq"],
        label=([config["label"]["expression"]], [config["label"]["name"]]),
    )
    fundamental_result = None
    market_feature_result = None
    macro_result = None
    industry_result = None
    extra_feature_frames: list[pd.DataFrame] = []
    if config.get("market_features", {}).get("enabled", False):
        print("Building market-derived sector-relative features...")
        market_feature_result = build_market_feature_frame(universe, config, paths)
        extra_feature_frames.append(market_feature_result.features)
    if config.get("fundamentals", {}).get("enabled", False):
        print("Building SEC EDGAR point-in-time fundamental features...")
        fundamental_result = build_fundamental_features(universe, config, paths)
        extra_feature_frames.append(fundamental_result.features)
    if config.get("macro_features", {}).get("enabled", False):
        print("Building FRED/ALFRED point-in-time macro features...")
        macro_result = build_macro_feature_frame(universe, config, paths)
        extra_feature_frames.append(macro_result.features)
    if config.get("industry", {}).get("enabled", False):
        print("Building industry-relative fundamental features...")
        if fundamental_result is None:
            raise RuntimeError("industry features require fundamental features to be built first")
        industry_result = build_industry_feature_frame(universe, config, paths, fundamental_result.features)
        extra_feature_frames.append(industry_result.features)
    if extra_feature_frames:
        raw = handler.fetch(
            selector=slice(segments["all"][0], segments["all"][1]),
            col_set=["feature", "label"],
            data_key=DataHandlerLP.DK_R,
        )
        combined = combine_alpha_and_feature_frames_raw(raw, extra_feature_frames)
        handler = DataHandlerLP(
            data_loader=StaticDataLoader(combined),
            learn_processors=[
                {"class": "DropnaLabel"},
                {"class": "CSZScoreNorm", "kwargs": {"fields_group": "label"}},
            ],
        )

    dataset = DatasetH(
        handler=handler,
        segments={
            "train": segments["train"],
            "valid": segments["valid"],
            "test": segments["test"],
        },
    )
    training_seed = set_training_seed(config)
    if use_cached_test_predictions(config):
        print(f"Reusing cached test predictions from {paths['test_predictions_csv']}...")
        pred_frame = read_test_predictions(paths["test_predictions_csv"])
        pred = prediction_frame_to_series(pred_frame)
        prediction_source = "cached_test_predictions"
    else:
        model = LGBModel(**config["model"]["kwargs"])
        print("Training Qlib LGBModel on Alpha158 features...")
        model.fit(dataset)
        pred = model.predict(dataset, segment="test")
        pred.name = "score"
        pred_frame = pred.reset_index()
        pred_frame.columns = ["datetime", "instrument", "score"]
        pred_frame["datetime"] = pd.to_datetime(pred_frame["datetime"]).dt.normalize()
        pred_frame["instrument"] = pred_frame["instrument"].astype(str).str.upper()
        pred_frame.to_csv(paths["test_predictions_csv"], index=False)
        prediction_source = "trained"
    latest_date = pred_frame["datetime"].max()
    latest = pred_frame[pred_frame["datetime"] == latest_date].copy()
    latest["symbol"] = latest["instrument"].astype(str).str.upper()
    merged = latest.merge(universe, on="symbol", how="left")
    merged = merged.sort_values("score", ascending=False)
    merged.to_csv(paths["predictions_csv"], index=False)
    top_predictions, bucket_meta = apply_bucket_ranking(merged, config, paths)

    label = dataset.prepare("test", col_set="label", data_key=DataHandlerLP.DK_L)
    label_series = label.iloc[:, 0] if isinstance(label, pd.DataFrame) else label
    aligned = pd.concat([pred.rename("pred"), label_series.rename("label")], axis=1).dropna()
    if aligned.empty:
        ic_mean = math.nan
        rank_ic_mean = math.nan
        ic_count = 0
    else:
        ic = aligned.groupby(level="datetime").apply(lambda x: x["pred"].corr(x["label"]))
        rank_ic = aligned.groupby(level="datetime").apply(lambda x: x["pred"].corr(x["label"], method="spearman"))
        ic_mean = float(ic.mean())
        rank_ic_mean = float(rank_ic.mean())
        ic_count = int(ic.notna().sum())

    backtest_result = run_topk_backtest(pred_frame, universe, config, paths)
    strategy_comparison = run_strategy_comparison(pred_frame, universe, config, paths)
    within_sector_result = run_within_sector_review(pred_frame, universe, config, paths)
    sector_error_result = run_sector_error_review(pred_frame, universe, config, paths)
    short_history_result = run_short_history_review(pred_frame, universe, config, paths)

    meta = {
        "segments": segments,
        "latest_date": str(pd.Timestamp(latest_date).date()),
        "prediction_count": int(len(merged)),
        "ic_mean": ic_mean,
        "rank_ic_mean": rank_ic_mean,
        "ic_count": ic_count,
        "prediction_source": prediction_source,
        "training_seed": training_seed,
        "deterministic_training": bool(config.get("training", {}).get("deterministic", False)),
        "reuse_test_predictions": bool(use_cached_test_predictions(config)),
        "fundamentals_enabled": bool(config.get("fundamentals", {}).get("enabled", False)),
        "fundamental_feature_count": 0 if fundamental_result is None else int(fundamental_result.features.shape[1]),
        "fundamental_failure_count": 0 if fundamental_result is None else int(len(fundamental_result.failures)),
        "cik_mapped_count": 0 if fundamental_result is None else int(len(fundamental_result.cik_map)),
        "market_features_enabled": bool(config.get("market_features", {}).get("enabled", False)),
        "market_feature_count": 0 if market_feature_result is None else int(market_feature_result.features.shape[1]),
        "market_feature_failure_count": 0 if market_feature_result is None else int(len(market_feature_result.failures)),
        "market_feature_coverage": {} if market_feature_result is None else market_feature_result.coverage,
        "macro_features_enabled": bool(config.get("macro_features", {}).get("enabled", False)),
        "macro_feature_count": 0 if macro_result is None else int(macro_result.features.shape[1]),
        "macro_failure_count": 0 if macro_result is None else int(len(macro_result.failures)),
        "macro_feature_coverage": {} if macro_result is None else macro_result.coverage,
        "industry_enabled": bool(config.get("industry", {}).get("enabled", False)),
        "industry_feature_count": 0 if industry_result is None else int(industry_result.features.shape[1]),
        "industry_failure_count": 0 if industry_result is None else int(len(industry_result.failures)),
        "industry_coverage": {} if industry_result is None else industry_result.coverage,
        "bucket_ranking_enabled": bool(bucket_meta["bucket_ranking_enabled"]),
        "history_bucket_counts": bucket_meta["bucket_counts"],
        "bucket_quotas": bucket_meta["bucket_quotas"],
        "selected_bucket_counts": bucket_meta["selected_bucket_counts"],
        "industry_constraints_enabled": bool(bucket_meta.get("industry_constraints_enabled", False)),
        "industry_constraints": bucket_meta.get("industry_constraints", {}),
        "selected_sector_counts": bucket_meta.get("selected_sector_counts", {}),
        "selected_industry_counts": bucket_meta.get("selected_industry_counts", {}),
        "score_calibration_enabled": bool(bucket_meta.get("score_calibration_enabled", False)),
        "score_calibration_exclusion_count": int(bucket_meta.get("score_calibration_exclusion_count", 0)),
        "top_sector_counts": top_predictions["sector"].fillna("UNKNOWN").value_counts().to_dict()
        if "sector" in top_predictions
        else {},
        "top_industry_counts": top_predictions["industry"].fillna("UNKNOWN").value_counts().to_dict()
        if "industry" in top_predictions
        else {},
        "backtest_enabled": bool(backtest_result.summary.get("enabled", False)),
        "backtest_summary": backtest_result.summary,
        "strategy_comparison": strategy_comparison,
        "within_sector_review": within_sector_result.summary,
        "sector_error_review": sector_error_result.yaml_summary,
        "short_history_review": short_history_result.yaml_summary,
    }
    return top_predictions, meta


def run_strategy_comparison(
    predictions: pd.DataFrame,
    universe: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
) -> dict[str, Any]:
    comparison = config.get("strategy_comparison", {})
    if not comparison.get("enabled", False):
        return {"enabled": False, "rows": []}

    rows = []
    variant_summaries = []
    paths["strategy_comparison_dir"].mkdir(parents=True, exist_ok=True)
    for variant in comparison.get("variants", []):
        variant_config = build_strategy_variant_config(config, variant)
        variant_paths = build_strategy_variant_paths(paths, variant)
        result = run_topk_backtest(predictions, universe, variant_config, variant_paths)
        row = summarize_strategy_variant(variant, result, variant_paths)
        rows.append(row)
        variant_summaries.append(
            {
                "name": row["name"],
                "description": row["description"],
                "output_dir": row["output_dir"],
                "summary": result.summary,
            }
        )

    frame = pd.DataFrame(rows)
    frame.to_csv(paths["strategy_comparison_csv"], index=False)
    summary = {
        "enabled": True,
        "rows": rows,
        "variants": variant_summaries,
        "insights": build_strategy_comparison_insights(rows),
    }
    paths["strategy_comparison_summary"].write_text(
        yaml.safe_dump(summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return summary


def build_strategy_variant_config(config: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
    variant_config = deepcopy(config)
    variant_name = str(variant["name"])
    if "experiment" in variant_config:
        base_name = config.get("experiment", {}).get("name", "strategy_comparison")
        variant_config["experiment"]["name"] = f"{base_name}__{variant_name}"
    for key in ["bucket_ranking", "backtest", "benchmark", "attribution", "score_calibration"]:
        if key in variant:
            variant_config[key] = deep_merge_dicts(variant_config.get(key, {}), variant[key])
    if "industry_constraints" in variant:
        variant_config["industry_constraints"] = deepcopy(variant["industry_constraints"])
    if "overrides" in variant:
        variant_config = deep_merge_dicts(variant_config, variant["overrides"])
    return variant_config


def deep_merge_dicts(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_dicts(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def build_strategy_variant_paths(paths: dict[str, Path], variant: dict[str, Any]) -> dict[str, Path]:
    suffix = str(variant.get("output_dir_suffix") or variant["name"])
    variant_dir = paths["strategy_comparison_dir"] / suffix
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


def summarize_strategy_variant(
    variant: dict[str, Any],
    result: Any,
    variant_paths: dict[str, Path],
) -> dict[str, Any]:
    summary = result.summary
    benchmark = summary.get("benchmark", {})
    concentration = sector_concentration_stats(result.positions)
    constraints = variant.get("industry_constraints", {})
    calibration = variant.get("score_calibration", {})
    return {
        "name": str(variant["name"]),
        "description": str(variant.get("description", "")),
        "output_dir": str(variant_paths["output_dir"]),
        "industry_constraints_enabled": bool(constraints.get("enabled", False)),
        "sector_momentum_tilt_enabled": bool(constraints.get("sector_momentum_tilt", {}).get("enabled", False)),
        "score_calibration_enabled": bool(calibration.get("enabled", False)),
        "score_calibration_method": calibration.get("method"),
        "max_sector": constraints.get("max_sector"),
        "max_industry": constraints.get("max_industry"),
        "period_count": summary.get("period_count"),
        "cumulative_return": summary.get("cumulative_return"),
        "annualized_return": summary.get("annualized_return"),
        "annualized_volatility": summary.get("annualized_volatility"),
        "information_ratio": summary.get("information_ratio"),
        "max_drawdown": summary.get("max_drawdown"),
        "avg_turnover": summary.get("avg_turnover"),
        "avg_position_count": summary.get("avg_position_count"),
        "excess_cumulative_return": benchmark.get("excess_cumulative_return"),
        "relative_information_ratio": benchmark.get("relative_information_ratio"),
        "alpha_annualized": benchmark.get("alpha_annualized"),
        "beta": benchmark.get("beta"),
        "correlation": benchmark.get("correlation"),
        "max_avg_sector": concentration.get("max_avg_sector"),
        "max_avg_sector_exposure": concentration.get("max_avg_sector_exposure"),
        "max_sector_weight_any_period": concentration.get("max_sector_weight_any_period"),
        "avg_sector_hhi": concentration.get("avg_sector_hhi"),
    }


def build_strategy_comparison_insights(rows: list[dict[str, Any]]) -> dict[str, Any]:
    sensitivity_rows = [row for row in rows if is_sector_cap_sensitivity_row(row)]
    if not sensitivity_rows:
        return {"enabled": False}

    return {
        "enabled": True,
        "best_annualized_return": metric_leader(sensitivity_rows, "annualized_return", higher_is_better=True),
        "best_max_drawdown": metric_leader(sensitivity_rows, "max_drawdown", higher_is_better=True),
        "best_excess_cumulative_return": metric_leader(sensitivity_rows, "excess_cumulative_return", higher_is_better=True),
        "lowest_sector_concentration": metric_leader(sensitivity_rows, "avg_sector_hhi", higher_is_better=False),
        "recommended_default": recommend_sector_cap(sensitivity_rows),
    }


def is_sector_cap_sensitivity_row(row: dict[str, Any]) -> bool:
    name = str(row.get("name", ""))
    if name in {"sector_cap_2_top10", "sector_cap_3_top10", "sector_cap_4_top10"}:
        return True
    if bool(row.get("score_calibration_enabled")):
        return False
    return (
        bool(row.get("industry_constraints_enabled"))
        and not bool(row.get("sector_momentum_tilt_enabled"))
        and pd.notna(row.get("max_sector"))
    )


def metric_leader(rows: list[dict[str, Any]], key: str, higher_is_better: bool) -> dict[str, Any]:
    usable = [row for row in rows if pd.notna(row.get(key))]
    if not usable:
        return {}
    best = max(usable, key=lambda row: float(row[key])) if higher_is_better else min(usable, key=lambda row: float(row[key]))
    return metric_record(best, key)


def recommend_sector_cap(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = [
        ("annualized_return", True),
        ("excess_cumulative_return", True),
        ("max_drawdown", True),
        ("avg_sector_hhi", False),
    ]
    scored = []
    for row in rows:
        score = 0
        for metric, higher_is_better in metrics:
            ordered = sorted(
                [candidate for candidate in rows if pd.notna(candidate.get(metric))],
                key=lambda candidate: float(candidate[metric]),
                reverse=higher_is_better,
            )
            ranks = {candidate["name"]: rank + 1 for rank, candidate in enumerate(ordered)}
            score += ranks.get(row["name"], len(rows) + 1)
        scored.append((score, sector_cap_tie_breaker(row), row))

    if not scored:
        return {}
    _, _, selected = min(scored, key=lambda item: (item[0], item[1]))
    record = metric_record(selected, "balanced_rank_score")
    record["balanced_rank_score"] = int(min(scored, key=lambda item: (item[0], item[1]))[0])
    record["reason"] = "综合年化收益、超额收益、最大回撤和行业集中度排名，平局时优先选择中等约束。"
    return record


def sector_cap_tie_breaker(row: dict[str, Any]) -> int:
    preferred_order = {3: 0, 2: 1, 4: 2}
    try:
        return preferred_order.get(int(row.get("max_sector")), 99)
    except (TypeError, ValueError):
        return 99


def metric_record(row: dict[str, Any], metric: str) -> dict[str, Any]:
    return {
        "name": row.get("name"),
        "max_sector": normalize_report_scalar(row.get("max_sector")),
        "max_industry": normalize_report_scalar(row.get("max_industry")),
        "metric": metric,
        "value": normalize_report_scalar(row.get(metric)),
        "annualized_return": normalize_report_scalar(row.get("annualized_return")),
        "max_drawdown": normalize_report_scalar(row.get("max_drawdown")),
        "excess_cumulative_return": normalize_report_scalar(row.get("excess_cumulative_return")),
        "alpha_annualized": normalize_report_scalar(row.get("alpha_annualized")),
        "avg_sector_hhi": normalize_report_scalar(row.get("avg_sector_hhi")),
    }


def normalize_report_scalar(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (bool, int, str)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def sector_concentration_stats(positions: pd.DataFrame) -> dict[str, Any]:
    if positions.empty or "sector" not in positions.columns:
        return {}
    working = positions.copy()
    working["sector"] = working["sector"].fillna("UNKNOWN").replace("", "UNKNOWN")
    period_sector = working.groupby(["period", "sector"], dropna=False)["weight"].sum().reset_index()
    if period_sector.empty:
        return {}
    sector_avg = period_sector.groupby("sector", dropna=False)["weight"].mean().sort_values(ascending=False)
    hhi = period_sector.assign(weight_sq=period_sector["weight"] ** 2).groupby("period")["weight_sq"].sum()
    return {
        "max_avg_sector": str(sector_avg.index[0]),
        "max_avg_sector_exposure": float(sector_avg.iloc[0]),
        "max_sector_weight_any_period": float(period_sector["weight"].max()),
        "avg_sector_hhi": float(hhi.mean()),
    }


def combine_alpha_and_feature_frames_raw(
    alpha_raw: pd.DataFrame,
    extra_feature_frames: list[pd.DataFrame],
) -> pd.DataFrame:
    alpha_features = alpha_raw["feature"]
    labels = alpha_raw["label"]
    aligned_features = [frame.reindex(alpha_features.index) for frame in extra_feature_frames if not frame.empty]
    combined_features = pd.concat([alpha_features, *aligned_features], axis=1)
    combined_features = combined_features.mask(combined_features.isna(), np.nan).apply(pd.to_numeric, errors="coerce")
    labels = labels.mask(labels.isna(), np.nan).apply(pd.to_numeric, errors="coerce")
    return pd.concat({"feature": combined_features, "label": labels}, axis=1).sort_index()


def combine_alpha_and_fundamental_raw(alpha_raw: pd.DataFrame, fundamental_features: pd.DataFrame) -> pd.DataFrame:
    return combine_alpha_and_feature_frames_raw(alpha_raw, [fundamental_features])


def fmt_money(value: float) -> str:
    if pd.isna(value):
        return "N/A"
    if value >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value:,.0f}"


def fmt_optional_money(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/A"
    return fmt_money(numeric)


def fmt_optional_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).replace("|", "/")


def format_yaml_block(value: Any) -> list[str]:
    dumped = yaml.safe_dump(value, allow_unicode=True, sort_keys=False).strip()
    return ["```yaml", dumped, "```"]


def universe_future_information_warning(config: dict[str, Any]) -> list[str]:
    selection = config["universe"].get("selection", {})
    if selection.get("method") == "approximate_market_cap_asof":
        return [
            "重要限制：本配置使用 as-of 近似冻结股票池，已经避免直接用测试期后的市值排名选股；但 `nasdaq_public` 仍缺少历史 shares outstanding、退市股票和历史证券主数据，因此它只能降低未来信息风险，不能等同于完整 PIT 股票池。",
        ]
    return [
        "重要限制：当前 `nasdaq_public` 股票池仍按运行日的 Nasdaq 市值前 500 构建，不是历史 PIT 股票池；因此即使启用 point_in_time_filters，仍不能视为完全杜绝未来信息的严谨回测。",
    ]


def fmt_pct(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if math.isnan(numeric):
        return "N/A"
    return f"{numeric:.2%}"


def fmt_number(value: Any, digits: int = 4) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if math.isnan(numeric):
        return "N/A"
    return f"{numeric:.{digits}f}"


def fmt_delta_pct(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if math.isnan(numeric):
        return "N/A"
    sign = "+" if numeric >= 0 else ""
    return f"{sign}{numeric:.2%}"


def fmt_delta_number(value: Any, digits: int = 3) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if math.isnan(numeric):
        return "N/A"
    sign = "+" if numeric >= 0 else ""
    return f"{sign}{numeric:.{digits}f}"


def fmt_optional_int(value: Any) -> str:
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return "N/A"


def metric_delta(left: dict[str, Any], right: dict[str, Any], key: str) -> float:
    try:
        return float(left.get(key)) - float(right.get(key))
    except (TypeError, ValueError):
        return math.nan


def strategy_comparison_report_lines(summary: dict[str, Any]) -> list[str]:
    if not summary.get("enabled", False):
        return ["- 未启用。"]
    rows = summary.get("rows", [])
    if not rows:
        return ["- 已启用，但没有生成策略对照结果。"]

    lines = [
        "| Variant | 规则 | Score 校准 | Max Sector | 累计收益 | 年化收益 | 最大回撤 | 超额累计收益 | 年化 Alpha | Beta | 最大平均 sector 暴露 | Sector HHI |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        rule = "行业增强" if row.get("sector_momentum_tilt_enabled") else "行业约束" if row.get("industry_constraints_enabled") else "不限制行业"
        calibration = "短历史校准" if row.get("score_calibration_enabled") else "无"
        lines.append(
            "| {name} | {rule} | {calibration} | {max_sector} | {cum} | {ann} | {dd} | {excess} | {alpha} | {beta} | {sector} {sector_weight} | {hhi} |".format(
                name=row.get("name", "N/A"),
                rule=rule,
                calibration=calibration,
                max_sector=fmt_optional_int(row.get("max_sector")),
                cum=fmt_pct(row.get("cumulative_return")),
                ann=fmt_pct(row.get("annualized_return")),
                dd=fmt_pct(row.get("max_drawdown")),
                excess=fmt_pct(row.get("excess_cumulative_return")),
                alpha=fmt_pct(row.get("alpha_annualized")),
                beta=fmt_number(row.get("beta"), 3),
                sector=row.get("max_avg_sector") or "N/A",
                sector_weight=fmt_pct(row.get("max_avg_sector_exposure")),
                hhi=fmt_number(row.get("avg_sector_hhi"), 3),
            )
        )

    by_name = {row.get("name"): row for row in rows}
    unconstrained = by_name.get("unconstrained_top10")
    cap2 = by_name.get("sector_cap_2_top10")
    cap3 = by_name.get("sector_cap_3_top10") or by_name.get("sector_capped_top10")
    cap4 = by_name.get("sector_cap_4_top10")
    tilted = by_name.get("sector_momentum_tilt_top10")
    raw_cap2 = by_name.get("raw_score_sector_cap_2_top10")
    penalty_cap2 = by_name.get("short_history_penalty_sector_cap_2_top10")
    strict_cap2 = by_name.get("short_history_strict_sector_cap_2_top10")
    lines.extend(["", "对照解读："])
    if unconstrained and cap3:
        lines.append(
            f"- max_sector=3 相对原始 Top10 的年化收益变化：{fmt_delta_pct(metric_delta(cap3, unconstrained, 'annualized_return'))}；超额累计收益变化：{fmt_delta_pct(metric_delta(cap3, unconstrained, 'excess_cumulative_return'))}。"
        )
    if cap2 and cap3:
        lines.append(
            f"- max_sector=2 相对 max_sector=3 的年化收益变化：{fmt_delta_pct(metric_delta(cap2, cap3, 'annualized_return'))}；Sector HHI 变化：{fmt_delta_number(metric_delta(cap2, cap3, 'avg_sector_hhi'))}。"
        )
    if cap4 and cap3:
        lines.append(
            f"- max_sector=4 相对 max_sector=3 的年化收益变化：{fmt_delta_pct(metric_delta(cap4, cap3, 'annualized_return'))}；Sector HHI 变化：{fmt_delta_number(metric_delta(cap4, cap3, 'avg_sector_hhi'))}。"
        )
    if cap3 and tilted:
        lines.append(
            f"- 行业增强相对 max_sector=3 的年化收益变化：{fmt_delta_pct(metric_delta(tilted, cap3, 'annualized_return'))}；超额累计收益变化：{fmt_delta_pct(metric_delta(tilted, cap3, 'excess_cumulative_return'))}。"
        )
    if raw_cap2 and penalty_cap2:
        lines.append(
            f"- 短历史惩罚相对原始 max_sector=2 的年化收益变化：{fmt_delta_pct(metric_delta(penalty_cap2, raw_cap2, 'annualized_return'))}；最大回撤变化：{fmt_delta_pct(metric_delta(penalty_cap2, raw_cap2, 'max_drawdown'))}。"
        )
    if raw_cap2 and strict_cap2:
        lines.append(
            f"- 短历史惩罚 + 更高流动性门槛相对原始 max_sector=2 的年化收益变化：{fmt_delta_pct(metric_delta(strict_cap2, raw_cap2, 'annualized_return'))}；超额累计收益变化：{fmt_delta_pct(metric_delta(strict_cap2, raw_cap2, 'excess_cumulative_return'))}。"
        )
    insights = summary.get("insights", {})
    if insights.get("enabled", False):
        lines.extend(["", "行业约束参数敏感性：", *strategy_insight_report_lines(insights)])
    lines.append(
        "- 判断口径：如果行业约束后收益明显下降，原策略更像行业押注；如果约束后仍稳定，模型更可能有行业内选股能力；如果行业增强最好，说明行业趋势和个股精选可能都值得保留。"
    )
    return lines


def strategy_insight_report_lines(insights: dict[str, Any]) -> list[str]:
    return [
        f"- 年化收益最高：{format_strategy_insight(insights.get('best_annualized_return'))}",
        f"- 最大回撤最小：{format_strategy_insight(insights.get('best_max_drawdown'))}",
        f"- 超额收益最好：{format_strategy_insight(insights.get('best_excess_cumulative_return'))}",
        f"- 行业集中度最低：{format_strategy_insight(insights.get('lowest_sector_concentration'))}",
        f"- 推荐默认约束：{format_strategy_insight(insights.get('recommended_default'))}",
    ]


def format_strategy_insight(record: dict[str, Any] | None) -> str:
    if not record:
        return "N/A"
    return (
        f"{record.get('name', 'N/A')} "
        f"(max_sector={fmt_optional_int(record.get('max_sector'))}, "
        f"年化={fmt_pct(record.get('annualized_return'))}, "
        f"最大回撤={fmt_pct(record.get('max_drawdown'))}, "
        f"超额={fmt_pct(record.get('excess_cumulative_return'))}, "
        f"HHI={fmt_number(record.get('avg_sector_hhi'), 3)})"
    )


def within_sector_report_lines(summary: dict[str, Any]) -> list[str]:
    if not summary.get("enabled", False):
        return ["- 未启用。"]
    lines = [
        f"- sector 覆盖数量：{summary.get('sector_count', 0)}",
        f"- industry 覆盖数量：{summary.get('industry_count', 0)}",
        f"- 低样本 sector 数量：{summary.get('low_sample_sector_count', 0)}",
        "- Rank IC 最好的 sector：",
        *format_yaml_block(summary.get("top_sectors_by_rank_ic", [])[:5]),
        "- Rank IC 最弱的 sector：",
        *format_yaml_block(summary.get("bottom_sectors_by_rank_ic", [])[:5]),
        "- Top-Bottom spread 最好的 sector：",
        *format_yaml_block(summary.get("top_sectors_by_spread", [])[:5]),
        "- Top-Bottom spread 最弱的 sector：",
        *format_yaml_block(summary.get("bottom_sectors_by_spread", [])[:5]),
        "",
        "行业内复盘口径：每个信号日先按 sector 分组，只在同一 sector 内比较 score 和未来 5 日实际收益；sector 内可交易股票少于配置阈值时不计算 Top/Bottom spread。",
    ]
    return lines


def sector_error_review_report_lines(summary: dict[str, Any]) -> list[str]:
    if not summary.get("enabled", False):
        return ["- 未启用。"]
    sectors = summary.get("sectors", [])
    if not sectors:
        return ["- 已启用，但没有生成重点行业错误复盘结果。"]

    lines = [
        "| Sector | 诊断 | Rank IC | Top-Bottom Spread | 高分输家率 | 低分赢家率 | 财报覆盖率 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in sectors:
        lines.append(
            "| {sector} | {diagnosis} | {rank_ic} | {spread} | {high_loser} | {low_winner} | {coverage} |".format(
                sector=row.get("sector", "N/A"),
                diagnosis=row.get("diagnosis", "N/A"),
                rank_ic=fmt_number(row.get("rank_ic_mean"), 4),
                spread=fmt_pct(row.get("top_bottom_spread_mean")),
                high_loser=fmt_pct(row.get("high_score_loser_rate")),
                low_winner=fmt_pct(row.get("low_score_winner_rate")),
                coverage=fmt_pct(row.get("fundamental_coverage_mean")),
            )
        )
    lines.extend(
        [
            "",
            "错误类别：`high_score_losers` 是模型高分但未来收益落后的假阳性；`low_score_winners` 是模型低分但未来收益靠前的漏选赢家。",
            "诊断口径：`model_effective` 表示该 sector 的行业内 Rank IC 和 Top-Bottom spread 同时为正；`model_weak` 表示两者同时偏弱或为负；其他为混合或噪声较大。",
        ]
    )
    differences = summary.get("largest_feature_differences", [])
    if differences:
        lines.extend(["", "差异最大的特征片段：", *format_yaml_block(differences[:8])])
    return lines


def short_history_review_report_lines(summary: dict[str, Any]) -> list[str]:
    if not summary.get("enabled", False):
        return ["- 未启用。"]
    buckets = summary.get("bucket_summary", [])
    if not buckets:
        return ["- 已启用，但没有生成短历史复盘结果。"]

    lines = [
        f"- 基线策略：`{summary.get('baseline_variant', 'N/A')}`",
        f"- 结论标签：`{summary.get('conclusion', 'N/A')}`",
        "",
        "| Bucket | 持仓次数 | 股票数 | 平均收益 | 胜率 | 净贡献 | 最差单票 | 输家低流动性 | 输家高估值 | 输家亏损公司 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in buckets:
        lines.append(
            "| {bucket} | {count} | {symbols} | {avg} | {win} | {contrib} | {worst} | {low_liq} | {valuation} | {unprofitable} |".format(
                bucket=row.get("history_bucket", "N/A"),
                count=fmt_optional_int(row.get("position_count")),
                symbols=fmt_optional_int(row.get("symbol_count")),
                avg=fmt_pct(row.get("avg_gross_return")),
                win=fmt_pct(row.get("win_rate")),
                contrib=fmt_pct(row.get("net_contribution_sum")),
                worst=fmt_pct(row.get("worst_position_return")),
                low_liq=fmt_pct(row.get("loser_low_liquidity_rate")),
                valuation=fmt_pct(row.get("loser_high_valuation_rate")),
                unprofitable=fmt_pct(row.get("loser_unprofitable_rate")),
            )
        )

    losses = summary.get("top_loss_sectors", [])
    gains = summary.get("top_gain_sectors", [])
    if losses:
        lines.extend(["", "短历史净贡献最弱的 sector：", *format_yaml_block(losses[:5])])
    if gains:
        lines.extend(["", "短历史净贡献最强的 sector：", *format_yaml_block(gains[:5])])
    differences = summary.get("largest_feature_differences", [])
    if differences:
        lines.extend(["", "赢家/输家差异最大的特征：", *format_yaml_block(differences[:8])])
    lines.append("")
    lines.append("复盘口径：本节直接读取基线策略的实际 `backtest_positions.csv`，解释已发生的持仓收益，不重新训练模型，也不重新生成一套选股结果。")
    return lines


def write_report(
    predictions: pd.DataFrame,
    meta: dict[str, Any],
    failures: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
) -> None:
    top_n = int(config["report"]["top_n"])
    top_predictions = predictions.head(top_n)
    model_kwargs = config["model"]["kwargs"]
    security_master = read_optional_csv(paths["security_master_csv"])
    security_master_exclusions = read_optional_csv(paths["security_master_exclusions_csv"])
    universe_exclusions = read_optional_csv(paths["universe_exclusions_csv"])
    liquidity_exclusions = read_optional_csv(paths["liquidity_exclusions_csv"])
    security_asset_counts = (
        security_master["asset_type"].value_counts().to_dict()
        if "asset_type" in security_master and not security_master.empty
        else {}
    )
    security_exclusion_counts = (
        security_master_exclusions["exclusion_reason"].value_counts().to_dict()
        if "exclusion_reason" in security_master_exclusions and not security_master_exclusions.empty
        else {}
    )
    exclusion_reason_counts = (
        universe_exclusions["exclusion_reason"].value_counts().to_dict()
        if "exclusion_reason" in universe_exclusions and not universe_exclusions.empty
        else {}
    )
    liquidity_exclusion_reason_counts = (
        liquidity_exclusions["exclusion_reason"].value_counts().to_dict()
        if "exclusion_reason" in liquidity_exclusions and not liquidity_exclusions.empty
        else {}
    )
    backtest_summary = meta.get("backtest_summary", {})
    benchmark_summary = backtest_summary.get("benchmark", {})
    attribution_summary = backtest_summary.get("attribution", {})
    strategy_comparison_summary = meta.get("strategy_comparison", {})
    within_sector_summary = meta.get("within_sector_review", {})
    sector_error_summary = meta.get("sector_error_review", {})
    short_history_summary = meta.get("short_history_review", {})
    lines = [
        f"# {config['experiment']['name']} Report",
        "",
        f"Generated at: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        "## 结论口径",
        "",
        "- 这次结果经过了 Qlib 模型流程：Qlib 数据格式、Alpha158 特征、LightGBM 模型训练、最新日预测分数排序。",
        "- 结果是学习研究材料，不是投资建议。",
        "",
        "## 实验名",
        "",
        f"- `{config['experiment']['name']}`",
        "",
        "## 股票池规则",
        "",
        *format_yaml_block(config["universe"]),
        "",
        "## 数据口径",
        "",
        *format_yaml_block(config["data"]),
        "",
        "## 证券主数据",
        "",
        *(
            [
                "- 证券主数据：已启用。",
                "- 主数据规则：",
                *format_yaml_block(config["universe"].get("security_master", {})),
                f"- 主数据记录数：{len(security_master)}",
                f"- 主数据剔除数：{len(security_master_exclusions)}",
                f"- ADR/ADS 数量：{int(security_master['is_adr_ads'].fillna(False).sum()) if 'is_adr_ads' in security_master else 0}",
                f"- Share class 数量：{int(security_master['is_share_class'].fillna(False).sum()) if 'is_share_class' in security_master else 0}",
                "- 资产类型分布：",
                *format_yaml_block(security_asset_counts),
                "- 主数据剔除原因：",
                *format_yaml_block(security_exclusion_counts),
            ]
            if config["universe"].get("security_master", {}).get("enabled", False)
            else ["- 未启用。"]
        ),
        "",
        "## 财报与估值特征",
        "",
        *(
            format_yaml_block(config.get("fundamentals", {}))
            if config.get("fundamentals", {}).get("enabled", False)
            else ["- 未启用。"]
        ),
        "",
        "## 行业相对特征",
        "",
        *(
            format_yaml_block(config.get("industry", {}))
            if config.get("industry", {}).get("enabled", False)
            else ["- 未启用。"]
        ),
        "",
        "## 行情相对特征",
        "",
        *(
            [
                *format_yaml_block(config.get("market_features", {})),
                f"- 行情相对特征数量：{meta.get('market_feature_count', 0)}",
                f"- 行情相对特征失败或跳过数量：{meta.get('market_feature_failure_count', 0)}",
                "- 行情相对特征覆盖：",
                *format_yaml_block(meta.get("market_feature_coverage", {})),
            ]
            if config.get("market_features", {}).get("enabled", False)
            else ["- 未启用。"]
        ),
        "",
        "## 宏观特征",
        "",
        *(
            [
                *format_yaml_block(config.get("macro_features", {})),
                f"- 宏观特征数量：{meta.get('macro_feature_count', 0)}",
                f"- 宏观特征失败或跳过数量：{meta.get('macro_failure_count', 0)}",
                "- 宏观特征覆盖：",
                *format_yaml_block(meta.get("macro_feature_coverage", {})),
                "",
                "宏观特征按 FRED/ALFRED 的 real-time/vintage 口径重建 as-of 序列，并顺延到下一个交易日后才进入模型。它是所有股票共享的市场状态变量，不单独决定横截面排名。",
            ]
            if config.get("macro_features", {}).get("enabled", False)
            else ["- 未启用。"]
        ),
        "",
        "## 标签与特征",
        "",
        f"- 标签名：`{config['label']['name']}`",
        f"- 标签表达式：`{config['label']['expression']}`",
        f"- 特征处理器：`{config['features']['handler']}`",
        f"- 特征股票范围：`{config['features']['instruments']}`",
        "",
        "## 模型参数",
        "",
        *format_yaml_block(model_kwargs),
        "",
        "## 训练复现控制",
        "",
        *(
            format_yaml_block(config.get("training", {}))
            if config.get("training")
            else ["- 未配置。"]
        ),
        f"- 预测分数来源：`{meta.get('prediction_source', 'trained')}`",
        f"- 训练随机种子：`{meta.get('training_seed')}`",
        f"- 是否复用 `test_predictions.csv`：`{meta.get('reuse_test_predictions', False)}`",
        "",
        "## 训练/验证/测试区间",
        "",
        f"- Fit: {meta['segments']['fit'][0]} 到 {meta['segments']['fit'][1]}",
        f"- Train: {meta['segments']['train'][0]} 到 {meta['segments']['train'][1]}",
        f"- Valid: {meta['segments']['valid'][0]} 到 {meta['segments']['valid'][1]}",
        f"- Test: {meta['segments']['test'][0]} 到 {meta['segments']['test'][1]}",
        f"- 最新预测日：{meta['latest_date']}",
        "",
        f"## Top {top_n} 预测结果",
        "",
    ]
    if meta.get("bucket_ranking_enabled", False):
        lines.extend(
            [
                "| Rank | Symbol | Bucket | Bucket Rank | Global Rank | Asset Type | ADR/ADS | Share Class | Name | Qlib Score | Market Cap | Sector | Industry |",
                "|---:|---|---|---:|---:|---|---|---|---|---:|---:|---|---|",
            ]
        )
    else:
        lines.extend(
            [
                "| Rank | Symbol | Name | Qlib Score | Market Cap | Sector | Industry |",
                "|---:|---|---|---:|---:|---|---|",
            ]
        )
    for rank, (_, row) in enumerate(top_predictions.iterrows(), start=1):
        if meta.get("bucket_ranking_enabled", False):
            lines.append(
                "| {rank} | {symbol} | {bucket} | {bucket_rank} | {global_rank} | {asset_type} | {is_adr_ads} | {share_class} | {name} | {score:.8f} | {market_cap} | {sector} | {industry} |".format(
                    rank=rank,
                    symbol=row.get("symbol", row.get("instrument", "N/A")),
                    bucket=row.get("history_bucket", "N/A"),
                    bucket_rank=row.get("bucket_rank", "N/A"),
                    global_rank=row.get("global_rank", "N/A"),
                    asset_type=fmt_optional_text(row.get("asset_type")),
                    is_adr_ads=fmt_optional_text(row.get("is_adr_ads")),
                    share_class=fmt_optional_text(row.get("share_class")),
                    name=str(row.get("name", "")).replace("|", "/"),
                    score=float(row["score"]),
                    market_cap=fmt_optional_money(row.get("market_cap")),
                    sector=str(row.get("sector", "")).replace("|", "/"),
                    industry=str(row.get("industry", "")).replace("|", "/"),
                )
            )
        else:
            lines.append(
                "| {rank} | {symbol} | {name} | {score:.8f} | {market_cap} | {sector} | {industry} |".format(
                    rank=rank,
                    symbol=row.get("symbol", row.get("instrument", "N/A")),
                    name=str(row.get("name", "")).replace("|", "/"),
                    score=float(row["score"]),
                    market_cap=fmt_optional_money(row.get("market_cap")),
                    sector=str(row.get("sector", "")).replace("|", "/"),
                    industry=str(row.get("industry", "")).replace("|", "/"),
                )
            )

    lines.extend(
        [
            "",
            "## 模型验证",
            "",
            f"- Test 日均 IC：{meta['ic_mean']:.6f}" if not math.isnan(meta["ic_mean"]) else "- Test 日均 IC：N/A",
            f"- Test 日均 Rank IC：{meta['rank_ic_mean']:.6f}"
            if not math.isnan(meta["rank_ic_mean"])
            else "- Test 日均 Rank IC：N/A",
            f"- 参与 IC 计算的交易日：{meta['ic_count']}",
            f"- EDGAR 特征数量：{meta.get('fundamental_feature_count', 0)}",
            f"- EDGAR CIK 映射数量：{meta.get('cik_mapped_count', 0)}",
            f"- EDGAR 失败或跳过数量：{meta.get('fundamental_failure_count', 0)}",
            f"- 行业相对特征数量：{meta.get('industry_feature_count', 0)}",
            f"- 行业分类失败或跳过数量：{meta.get('industry_failure_count', 0)}",
            f"- 宏观特征数量：{meta.get('macro_feature_count', 0)}",
            f"- 宏观特征失败或跳过数量：{meta.get('macro_failure_count', 0)}",
            "",
            "IC 可以粗略理解为：每个交易日横截面上，模型预测分数和真实后续收益的相关性。",
            "",
            "## TopK 成本后回测",
            "",
            *(
                [
                    "- 回测状态：已启用。",
                    "- 回测配置：",
                    *format_yaml_block(backtest_summary.get("config", config.get("backtest", {}))),
                    f"- 回测期数：{backtest_summary.get('period_count', 0)}",
                    f"- 跳过期数：{backtest_summary.get('skipped_periods', 0)}",
                    f"- 起始入场日：{backtest_summary.get('start_entry_date', 'N/A')}",
                    f"- 最终退出日：{backtest_summary.get('end_exit_date', 'N/A')}",
                    f"- 累计收益：{fmt_pct(backtest_summary.get('cumulative_return'))}",
                    f"- 年化收益：{fmt_pct(backtest_summary.get('annualized_return'))}",
                    f"- 年化波动：{fmt_pct(backtest_summary.get('annualized_volatility'))}",
                    f"- 信息比率：{fmt_number(backtest_summary.get('information_ratio'), 3)}",
                    f"- 最大回撤：{fmt_pct(backtest_summary.get('max_drawdown'))}",
                    f"- 平均单期毛收益：{fmt_pct(backtest_summary.get('avg_gross_return'))}",
                    f"- 平均单期净收益：{fmt_pct(backtest_summary.get('avg_net_return'))}",
                    f"- 胜率：{fmt_pct(backtest_summary.get('win_rate'))}",
                    f"- 平均换手：{fmt_pct(backtest_summary.get('avg_turnover'))}",
                    f"- 累计成本扣减：{fmt_pct(backtest_summary.get('total_cost_return'))}",
                    f"- 平均持仓数量：{fmt_number(backtest_summary.get('avg_position_count'), 2)}",
                    f"- 平均 PIT 过滤前候选数：{fmt_number(backtest_summary.get('avg_candidate_count_before_pit'), 2)}",
                    f"- 平均 PIT 过滤后候选数：{fmt_number(backtest_summary.get('avg_candidate_count_after_pit'), 2)}",
                    f"- 平均 PIT 历史长度通过数：{fmt_number(backtest_summary.get('avg_pit_history_pass_count'), 2)}",
                    f"- 平均 PIT 流动性通过数：{fmt_number(backtest_summary.get('avg_pit_liquidity_pass_count'), 2)}",
                    "- 出现次数最多的持仓：",
                    *format_yaml_block(backtest_summary.get("top_symbols_by_holding_count", {})),
                    "",
                    "本回测使用测试期每日模型分数，按配置的调仓间隔做非重叠 TopK 组合；信号日后一个交易日入场，持有指定交易日后退出，并扣除单边交易成本。若启用 point_in_time_filters，历史长度分桶和流动性过滤按信号日当时可见行情重新计算。它仍是学习研究材料，不是投资建议。",
                    "",
                    *universe_future_information_warning(config),
                ]
                if meta.get("backtest_enabled", False)
                else ["- 未启用。"]
            ),
            "",
            "## 基准与超额收益",
            "",
            *(
                [
                    "- 基准复盘：已启用。",
                    f"- 基准：{benchmark_summary.get('symbol', 'N/A')} / {benchmark_summary.get('name', 'N/A')}",
                    f"- 对齐回测期数：{benchmark_summary.get('period_count', 0)}",
                    f"- 策略累计收益：{fmt_pct(benchmark_summary.get('strategy_cumulative_return'))}",
                    f"- 基准累计收益：{fmt_pct(benchmark_summary.get('benchmark_cumulative_return'))}",
                    f"- 超额累计收益：{fmt_pct(benchmark_summary.get('excess_cumulative_return'))}",
                    f"- 基准年化收益：{fmt_pct(benchmark_summary.get('benchmark_annualized_return'))}",
                    f"- 基准年化波动：{fmt_pct(benchmark_summary.get('benchmark_annualized_volatility'))}",
                    f"- 基准最大回撤：{fmt_pct(benchmark_summary.get('benchmark_max_drawdown'))}",
                    f"- 跟踪误差：{fmt_pct(benchmark_summary.get('tracking_error'))}",
                    f"- 相对信息比率：{fmt_number(benchmark_summary.get('relative_information_ratio'), 3)}",
                    f"- Beta：{fmt_number(benchmark_summary.get('beta'), 3)}",
                    f"- 年化 Alpha：{fmt_pct(benchmark_summary.get('alpha_annualized'))}",
                    f"- 策略/基准相关性：{fmt_number(benchmark_summary.get('correlation'), 3)}",
                    f"- 相对最大回撤：{fmt_pct(benchmark_summary.get('relative_max_drawdown'))}",
                    f"- 跑赢基准期数占比：{fmt_pct(benchmark_summary.get('win_rate_vs_benchmark'))}",
                    "",
                    "基准复盘使用与策略相同的入场日和退出日计算同期收益。当前基准价格不是专业总回报复权指数口径，因此它适合学习比较，不等同于生产级绩效归因。",
                ]
                if benchmark_summary.get("enabled", False) and "error" not in benchmark_summary
                else [
                    f"- 基准复盘未生成：{benchmark_summary.get('error', '未启用。')}"
                    if benchmark_summary
                    else "- 未启用。"
                ]
            ),
            "",
            "## 行业暴露对照实验",
            "",
            *strategy_comparison_report_lines(strategy_comparison_summary),
            "",
            "## 行业内选股复盘",
            "",
            *within_sector_report_lines(within_sector_summary),
            "",
            "## 重点行业错误复盘",
            "",
            *sector_error_review_report_lines(sector_error_summary),
            "",
            "## 短历史股票专项复盘",
            "",
            *short_history_review_report_lines(short_history_summary),
            "",
            "## 持仓贡献与行业暴露",
            "",
            *(
                [
                    "- 贡献复盘：已启用。",
                    f"- 前 5 大正贡献占全部正贡献比例：{fmt_pct(attribution_summary.get('top_positive_contribution_share'))}",
                    "- 正贡献最大的股票：",
                    *format_yaml_block(attribution_summary.get("top_symbols", [])[:5]),
                    "- 负贡献最大的股票：",
                    *format_yaml_block(attribution_summary.get("bottom_symbols", [])[:5]),
                    "- 正贡献最大的 sector：",
                    *format_yaml_block(attribution_summary.get("top_sectors", [])[:5]),
                    "- 负贡献最大的 sector：",
                    *format_yaml_block(attribution_summary.get("bottom_sectors", [])[:5]),
                    "- 正贡献最大的 industry：",
                    *format_yaml_block(attribution_summary.get("top_industries", [])[:5]),
                    "- 负贡献最大的 industry：",
                    *format_yaml_block(attribution_summary.get("bottom_industries", [])[:5]),
                    "",
                    "贡献口径：单票净贡献 = 持仓权重 × 单票收益 - 当期交易成本按持仓数平均分摊。行业暴露来自回测实际持仓权重，不是模型特征重要性。",
                ]
                if attribution_summary.get("enabled", False)
                else ["- 未启用。"]
            ),
            "",
            "## 流动性过滤",
            "",
            *(
                [
                    "- 流动性过滤：已启用。",
                    "- 过滤规则：",
                    *format_yaml_block(meta.get("liquidity_filter", {})),
                    f"- 生成流动性画像股票数：{meta.get('liquidity_profile_count', 0)}",
                    f"- 流动性剔除数量：{meta.get('liquidity_exclusion_count', 0)}",
                    "- 流动性剔除原因：",
                    *format_yaml_block(liquidity_exclusion_reason_counts),
                ]
                if meta.get("liquidity_filter_enabled", False)
                else ["- 未启用。"]
            ),
            "",
            "## 股票池清洗与历史分桶",
            "",
            *(
                [
                    "- 桶内 TopN 排名：已启用。",
                    f"- 股票池清洗剔除数量：{len(universe_exclusions)}",
                    "- 清洗剔除原因：",
                    *format_yaml_block(exclusion_reason_counts),
                    "- 桶名额：",
                    *format_yaml_block(meta.get("bucket_quotas", {})),
                    "- 最新日可预测股票分桶：",
                    *format_yaml_block(meta.get("history_bucket_counts", {})),
                    "- 最终 TopN 分桶：",
                    *format_yaml_block(meta.get("selected_bucket_counts", {})),
                    "- 行业名额约束：",
                    *(
                        format_yaml_block(meta.get("industry_constraints", {}))
                        if meta.get("industry_constraints_enabled", False)
                        else ["未启用。"]
                    ),
                    "- 最终 TopN sector 分布：",
                    *format_yaml_block(meta.get("selected_sector_counts", {})),
                    "- 最终 TopN industry 分布：",
                    *format_yaml_block(meta.get("selected_industry_counts", {})),
                ]
                if meta.get("bucket_ranking_enabled", False)
                else ["- 未启用。"]
            ),
            "",
            "## 行业覆盖",
            "",
            f"- 股票池 sector 缺失数量：{meta.get('industry_coverage', {}).get('sector_missing_count', 0)}",
            f"- 股票池 industry 缺失数量：{meta.get('industry_coverage', {}).get('industry_missing_count', 0)}",
            "- TopN sector 分布：",
            *format_yaml_block(meta.get("top_sector_counts", {})),
            "- TopN industry 分布：",
            *format_yaml_block(meta.get("top_industry_counts", {})),
            "",
            "第一版行业分类来自当前 Nasdaq public snapshot，不是历史 PIT 行业分类。它适合学习行业内比较，但不能替代严谨回测里的历史行业口径。",
            "",
            "## 数据失败数量",
            "",
            f"- 最新日可预测股票数：{meta['prediction_count']}",
            f"- 下载失败或历史不足：{len(failures)}",
            "",
            "## 输出文件",
            "",
            "- `universe.csv`：本次实验股票池。",
            "- `universe_candidates.csv`：冻结股票池实验中的初始候选池；普通实验与 `universe.csv` 一致。",
            "- `universe_selection.csv`：as-of 近似冻结股票池的候选诊断、估算市值和入选状态。",
            "- `security_master.csv`：本次实验证券主数据和证券类型分类。",
            "- `security_master_exclusions.csv`：证券主数据层剔除记录。",
            "- `universe_exclusions.csv`：股票池清洗剔除记录；仅启用清洗时生成有效内容。",
            "- `membership.csv`：历史指数成分日级标记；仅 Norgate 等成分感知数据源生成有效内容。",
            "- `download_failures.csv`：下载失败或历史不足的股票。",
            "- `liquidity_profile.csv`：每只已下载股票的成交额、价格和零成交画像。",
            "- `liquidity_exclusions.csv`：流动性过滤剔除记录。",
            "- `history_buckets.csv`：每只进入 Qlib source CSV 股票的历史长度分桶。",
            "- `fundamental_features.parquet`：日频 PIT 财报与估值特征；仅启用 EDGAR 时生成有效内容。",
            "- `fundamental_failures.csv`：EDGAR 映射、字段或行情缺失记录。",
            "- `edgar_cik_map.csv`：本次股票池 ticker 到 SEC CIK 的映射。",
            "- `market_features.parquet`：日频 PIT 行情派生特征和 sector / industry 内相对特征。",
            "- `market_feature_failures.csv`：行情相对特征失败原因。",
            "- `macro_raw_observations.parquet`：FRED/ALFRED 原始 observation 与 real-time/vintage 记录。",
            "- `macro_asof_observations.parquet`：按交易日重建的 PIT 宏观 as-of 序列。",
            "- `macro_features.parquet`：广播到 `(datetime, instrument)` 的日频宏观特征。",
            "- `macro_failures.csv`：宏观序列下载、解析或缺失记录。",
            "- `industry_features.parquet`：行业内 rank / percentile 特征；仅启用行业特征时生成有效内容。",
            "- `industry_failures.csv`：sector / industry 缺失或 rank 字段缺失记录。",
            "- `predictions.csv`：最新日全部模型分数。",
            "- `bucketed_predictions.csv`：追加历史分桶、桶内排名和全局排名后的全部模型分数。",
            "- `selected_top10.csv`：按历史长度桶名额选择后的最终 Top10。",
            "- `test_predictions.csv`：测试期所有交易日的模型预测分数，回测使用这个文件。",
            "- `backtest_nav.csv`：TopK 成本后回测每期净值、收益、换手和成本。",
            "- `backtest_positions.csv`：每个回测期实际持仓、权重、入场价、退出价和单票收益。",
            "- `backtest_summary.yaml`：回测汇总指标。",
            "- `benchmark_prices.csv`：基准资产价格数据；仅启用基准复盘时生成有效内容。",
            "- `benchmark_summary.yaml`：基准、超额收益、alpha/beta 和跟踪误差摘要。",
            "- `contribution_by_symbol.csv`：按股票聚合的持仓贡献。",
            "- `contribution_by_sector.csv`：按 sector 聚合的持仓贡献。",
            "- `contribution_by_industry.csv`：按 industry 聚合的持仓贡献。",
            "- `exposure_by_sector.csv`：按 sector 聚合的平均/最大持仓权重。",
            "- `exposure_by_industry.csv`：按 industry 聚合的平均/最大持仓权重。",
            "- `contribution_summary.yaml`：持仓贡献和行业暴露摘要。",
            "- `strategy_comparison.csv`：原始 Top10、行业约束 Top10、行业增强 Top10 的对照指标。",
            "- `strategy_comparison/`：每个策略 variant 的独立回测、基准和归因输出。",
            "- `within_sector_daily_metrics.csv`：每个交易日、每个 sector / industry 的行业内 IC、Rank IC 和 Top-Bottom spread。",
            "- `within_sector_summary.csv`：按 sector 聚合的行业内选股复盘。",
            "- `within_industry_summary.csv`：按 industry 聚合的补充复盘。",
            "- `within_sector_quantile_returns.csv`：sector 内 score 五分位组合平均未来收益。",
            "- `within_sector_selection_summary.yaml`：行业内选股复盘摘要。",
            "- `sector_error_review_summary.csv`：Technology、Health Care、Consumer Discretionary 的错误复盘摘要。",
            "- `sector_error_examples.csv`：高分赢家、高分输家、低分赢家、低分输家的样本明细。",
            "- `sector_error_feature_differences.csv`：错误类别之间的特征均值差异。",
            "- `sector_error_review_summary.yaml`：重点行业错误复盘摘要。",
            "- `short_history_bucket_summary.csv`：按历史长度桶聚合的持仓收益、贡献和风险特征。",
            "- `short_history_examples.csv`：短历史赢家和输家的样本明细。",
            "- `short_history_feature_differences.csv`：短历史赢家 vs 输家的特征差异。",
            "- `short_history_sector_breakdown.csv`：短历史收益和亏损按 sector / industry 拆分。",
            "- `short_history_review_summary.yaml`：短历史专项复盘摘要。",
            "- `report.md`：本报告。",
            "- `resolved_config.yaml`：本次实际使用配置，复盘时优先看它。",
            "- `qlib_source_csv/`：逐股票原始日线 CSV。",
            "- `qlib_data/`：转换后的 Qlib bin 数据。",
        ]
    )
    paths["report_md"].write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_optional_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    paths = build_paths(config)
    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    write_resolved_config(config, paths)

    print(f"Experiment: {config['experiment']['name']}")
    print(f"Output dir: {paths['output_dir']}")
    try:
        prepared = create_data_source(config, paths).prepare()
    except DataSourceUnavailable as exc:
        raise SystemExit(f"Data source unavailable: {exc}") from None
    universe = prepared.universe
    failures = prepared.failures
    universe, liquidity_meta = apply_liquidity_filter(universe, paths["source_dir"], config, paths)
    build_history_buckets(paths["source_dir"], paths["history_buckets_csv"], config)
    dump_qlib_bin(config, paths)
    try:
        predictions, meta = train_and_predict(universe, config, paths)
        meta.update(liquidity_meta)
    except DataSourceUnavailable as exc:
        raise SystemExit(f"Feature data unavailable: {exc}") from None
    write_report(predictions, meta, failures, config, paths)
    print(f"Qlib model top {config['report']['top_n']}:")
    preview_columns = [
        column
        for column in ["symbol", "history_bucket", "bucket_rank", "global_rank", "name", "score", "market_cap", "sector", "industry"]
        if column in predictions
    ]
    print(predictions[preview_columns].head(int(config["report"]["top_n"])).to_string(index=False))
    print(f"Report: {paths['report_md']}")


if __name__ == "__main__":
    main()
