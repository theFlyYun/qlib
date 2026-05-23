from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from analysis.nasdaq_top500_score.data_sources import DataSourceUnavailable
from analysis.nasdaq_top500_score.data_sources.sharadar import (
    SharadarDataSource,
    run_sharadar_capability_probe,
)
from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import load_config


class FakeSharadarClient:
    def __init__(self, *, omit_daily_marketcap: bool = False) -> None:
        self.omit_daily_marketcap = omit_daily_marketcap

    def metadata(self, table: str) -> dict[str, Any]:
        columns_by_table = {
            "TICKERS": [
                "ticker",
                "name",
                "exchange",
                "category",
                "isdelisted",
                "firstpricedate",
                "lastpricedate",
                "sector",
                "industry",
            ],
            "SEP": ["ticker", "date", "open", "high", "low", "close", "volume"],
            "SF1": ["ticker", "dimension", "calendardate", "datekey", "reportperiod", "sharesbas"],
            "DAILY": ["ticker", "date"] if self.omit_daily_marketcap else ["ticker", "date", "marketcap"],
            "INDICATORS": ["table", "indicator", "description"],
        }
        return {
            "datatable": {
                "columns": [{"name": column, "type": "String"} for column in columns_by_table[table]],
                "filters": ["ticker", "date", "dimension"],
                "primary_key": ["ticker", "date"],
            }
        }

    def table(self, table: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
        params = params or {}
        if table == "TICKERS":
            return pd.DataFrame(
                [
                    {
                        "ticker": "AAA",
                        "name": "AAA Inc",
                        "exchange": "NASDAQ",
                        "category": "Domestic Common Stock",
                        "isdelisted": "N",
                        "firstpricedate": "2010-01-04",
                        "lastpricedate": None,
                        "sector": "Technology",
                        "industry": "Software",
                    },
                    {
                        "ticker": "BBB",
                        "name": "BBB Old",
                        "exchange": "NASDAQ",
                        "category": "Domestic Common Stock",
                        "isdelisted": "Y",
                        "firstpricedate": "2010-01-04",
                        "lastpricedate": "2025-06-30",
                        "sector": "Health Care",
                        "industry": "Biotech",
                    },
                    {
                        "ticker": "CCC",
                        "name": "CCC NYSE",
                        "exchange": "NYSE",
                        "category": "Domestic Common Stock",
                        "isdelisted": "N",
                        "firstpricedate": "2010-01-04",
                        "lastpricedate": None,
                        "sector": "Industrials",
                        "industry": "Machinery",
                    },
                    {
                        "ticker": "DDD",
                        "name": "DDD Warrant",
                        "exchange": "NASDAQ",
                        "category": "Warrant",
                        "isdelisted": "N",
                        "firstpricedate": "2010-01-04",
                        "lastpricedate": None,
                        "sector": "Finance",
                        "industry": "Shell",
                    },
                ]
            )
        if table == "DAILY":
            if self.omit_daily_marketcap:
                return pd.DataFrame([{"ticker": "AAA", "date": params.get("date", "2023-12-29")}])
            return pd.DataFrame(
                [
                    {"ticker": "AAA", "date": "2023-12-29", "marketcap": 300.0},
                    {"ticker": "BBB", "date": "2023-12-29", "marketcap": 400.0},
                    {"ticker": "CCC", "date": "2023-12-29", "marketcap": 500.0},
                ]
            )
        if table == "SEP":
            if "ticker" not in params:
                return pd.DataFrame(
                    [
                        {"ticker": "AAA", "date": "2023-12-29", "close": 11},
                        {"ticker": "BBB", "date": "2023-12-29", "close": 22},
                        {"ticker": "CCC", "date": "2023-12-29", "close": 33},
                    ]
                )
            symbol = params["ticker"]
            return pd.DataFrame(
                [
                    {"ticker": symbol, "date": "2023-12-28", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1000},
                    {"ticker": symbol, "date": "2023-12-29", "open": 11, "high": 12, "low": 10, "close": 11, "volume": 1100},
                    {"ticker": symbol, "date": "2024-01-02", "open": 12, "high": 13, "low": 11, "close": 12, "volume": 1200},
                ]
            )
        if table == "SF1":
            return pd.DataFrame(
                [
                    {"ticker": "AAA", "datekey": "2023-11-01", "sharesbas": 10.0, "shareswa": 10.0},
                    {"ticker": "BBB", "datekey": "2023-11-01", "sharesbas": 30.0, "shareswa": 30.0},
                    {"ticker": "CCC", "datekey": "2023-11-01", "sharesbas": 20.0, "shareswa": 20.0},
                ]
            )
        raise AssertionError(f"unexpected table call: {table}")


def make_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "source_dir": tmp_path / "qlib_source_csv",
        "sharadar_cache_dir": tmp_path / "sharadar_cache",
        "universe_csv": tmp_path / "universe.csv",
        "universe_candidates_csv": tmp_path / "universe_candidates.csv",
        "universe_selection_csv": tmp_path / "universe_selection.csv",
        "security_master_csv": tmp_path / "security_master.csv",
        "failures_csv": tmp_path / "download_failures.csv",
        "membership_csv": tmp_path / "membership.csv",
        "provider_capability_summary": tmp_path / "provider_capability_summary.yaml",
        "provider_table_columns": tmp_path / "provider_table_columns.csv",
        "provider_capability_report": tmp_path / "provider_capability_report.md",
    }


def make_config() -> dict[str, Any]:
    return {
        "strict_pit": {"enabled": True, "mode": "launch_pit_2023", "enforcement": "fail"},
        "universe": {
            "provider": "sharadar",
            "exchange": "NASDAQ",
            "as_of_date": "2023-12-31",
            "as_of_trade_date": "2023-12-29",
            "top_n_by_market_cap": 2,
            "include_delisted": True,
            "min_history_rows": 2,
        },
        "data": {
            "source": "sharadar",
            "start_date": "2023-12-28",
            "end_date": "2024-01-02",
            "freq": "day",
            "price_adjustment": "CAPITAL",
            "vwap_method": "ohlc_mean",
        },
        "sharadar": {"tables": ["TICKERS", "SEP", "SF1", "DAILY", "INDICATORS"]},
    }


def test_sharadar_capability_probe_writes_outputs_and_passes(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)

    result = run_sharadar_capability_probe(make_config(), paths, FakeSharadarClient())

    assert result.strict_pass is True
    assert paths["provider_capability_summary"].exists()
    assert paths["provider_table_columns"].exists()
    assert paths["provider_capability_report"].exists()


def test_sharadar_data_source_builds_launch_pit_without_current_market_cap_proxy(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    prepared = SharadarDataSource(make_config(), paths, client=FakeSharadarClient()).prepare()

    assert prepared.metadata["source"] == "sharadar"
    assert prepared.universe["symbol"].tolist() == ["BBB", "AAA"]
    assert "market_cap_asof" in prepared.universe.columns
    assert "market_cap_asof_estimate" not in prepared.universe.columns
    assert bool(prepared.universe.loc[prepared.universe["symbol"].eq("BBB"), "is_delisted"].iloc[0]) is True
    assert (paths["source_dir"] / "BBB.csv").exists()

    candidates = pd.read_csv(paths["universe_candidates_csv"])
    security_master = pd.read_csv(paths["security_master_csv"])
    assert "DDD" not in set(candidates["symbol"])
    assert "DDD" in set(security_master["symbol"])


def test_sharadar_without_api_key_writes_capability_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NASDAQ_DATA_LINK_API_KEY", raising=False)
    monkeypatch.delenv("SHARADAR_API_KEY", raising=False)
    paths = make_paths(tmp_path)

    with pytest.raises(DataSourceUnavailable, match="NASDAQ_DATA_LINK_API_KEY"):
        SharadarDataSource(make_config(), paths).prepare()

    assert paths["provider_capability_summary"].exists()
    assert "strict_capability_pass: false" in paths["provider_capability_summary"].read_text(encoding="utf-8")


def test_sharadar_prepare_can_fallback_to_sf1_shares_times_asof_close(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)

    result = run_sharadar_capability_probe(make_config(), paths, FakeSharadarClient(omit_daily_marketcap=True))
    checks = {check["check_id"]: check["status"] for check in result.summary["checks"]}
    assert checks["C6"] == "pass"
    prepared = SharadarDataSource(make_config(), paths, client=FakeSharadarClient(omit_daily_marketcap=True)).prepare()
    assert prepared.universe["symbol"].tolist() == ["BBB", "AAA"]
    assert set(prepared.universe["market_cap_source"]) == {"sharadar_sf1_shares_x_sep_close"}


def test_strict_sharadar_configs_parse() -> None:
    for path in [
        Path("analysis/nasdaq_top500_score/configs/strict/strict_sharadar_baseline_alpha158_edgar_5d.yaml"),
        Path("analysis/nasdaq_top500_score/configs/strict/strict_sharadar_macro_direct_5d.yaml"),
        Path("analysis/nasdaq_top500_score/configs/strict/strict_sharadar_macro_interactions_no_credit_5d.yaml"),
    ]:
        config = load_config(path)
        assert config["strict_pit"]["enabled"] is True
        assert config["strict_pit"]["mode"] == "launch_pit_2023"
        assert config["data"]["source"] == "sharadar"
        assert config["universe"]["as_of_trade_date"] == "2023-12-29"
        assert config["industry_constraints"]["enabled"] is False
