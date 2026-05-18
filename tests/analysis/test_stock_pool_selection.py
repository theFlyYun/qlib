from __future__ import annotations

from pathlib import Path

import pandas as pd

from analysis.nasdaq_top500_score.data_sources.nasdaq_public import select_approximate_asof_universe
from analysis.nasdaq_top500_score.selection import (
    apply_bucket_ranking,
    apply_liquidity_filter,
    apply_security_master_filter,
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


def test_security_master_classifies_and_filters_security_types(tmp_path: Path) -> None:
    screener = pd.DataFrame(
        [
            {"symbol": "AAA", "name": "AAA Corporation Common Stock", "market_cap": 100, "sector": "Technology", "industry": "Software"},
            {"symbol": "BBB", "name": "BBB Ltd. American Depositary Shares", "market_cap": 90, "sector": "Technology", "industry": "Software"},
            {"symbol": "CCC", "name": "CCC Inc. Class A Common Stock", "market_cap": 80, "sector": "Finance", "industry": "Banks"},
            {"symbol": "DDDW", "name": "DDD Inc. Warrant", "market_cap": 70, "sector": "Finance", "industry": "Banks"},
            {"symbol": "EEE", "name": "EEE Preferred Stock", "market_cap": 60, "sector": "Finance", "industry": "Banks"},
        ]
    )
    listed = pd.DataFrame(
        [
            {"symbol": "AAA", "security_name": "AAA Corporation Common Stock", "market_category": "Q", "test_issue": "N", "financial_status": "N", "round_lot_size": "100", "etf": "N"},
            {"symbol": "BBB", "security_name": "BBB Ltd. American Depositary Shares", "market_category": "Q", "test_issue": "N", "financial_status": "N", "round_lot_size": "100", "etf": "N"},
            {"symbol": "CCC", "security_name": "CCC Inc. Class A Common Stock", "market_category": "Q", "test_issue": "N", "financial_status": "N", "round_lot_size": "100", "etf": "N"},
            {"symbol": "DDDW", "security_name": "DDD Inc. Warrant", "market_category": "Q", "test_issue": "N", "financial_status": "N", "round_lot_size": "100", "etf": "N"},
            {"symbol": "EEE", "security_name": "EEE Preferred Stock", "market_category": "Q", "test_issue": "N", "financial_status": "N", "round_lot_size": "100", "etf": "N"},
        ]
    )
    config = {
        "exclude_etf": True,
        "exclude_test_issue": True,
        "security_master": {
            "enabled": True,
            "allowed_asset_types": ["common_stock", "ordinary_share", "adr_ads", "unknown_equity_like"],
            "allow_adr_ads": True,
            "require_not_etf": True,
            "require_not_test_issue": True,
        },
    }
    paths = {
        "security_master_csv": tmp_path / "security_master.csv",
        "security_master_exclusions_csv": tmp_path / "security_master_exclusions.csv",
        "universe_exclusions_csv": tmp_path / "universe_exclusions.csv",
    }

    filtered, master, exclusions = apply_security_master_filter(screener, listed, config, paths)

    assert filtered["symbol"].tolist() == ["AAA", "BBB", "CCC"]
    assert master.set_index("symbol").loc["BBB", "asset_type"] == "adr_ads"
    assert master.set_index("symbol").loc["CCC", "share_class"] == "A"
    assert set(exclusions["symbol"]) == {"DDDW", "EEE"}
    assert (tmp_path / "security_master.csv").exists()
    assert (tmp_path / "security_master_exclusions.csv").exists()


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


def test_approximate_asof_universe_uses_pre_test_price_snapshot(tmp_path: Path) -> None:
    source_dir = tmp_path / "qlib_source_csv"
    source_dir.mkdir()

    def write_symbol(symbol: str, closes: list[tuple[str, float]]) -> None:
        pd.DataFrame(
            {
                "date": [date for date, _ in closes],
                "symbol": symbol,
                "open": [close for _, close in closes],
                "high": [close for _, close in closes],
                "low": [close for _, close in closes],
                "close": [close for _, close in closes],
                "vwap": [close for _, close in closes],
                "volume": [1 for _ in closes],
            }
        ).to_csv(source_dir / f"{symbol}.csv", index=False)

    write_symbol("AAA", [("2023-12-29", 10), ("2026-05-15", 100)])
    write_symbol("BBB", [("2023-12-29", 80), ("2026-05-15", 80)])
    write_symbol("CCC", [("2024-01-02", 200), ("2026-05-15", 200)])
    universe = pd.DataFrame(
        [
            {"symbol": "AAA", "market_cap": 1000.0},
            {"symbol": "BBB", "market_cap": 800.0},
            {"symbol": "CCC", "market_cap": 700.0},
        ]
    )

    selected, diagnostics = select_approximate_asof_universe(
        universe,
        source_dir,
        {"as_of_date": "2023-12-31"},
        top_n=1,
    )

    assert selected["symbol"].tolist() == ["BBB"]
    assert selected.iloc[0]["asof_close_date"] == "2023-12-29"
    assert selected.iloc[0]["market_cap_asof_estimate"] == 800.0
    diagnostics_by_symbol = diagnostics.set_index("symbol")
    assert diagnostics_by_symbol.loc["AAA", "market_cap_asof_estimate"] == 100.0
    assert diagnostics_by_symbol.loc["CCC", "selection_error"] == "no_price_on_or_before_asof"


def test_liquidity_filter_removes_low_dollar_volume_and_low_price_symbols(tmp_path: Path) -> None:
    source_dir = tmp_path / "qlib_source_csv"
    source_dir.mkdir()
    dates = pd.bdate_range("2026-01-01", periods=80).strftime("%Y-%m-%d")

    def write_symbol(symbol: str, close: float, volume: int) -> None:
        pd.DataFrame(
            {
                "date": dates,
                "symbol": symbol,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "vwap": close,
                "volume": volume,
            }
        ).to_csv(source_dir / f"{symbol}.csv", index=False)

    write_symbol("LIQ", 20, 1_000_000)
    write_symbol("THIN", 2, 10_000)
    write_symbol("PENNY", 0.5, 10_000_000)
    universe = pd.DataFrame(
        [
            {"symbol": "LIQ", "name": "Liquid Common Stock"},
            {"symbol": "THIN", "name": "Thin Common Stock"},
            {"symbol": "PENNY", "name": "Penny Common Stock"},
        ]
    )
    config = {
        "liquidity_filter": {
            "enabled": True,
            "min_latest_close": 1.0,
            "min_avg_dollar_volume_20d": 5_000_000,
            "min_median_dollar_volume_60d": 2_000_000,
            "max_zero_volume_ratio_60d": 0.05,
            "min_recent_trading_days_60d": 40,
        }
    }
    paths = {
        "universe_csv": tmp_path / "universe.csv",
        "liquidity_profile_csv": tmp_path / "liquidity_profile.csv",
        "liquidity_exclusions_csv": tmp_path / "liquidity_exclusions.csv",
    }

    filtered, meta = apply_liquidity_filter(universe, source_dir, config, paths)

    assert filtered["symbol"].tolist() == ["LIQ"]
    assert (source_dir / "LIQ.csv").exists()
    assert not (source_dir / "THIN.csv").exists()
    assert not (source_dir / "PENNY.csv").exists()
    assert meta["liquidity_exclusion_count"] == 2
    exclusions = pd.read_csv(paths["liquidity_exclusions_csv"])
    assert set(exclusions["symbol"]) == {"THIN", "PENNY"}


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
