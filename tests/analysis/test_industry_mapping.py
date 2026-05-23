from __future__ import annotations

from pathlib import Path

import pandas as pd

from analysis.nasdaq_top500_score.industry_mapping import build_industry_mapping


def make_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "membership_csv": tmp_path / "membership.csv",
        "industry_master": tmp_path / "industry_master.parquet",
        "industry_mapping_failures": tmp_path / "industry_mapping_failures.csv",
        "industry_mapping_coverage": tmp_path / "industry_mapping_coverage.csv",
        "industry_mapping_summary": tmp_path / "industry_mapping_summary.yaml",
    }


def make_config() -> dict:
    return {
        "data": {"source": "crsp"},
        "split": {
            "train": {"start": "2020-01-01", "end": "2020-12-31"},
            "test": {"start": "2021-01-01", "end": "2021-12-31"},
        },
        "industry_mapping": {
            "enabled": True,
            "primary_source": "crsp_monthly_row",
            "fallbacks": ["sec_edgar_sic"],
            "sector_scheme": "sic2",
            "industry_scheme": "sic4",
            "min_train_annual_sector_coverage": 0.80,
            "min_test_rebalance_sector_coverage": 0.85,
        },
    }


def test_industry_mapping_prefers_crsp_monthly_row(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    pd.DataFrame(
        [
            {
                "instrument": "P10001",
                "symbol": "P10001",
                "permno": 10001,
                "month_end_date": "2020-01-31",
                "effective_start": "2020-02-03",
                "effective_end": "2020-02-28",
                "siccd": "7372",
                "naics": "513210",
            }
        ]
    ).to_csv(paths["membership_csv"], index=False)

    result = build_industry_mapping(make_config(), paths)

    row = result.master.iloc[0]
    assert row["source"] == "crsp_monthly_row"
    assert row["is_pit"] is True or row["is_pit"] == True
    assert row["sector"] == "73"
    assert result.summary["crsp_pit_rows"] == 1
    assert paths["industry_master"].exists()


def test_industry_mapping_fallback_only_fills_missing_crsp_sic(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    fallback = tmp_path / "edgar_sic.csv"
    pd.DataFrame(
        [
            {"instrument": "P10001", "siccd": "2834", "evidence_date": "2020-01-15", "is_pit": False},
            {"instrument": "P10002", "siccd": "6021", "evidence_date": "2020-01-15", "is_pit": False},
        ]
    ).to_csv(fallback, index=False)
    membership = pd.DataFrame(
        [
            {
                "instrument": "P10001",
                "symbol": "P10001",
                "permno": 10001,
                "month_end_date": "2020-01-31",
                "effective_start": "2020-02-03",
                "effective_end": "2020-02-28",
                "siccd": "7372",
                "naics": "513210",
            },
            {
                "instrument": "P10002",
                "symbol": "P10002",
                "permno": 10002,
                "month_end_date": "2020-01-31",
                "effective_start": "2020-02-03",
                "effective_end": "2020-02-28",
                "siccd": "0",
                "naics": "0",
            },
        ]
    )
    membership.to_csv(paths["membership_csv"], index=False)
    config = make_config()
    config["industry_mapping"]["edgar_sic_map_path"] = str(fallback)

    result = build_industry_mapping(config, paths)

    by_symbol = result.master.set_index("instrument")
    assert by_symbol.loc["P10001", "sector"] == "73"
    assert by_symbol.loc["P10001", "source"] == "crsp_monthly_row"
    assert by_symbol.loc["P10002", "sector"] == "60"
    assert by_symbol.loc["P10002", "source"] == "sec_edgar_sic"
    assert by_symbol.loc["P10002", "is_pit"] is False or by_symbol.loc["P10002", "is_pit"] == False
    assert result.summary["edgar_fallback_rows"] == 1
    assert result.summary["non_pit_or_unverified_rows"] == 1


def test_industry_mapping_keeps_unknown_when_no_valid_source(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    pd.DataFrame(
        [
            {
                "instrument": "P10001",
                "symbol": "P10001",
                "permno": 10001,
                "month_end_date": "2020-01-31",
                "effective_start": "2020-02-03",
                "effective_end": "2020-02-28",
                "siccd": "0",
                "naics": "0",
            }
        ]
    ).to_csv(paths["membership_csv"], index=False)

    result = build_industry_mapping(make_config(), paths)

    assert result.master.iloc[0]["sector"] == "UNKNOWN"
    assert result.summary["unknown_rows"] == 1
    assert result.failures.iloc[0]["reason"] == "missing_industry"
