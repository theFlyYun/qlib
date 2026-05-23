from __future__ import annotations

from pathlib import Path

import pandas as pd

from analysis.nasdaq_top500_score.macro_interactions import build_macro_interaction_frame


def make_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "macro_interaction_features": tmp_path / "macro_interaction_features.parquet",
        "macro_interaction_failures": tmp_path / "macro_interaction_failures.csv",
    }


def make_index() -> pd.MultiIndex:
    return pd.MultiIndex.from_product(
        [[pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")], ["AAA", "BBB"]],
        names=["datetime", "instrument"],
    )


def test_macro_interactions_cross_macro_with_stock_level_features(tmp_path: Path) -> None:
    index = make_index()
    universe = pd.DataFrame(
        [
            {"symbol": "AAA", "sector": "Technology"},
            {"symbol": "BBB", "sector": "Finance"},
        ]
    )
    macro = pd.DataFrame(
        {
            "macro_vix_zscore_60d": [2.0, 2.0, 3.0, 3.0],
            "macro_yield_curve_10y_2y_inverted": [1.0, 1.0, 0.0, 0.0],
        },
        index=index,
    )
    market = pd.DataFrame({"market_sector_pct_momentum_20d": [0.4, 0.2, 0.1, 0.5]}, index=index)
    fundamental = pd.DataFrame({"edgar_price_to_sales": [10.0, 5.0, 8.0, 4.0]}, index=index)
    config = {
        "macro_interactions": {
            "enabled": True,
            "interactions": [
                {
                    "name": "macro_x_vix_momentum",
                    "left": "macro_vix_zscore_60d",
                    "right": "market_sector_pct_momentum_20d",
                },
                {
                    "name": "macro_x_curve_finance",
                    "left": "macro_yield_curve_10y_2y_inverted",
                    "sector": "Finance",
                },
            ],
        }
    }

    result = build_macro_interaction_frame(
        universe,
        config,
        make_paths(tmp_path),
        macro_features=macro,
        market_features=market,
        fundamental_features=fundamental,
    )

    assert result.features.loc[(pd.Timestamp("2024-01-02"), "AAA"), "macro_x_vix_momentum"] == 0.8
    assert result.features.loc[(pd.Timestamp("2024-01-02"), "BBB"), "macro_x_vix_momentum"] == 0.4
    assert result.features.loc[(pd.Timestamp("2024-01-02"), "AAA"), "macro_x_curve_finance"] == 0.0
    assert result.features.loc[(pd.Timestamp("2024-01-02"), "BBB"), "macro_x_curve_finance"] == 1.0
    assert result.failures.empty
    assert (tmp_path / "macro_interaction_features.parquet").exists()


def test_macro_interactions_records_missing_inputs(tmp_path: Path) -> None:
    index = make_index()
    macro = pd.DataFrame({"macro_vix_zscore_60d": [1.0, 1.0, 1.0, 1.0]}, index=index)
    config = {
        "macro_interactions": {
            "enabled": True,
            "interactions": [
                {
                    "name": "missing_right",
                    "left": "macro_vix_zscore_60d",
                    "right": "market_missing",
                },
                {
                    "name": "missing_left",
                    "left": "macro_missing",
                    "right": "macro_vix_zscore_60d",
                },
            ],
        }
    }

    result = build_macro_interaction_frame(
        pd.DataFrame([{"symbol": "AAA", "sector": "Technology"}]),
        config,
        make_paths(tmp_path),
        macro_features=macro,
        market_features=None,
        fundamental_features=None,
    )

    assert result.features.empty
    assert set(result.failures["error"]) == {"missing_left", "missing_right"}


def test_crsp_macro_interactions_generate_eight_market_only_features(tmp_path: Path) -> None:
    index = make_index()
    universe = pd.DataFrame([{"symbol": "AAA"}, {"symbol": "BBB"}])
    macro = pd.DataFrame(
        {
            "macro_vix_zscore_60d": [1.0, 1.0, 2.0, 2.0],
            "macro_vix_change_20d": [0.2, 0.2, 0.3, 0.3],
            "macro_dgs10": [4.0, 4.0, 4.1, 4.1],
            "macro_dgs10_change_20d": [0.1, 0.1, 0.2, 0.2],
            "macro_yield_curve_10y_2y_inverted": [0.0, 0.0, 1.0, 1.0],
            "macro_baa10y_credit_spread_change_20d": [0.05, 0.05, 0.07, 0.07],
            "macro_broad_dollar_index_pct_change_20d": [0.01, 0.01, -0.02, -0.02],
            "macro_wti_oil_pct_change_20d": [0.03, 0.03, 0.04, 0.04],
        },
        index=index,
    )
    market = pd.DataFrame(
        {
            "market_momentum_20d": [0.10, 0.20, 0.30, 0.40],
            "market_volatility_20d": [0.15, 0.25, 0.35, 0.45],
            "market_momentum_60d": [0.11, 0.21, 0.31, 0.41],
            "market_volatility_60d": [0.16, 0.26, 0.36, 0.46],
            "market_momentum_120d": [0.12, 0.22, 0.32, 0.42],
        },
        index=index,
    )
    config = {
        "macro_interactions": {
            "enabled": True,
            "interactions": [
                {"name": "vix_z_mom20", "left": "macro_vix_zscore_60d", "right": "market_momentum_20d"},
                {"name": "vix_chg_vol20", "left": "macro_vix_change_20d", "right": "market_volatility_20d"},
                {"name": "rate_mom60", "left": "macro_dgs10", "right": "market_momentum_60d"},
                {"name": "rate_chg_vol20", "left": "macro_dgs10_change_20d", "right": "market_volatility_20d"},
                {"name": "curve_mom120", "left": "macro_yield_curve_10y_2y_inverted", "right": "market_momentum_120d"},
                {
                    "name": "credit_chg_vol60",
                    "left": "macro_baa10y_credit_spread_change_20d",
                    "right": "market_volatility_60d",
                },
                {
                    "name": "dollar_chg_mom60",
                    "left": "macro_broad_dollar_index_pct_change_20d",
                    "right": "market_momentum_60d",
                },
                {"name": "oil_chg_mom20", "left": "macro_wti_oil_pct_change_20d", "right": "market_momentum_20d"},
            ],
        }
    }

    result = build_macro_interaction_frame(
        universe,
        config,
        make_paths(tmp_path),
        macro_features=macro,
        market_features=market,
        fundamental_features=None,
    )

    assert result.features.shape[1] == 8
    assert result.failures.empty
    assert result.features.loc[(pd.Timestamp("2024-01-02"), "AAA"), "vix_z_mom20"] == 0.10


def test_crsp_macro_interactions_tolerate_numeric_sector_values(tmp_path: Path) -> None:
    index = pd.MultiIndex.from_product(
        [[pd.Timestamp("2024-01-02")], ["AAA", "BBB"]],
        names=["datetime", "instrument"],
    )
    universe = pd.DataFrame([{"symbol": "AAA", "sector": 7371}, {"symbol": "BBB", "sector": 3841}])
    macro = pd.DataFrame({"macro_vix_change_20d": [1.0, 2.0]}, index=index)
    market = pd.DataFrame({"market_volatility_20d": [0.1, 0.2]}, index=index)
    config = {
        "macro_interactions": {
            "enabled": True,
            "interactions": [
                {
                    "name": "macro_x_vix_change_volatility_20d",
                    "left": "macro_vix_change_20d",
                    "right": "market_volatility_20d",
                }
            ],
        }
    }

    result = build_macro_interaction_frame(
        universe,
        config,
        make_paths(tmp_path),
        macro_features=macro,
        market_features=market,
        fundamental_features=None,
    )

    assert result.failures.empty
    assert list(result.features["macro_x_vix_change_volatility_20d"]) == [0.1, 0.4]
