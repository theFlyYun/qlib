from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from analysis.nasdaq_top500_score.market_features import build_market_feature_frame
from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import combine_alpha_and_feature_frames_raw, load_config


def write_price_csv(source_dir: Path, symbol: str, dates: pd.DatetimeIndex, close: list[float], volume: list[int]) -> None:
    pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "symbol": symbol,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "vwap": close,
            "volume": volume,
        }
    ).to_csv(source_dir / f"{symbol}.csv", index=False)


def make_config() -> dict[str, Any]:
    return {
        "market_features": {
            "enabled": True,
            "source": "qlib_source_csv",
            "group_levels": ["sector", "industry"],
            "min_group_size": 2,
            "dollar_volume_windows": [2],
            "momentum_windows": [2],
            "volatility_windows": [2],
            "relative_features": [
                "log_avg_dollar_volume_2d",
                "momentum_2d",
                "volatility_2d",
                "history_rows_asof",
            ],
        }
    }


def make_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "source_dir": tmp_path / "qlib_source_csv",
        "market_features": tmp_path / "market_features.parquet",
        "market_feature_failures": tmp_path / "market_feature_failures.csv",
    }


def make_universe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"symbol": "AAA", "sector": "Technology", "industry": "Software"},
            {"symbol": "BBB", "sector": "Technology", "industry": "Software"},
            {"symbol": "CCC", "sector": "Technology", "industry": "Hardware"},
        ]
    )


def test_market_features_are_point_in_time_and_ranked_within_sector_and_industry(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    source_dir = paths["source_dir"]
    source_dir.mkdir()
    dates = pd.bdate_range("2024-01-02", periods=4)
    write_price_csv(source_dir, "AAA", dates, [10, 11, 12, 13], [100, 100, 100, 100])
    write_price_csv(source_dir, "BBB", dates, [10, 10, 10, 10], [10, 10, 10, 10])
    write_price_csv(source_dir, "CCC", dates, [20, 20, 20, 20], [100, 100, 100, 100])

    result = build_market_feature_frame(make_universe(), make_config(), paths)
    features = result.features
    key = (pd.Timestamp("2024-01-04"), "AAA")
    peer_key = (pd.Timestamp("2024-01-04"), "BBB")
    single_industry_key = (pd.Timestamp("2024-01-04"), "CCC")

    assert round(float(features.loc[key, "market_momentum_2d"]), 6) == 0.2
    assert pd.isna(features.loc[(pd.Timestamp("2024-01-03"), "AAA"), "market_momentum_2d"])
    assert features.loc[key, "market_sector_pct_momentum_2d"] == 1.0
    assert features.loc[peer_key, "market_sector_pct_momentum_2d"] == 0.5
    assert features.loc[key, "market_industry_pct_log_avg_dollar_volume_2d"] == 1.0
    assert pd.isna(features.loc[single_industry_key, "market_industry_pct_momentum_2d"])
    assert paths["market_features"].exists()
    assert paths["market_feature_failures"].exists()


def test_market_features_merge_with_alpha_feature_group(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    source_dir = paths["source_dir"]
    source_dir.mkdir()
    dates = pd.bdate_range("2024-01-02", periods=4)
    write_price_csv(source_dir, "AAA", dates, [10, 11, 12, 13], [100, 100, 100, 100])
    result = build_market_feature_frame(
        pd.DataFrame([{"symbol": "AAA", "sector": "Technology", "industry": "Software"}]),
        make_config(),
        paths,
    )
    index = pd.MultiIndex.from_tuples(
        [(pd.Timestamp("2024-01-04"), "AAA")],
        names=["datetime", "instrument"],
    )
    alpha_raw = pd.concat(
        {
            "feature": pd.DataFrame({"KMID": [0.1]}, index=index),
            "label": pd.DataFrame({"LABEL0": [0.02]}, index=index),
        },
        axis=1,
    )

    combined = combine_alpha_and_feature_frames_raw(alpha_raw, [result.features])

    assert ("feature", "KMID") in combined.columns
    assert ("feature", "market_momentum_2d") in combined.columns
    assert ("label", "LABEL0") in combined.columns


def test_frozen_config_enables_market_relative_features() -> None:
    config = load_config(
        Path("analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml")
    )

    assert config["market_features"]["enabled"] is True
    assert "sector" in config["market_features"]["group_levels"]
    assert "momentum_60d" in config["market_features"]["relative_features"]
