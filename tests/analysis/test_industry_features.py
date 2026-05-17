from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from analysis.nasdaq_top500_score.industry.features import build_industry_features, build_symbol_industry_map
from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import combine_alpha_and_feature_frames_raw


def make_config() -> dict[str, Any]:
    return {
        "industry": {
            "enabled": True,
            "source": "universe",
            "group_level": "industry",
            "fallback_group_level": "sector",
            "min_group_size": 2,
            "rank_features": ["edgar_roe", "edgar_price_to_sales"],
        }
    }


def make_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "industry_features": tmp_path / "industry_features.parquet",
        "industry_failures": tmp_path / "industry_failures.csv",
    }


def make_universe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"symbol": "AAA", "sector": "Technology", "industry": "Software"},
            {"symbol": "BBB", "sector": "Technology", "industry": "Software"},
            {"symbol": "CCC", "sector": "Technology", "industry": "Hardware"},
            {"symbol": "DDD", "sector": "Financial Services", "industry": "Banks"},
            {"symbol": "EEE", "sector": "", "industry": None},
        ]
    )


def make_base_features() -> pd.DataFrame:
    index = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2024-01-02"), "AAA"),
            (pd.Timestamp("2024-01-02"), "BBB"),
            (pd.Timestamp("2024-01-02"), "CCC"),
            (pd.Timestamp("2024-01-02"), "DDD"),
            (pd.Timestamp("2024-01-02"), "EEE"),
        ],
        names=["datetime", "instrument"],
    )
    return pd.DataFrame(
        {
            "edgar_roe": [0.20, 0.10, 0.30, 0.05, 0.90],
            "edgar_price_to_sales": [5.0, 3.0, 8.0, 2.0, 1.0],
        },
        index=index,
    )


def test_symbol_to_sector_and_industry_mapping() -> None:
    mapped = build_symbol_industry_map(make_universe()).set_index("symbol")

    assert mapped.loc["AAA", "sector"] == "Technology"
    assert mapped.loc["AAA", "industry"] == "Software"
    assert pd.isna(mapped.loc["EEE", "sector"])
    assert pd.isna(mapped.loc["EEE", "industry"])


def test_industry_percentile_uses_same_industry_and_sector_fallback(tmp_path: Path) -> None:
    result = build_industry_features(make_universe(), make_config(), make_paths(tmp_path), make_base_features())
    features = result.features

    aaa_key = (pd.Timestamp("2024-01-02"), "AAA")
    bbb_key = (pd.Timestamp("2024-01-02"), "BBB")
    ccc_key = (pd.Timestamp("2024-01-02"), "CCC")

    assert features.loc[aaa_key, "industry_pct_roe"] == 1.0
    assert features.loc[bbb_key, "industry_pct_roe"] == 0.5
    assert features.loc[ccc_key, "industry_used_sector_fallback"] == 1.0
    assert features.loc[ccc_key, "sector_pct_roe"] == 1.0
    assert features.loc[ccc_key, "sector_group_size"] == 3

    failures = result.failures.set_index(["symbol", "error"])
    assert ("EEE", "missing_industry_classification") in failures.index
    assert (tmp_path / "industry_features.parquet").exists()
    assert (tmp_path / "industry_failures.csv").exists()


def test_missing_rank_feature_is_recorded(tmp_path: Path) -> None:
    config = make_config()
    config["industry"]["rank_features"] = ["edgar_roe", "edgar_missing_metric"]

    result = build_industry_features(make_universe(), config, make_paths(tmp_path), make_base_features())

    failures = result.failures.set_index(["error", "detail"])
    assert ("missing_rank_feature", "edgar_missing_metric") in failures.index
    assert "industry_pct_missing_metric" in result.features.columns


def test_combined_frame_keeps_alpha_fundamental_industry_and_label_groups() -> None:
    index = pd.MultiIndex.from_tuples(
        [(pd.Timestamp("2024-01-02"), "AAA")],
        names=["datetime", "instrument"],
    )
    alpha_raw = pd.concat(
        {
            "feature": pd.DataFrame({"KMID": [0.1]}, index=index),
            "label": pd.DataFrame({"LABEL0": [0.02]}, index=index),
        },
        axis=1,
    )
    fundamentals = pd.DataFrame({"edgar_roe": [0.2]}, index=index)
    industry = pd.DataFrame({"industry_pct_roe": [pd.NA]}, index=index)

    combined = combine_alpha_and_feature_frames_raw(alpha_raw, [fundamentals, industry])

    assert ("feature", "KMID") in combined.columns
    assert ("feature", "edgar_roe") in combined.columns
    assert ("feature", "industry_pct_roe") in combined.columns
    assert ("label", "LABEL0") in combined.columns
    assert pd.isna(combined.loc[(pd.Timestamp("2024-01-02"), "AAA"), ("feature", "industry_pct_roe")])
    assert combined["feature"].dtypes["industry_pct_roe"].kind == "f"
