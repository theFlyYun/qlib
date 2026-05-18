from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from analysis.nasdaq_top500_score.within_sector import run_within_sector_review


def write_price_csv(source_dir: Path, symbol: str, dates: pd.DatetimeIndex, close: list[float]) -> None:
    pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "symbol": symbol,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "vwap": close,
            "volume": 1_000_000,
        }
    ).to_csv(source_dir / f"{symbol}.csv", index=False)


def build_review_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "source_dir": tmp_path / "qlib_source_csv",
        "qlib_dir": tmp_path / "qlib_data",
        "history_buckets_csv": tmp_path / "history_buckets.csv",
        "within_sector_daily_metrics": tmp_path / "within_sector_daily_metrics.csv",
        "within_sector_summary": tmp_path / "within_sector_summary.csv",
        "within_industry_summary": tmp_path / "within_industry_summary.csv",
        "within_sector_quantile_returns": tmp_path / "within_sector_quantile_returns.csv",
        "within_sector_selection_summary": tmp_path / "within_sector_selection_summary.yaml",
    }


def test_within_sector_review_calculates_ic_inside_each_sector(tmp_path: Path) -> None:
    paths = build_review_paths(tmp_path)
    source_dir = paths["source_dir"]
    calendar_dir = paths["qlib_dir"] / "calendars"
    source_dir.mkdir()
    calendar_dir.mkdir(parents=True)
    dates = pd.bdate_range("2024-01-02", periods=8)
    pd.Series(dates.strftime("%Y-%m-%d")).to_csv(calendar_dir / "day.txt", index=False, header=False)

    future_returns = {
        "T0": 0.30,
        "T1": 0.20,
        "T2": -0.10,
        "E0": -0.20,
        "E1": 0.10,
        "E2": 0.30,
    }
    for symbol, future_return in future_returns.items():
        close = [10.0] * len(dates)
        close[5] = 10.0 * (1.0 + future_return)
        write_price_csv(source_dir, symbol, dates, close)

    pd.DataFrame(
        [
            {"symbol": symbol, "history_rows": 8, "first_date": "2024-01-02", "last_date": "2024-01-11", "history_bucket": "full_10y"}
            for symbol in future_returns
        ]
    ).to_csv(paths["history_buckets_csv"], index=False)
    predictions = pd.DataFrame(
        [
            {"datetime": dates[2], "instrument": "T0", "score": 0.9},
            {"datetime": dates[2], "instrument": "T1", "score": 0.8},
            {"datetime": dates[2], "instrument": "T2", "score": 0.1},
            {"datetime": dates[2], "instrument": "E0", "score": 0.9},
            {"datetime": dates[2], "instrument": "E1", "score": 0.8},
            {"datetime": dates[2], "instrument": "E2", "score": 0.1},
        ]
    )
    universe = pd.DataFrame(
        [
            {"symbol": "T0", "sector": "Technology", "industry": "Software"},
            {"symbol": "T1", "sector": "Technology", "industry": "Software"},
            {"symbol": "T2", "sector": "Technology", "industry": "Software"},
            {"symbol": "E0", "sector": "Energy", "industry": "Oil"},
            {"symbol": "E1", "sector": "Energy", "industry": "Oil"},
            {"symbol": "E2", "sector": "Energy", "industry": "Oil"},
        ]
    )
    config = {
        "universe": {"min_history_rows": 3},
        "history_buckets": {"enabled": True, "thresholds": {"full_10y": 3, "5_10y": 2, "2_5y": 1, "lt_2y": 1}},
        "backtest": {
            "enabled": True,
            "holding_days": 2,
            "rebalance_days": 1,
            "entry_lag_days": 1,
            "price": "close",
            "point_in_time_filters": {
                "enabled": True,
                "history_bucket_asof": True,
                "liquidity_asof": True,
                "min_history_rows": 3,
                "liquidity": {
                    "min_latest_close": 1.0,
                    "min_avg_dollar_volume_20d": 0,
                    "min_median_dollar_volume_60d": 0,
                    "max_zero_volume_ratio_60d": 0.05,
                    "min_recent_trading_days_60d": 1,
                },
            },
        },
        "within_sector_review": {
            "enabled": True,
            "group_levels": ["sector", "industry"],
            "quantiles": 3,
            "min_group_size": 3,
            "min_summary_periods": 1,
        },
    }

    result = run_within_sector_review(predictions, universe, config, paths)

    sector_summary = result.sector_summary.set_index("group_value")
    assert sector_summary.loc["Technology", "rank_ic_mean"] > 0
    assert sector_summary.loc["Energy", "rank_ic_mean"] < 0
    assert sector_summary.loc["Technology", "top_bottom_spread_mean"] > 0
    assert sector_summary.loc["Energy", "top_bottom_spread_mean"] < 0
    assert result.summary["sector_count"] == 2
    assert paths["within_sector_daily_metrics"].exists()
    assert paths["within_sector_quantile_returns"].exists()
    tech_daily = result.daily_metrics[
        (result.daily_metrics["group_level"] == "sector") & (result.daily_metrics["group_value"] == "Technology")
    ].iloc[0]
    assert math.isclose(float(tech_daily["top_quantile_mean_return"]), 0.30, rel_tol=0, abs_tol=1e-9)
    assert math.isclose(float(tech_daily["bottom_quantile_mean_return"]), -0.10, rel_tol=0, abs_tol=1e-9)


def test_within_sector_review_records_small_groups_without_spread(tmp_path: Path) -> None:
    paths = build_review_paths(tmp_path)
    source_dir = paths["source_dir"]
    calendar_dir = paths["qlib_dir"] / "calendars"
    source_dir.mkdir()
    calendar_dir.mkdir(parents=True)
    dates = pd.bdate_range("2024-01-02", periods=8)
    pd.Series(dates.strftime("%Y-%m-%d")).to_csv(calendar_dir / "day.txt", index=False, header=False)
    for symbol in ["AAA", "BBB"]:
        close = [10.0] * len(dates)
        close[5] = 11.0
        write_price_csv(source_dir, symbol, dates, close)
    pd.DataFrame(
        [
            {"symbol": "AAA", "history_rows": 8, "first_date": "2024-01-02", "last_date": "2024-01-11", "history_bucket": "full_10y"},
            {"symbol": "BBB", "history_rows": 8, "first_date": "2024-01-02", "last_date": "2024-01-11", "history_bucket": "full_10y"},
        ]
    ).to_csv(paths["history_buckets_csv"], index=False)
    predictions = pd.DataFrame(
        [
            {"datetime": dates[2], "instrument": "AAA", "score": 0.9},
            {"datetime": dates[2], "instrument": "BBB", "score": 0.1},
        ]
    )
    universe = pd.DataFrame(
        [
            {"symbol": "AAA", "sector": "Technology", "industry": "Software"},
            {"symbol": "BBB", "sector": "Technology", "industry": "Software"},
        ]
    )
    config = {
        "universe": {"min_history_rows": 3},
        "history_buckets": {"enabled": True, "thresholds": {"full_10y": 3, "5_10y": 2, "2_5y": 1, "lt_2y": 1}},
        "backtest": {
            "enabled": True,
            "holding_days": 2,
            "rebalance_days": 1,
            "entry_lag_days": 1,
            "price": "close",
            "point_in_time_filters": {"enabled": False},
        },
        "within_sector_review": {
            "enabled": True,
            "group_levels": ["sector"],
            "quantiles": 5,
            "min_group_size": 3,
            "min_summary_periods": 1,
        },
    }

    result = run_within_sector_review(predictions, universe, config, paths)

    daily = result.daily_metrics.iloc[0]
    assert daily["candidate_count"] == 2
    assert daily["tradable_count"] == 2
    assert pd.isna(daily["top_bottom_spread"])
    assert daily["skip_reason"] == "tradable_count < 3"
