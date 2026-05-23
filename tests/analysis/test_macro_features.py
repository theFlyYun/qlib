from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from analysis.nasdaq_top500_score.macro_features import build_macro_feature_frame
from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import combine_alpha_and_feature_frames_raw, load_config


class FakeFredClient:
    def __init__(self, rows_by_series: dict[str, list[dict[str, Any]]]) -> None:
        self.rows_by_series = rows_by_series

    def observations(self, series_id: str, **_: Any) -> list[dict[str, Any]]:
        return self.rows_by_series.get(series_id, [])


def write_calendar(tmp_path: Path, dates: pd.DatetimeIndex) -> dict[str, Path]:
    qlib_dir = tmp_path / "qlib_data"
    calendar_dir = qlib_dir / "calendars"
    calendar_dir.mkdir(parents=True)
    (calendar_dir / "day.txt").write_text("\n".join(dates.strftime("%Y-%m-%d")) + "\n", encoding="utf-8")
    return {
        "qlib_dir": qlib_dir,
        "source_dir": tmp_path / "qlib_source_csv",
        "macro_cache_dir": tmp_path / "fred_alfred_cache",
        "macro_raw_observations": tmp_path / "macro_raw_observations.parquet",
        "macro_asof_observations": tmp_path / "macro_asof_observations.parquet",
        "macro_features": tmp_path / "macro_features.parquet",
        "macro_failures": tmp_path / "macro_failures.csv",
    }


def make_universe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"symbol": "AAA", "sector": "Technology", "industry": "Software"},
            {"symbol": "BBB", "sector": "Health Care", "industry": "Biotech"},
        ]
    )


def make_config(series: list[dict[str, Any]], *, max_staleness_days: int | None = None) -> dict[str, Any]:
    configured = []
    for spec in series:
        item = dict(spec)
        if max_staleness_days is not None:
            item["max_staleness_days"] = max_staleness_days
        configured.append(item)
    return {
        "data": {"start_date": "2024-01-01", "end_date": "2024-03-31"},
        "macro_features": {
            "enabled": True,
            "source": "fred_alfred",
            "output_type": 4,
            "effective_lag_trading_days": 1,
            "history_buffer_days": 0,
            "series": configured,
            "derived": [],
        },
    }


def test_monthly_macro_is_not_visible_until_next_trading_day(tmp_path: Path) -> None:
    dates = pd.bdate_range("2024-02-12", "2024-02-16")
    paths = write_calendar(tmp_path, dates)
    config = make_config([{"id": "CPIAUCSL", "name": "cpi", "transforms": ["level"]}])
    client = FakeFredClient(
        {
            "CPIAUCSL": [
                {"date": "2024-01-01", "realtime_start": "2024-02-13", "realtime_end": "2024-03-11", "value": "100.0"}
            ]
        }
    )

    result = build_macro_feature_frame(make_universe(), config, paths, client=client)
    features = result.features

    assert pd.isna(features.loc[(pd.Timestamp("2024-02-13"), "AAA"), "macro_cpi"])
    assert features.loc[(pd.Timestamp("2024-02-14"), "AAA"), "macro_cpi"] == 100.0
    assert features.loc[(pd.Timestamp("2024-02-14"), "BBB"), "macro_cpi"] == 100.0
    assert paths["macro_asof_observations"].exists()


def test_old_revision_does_not_overwrite_newer_known_observation(tmp_path: Path) -> None:
    dates = pd.bdate_range("2024-03-11", "2024-03-20")
    paths = write_calendar(tmp_path, dates)
    config = make_config([{"id": "CPIAUCSL", "name": "cpi", "transforms": ["level"]}])
    client = FakeFredClient(
        {
            "CPIAUCSL": [
                {"date": "2024-01-01", "realtime_start": "2024-02-13", "realtime_end": "2024-03-14", "value": "100.0"},
                {"date": "2024-02-01", "realtime_start": "2024-03-12", "realtime_end": "9999-12-31", "value": "105.0"},
                {"date": "2024-01-01", "realtime_start": "2024-03-15", "realtime_end": "9999-12-31", "value": "200.0"},
            ]
        }
    )

    result = build_macro_feature_frame(make_universe(), config, paths, client=client)
    features = result.features

    assert features.loc[(pd.Timestamp("2024-03-13"), "AAA"), "macro_cpi"] == 105.0
    assert features.loc[(pd.Timestamp("2024-03-18"), "AAA"), "macro_cpi"] == 105.0


def test_daily_macro_also_lags_one_trading_day(tmp_path: Path) -> None:
    dates = pd.bdate_range("2024-01-02", "2024-01-05")
    paths = write_calendar(tmp_path, dates)
    config = make_config([{"id": "DGS10", "name": "dgs10", "transforms": ["level", "change_20d"]}])
    client = FakeFredClient(
        {
            "DGS10": [
                {"date": "2024-01-02", "realtime_start": "2024-01-02", "realtime_end": "9999-12-31", "value": "4.0"},
                {"date": "2024-01-03", "realtime_start": "2024-01-03", "realtime_end": "9999-12-31", "value": "4.1"},
            ]
        }
    )

    result = build_macro_feature_frame(make_universe(), config, paths, client=client)
    features = result.features

    assert pd.isna(features.loc[(pd.Timestamp("2024-01-02"), "AAA"), "macro_dgs10"])
    assert features.loc[(pd.Timestamp("2024-01-03"), "AAA"), "macro_dgs10"] == 4.0
    assert features.loc[(pd.Timestamp("2024-01-04"), "AAA"), "macro_dgs10"] == 4.1


def test_max_staleness_masks_forward_filled_value(tmp_path: Path) -> None:
    dates = pd.bdate_range("2024-01-02", "2024-01-10")
    paths = write_calendar(tmp_path, dates)
    config = make_config(
        [{"id": "CPIAUCSL", "name": "cpi", "transforms": ["level"]}],
        max_staleness_days=2,
    )
    client = FakeFredClient(
        {
            "CPIAUCSL": [
                {"date": "2023-12-01", "realtime_start": "2024-01-02", "realtime_end": "9999-12-31", "value": "100.0"}
            ]
        }
    )

    result = build_macro_feature_frame(make_universe(), config, paths, client=client)
    features = result.features

    assert features.loc[(pd.Timestamp("2024-01-03"), "AAA"), "macro_cpi"] == 100.0
    assert pd.isna(features.loc[(pd.Timestamp("2024-01-08"), "AAA"), "macro_cpi"])


def test_macro_features_merge_with_alpha_feature_group(tmp_path: Path) -> None:
    dates = pd.bdate_range("2024-01-02", "2024-01-05")
    paths = write_calendar(tmp_path, dates)
    config = make_config([{"id": "DGS10", "name": "dgs10", "transforms": ["level"]}])
    client = FakeFredClient(
        {"DGS10": [{"date": "2024-01-02", "realtime_start": "2024-01-02", "realtime_end": "9999-12-31", "value": "4.0"}]}
    )
    result = build_macro_feature_frame(make_universe().head(1), config, paths, client=client)
    index = pd.MultiIndex.from_tuples([(pd.Timestamp("2024-01-03"), "AAA")], names=["datetime", "instrument"])
    alpha_raw = pd.concat(
        {
            "feature": pd.DataFrame({"KMID": [0.1]}, index=index),
            "label": pd.DataFrame({"LABEL0": [0.02]}, index=index),
        },
        axis=1,
    )

    combined = combine_alpha_and_feature_frames_raw(alpha_raw, [result.features])

    assert ("feature", "KMID") in combined.columns
    assert ("feature", "macro_dgs10") in combined.columns
    assert ("label", "LABEL0") in combined.columns
    assert combined.loc[(pd.Timestamp("2024-01-03"), "AAA"), ("feature", "macro_dgs10")] == 4.0


def test_macro_config_is_parseable() -> None:
    config = load_config(
        Path(
            "analysis/nasdaq_top500_score/configs/"
            "nasdaq_alpha158_edgar_macro_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml"
        )
    )

    assert config["macro_features"]["enabled"] is True
    assert config["macro_features"]["output_type"] == 4
    assert config["training"]["reuse_test_predictions"] is False


def test_macro_interaction_config_is_parseable() -> None:
    config = load_config(
        Path(
            "analysis/nasdaq_top500_score/configs/"
            "nasdaq_alpha158_edgar_macro_interactions_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml"
        )
    )

    assert config["macro_features"]["enabled"] is True
    assert config["macro_features"]["append_to_model"] is False
    assert config["macro_interactions"]["enabled"] is True
    assert config["macro_regime_review"]["enabled"] is True
