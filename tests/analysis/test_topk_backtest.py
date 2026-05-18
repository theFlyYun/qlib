from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import yaml

from analysis.nasdaq_top500_score.backtest import compute_sector_momentum, run_topk_backtest
from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import run_strategy_comparison


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


def test_topk_backtest_uses_signal_entry_exit_costs_and_writes_outputs(tmp_path: Path) -> None:
    source_dir = tmp_path / "qlib_source_csv"
    qlib_dir = tmp_path / "qlib_data"
    calendar_dir = qlib_dir / "calendars"
    source_dir.mkdir()
    calendar_dir.mkdir(parents=True)
    dates = pd.bdate_range("2024-01-02", periods=10)
    pd.Series(dates.strftime("%Y-%m-%d")).to_csv(calendar_dir / "day.txt", index=False, header=False)

    write_price_csv(source_dir, "AAA", dates, [10, 10, 10.5, 11, 11, 11, 11, 11, 11, 11])
    write_price_csv(source_dir, "BBB", dates, [20, 20, 20, 20, 20, 20, 20, 20, 20, 20])
    write_price_csv(source_dir, "CCC", dates, [30, 30, 30, 29, 29, 29, 29, 29, 29, 29])
    benchmark_csv = tmp_path / "benchmark_QQQ.csv"
    write_price_csv(benchmark_csv.parent, "benchmark_QQQ", dates, [100, 100, 101, 102, 102, 102, 102, 102, 102, 102])

    pd.DataFrame(
        [
            {"symbol": "AAA", "history_rows": 2400, "first_date": "2016-05-17", "last_date": "2026-05-15", "history_bucket": "full_10y"},
            {"symbol": "BBB", "history_rows": 2400, "first_date": "2016-05-17", "last_date": "2026-05-15", "history_bucket": "full_10y"},
            {"symbol": "CCC", "history_rows": 2400, "first_date": "2016-05-17", "last_date": "2026-05-15", "history_bucket": "full_10y"},
        ]
    ).to_csv(tmp_path / "history_buckets.csv", index=False)

    predictions = pd.DataFrame(
        [
            {"datetime": date, "instrument": "AAA", "score": 0.9}
            for date in dates[:6]
        ]
        + [{"datetime": date, "instrument": "BBB", "score": 0.8} for date in dates[:6]]
        + [{"datetime": date, "instrument": "CCC", "score": 0.1} for date in dates[:6]]
    )
    universe = pd.DataFrame(
        [
            {"symbol": "AAA", "sector": "Technology", "industry": "Software"},
            {"symbol": "BBB", "sector": "Health Care", "industry": "Biotech"},
            {"symbol": "CCC", "sector": "Industrials", "industry": "Machinery"},
        ]
    )
    config = {
        "report": {"top_n": 2},
        "bucket_ranking": {
            "enabled": True,
            "quotas": {"full_10y": 2, "5_10y": 0, "2_5y": 0, "lt_2y": 0},
            "refill_order": ["full_10y", "5_10y", "2_5y", "lt_2y"],
        },
        "industry_constraints": {"enabled": False},
        "backtest": {
            "enabled": True,
            "strategy": "bucketed_topk",
            "top_n": 2,
            "holding_days": 2,
            "rebalance_days": 2,
            "entry_lag_days": 1,
            "price": "close",
            "cost_bps": 10,
            "min_positions": 1,
        },
        "benchmark": {
            "enabled": True,
            "source": "csv",
            "path": str(benchmark_csv),
            "symbol": "QQQ",
            "name": "Invesco QQQ Trust",
        },
        "attribution": {"enabled": True, "top_n": 5},
    }
    paths = {
        "source_dir": source_dir,
        "qlib_dir": qlib_dir,
        "history_buckets_csv": tmp_path / "history_buckets.csv",
        "backtest_nav_csv": tmp_path / "backtest_nav.csv",
        "backtest_positions_csv": tmp_path / "backtest_positions.csv",
        "backtest_summary": tmp_path / "backtest_summary.yaml",
        "benchmark_summary": tmp_path / "benchmark_summary.yaml",
        "contribution_by_symbol": tmp_path / "contribution_by_symbol.csv",
        "contribution_by_sector": tmp_path / "contribution_by_sector.csv",
        "contribution_by_industry": tmp_path / "contribution_by_industry.csv",
        "exposure_by_sector": tmp_path / "exposure_by_sector.csv",
        "exposure_by_industry": tmp_path / "exposure_by_industry.csv",
        "contribution_summary": tmp_path / "contribution_summary.yaml",
    }

    result = run_topk_backtest(predictions, universe, config, paths)

    assert result.summary["enabled"] is True
    assert result.summary["period_count"] > 0
    assert set(result.positions[result.positions["period"] == 1]["symbol"]) == {"AAA", "BBB"}
    assert math.isclose(float(result.nav.iloc[0]["gross_return"]), 0.05, rel_tol=0, abs_tol=1e-9)
    assert math.isclose(float(result.nav.iloc[0]["cost_return"]), 0.001, rel_tol=0, abs_tol=1e-9)
    assert math.isclose(float(result.nav.iloc[0]["net_return"]), 0.049, rel_tol=0, abs_tol=1e-9)
    assert math.isclose(float(result.nav.iloc[0]["benchmark_return"]), 0.02, rel_tol=0, abs_tol=1e-9)
    assert math.isclose(float(result.nav.iloc[0]["excess_return"]), 0.029, rel_tol=0, abs_tol=1e-9)
    assert result.summary["benchmark"]["symbol"] == "QQQ"
    assert "gross_contribution" in result.positions.columns
    assert "net_contribution" in result.positions.columns
    first_period_net_contribution = result.positions[result.positions["period"] == 1]["net_contribution"].sum()
    assert math.isclose(float(first_period_net_contribution), 0.049, rel_tol=0, abs_tol=1e-9)
    assert result.summary["attribution"]["enabled"] is True
    assert result.summary["attribution"]["top_symbols"][0]["symbol"] == "AAA"
    assert paths["backtest_nav_csv"].exists()
    assert paths["backtest_positions_csv"].exists()
    assert paths["benchmark_summary"].exists()
    assert paths["contribution_by_symbol"].exists()
    assert paths["contribution_by_sector"].exists()
    assert paths["contribution_summary"].exists()
    summary = yaml.safe_load(paths["backtest_summary"].read_text(encoding="utf-8"))
    assert summary["period_count"] == result.summary["period_count"]
    contribution = pd.read_csv(paths["contribution_by_symbol"])
    assert contribution.iloc[0]["symbol"] == "AAA"


def test_topk_backtest_point_in_time_filters_use_signal_date_history_and_liquidity(tmp_path: Path) -> None:
    source_dir = tmp_path / "qlib_source_csv"
    qlib_dir = tmp_path / "qlib_data"
    calendar_dir = qlib_dir / "calendars"
    source_dir.mkdir()
    calendar_dir.mkdir(parents=True)
    dates = pd.bdate_range("2024-01-02", periods=8)
    pd.Series(dates.strftime("%Y-%m-%d")).to_csv(calendar_dir / "day.txt", index=False, header=False)

    write_price_csv(source_dir, "AAA", dates, [10, 10, 10, 11, 11, 11, 11, 11])
    write_price_csv(source_dir, "BBB", dates, [20, 20, 20, 21, 21, 21, 21, 21])
    write_price_csv(source_dir, "NEW", dates[2:], [5, 6, 7, 8, 9, 10])
    pd.DataFrame(
        [
            {"symbol": "AAA", "history_rows": 8, "first_date": "2024-01-02", "last_date": "2024-01-11", "history_bucket": "full_10y"},
            {"symbol": "BBB", "history_rows": 8, "first_date": "2024-01-02", "last_date": "2024-01-11", "history_bucket": "full_10y"},
            {"symbol": "NEW", "history_rows": 6, "first_date": "2024-01-04", "last_date": "2024-01-11", "history_bucket": "full_10y"},
        ]
    ).to_csv(tmp_path / "history_buckets.csv", index=False)

    predictions = pd.DataFrame(
        [
            {"datetime": dates[2], "instrument": "NEW", "score": 0.99},
            {"datetime": dates[2], "instrument": "AAA", "score": 0.80},
            {"datetime": dates[2], "instrument": "BBB", "score": 0.70},
        ]
    )
    universe = pd.DataFrame(
        [
            {"symbol": "AAA", "sector": "Technology", "industry": "Software"},
            {"symbol": "BBB", "sector": "Health Care", "industry": "Biotech"},
            {"symbol": "NEW", "sector": "Industrials", "industry": "Machinery"},
        ]
    )
    config = {
        "universe": {"min_history_rows": 3},
        "history_buckets": {
            "enabled": True,
            "thresholds": {"full_10y": 3, "5_10y": 2, "2_5y": 1, "lt_2y": 1},
        },
        "report": {"top_n": 2},
        "bucket_ranking": {
            "enabled": True,
            "quotas": {"full_10y": 2, "5_10y": 0, "2_5y": 0, "lt_2y": 0},
            "refill_order": ["full_10y", "5_10y", "2_5y", "lt_2y"],
        },
        "industry_constraints": {"enabled": False},
        "backtest": {
            "enabled": True,
            "strategy": "bucketed_topk",
            "top_n": 2,
            "holding_days": 2,
            "rebalance_days": 1,
            "entry_lag_days": 1,
            "price": "close",
            "cost_bps": 0,
            "min_positions": 1,
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
    }
    paths = {
        "source_dir": source_dir,
        "qlib_dir": qlib_dir,
        "history_buckets_csv": tmp_path / "history_buckets.csv",
        "backtest_nav_csv": tmp_path / "backtest_nav.csv",
        "backtest_positions_csv": tmp_path / "backtest_positions.csv",
        "backtest_summary": tmp_path / "backtest_summary.yaml",
    }

    result = run_topk_backtest(predictions, universe, config, paths)

    assert result.positions["symbol"].tolist() == ["AAA", "BBB"]
    assert "NEW" not in set(result.positions["symbol"])
    assert result.nav.iloc[0]["candidate_count_before_pit"] == 3
    assert result.nav.iloc[0]["candidate_count_after_pit"] == 2


def test_sector_momentum_uses_only_prices_visible_on_signal_date() -> None:
    dates = pd.bdate_range("2024-01-02", periods=5)
    day = pd.DataFrame(
        [
            {"symbol": "AAA", "sector": "Technology"},
            {"symbol": "BBB", "sector": "Energy"},
        ]
    )
    market_data = {
        "AAA": pd.DataFrame({"execution_price": [10, 11, 12, 1, 1]}, index=dates),
        "BBB": pd.DataFrame({"execution_price": [10, 10, 10, 100, 100]}, index=dates),
    }

    momentum = compute_sector_momentum(day, market_data, dates[2], lookback_days=2)

    assert momentum.iloc[0]["sector"] == "Technology"
    assert math.isclose(float(momentum.iloc[0]["momentum_return"]), 0.2, rel_tol=0, abs_tol=1e-9)


def test_strategy_comparison_reuses_predictions_and_writes_variant_outputs(tmp_path: Path) -> None:
    source_dir = tmp_path / "qlib_source_csv"
    qlib_dir = tmp_path / "qlib_data"
    calendar_dir = qlib_dir / "calendars"
    source_dir.mkdir()
    calendar_dir.mkdir(parents=True)
    dates = pd.bdate_range("2024-01-02", periods=8)
    pd.Series(dates.strftime("%Y-%m-%d")).to_csv(calendar_dir / "day.txt", index=False, header=False)

    symbols = ["T0", "T1", "T2", "T3", "H0", "E0", "F0"]
    for symbol in symbols:
        close = [10, 11, 12, 13, 13, 13, 13, 13] if symbol.startswith("T") else [10] * len(dates)
        write_price_csv(source_dir, symbol, dates, close)
    pd.DataFrame(
        [
            {"symbol": symbol, "history_rows": 2400, "first_date": "2016-05-17", "last_date": "2026-05-15", "history_bucket": "full_10y"}
            for symbol in symbols
        ]
    ).to_csv(tmp_path / "history_buckets.csv", index=False)

    scores = {"T0": 0.99, "T1": 0.98, "T2": 0.97, "T3": 0.96, "H0": 0.80, "E0": 0.70, "F0": 0.60}
    predictions = pd.DataFrame(
        [{"datetime": dates[2], "instrument": symbol, "score": score} for symbol, score in scores.items()]
    )
    universe = pd.DataFrame(
        [
            {"symbol": "T0", "sector": "Technology", "industry": "Software 0"},
            {"symbol": "T1", "sector": "Technology", "industry": "Software 1"},
            {"symbol": "T2", "sector": "Technology", "industry": "Software 2"},
            {"symbol": "T3", "sector": "Technology", "industry": "Software 3"},
            {"symbol": "H0", "sector": "Health Care", "industry": "Biotech"},
            {"symbol": "E0", "sector": "Energy", "industry": "Oil"},
            {"symbol": "F0", "sector": "Financial Services", "industry": "Banks"},
        ]
    )
    config = {
        "report": {"top_n": 4},
        "bucket_ranking": {
            "enabled": True,
            "quotas": {"full_10y": 4, "5_10y": 0, "2_5y": 0, "lt_2y": 0},
            "refill_order": ["full_10y", "5_10y", "2_5y", "lt_2y"],
        },
        "industry_constraints": {"enabled": False},
        "backtest": {
            "enabled": True,
            "top_n": 4,
            "holding_days": 2,
            "rebalance_days": 1,
            "entry_lag_days": 1,
            "price": "close",
            "cost_bps": 0,
            "min_positions": 1,
        },
        "benchmark": {"enabled": False},
        "attribution": {"enabled": True, "top_n": 5},
        "strategy_comparison": {
            "enabled": True,
            "variants": [
                {"name": "unconstrained_top10", "industry_constraints": {"enabled": False}},
                {"name": "sector_cap_2_top10", "industry_constraints": {"enabled": True, "max_sector": 2, "max_industry": 1}},
                {"name": "sector_cap_3_top10", "industry_constraints": {"enabled": True, "max_sector": 3, "max_industry": 1}},
                {"name": "sector_cap_4_top10", "industry_constraints": {"enabled": True, "max_sector": 4, "max_industry": 1}},
                {
                    "name": "sector_momentum_tilt_top10",
                    "industry_constraints": {
                        "enabled": True,
                        "max_sector": 2,
                        "max_industry": 1,
                        "sector_momentum_tilt": {
                            "enabled": True,
                            "lookback_days": 2,
                            "top_sector_count": 1,
                            "extra_max_sector": 1,
                            "max_sector_cap": 3,
                        },
                    },
                },
            ],
        },
    }
    paths = {
        "source_dir": source_dir,
        "qlib_dir": qlib_dir,
        "history_buckets_csv": tmp_path / "history_buckets.csv",
        "benchmark_prices_csv": tmp_path / "benchmark_prices.csv",
        "strategy_comparison_dir": tmp_path / "strategy_comparison",
        "strategy_comparison_csv": tmp_path / "strategy_comparison.csv",
        "strategy_comparison_summary": tmp_path / "strategy_comparison_summary.yaml",
    }

    summary = run_strategy_comparison(predictions, universe, config, paths)

    assert summary["enabled"] is True
    comparison = pd.read_csv(paths["strategy_comparison_csv"]).set_index("name")
    assert set(comparison.index) == {
        "unconstrained_top10",
        "sector_cap_2_top10",
        "sector_cap_3_top10",
        "sector_cap_4_top10",
        "sector_momentum_tilt_top10",
    }
    unconstrained = pd.read_csv(paths["strategy_comparison_dir"] / "unconstrained_top10" / "backtest_positions.csv")
    cap2 = pd.read_csv(paths["strategy_comparison_dir"] / "sector_cap_2_top10" / "backtest_positions.csv")
    cap3 = pd.read_csv(paths["strategy_comparison_dir"] / "sector_cap_3_top10" / "backtest_positions.csv")
    cap4 = pd.read_csv(paths["strategy_comparison_dir"] / "sector_cap_4_top10" / "backtest_positions.csv")
    tilted = pd.read_csv(paths["strategy_comparison_dir"] / "sector_momentum_tilt_top10" / "backtest_positions.csv")
    assert unconstrained["sector"].value_counts().to_dict()["Technology"] == 4
    assert cap2["sector"].value_counts().max() <= 2
    assert cap3["sector"].value_counts().max() <= 3
    assert cap4["sector"].value_counts().max() <= 4
    assert comparison.loc["sector_cap_2_top10", "max_sector"] == 2
    assert comparison.loc["sector_cap_3_top10", "max_sector"] == 3
    assert comparison.loc["sector_cap_4_top10", "max_sector"] == 4
    assert tilted["sector"].value_counts().to_dict()["Technology"] == 3
    assert summary["insights"]["enabled"] is True
    assert summary["insights"]["recommended_default"]["max_sector"] in {2, 3, 4}
