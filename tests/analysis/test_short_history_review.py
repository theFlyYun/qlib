from __future__ import annotations

from pathlib import Path

import pandas as pd

from analysis.nasdaq_top500_score.short_history_review import run_short_history_review


def build_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "strategy_comparison_dir": tmp_path / "strategy_comparison",
        "backtest_positions_csv": tmp_path / "backtest_positions.csv",
        "market_features": tmp_path / "market_features.parquet",
        "fundamental_features": tmp_path / "fundamental_features.parquet",
        "short_history_bucket_summary": tmp_path / "short_history_bucket_summary.csv",
        "short_history_examples": tmp_path / "short_history_examples.csv",
        "short_history_feature_differences": tmp_path / "short_history_feature_differences.csv",
        "short_history_sector_breakdown": tmp_path / "short_history_sector_breakdown.csv",
        "short_history_review_summary": tmp_path / "short_history_review_summary.yaml",
    }


def write_baseline_positions(paths: dict[str, Path], frame: pd.DataFrame, variant: str = "raw_score_sector_cap_2_top10") -> None:
    path = paths["strategy_comparison_dir"] / variant / "backtest_positions.csv"
    path.parent.mkdir(parents=True)
    frame.to_csv(path, index=False)


def test_short_history_review_classifies_short_history_winners_and_losers(tmp_path: Path) -> None:
    paths = build_paths(tmp_path)
    signal_date = pd.Timestamp("2024-01-02")
    positions = pd.DataFrame(
        [
            bucket_position("NWIN", "lt_2y", "Technology", 0.20, 0.90, 200, 30_000_000),
            bucket_position("NLOSE", "lt_2y", "Technology", -0.20, 0.80, 190, 1_000_000),
            bucket_position("NMID", "lt_2y", "Health Care", 0.04, 0.50, 210, 15_000_000),
            bucket_position("NLOW", "lt_2y", "Health Care", -0.05, 0.30, 195, 4_000_000),
            bucket_position("SWIN", "2_5y", "Technology", 0.15, 0.70, 700, 25_000_000),
            bucket_position("SLOSE", "2_5y", "Technology", -0.10, 0.60, 650, 3_000_000),
            bucket_position("FULL", "full_10y", "Finance", 0.02, 0.40, 2500, 40_000_000),
            bucket_position("MID", "5_10y", "Finance", 0.01, 0.35, 1500, 35_000_000),
        ]
    )
    positions["signal_date"] = signal_date.date().isoformat()
    write_baseline_positions(paths, positions)
    universe = pd.DataFrame(
        [
            {"symbol": symbol, "name": f"{symbol} Inc.", "asset_type": "common_stock"}
            for symbol in positions["symbol"]
        ]
    )
    write_feature_parquets(paths, signal_date)
    config = {
        "backtest": {"enabled": True},
        "short_history_review": {
            "enabled": True,
            "baseline_variant": "raw_score_sector_cap_2_top10",
            "target_buckets": ["lt_2y", "2_5y"],
            "comparison_buckets": ["full_10y", "5_10y"],
            "quantiles": 2,
            "min_bucket_samples": 2,
        },
    }

    result = run_short_history_review(pd.DataFrame(), universe, config, paths)

    examples = result.examples.set_index("symbol")
    assert examples.loc["NWIN", "short_history_category"] == "bucket_winners"
    assert examples.loc["NLOSE", "short_history_category"] == "bucket_losers"
    assert examples.loc["SWIN", "short_history_category"] == "bucket_winners"
    assert examples.loc["SLOSE", "short_history_category"] == "bucket_losers"
    assert pd.isna(examples.loc["SLOSE", "edgar_roe"])
    summary = result.bucket_summary.set_index("history_bucket")
    assert summary.loc["lt_2y", "position_count"] == 4
    assert summary.loc["2_5y", "winner_count"] == 1
    assert summary.loc["lt_2y", "loser_low_liquidity_rate"] == 0.5
    breakdown = result.sector_breakdown
    assert set(breakdown["group_level"]) == {"sector", "industry"}
    assert not result.feature_differences.empty
    assert result.yaml_summary["baseline_variant"] == "raw_score_sector_cap_2_top10"
    assert paths["short_history_bucket_summary"].exists()
    assert paths["short_history_examples"].exists()
    assert paths["short_history_feature_differences"].exists()
    assert paths["short_history_sector_breakdown"].exists()
    assert paths["short_history_review_summary"].exists()


def test_short_history_review_disabled_writes_empty_outputs(tmp_path: Path) -> None:
    paths = build_paths(tmp_path)
    result = run_short_history_review(
        pd.DataFrame(),
        pd.DataFrame(),
        {"short_history_review": {"enabled": False}},
        paths,
    )

    assert result.yaml_summary == {"enabled": False}
    assert paths["short_history_bucket_summary"].exists()
    assert paths["short_history_review_summary"].exists()


def bucket_position(
    symbol: str,
    bucket: str,
    sector: str,
    gross_return: float,
    score: float,
    history_rows: int,
    dollar_volume: float,
) -> dict[str, object]:
    return {
        "period": 1,
        "entry_date": "2024-01-03",
        "exit_date": "2024-01-10",
        "symbol": symbol,
        "selected_rank": 1,
        "history_bucket": bucket,
        "sector": sector,
        "industry": f"{sector} Industry",
        "score": score,
        "raw_score": score,
        "adjusted_score": score,
        "weight": 0.1,
        "history_rows_asof": history_rows,
        "latest_close_asof": 10.0,
        "avg_dollar_volume_20d_asof": dollar_volume,
        "median_dollar_volume_60d_asof": dollar_volume,
        "entry_price": 10.0,
        "exit_price": 10.0 * (1.0 + gross_return),
        "gross_return": gross_return,
        "gross_contribution": gross_return * 0.1,
        "net_contribution": gross_return * 0.1 - 0.0001,
    }


def write_feature_parquets(paths: dict[str, Path], signal_date: pd.Timestamp) -> None:
    market = pd.DataFrame(
        {
            "market_momentum_60d": [0.4, -0.2, 0.1, -0.1, 0.3, -0.3],
            "market_volatility_20d": [0.2, 0.8, 0.3, 0.7, 0.25, 0.9],
        },
        index=pd.MultiIndex.from_tuples(
            [
                (signal_date, "NWIN"),
                (signal_date, "NLOSE"),
                (signal_date, "NMID"),
                (signal_date, "NLOW"),
                (signal_date, "SWIN"),
                (signal_date, "SLOSE"),
            ],
            names=["datetime", "instrument"],
        ),
    )
    fundamentals = pd.DataFrame(
        {
            "edgar_price_to_sales": [3.0, 12.0, 5.0, 8.0, 2.0],
            "edgar_roe": [0.2, -0.4, 0.1, -0.2, 0.15],
            "edgar_net_margin": [0.1, -0.3, 0.05, -0.1, 0.07],
            "edgar_is_recent_filing": [0, 1, 0, 0, 0],
        },
        index=pd.MultiIndex.from_tuples(
            [
                (signal_date, "NWIN"),
                (signal_date, "NLOSE"),
                (signal_date, "NMID"),
                (signal_date, "NLOW"),
                (signal_date, "SWIN"),
            ],
            names=["datetime", "instrument"],
        ),
    )
    market.to_parquet(paths["market_features"])
    fundamentals.to_parquet(paths["fundamental_features"])
