from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from analysis.nasdaq_top500_score.edgar_coverage import build_edgar_coverage_review, build_edgar_effectiveness_review


def make_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "fundamental_features": tmp_path / "fundamental_features.parquet",
        "fundamental_features_cleaned": tmp_path / "fundamental_features_cleaned.parquet",
        "fundamental_failures": tmp_path / "fundamental_failures.csv",
        "edgar_cik_map": tmp_path / "edgar_cik_map.csv",
        "industry_master": tmp_path / "industry_master.parquet",
        "history_buckets_csv": tmp_path / "history_buckets.csv",
        "edgar_coverage_summary": tmp_path / "edgar_coverage_summary.yaml",
        "edgar_coverage_by_year": tmp_path / "edgar_coverage_by_year.csv",
        "edgar_coverage_by_split": tmp_path / "edgar_coverage_by_split.csv",
        "edgar_coverage_by_sector": tmp_path / "edgar_coverage_by_sector.csv",
        "edgar_coverage_by_industry": tmp_path / "edgar_coverage_by_industry.csv",
        "edgar_coverage_by_history_bucket": tmp_path / "edgar_coverage_by_history_bucket.csv",
        "edgar_feature_missingness": tmp_path / "edgar_feature_missingness.csv",
        "edgar_failure_breakdown": tmp_path / "edgar_failure_breakdown.csv",
        "edgar_missingness_root_cause": tmp_path / "edgar_missingness_root_cause.csv",
        "edgar_field_availability_by_year": tmp_path / "edgar_field_availability_by_year.csv",
        "edgar_feature_effectiveness_summary": tmp_path / "edgar_feature_effectiveness_summary.yaml",
        "edgar_feature_ic_summary": tmp_path / "edgar_feature_ic_summary.csv",
        "edgar_feature_ic_by_year": tmp_path / "edgar_feature_ic_by_year.csv",
        "edgar_feature_ic_by_sector": tmp_path / "edgar_feature_ic_by_sector.csv",
        "edgar_feature_quantile_spread": tmp_path / "edgar_feature_quantile_spread.csv",
    }


def make_config() -> dict:
    return {
        "split": {
            "method": "date",
            "train": {"start": "2020-01-01", "end": "2020-12-31"},
            "valid": {"start": "2021-01-01", "end": "2021-12-31"},
            "test": {"start": "2022-01-01", "end": "2022-12-31"},
        }
    }


def test_edgar_coverage_review_groups_by_year_sector_and_failures(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    index = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2020-01-02"), "P1"),
            (pd.Timestamp("2020-01-03"), "P1"),
            (pd.Timestamp("2022-01-04"), "P2"),
        ],
        names=["datetime", "instrument"],
    )
    features = pd.DataFrame(
        {
            "edgar_roe": [0.1, pd.NA, 0.2],
            "edgar_price_to_sales": [5.0, pd.NA, pd.NA],
        },
        index=index,
    )
    failures = pd.DataFrame(
        [
            {"symbol": "P3", "cik": None, "error": "missing_cik", "detail": "lookup candidates: OLD"},
            {"symbol": "P2", "cik": 2, "error": "missing_fields", "detail": "gross_profit"},
        ]
    )
    cik_map = pd.DataFrame(
        [
            {"symbol": "P1", "cik": 1},
            {"symbol": "P2", "cik": 2},
        ]
    )
    pd.DataFrame(
        [
            {
                "instrument": "P1",
                "effective_start": "2020-01-01",
                "effective_end": "2020-12-31",
                "sector": "73",
                "industry": "7372",
                "is_pit": True,
            },
            {
                "instrument": "P2",
                "effective_start": "2022-01-01",
                "effective_end": "2022-12-31",
                "sector": "28",
                "industry": "2834",
                "is_pit": True,
            },
        ]
    ).to_parquet(paths["industry_master"], index=False)
    pd.DataFrame(
        [
            {"symbol": "P1", "history_bucket": "full_10y"},
            {"symbol": "P2", "history_bucket": "2_5y"},
        ]
    ).to_csv(paths["history_buckets_csv"], index=False)

    result = build_edgar_coverage_review(
        pd.DataFrame({"symbol": ["P1", "P2", "P3"]}),
        make_config(),
        paths,
        features=features,
        failures=failures,
        cik_map=cik_map,
    )

    assert result.summary["universe_instrument_count"] == 3
    assert result.summary["cik_mapped_count"] == 2
    assert result.summary["feature_instrument_count"] == 2
    assert result.summary["failure_counts"]["missing_cik"] == 1
    assert "missingness_root_cause" in result.__dataclass_fields__
    assert result.by_year.set_index("year").loc[2020, "row_count"] == 2
    assert result.by_sector.set_index("sector").loc["73", "instrument_count"] == 1
    assert result.by_history_bucket.set_index("history_bucket").loc["full_10y", "row_count"] == 2
    missing = result.feature_missingness.set_index("feature")
    assert missing.loc["edgar_price_to_sales", "missing_count"] == 2
    assert paths["edgar_coverage_summary"].exists()
    assert paths["edgar_missingness_root_cause"].exists()
    assert paths["edgar_field_availability_by_year"].exists()
    assert yaml.safe_load(paths["edgar_coverage_summary"].read_text())["feature_column_count"] == 2
    root_cause = pd.read_csv(paths["edgar_missingness_root_cause"])
    assert "missing_cik_mapping" in root_cause["root_cause"].tolist()
    availability = pd.read_csv(paths["edgar_field_availability_by_year"])
    assert availability.set_index(["year", "feature"]).loc[(2020, "edgar_roe"), "availability_ratio"] == 0.5


def test_edgar_effectiveness_review_scores_fields_by_daily_cross_section(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    dates = [pd.Timestamp("2022-01-03"), pd.Timestamp("2022-01-03"), pd.Timestamp("2022-01-03"), pd.Timestamp("2022-01-04"), pd.Timestamp("2022-01-04"), pd.Timestamp("2022-01-04")]
    instruments = ["P1", "P2", "P3", "P1", "P2", "P3"]
    index = pd.MultiIndex.from_arrays([dates, instruments], names=["datetime", "instrument"])
    features = pd.DataFrame(
        {
            "edgar_roe": [0.1, 0.2, 0.3, 0.1, 0.2, 0.3],
            "edgar_price_to_sales": [3.0, 2.0, 1.0, 3.0, 2.0, 1.0],
        },
        index=index,
    )
    labels = pd.Series([0.01, 0.02, 0.03, 0.01, 0.02, 0.03], index=index, name="LABEL0")
    pd.DataFrame(
        [
            {
                "instrument": "P1",
                "effective_start": "2022-01-01",
                "effective_end": "2022-12-31",
                "sector": "73",
                "industry": "7372",
                "is_pit": True,
            },
            {
                "instrument": "P2",
                "effective_start": "2022-01-01",
                "effective_end": "2022-12-31",
                "sector": "73",
                "industry": "7372",
                "is_pit": True,
            },
            {
                "instrument": "P3",
                "effective_start": "2022-01-01",
                "effective_end": "2022-12-31",
                "sector": "28",
                "industry": "2834",
                "is_pit": True,
            },
        ]
    ).to_parquet(paths["industry_master"], index=False)
    config = make_config() | {"edgar_effectiveness_review": {"min_observations": 3, "quantiles": 3}}

    result = build_edgar_effectiveness_review(features, labels, config, paths)

    by_feature = result.by_feature.set_index("feature")
    assert by_feature.loc["edgar_roe", "rank_ic_mean"] == 1.0
    assert by_feature.loc["edgar_price_to_sales", "rank_ic_mean"] == -1.0
    spread = result.quantile_spread.set_index("feature")
    assert spread.loc["edgar_roe", "top_bottom_spread"] > 0
    assert spread.loc["edgar_price_to_sales", "top_bottom_spread"] < 0
    assert paths["edgar_feature_effectiveness_summary"].exists()
    assert paths["edgar_feature_ic_by_sector"].exists()
