from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from analysis.nasdaq_top500_score.data_sources import DataSourceUnavailable
from analysis.nasdaq_top500_score.data_sources.databento import (
    DatabentoDataSource,
    run_databento_capability_probe,
)
from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import load_config


class FakeDatabentoClient:
    def security_master_range(self, **kwargs: Any) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "issuer_name": "AAA Inc",
                    "exchange": "NASDAQ",
                    "primary_exchange": "XNAS",
                    "operating_mic": "XNAS",
                    "security_type": "Common Stock",
                    "listing_date": "2010-01-04",
                    "delisting_date": None,
                    "listing_status": "ACTIVE",
                    "new_shares_outstanding": 10.0,
                    "new_outstanding_date": "2023-12-28",
                    "cik": "0000000001",
                    "naics": "511210",
                    "effective_date": "2023-12-28",
                },
                {
                    "symbol": "BBB",
                    "issuer_name": "BBB Delisted",
                    "exchange": "NASDAQ",
                    "primary_exchange": "XNAS",
                    "operating_mic": "XNAS",
                    "security_type": "Common Stock",
                    "listing_date": "2011-02-01",
                    "delisting_date": "2025-06-30",
                    "listing_status": "ACTIVE",
                    "new_shares_outstanding": 30.0,
                    "new_outstanding_date": "2023-12-28",
                    "cik": "0000000002",
                    "naics": "325412",
                    "effective_date": "2023-12-28",
                },
                {
                    "symbol": "CCC",
                    "issuer_name": "CCC NYSE",
                    "exchange": "NYSE",
                    "primary_exchange": "XNYS",
                    "operating_mic": "XNYS",
                    "security_type": "Common Stock",
                    "listing_date": "2010-01-04",
                    "delisting_date": None,
                    "listing_status": "ACTIVE",
                    "new_shares_outstanding": 20.0,
                    "new_outstanding_date": "2023-12-28",
                    "cik": "0000000003",
                    "naics": "333120",
                    "effective_date": "2023-12-28",
                },
                {
                    "symbol": "DDD",
                    "issuer_name": "DDD Warrant",
                    "exchange": "NASDAQ",
                    "primary_exchange": "XNAS",
                    "operating_mic": "XNAS",
                    "security_type": "Warrant",
                    "listing_date": "2010-01-04",
                    "delisting_date": None,
                    "listing_status": "ACTIVE",
                    "new_shares_outstanding": 40.0,
                    "new_outstanding_date": "2023-12-28",
                    "cik": "0000000004",
                    "naics": "525990",
                    "effective_date": "2023-12-28",
                },
            ]
        )

    def ohlcv_1d(self, **kwargs: Any) -> pd.DataFrame:
        symbols = kwargs["symbols"]
        if isinstance(symbols, str):
            symbols = [symbols]
        if len(symbols) > 1:
            return pd.DataFrame(
                [
                    {"date": "2023-12-29", "symbol": "AAA", "open": 10, "high": 12, "low": 9, "close": 11, "volume": 1000},
                    {"date": "2023-12-29", "symbol": "BBB", "open": 21, "high": 23, "low": 20, "close": 22, "volume": 2000},
                    {"date": "2023-12-29", "symbol": "CCC", "open": 31, "high": 34, "low": 30, "close": 33, "volume": 3000},
                ]
            )
        symbol = symbols[0]
        return pd.DataFrame(
            [
                {"date": "2023-12-28", "symbol": symbol, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1000},
                {"date": "2023-12-29", "symbol": symbol, "open": 11, "high": 12, "low": 10, "close": 11, "volume": 1100},
                {"date": "2024-01-02", "symbol": symbol, "open": 12, "high": 13, "low": 11, "close": 12, "volume": 1200},
            ]
        )

    def corporate_actions_sample(self, **kwargs: Any) -> pd.DataFrame:
        return pd.DataFrame([{"symbol": "AAPL", "action": "split", "effective_date": "2020-08-31"}])

    def adjustment_factors_sample(self, **kwargs: Any) -> pd.DataFrame:
        return pd.DataFrame([{"symbol": "AAPL", "effective_date": "2020-08-31", "factor": 0.25}])


def make_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "source_dir": tmp_path / "qlib_source_csv",
        "databento_cache_dir": tmp_path / "databento_cache",
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
            "provider": "databento",
            "exchange": "NASDAQ",
            "as_of_date": "2023-12-31",
            "as_of_trade_date": "2023-12-29",
            "top_n_by_market_cap": 2,
            "include_delisted": True,
            "min_history_rows": 2,
        },
        "data": {
            "source": "databento",
            "start_date": "2023-12-28",
            "end_date": "2024-01-02",
            "freq": "day",
            "price_adjustment": "EQUS_SUMMARY",
            "vwap_method": "ohlc_mean",
        },
        "databento": {
            "dataset": "EQUS.SUMMARY",
            "schema": "ohlcv-1d",
            "stype_out": "raw_symbol",
            "countries": ["US"],
            "exchanges": ["XNAS"],
            "probe_symbols": ["AAPL"],
        },
    }


def test_databento_capability_probe_writes_outputs_and_passes(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)

    result = run_databento_capability_probe(make_config(), paths, FakeDatabentoClient())

    assert result.strict_pass is True
    assert paths["provider_capability_summary"].exists()
    assert paths["provider_table_columns"].exists()
    assert paths["provider_capability_report"].exists()


def test_databento_data_source_builds_launch_pit_without_current_market_cap_proxy(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    prepared = DatabentoDataSource(make_config(), paths, client=FakeDatabentoClient()).prepare()

    assert prepared.metadata["source"] == "databento"
    assert prepared.universe["symbol"].tolist() == ["BBB", "AAA"]
    assert "market_cap_asof" in prepared.universe.columns
    assert "market_cap_asof_estimate" not in prepared.universe.columns
    assert bool(prepared.universe.loc[prepared.universe["symbol"].eq("BBB"), "is_delisted"].iloc[0]) is True
    assert (paths["source_dir"] / "BBB.csv").exists()

    candidates = pd.read_csv(paths["universe_candidates_csv"])
    security_master = pd.read_csv(paths["security_master_csv"])
    assert "DDD" not in set(candidates["symbol"])
    assert "DDD" in set(security_master["symbol"])


def test_databento_without_api_key_writes_capability_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    paths = make_paths(tmp_path)

    with pytest.raises(DataSourceUnavailable, match="DATABENTO_API_KEY"):
        DatabentoDataSource(make_config(), paths).prepare()

    assert paths["provider_capability_summary"].exists()
    assert "strict_capability_pass: false" in paths["provider_capability_summary"].read_text(encoding="utf-8")


def test_strict_databento_configs_parse() -> None:
    for path in [
        Path("analysis/nasdaq_top500_score/configs/strict/strict_databento_baseline_alpha158_edgar_5d.yaml"),
        Path("analysis/nasdaq_top500_score/configs/strict/strict_databento_macro_direct_5d.yaml"),
        Path("analysis/nasdaq_top500_score/configs/strict/strict_databento_macro_interactions_no_credit_5d.yaml"),
    ]:
        config = load_config(path)
        assert config["strict_pit"]["enabled"] is True
        assert config["strict_pit"]["mode"] == "launch_pit_2023"
        assert config["data"]["source"] == "databento"
        assert config["universe"]["as_of_trade_date"] == "2023-12-29"
        assert config["industry_constraints"]["enabled"] is False
