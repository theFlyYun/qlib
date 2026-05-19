from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from analysis.nasdaq_top500_score.data_sources.nasdaq_public import nasdaq_history_window
from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import (
    choose_segments,
    load_config,
    prediction_frame_to_series,
    read_test_predictions,
    validate_config,
)


def test_nasdaq_history_window_prefers_fixed_start_and_end_dates() -> None:
    data_config = {
        "source": "nasdaq_public",
        "start_date": "2011-05-17",
        "end_date": "2026-05-17",
        "freq": "day",
        "vwap_method": "ohlc_mean",
    }

    assert nasdaq_history_window(data_config) == ("2011-05-17", "2026-05-17")


def test_date_split_uses_fixed_calendar_segments_and_warmup(tmp_path: Path) -> None:
    qlib_dir = tmp_path / "qlib_data"
    calendar_dir = qlib_dir / "calendars"
    calendar_dir.mkdir(parents=True)
    dates = pd.bdate_range("2020-01-01", periods=320)
    pd.Series(dates.strftime("%Y-%m-%d")).to_csv(calendar_dir / "day.txt", index=False, header=False)
    config = {
        "split": {
            "method": "date",
            "warmup_days": 2,
            "train": {"start": "2020-01-01", "end": "2020-01-06"},
            "valid": {"start": "2020-01-07", "end": "2020-01-08"},
            "test": {"start": "2020-01-09", "end": "2020-01-10"},
        }
    }

    segments = choose_segments(config, {"qlib_dir": qlib_dir})

    assert segments["fit"] == ("2020-01-01", "2020-01-06")
    assert segments["all"] == ("2020-01-01", dates[-1].strftime("%Y-%m-%d"))
    assert segments["train"] == ("2020-01-03", "2020-01-06")
    assert segments["valid"] == ("2020-01-07", "2020-01-08")
    assert segments["test"] == ("2020-01-09", "2020-01-10")


def test_date_split_validation_rejects_overlapping_segments() -> None:
    config = {
        "experiment": {},
        "universe": {"exchange": "NASDAQ"},
        "data": {
            "source": "nasdaq_public",
            "start_date": "2011-05-17",
            "end_date": "2026-05-17",
            "freq": "day",
            "vwap_method": "ohlc_mean",
        },
        "label": {},
        "features": {"handler": "Alpha158"},
        "split": {
            "method": "date",
            "warmup_days": 60,
            "train": {"start": "2020-01-01", "end": "2020-12-31"},
            "valid": {"start": "2020-12-31", "end": "2021-12-31"},
            "test": {"start": "2022-01-01", "end": "2022-12-31"},
        },
        "model": {"class": "LGBModel"},
        "report": {},
    }

    with pytest.raises(ValueError, match="train.end must be before valid.start"):
        validate_config(config)


def test_fixed_15y_configs_parse() -> None:
    for path in [
        Path("analysis/nasdaq_top500_score/configs/nasdaq_alpha158_lgbm_15y_fixed.yaml"),
        Path("analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_15y_smoke.yaml"),
    ]:
        config = load_config(path)
        assert config["data"]["start_date"] == "2011-05-17"
        assert config["data"]["end_date"] == "2026-05-17"
        assert config["split"]["method"] == "date"


def test_frozen_2023_config_parses_and_selects_before_test_window() -> None:
    config = load_config(
        Path("analysis/nasdaq_top500_score/configs/nasdaq_alpha158_edgar_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml")
    )

    assert config["universe"]["selection"]["method"] == "approximate_market_cap_asof"
    assert config["universe"]["selection"]["as_of_date"] == "2023-12-31"
    assert config["split"]["test"]["start"] == "2024-01-01"
    assert config["training"]["seed"] == 20260519
    assert config["training"]["deterministic"] is True
    assert config["model"]["kwargs"]["seed"] == 20260519
    assert config["model"]["kwargs"]["deterministic"] is True


def test_training_control_validation_rejects_reuse_non_boolean() -> None:
    config = {
        "experiment": {},
        "universe": {"exchange": "NASDAQ"},
        "data": {
            "source": "nasdaq_public",
            "lookback_days": 10,
            "freq": "day",
            "vwap_method": "ohlc_mean",
        },
        "label": {},
        "features": {"handler": "Alpha158"},
        "split": {"method": "ratio", "train_ratio": 0.6, "valid_ratio": 0.2, "test_ratio": 0.2},
        "model": {"class": "LGBModel"},
        "report": {},
        "training": {"seed": 7, "deterministic": True, "reuse_test_predictions": "yes"},
    }

    with pytest.raises(ValueError, match="training.reuse_test_predictions"):
        validate_config(config)


def test_cached_test_predictions_are_normalized_and_convert_to_series(tmp_path: Path) -> None:
    path = tmp_path / "test_predictions.csv"
    pd.DataFrame(
        [
            {"datetime": "2024-01-02 15:30:00", "instrument": "aapl", "score": "0.12"},
            {"datetime": "2024-01-03 15:30:00", "instrument": "msft", "score": "0.34"},
        ]
    ).to_csv(path, index=False)

    frame = read_test_predictions(path)
    series = prediction_frame_to_series(frame)

    assert frame["datetime"].dt.strftime("%Y-%m-%d").tolist() == ["2024-01-02", "2024-01-03"]
    assert frame["instrument"].tolist() == ["AAPL", "MSFT"]
    assert series.index.names == ["datetime", "instrument"]
    assert series.loc[(pd.Timestamp("2024-01-02"), "AAPL")] == 0.12
