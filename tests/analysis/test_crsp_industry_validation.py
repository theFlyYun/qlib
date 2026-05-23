from __future__ import annotations

from pathlib import Path

import pandas as pd

from analysis.nasdaq_top500_score.crsp_industry_validation import run_crsp_industry_validation
from analysis.nasdaq_top500_score.data_sources import PreparedData
from analysis.nasdaq_top500_score.data_sources.crsp import sic_industry, sic_sector
from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import load_config


def make_paths(tmp_path: Path) -> dict[str, Path]:
    source_dir = tmp_path / "qlib_source_csv"
    source_dir.mkdir()
    pd.DataFrame({"date": pd.date_range("2024-01-02", periods=30, freq="B").strftime("%Y-%m-%d")}).to_csv(
        source_dir / "P10001.csv",
        index=False,
    )
    return {
        "source_dir": source_dir,
        "membership_csv": tmp_path / "membership.csv",
        "security_master_csv": tmp_path / "security_master.csv",
        "crsp_industry_validation": tmp_path / "crsp_industry_validation.csv",
        "crsp_industry_coverage_by_month": tmp_path / "crsp_industry_coverage_by_month.csv",
        "crsp_industry_coverage_by_year": tmp_path / "crsp_industry_coverage_by_year.csv",
        "crsp_industry_coverage_by_rebalance": tmp_path / "crsp_industry_coverage_by_rebalance.csv",
        "crsp_industry_validation_summary": tmp_path / "crsp_industry_validation_summary.yaml",
        "industry_master": tmp_path / "industry_master.parquet",
    }


def test_sic_sector_and_industry_normalize_invalid_values() -> None:
    assert sic_sector("7372") == "73"
    assert sic_industry("7372.0") == "7372"
    assert sic_sector("0") == "UNKNOWN"
    assert sic_industry(None) == "UNKNOWN"


def test_crsp_industry_validation_passes_when_sic2_coverage_meets_thresholds(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    pd.DataFrame(
        [
            {
                "symbol": "P10001",
                "month_end_date": "2023-12-29",
                "effective_start": "2024-01-02",
                "effective_end": "2024-12-31",
                "siccd": "7372",
                "naics": "513210",
            },
            {
                "symbol": "P10002",
                "month_end_date": "2023-12-29",
                "effective_start": "2024-01-02",
                "effective_end": "2024-12-31",
                "siccd": "2834",
                "naics": "325412",
            },
        ]
    ).to_csv(paths["membership_csv"], index=False)
    pd.DataFrame(columns=["instrument", "siccd", "naics"]).to_csv(paths["security_master_csv"], index=False)
    config = {
        "data": {"source": "crsp"},
        "split": {
            "method": "date",
            "train": {"start": "2024-01-01", "end": "2024-12-31"},
            "test": {"start": "2024-01-02", "end": "2024-02-29"},
        },
        "backtest": {"rebalance_days": 10},
        "industry_validation": {
            "enabled": True,
            "min_train_annual_sic2_coverage": 0.80,
            "min_test_rebalance_sic2_coverage": 0.85,
        },
    }

    result = run_crsp_industry_validation(config, paths, PreparedData(universe=pd.DataFrame(), failures=pd.DataFrame()))

    assert result.summary["industry_constraints_allowed"] is True
    assert result.summary["industry_features_allowed"] is True
    assert paths["crsp_industry_coverage_by_rebalance"].exists()


def test_crsp_industry_validation_fails_when_unknown_sic_is_too_high(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    pd.DataFrame(
        [
            {
                "symbol": "P10001",
                "month_end_date": "2023-12-29",
                "effective_start": "2024-01-02",
                "effective_end": "2024-12-31",
                "siccd": "0",
                "naics": "0",
            },
            {
                "symbol": "P10002",
                "month_end_date": "2023-12-29",
                "effective_start": "2024-01-02",
                "effective_end": "2024-12-31",
                "siccd": "2834",
                "naics": "325412",
            },
        ]
    ).to_csv(paths["membership_csv"], index=False)
    pd.DataFrame(columns=["instrument", "siccd", "naics"]).to_csv(paths["security_master_csv"], index=False)
    config = {
        "data": {"source": "crsp"},
        "split": {
            "method": "date",
            "train": {"start": "2024-01-01", "end": "2024-12-31"},
            "test": {"start": "2024-01-02", "end": "2024-02-29"},
        },
        "backtest": {"rebalance_days": 10},
        "industry_validation": {
            "enabled": True,
            "min_train_annual_sic2_coverage": 0.80,
            "min_test_rebalance_sic2_coverage": 0.85,
        },
    }

    result = run_crsp_industry_validation(config, paths, PreparedData(universe=pd.DataFrame(), failures=pd.DataFrame()))

    assert result.summary["industry_constraints_allowed"] is False
    assert result.summary["conclusion"] == "industry_review_only_until_coverage_improves"


def test_crsp_industry_validation_uses_industry_master_when_available(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    pd.DataFrame(
        [
            {
                "instrument": "P10001",
                "permno": 10001,
                "effective_start": "2024-01-02",
                "effective_end": "2024-12-31",
                "sector": "73",
                "industry": "7372",
                "raw_siccd": "7372",
                "raw_naics": "513210",
                "source": "crsp_monthly_row",
                "is_pit": True,
            },
            {
                "instrument": "P10002",
                "permno": 10002,
                "effective_start": "2024-01-02",
                "effective_end": "2024-12-31",
                "sector": "UNKNOWN",
                "industry": "UNKNOWN",
                "raw_siccd": "0",
                "raw_naics": "0",
                "source": "unknown",
                "is_pit": False,
            },
        ]
    ).to_parquet(paths["industry_master"], index=False)
    pd.DataFrame(columns=["instrument", "siccd", "naics"]).to_csv(paths["security_master_csv"], index=False)
    pd.DataFrame(columns=["symbol"]).to_csv(paths["membership_csv"], index=False)
    config = {
        "data": {"source": "crsp"},
        "split": {
            "method": "date",
            "train": {"start": "2024-01-01", "end": "2024-12-31"},
            "test": {"start": "2024-01-02", "end": "2024-02-29"},
        },
        "backtest": {"rebalance_days": 10},
        "industry_validation": {
            "enabled": True,
            "min_train_annual_sic2_coverage": 0.40,
            "min_test_rebalance_sic2_coverage": 0.40,
        },
    }

    result = run_crsp_industry_validation(config, paths, PreparedData(universe=pd.DataFrame(), failures=pd.DataFrame()))

    assert result.summary["source"] == "industry_master"
    assert result.summary["fallback_to_security_master"] is False
    assert result.summary["crsp_pit_rows"] == 1
    assert result.summary["unknown_rows"] == 1


def test_crsp_2010_configs_parse() -> None:
    base = load_config(Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_10d_conservative_2010_2025.yaml"))
    bucket = load_config(Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_bucket_top10_10d_conservative_2010_2025.yaml"))
    industry = load_config(Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_industry_constrained_10d_conservative_2010_2025.yaml"))
    comparison = load_config(
        Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_industry_strategy_comparison_10d_conservative_2010_2025.yaml")
    )
    relative = load_config(
        Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_industry_market_relative_10d_conservative_2010_2025.yaml")
    )
    edgar = load_config(
        Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_10d_conservative_2010_2025.yaml")
    )
    edgar_clean = load_config(
        Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_clean_10d_conservative_2010_2025.yaml")
    )
    edgar_relative = load_config(
        Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_relative_10d_conservative_2010_2025.yaml")
    )
    edgar_repaired_quality = load_config(
        Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_repaired_quality_10d_conservative_2010_2025.yaml")
    )
    edgar_quality_core = load_config(
        Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_quality_core_10d_conservative_2010_2025.yaml")
    )
    edgar_repaired_no_valuation = load_config(
        Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_repaired_no_valuation_10d_conservative_2010_2025.yaml")
    )

    assert base["data"]["start_date"] == "2010-01-01"
    assert base["backtest"]["cost_bps"] == 0
    assert base["backtest_stress"]["cost_bps"] == [0, 25, 50]
    assert bucket["bucket_ranking"]["enabled"] is True
    assert industry["strict_pit"]["pit_industry_classification"] is True
    assert comparison["run_mode"] == "backtest_only"
    assert comparison["training"]["reuse_test_predictions_path"].endswith("test_predictions.csv")
    assert len(comparison["strategy_comparison"]["variants"]) == 4
    assert relative["market_features"]["enabled"] is True
    assert relative["bucket_ranking"]["enabled"] is False
    assert relative["industry_constraints"]["enabled"] is False
    assert edgar["fundamentals"]["enabled"] is True
    assert edgar["fundamentals"]["valuation_price_source"] == "crsp_raw_close"
    assert edgar["strict_pit"]["pit_industry_classification"] is True
    assert len(edgar["strategy_comparison"]["variants"]) == 2
    assert edgar_clean["edgar_coverage_review"]["enabled"] is True
    assert edgar_clean["fundamentals"]["cleaning"]["enabled"] is True
    assert edgar_relative["industry"]["source"] == "industry_master"
    assert "edgar_price_to_sales" in edgar_relative["industry"]["rank_features"]
    assert edgar_repaired_quality["fundamentals"]["field_level_fill"]["enabled"] is True
    assert edgar_repaired_quality["fundamentals"]["coverage_features"]["enabled"] is True
    assert edgar_repaired_quality["fundamentals"]["include_feature_groups"] == [
        "profitability_quality",
        "filing_state",
        "coverage_state",
    ]
    assert edgar_quality_core["edgar_effectiveness_review"]["enabled"] is True
    assert edgar_quality_core["fundamentals"]["enable_valuation"] is False
    assert edgar_repaired_no_valuation["fundamentals"]["enable_valuation"] is False
    assert "valuation" in edgar_repaired_no_valuation["fundamentals"]["drop_feature_groups"]


def test_crsp_edgar_ablation_configs_parse() -> None:
    configs = [
        "drop_valuation",
        "drop_profitability_quality",
        "drop_growth",
        "drop_balance_sheet_stability",
        "drop_filing_state",
    ]
    for name in configs:
        config = load_config(Path(f"analysis/nasdaq_top500_score/configs/crsp_edgar_ablation/{name}.yaml"))
        assert config["fundamentals"]["cleaning"]["enabled"] is True
        assert config["industry"]["source"] == "industry_master"
        assert config["report"]["lightweight"] is True
    drop_valuation = load_config(Path("analysis/nasdaq_top500_score/configs/crsp_edgar_ablation/drop_valuation.yaml"))
    assert "valuation" in drop_valuation["fundamentals"]["drop_feature_groups"]
    assert all("price_to" not in feature for feature in drop_valuation["industry"]["rank_features"])
