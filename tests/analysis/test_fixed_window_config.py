from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from analysis.nasdaq_top500_score.data_sources.nasdaq_public import nasdaq_history_window
from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import choose_segments, load_config, validate_config


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
