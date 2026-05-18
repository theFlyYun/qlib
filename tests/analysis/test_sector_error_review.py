from __future__ import annotations

from pathlib import Path

import pandas as pd

from analysis.nasdaq_top500_score.sector_error_review import run_sector_error_review


def write_price_csv(source_dir: Path, symbol: str, dates: pd.DatetimeIndex, exit_close: float) -> None:
    close = [10.0] * len(dates)
    close[5] = exit_close
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


def build_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "source_dir": tmp_path / "qlib_source_csv",
        "qlib_dir": tmp_path / "qlib_data",
        "history_buckets_csv": tmp_path / "history_buckets.csv",
        "fundamental_features": tmp_path / "fundamental_features.parquet",
        "sector_error_review_summary_csv": tmp_path / "sector_error_review_summary.csv",
        "sector_error_examples_csv": tmp_path / "sector_error_examples.csv",
        "sector_error_feature_differences_csv": tmp_path / "sector_error_feature_differences.csv",
        "sector_error_review_summary_yaml": tmp_path / "sector_error_review_summary.yaml",
    }


def test_sector_error_review_classifies_target_sector_examples_and_preserves_missing_fundamentals(tmp_path: Path) -> None:
    paths = build_paths(tmp_path)
    source_dir = paths["source_dir"]
    calendar_dir = paths["qlib_dir"] / "calendars"
    source_dir.mkdir()
    calendar_dir.mkdir(parents=True)
    dates = pd.bdate_range("2024-01-02", periods=8)
    pd.Series(dates.strftime("%Y-%m-%d")).to_csv(calendar_dir / "day.txt", index=False, header=False)

    exits = {
        "TWIN": 13.0,
        "TLOSE": 8.0,
        "TMISS": 12.5,
        "TLOWLOSE": 9.0,
        "H0": 11.0,
    }
    for symbol, exit_close in exits.items():
        write_price_csv(source_dir, symbol, dates, exit_close)

    pd.DataFrame(
        [
            {"symbol": symbol, "history_rows": 8, "first_date": "2024-01-02", "last_date": "2024-01-11", "history_bucket": "full_10y"}
            for symbol in exits
        ]
    ).to_csv(paths["history_buckets_csv"], index=False)

    predictions = pd.DataFrame(
        [
            {"datetime": dates[2], "instrument": "TWIN", "score": 0.90},
            {"datetime": dates[2], "instrument": "TLOSE", "score": 0.80},
            {"datetime": dates[2], "instrument": "TMISS", "score": 0.20},
            {"datetime": dates[2], "instrument": "TLOWLOSE", "score": 0.10},
            {"datetime": dates[2], "instrument": "H0", "score": 0.95},
        ]
    )
    original_predictions = predictions.copy(deep=True)
    universe = pd.DataFrame(
        [
            {"symbol": "TWIN", "sector": "Technology", "industry": "Software", "market_cap_asof_estimate": 1000, "is_adr_ads": False},
            {"symbol": "TLOSE", "sector": "Technology", "industry": "Software", "market_cap_asof_estimate": 900, "is_adr_ads": False},
            {"symbol": "TMISS", "sector": "Technology", "industry": "Software", "market_cap_asof_estimate": 800, "is_adr_ads": True},
            {"symbol": "TLOWLOSE", "sector": "Technology", "industry": "Software", "market_cap_asof_estimate": 700, "is_adr_ads": False},
            {"symbol": "H0", "sector": "Health Care", "industry": "Biotech", "market_cap_asof_estimate": 600, "is_adr_ads": False},
        ]
    )
    fundamentals = pd.DataFrame(
        {
            "edgar_price_to_sales": [3.0, 9.0, pd.NA, 1.0],
            "edgar_roe": [0.2, -0.1, pd.NA, 0.1],
            "edgar_net_margin": [0.1, -0.2, pd.NA, 0.05],
            "edgar_is_recent_filing": [0, 1, pd.NA, 0],
        },
        index=pd.MultiIndex.from_tuples(
            [
                (dates[2], "TWIN"),
                (dates[2], "TLOSE"),
                (dates[2], "TMISS"),
                (dates[2], "TLOWLOSE"),
            ],
            names=["datetime", "instrument"],
        ),
    )
    fundamentals.to_parquet(paths["fundamental_features"])
    config = {
        "universe": {"min_history_rows": 1},
        "history_buckets": {"enabled": True, "thresholds": {"full_10y": 1}},
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
                "min_history_rows": 1,
                "liquidity": {
                    "min_latest_close": 1.0,
                    "min_avg_dollar_volume_20d": 0,
                    "min_median_dollar_volume_60d": 0,
                    "max_zero_volume_ratio_60d": 0.1,
                    "min_recent_trading_days_60d": 1,
                },
            },
        },
        "sector_error_review": {
            "enabled": True,
            "target_sectors": ["Technology"],
            "quantiles": 2,
            "min_group_size": 4,
            "min_summary_periods": 1,
        },
    }

    result = run_sector_error_review(predictions, universe, config, paths)

    pd.testing.assert_frame_equal(predictions, original_predictions)
    examples = result.examples.set_index("symbol")
    assert examples.loc["TWIN", "error_category"] == "high_score_winners"
    assert examples.loc["TLOSE", "error_category"] == "high_score_losers"
    assert examples.loc["TMISS", "error_category"] == "low_score_winners"
    assert examples.loc["TLOWLOSE", "error_category"] == "low_score_losers"
    assert "H0" not in examples.index
    assert round(float(examples.loc["TWIN", "future_return"]), 6) == 0.3
    assert round(float(examples.loc["TLOSE", "future_return"]), 6) == -0.2
    assert pd.isna(examples.loc["TMISS", "edgar_price_to_sales"])
    summary = result.summary.set_index("sector")
    assert summary.loc["Technology", "high_score_winners_count"] == 1
    assert summary.loc["Technology", "high_score_losers_count"] == 1
    assert summary.loc["Technology", "low_score_winners_count"] == 1
    assert summary.loc["Technology", "low_score_losers_count"] == 1
    assert summary.loc["Technology", "fundamental_coverage_mean"] < 1
    assert paths["sector_error_review_summary_csv"].exists()
    assert paths["sector_error_examples_csv"].exists()
    assert paths["sector_error_feature_differences_csv"].exists()
    assert paths["sector_error_review_summary_yaml"].exists()


def test_sector_error_review_records_low_sample_without_categories(tmp_path: Path) -> None:
    paths = build_paths(tmp_path)
    source_dir = paths["source_dir"]
    calendar_dir = paths["qlib_dir"] / "calendars"
    source_dir.mkdir()
    calendar_dir.mkdir(parents=True)
    dates = pd.bdate_range("2024-01-02", periods=8)
    pd.Series(dates.strftime("%Y-%m-%d")).to_csv(calendar_dir / "day.txt", index=False, header=False)
    for symbol in ["AAA", "BBB"]:
        write_price_csv(source_dir, symbol, dates, 11.0)
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
        "universe": {"min_history_rows": 1},
        "backtest": {
            "enabled": True,
            "holding_days": 2,
            "rebalance_days": 1,
            "entry_lag_days": 1,
            "price": "close",
            "point_in_time_filters": {"enabled": False},
        },
        "sector_error_review": {
            "enabled": True,
            "target_sectors": ["Technology"],
            "quantiles": 2,
            "min_group_size": 3,
            "min_summary_periods": 1,
        },
    }

    result = run_sector_error_review(predictions, universe, config, paths)

    assert result.examples.empty
    summary = result.summary.set_index("sector")
    assert summary.loc["Technology", "observation_count"] == 2
    assert summary.loc["Technology", "classified_example_count"] == 0
