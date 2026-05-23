from __future__ import annotations

from pathlib import Path

import pandas as pd

from analysis.nasdaq_top500_score.data_quality import run_data_quality_validation
from analysis.nasdaq_top500_score.data_sources import PreparedData


def test_data_quality_marks_nasdaq_approximate_universe_as_not_strict(tmp_path: Path) -> None:
    paths = {
        "membership_csv": tmp_path / "membership.csv",
        "security_master_csv": tmp_path / "security_master.csv",
        "universe_selection_csv": tmp_path / "universe_selection.csv",
        "pit_universe_validation": tmp_path / "pit_universe_validation.csv",
        "security_master_validation": tmp_path / "security_master_validation.csv",
        "market_cap_validation": tmp_path / "market_cap_validation.csv",
        "data_quality_summary": tmp_path / "data_quality_summary.yaml",
    }
    pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "market_cap_asof_estimate": 100.0,
                "selection_status": "selected",
            }
        ]
    ).to_csv(paths["universe_selection_csv"], index=False)
    prepared = PreparedData(
        universe=pd.DataFrame([{"symbol": "AAA", "market_cap": 1000.0}]),
        failures=pd.DataFrame(),
    )
    config = {
        "data": {"source": "nasdaq_public", "vwap_method": "ohlc_mean"},
        "universe": {
            "selection": {"method": "approximate_market_cap_asof", "as_of_date": "2023-12-31"},
        },
    }

    result = run_data_quality_validation(config, paths, prepared)

    assert result.summary["strict_result_status"] == "not_strict_pit"
    assert result.summary["strict_headline_allowed"] is False
    assert result.summary["survivorship_risk"] == "high"
    assert result.summary["market_cap_proxy_risk"] == "high"
    assert (tmp_path / "pit_universe_validation.csv").exists()
    assert (tmp_path / "market_cap_validation.csv").exists()


def test_data_quality_allows_sharadar_launch_pit_when_required_fields_exist(tmp_path: Path) -> None:
    paths = {
        "membership_csv": tmp_path / "membership.csv",
        "security_master_csv": tmp_path / "security_master.csv",
        "universe_selection_csv": tmp_path / "universe_selection.csv",
        "pit_universe_validation": tmp_path / "pit_universe_validation.csv",
        "security_master_validation": tmp_path / "security_master_validation.csv",
        "market_cap_validation": tmp_path / "market_cap_validation.csv",
        "data_quality_summary": tmp_path / "data_quality_summary.yaml",
    }
    pd.DataFrame([{"symbol": "AAA", "asset_type": "Domestic Common Stock"}]).to_csv(paths["security_master_csv"], index=False)
    pd.DataFrame([{"symbol": "AAA", "date": "2023-12-29", "is_member": 1}]).to_csv(paths["membership_csv"], index=False)
    prepared = PreparedData(
        universe=pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "is_delisted": False,
                    "first_quoted_date": "2010-01-04",
                    "last_quoted_date": "2026-05-17",
                    "market_cap_asof": 1000.0,
                    "market_cap_asof_date": "2023-12-29",
                }
            ]
        ),
        failures=pd.DataFrame(),
        metadata={"source": "sharadar"},
    )
    config = {
        "strict_pit": {"enabled": True, "mode": "launch_pit_2023", "enforcement": "fail"},
        "data": {"source": "sharadar", "vwap_method": "ohlc_mean", "price_adjustment": "CAPITAL"},
        "universe": {"include_delisted": True},
    }

    result = run_data_quality_validation(config, paths, prepared)

    assert result.summary["strict_result_status"] == "strict_pit_pass"
    assert result.summary["strict_headline_allowed"] is True
    assert result.summary["market_cap_proxy_risk"] == "low"


def test_data_quality_allows_databento_launch_pit_when_required_fields_exist(tmp_path: Path) -> None:
    paths = {
        "membership_csv": tmp_path / "membership.csv",
        "security_master_csv": tmp_path / "security_master.csv",
        "universe_selection_csv": tmp_path / "universe_selection.csv",
        "pit_universe_validation": tmp_path / "pit_universe_validation.csv",
        "security_master_validation": tmp_path / "security_master_validation.csv",
        "market_cap_validation": tmp_path / "market_cap_validation.csv",
        "data_quality_summary": tmp_path / "data_quality_summary.yaml",
    }
    pd.DataFrame([{"symbol": "AAA", "asset_type": "Common Stock"}]).to_csv(paths["security_master_csv"], index=False)
    pd.DataFrame([{"symbol": "AAA", "date": "2023-12-29", "is_member": 1}]).to_csv(paths["membership_csv"], index=False)
    prepared = PreparedData(
        universe=pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "is_delisted": False,
                    "first_quoted_date": "2010-01-04",
                    "last_quoted_date": "2026-05-17",
                    "market_cap_asof": 1000.0,
                    "market_cap_asof_date": "2023-12-29",
                    "shares_outstanding": 10.0,
                }
            ]
        ),
        failures=pd.DataFrame(),
        metadata={"source": "databento"},
    )
    config = {
        "strict_pit": {"enabled": True, "mode": "launch_pit_2023", "enforcement": "fail"},
        "data": {"source": "databento", "vwap_method": "ohlc_mean", "price_adjustment": "EQUS_SUMMARY"},
        "universe": {"include_delisted": True},
    }

    result = run_data_quality_validation(config, paths, prepared)

    assert result.summary["strict_result_status"] == "strict_pit_pass"
    assert result.summary["strict_headline_allowed"] is True
    assert result.summary["market_cap_proxy_risk"] == "low"
