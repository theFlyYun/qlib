from __future__ import annotations

from pathlib import Path

import pandas as pd

from analysis.nasdaq_top500_score.selection import (
    apply_bucket_ranking,
    build_history_buckets,
    clean_stock_universe,
    select_bucketed_top,
)


def test_stock_pool_cleaning_filters_special_securities_and_keeps_equity_like_names(tmp_path: Path) -> None:
    universe = pd.DataFrame(
        [
            {"symbol": "AAA", "name": "AAA Corporation Common Stock", "market_cap": 100},
            {"symbol": "BBB", "name": "BBB Ltd. Ordinary Shares", "market_cap": 90},
            {"symbol": "CCC", "name": "CCC Inc. Class A Common Stock", "market_cap": 80},
            {"symbol": "DDD", "name": "DDD plc American Depositary Shares", "market_cap": 70},
            {"symbol": "EEW", "name": "EEE Limited Warrant", "market_cap": 60},
            {"symbol": "FFF", "name": "FFF Preferred Stock", "market_cap": 50},
            {"symbol": "GGG", "name": "GGG Acquisition Unit", "market_cap": 40},
            {"symbol": "HHH", "name": "HHH Rights", "market_cap": 30},
            {"symbol": "III", "name": "III Depositary Shares", "market_cap": 20},
        ]
    )
    config = {"security_filter": {"enabled": True}}

    cleaned, exclusions = clean_stock_universe(universe, config, tmp_path / "universe_exclusions.csv")

    assert cleaned["symbol"].tolist() == ["AAA", "BBB", "CCC", "DDD"]
    assert set(exclusions["symbol"]) == {"EEW", "FFF", "GGG", "HHH", "III"}
    assert (tmp_path / "universe_exclusions.csv").exists()


def test_history_bucket_boundaries_are_inclusive(tmp_path: Path) -> None:
    source_dir = tmp_path / "qlib_source_csv"
    source_dir.mkdir()
    for symbol, rows in {"FULL": 2400, "MID": 1260, "SHORT": 504, "NEW": 180}.items():
        pd.DataFrame({"date": pd.bdate_range("2020-01-01", periods=rows).strftime("%Y-%m-%d")}).to_csv(
            source_dir / f"{symbol}.csv",
            index=False,
        )
    config = {
        "history_buckets": {
            "enabled": True,
            "thresholds": {"full_10y": 2400, "5_10y": 1260, "2_5y": 504, "lt_2y": 180},
        }
    }

    buckets = build_history_buckets(source_dir, tmp_path / "history_buckets.csv", config).set_index("symbol")

    assert buckets.loc["FULL", "history_bucket"] == "full_10y"
    assert buckets.loc["MID", "history_bucket"] == "5_10y"
    assert buckets.loc["SHORT", "history_bucket"] == "2_5y"
    assert buckets.loc["NEW", "history_bucket"] == "lt_2y"


def test_bucketed_top10_respects_quotas_and_keeps_one_lt_2y() -> None:
    predictions = pd.DataFrame(
        [
            {"symbol": f"F{i}", "score": 100 - i, "history_bucket": "full_10y"} for i in range(6)
        ]
        + [{"symbol": f"M{i}", "score": 80 - i, "history_bucket": "5_10y"} for i in range(4)]
        + [{"symbol": f"S{i}", "score": 70 - i, "history_bucket": "2_5y"} for i in range(3)]
        + [{"symbol": f"N{i}", "score": 60 - i, "history_bucket": "lt_2y"} for i in range(2)]
    )
    ranking_config = {
        "quotas": {"full_10y": 4, "5_10y": 3, "2_5y": 2, "lt_2y": 1},
        "refill_order": ["full_10y", "5_10y", "2_5y", "lt_2y"],
    }

    selected = select_bucketed_top(predictions, ranking_config, 10)

    assert len(selected) == 10
    assert selected["history_bucket"].value_counts().to_dict() == {
        "full_10y": 4,
        "5_10y": 3,
        "2_5y": 2,
        "lt_2y": 1,
    }
    assert selected[selected["history_bucket"] == "lt_2y"]["symbol"].tolist() == ["N0"]


def test_bucketed_top10_refills_shortfall_by_longer_history_first(tmp_path: Path) -> None:
    predictions = pd.DataFrame(
        [{"symbol": f"F{i}", "score": 100 - i, "history_bucket": "full_10y"} for i in range(6)]
        + [{"symbol": f"M{i}", "score": 80 - i, "history_bucket": "5_10y"} for i in range(3)]
        + [{"symbol": "S0", "score": 70, "history_bucket": "2_5y"}]
    )
    ranking_config = {
        "quotas": {"full_10y": 4, "5_10y": 3, "2_5y": 2, "lt_2y": 1},
        "refill_order": ["full_10y", "5_10y", "2_5y", "lt_2y"],
    }

    selected = select_bucketed_top(predictions, ranking_config, 10)

    assert len(selected) == 10
    assert selected["history_bucket"].value_counts().to_dict() == {"full_10y": 6, "5_10y": 3, "2_5y": 1}


def test_bucketed_top10_respects_sector_and_industry_constraints() -> None:
    predictions = pd.DataFrame(
        [
            {"symbol": "F0", "score": 100, "history_bucket": "full_10y", "sector": "Technology", "industry": "Semiconductors"},
            {"symbol": "F1", "score": 99, "history_bucket": "full_10y", "sector": "Technology", "industry": "Semiconductors"},
            {"symbol": "F2", "score": 98, "history_bucket": "full_10y", "sector": "Technology", "industry": "Semiconductors"},
            {"symbol": "F3", "score": 97, "history_bucket": "full_10y", "sector": "Technology", "industry": "Software"},
            {"symbol": "F4", "score": 96, "history_bucket": "full_10y", "sector": "Energy", "industry": "Machinery"},
            {"symbol": "F5", "score": 95, "history_bucket": "full_10y", "sector": "Financial Services", "industry": "Banks"},
            {"symbol": "M0", "score": 94, "history_bucket": "5_10y", "sector": "Technology", "industry": "Software"},
            {"symbol": "M1", "score": 93, "history_bucket": "5_10y", "sector": "Technology", "industry": "Software"},
            {"symbol": "M2", "score": 92, "history_bucket": "5_10y", "sector": "Industrials", "industry": "Aerospace"},
            {"symbol": "S0", "score": 91, "history_bucket": "2_5y", "sector": "Health Care", "industry": "Biotech"},
            {"symbol": "S1", "score": 90, "history_bucket": "2_5y", "sector": "Consumer Discretionary", "industry": "Auto Parts"},
            {"symbol": "N0", "score": 89, "history_bucket": "lt_2y", "sector": "Basic Materials", "industry": "Metals"},
        ]
    )
    ranking_config = {
        "quotas": {"full_10y": 4, "5_10y": 3, "2_5y": 2, "lt_2y": 1},
        "refill_order": ["full_10y", "5_10y", "2_5y", "lt_2y"],
    }

    selected = select_bucketed_top(
        predictions,
        ranking_config,
        10,
        {"enabled": True, "max_sector": 4, "max_industry": 2},
    )

    assert len(selected) == 10
    assert "F2" not in set(selected["symbol"])
    assert selected["sector"].value_counts().max() <= 4
    assert selected["industry"].value_counts().max() <= 2


def test_apply_bucket_ranking_writes_bucket_outputs(tmp_path: Path) -> None:
    predictions = pd.DataFrame(
        [
            {"symbol": "AAA", "score": 0.3, "name": "AAA Common Stock"},
            {"symbol": "BBB", "score": 0.2, "name": "BBB Common Stock"},
        ]
    )
    pd.DataFrame(
        [
            {"symbol": "AAA", "history_rows": 2400, "first_date": "2016-05-17", "last_date": "2026-05-15", "history_bucket": "full_10y"},
            {"symbol": "BBB", "history_rows": 180, "first_date": "2025-08-01", "last_date": "2026-05-15", "history_bucket": "lt_2y"},
        ]
    ).to_csv(tmp_path / "history_buckets.csv", index=False)
    config = {
        "report": {"top_n": 2},
        "bucket_ranking": {
            "enabled": True,
            "quotas": {"full_10y": 1, "5_10y": 0, "2_5y": 0, "lt_2y": 1},
            "refill_order": ["full_10y", "5_10y", "2_5y", "lt_2y"],
        },
    }
    paths = {
        "history_buckets_csv": tmp_path / "history_buckets.csv",
        "bucketed_predictions_csv": tmp_path / "bucketed_predictions.csv",
        "selected_top10_csv": tmp_path / "selected_top10.csv",
    }

    selected, meta = apply_bucket_ranking(predictions, config, paths)

    assert selected["symbol"].tolist() == ["AAA", "BBB"]
    assert meta["selected_bucket_counts"] == {"full_10y": 1, "lt_2y": 1}
    assert (tmp_path / "bucketed_predictions.csv").exists()
    assert (tmp_path / "selected_top10.csv").exists()
