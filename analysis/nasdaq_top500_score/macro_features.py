"""FRED/ALFRED macro feature adapter with point-in-time as-of reconstruction."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

try:
    from .data_sources.base import DataSourceUnavailable
except ImportError:  # pragma: no cover - supports running the pipeline as a script.
    from data_sources.base import DataSourceUnavailable


FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_UNAVAILABLE_MESSAGE = (
    "FRED/ALFRED macro features require FRED_API_KEY, for example "
    "`export FRED_API_KEY='your-fred-api-key'`."
)

MACRO_FAILURE_COLUMNS = ["series_id", "name", "error", "detail"]
RAW_OBSERVATION_COLUMNS = ["series_id", "name", "date", "realtime_start", "realtime_end", "value"]
ASOF_OBSERVATION_COLUMNS = [
    "datetime",
    "series_id",
    "name",
    "observation_date",
    "realtime_start",
    "realtime_end",
    "effective_date",
    "value",
    "days_since_release",
    "observation_age_days",
]

DEFAULT_TRANSFORMS = ["level", "change_20d", "change_60d"]
TRANSFORM_WINDOWS = {
    "change_20d": 20,
    "change_60d": 60,
    "change_3m": 63,
    "pct_change_20d": 20,
    "pct_change_60d": 60,
    "yoy": 252,
    "zscore_60d": 60,
}
KNOWN_TRANSFORMS = {"level", *TRANSFORM_WINDOWS}

DEFAULT_SERIES = [
    {"id": "DGS10", "name": "dgs10", "transforms": ["level", "change_20d", "change_60d"]},
    {"id": "DGS2", "name": "dgs2", "transforms": ["level", "change_20d", "change_60d"]},
    {"id": "FEDFUNDS", "name": "fed_funds", "transforms": ["level", "change_3m"]},
    {"id": "CPIAUCSL", "name": "cpi", "transforms": ["level", "yoy", "change_3m"]},
    {"id": "UNRATE", "name": "unemployment", "transforms": ["level", "change_3m"]},
    {"id": "INDPRO", "name": "industrial_production", "transforms": ["level", "yoy", "change_3m"]},
    {"id": "BAA10Y", "name": "baa10y_credit_spread", "transforms": ["level", "change_20d", "change_60d"]},
    {"id": "VIXCLS", "name": "vix", "transforms": ["level", "change_20d", "zscore_60d"]},
    {"id": "DCOILWTICO", "name": "wti_oil", "transforms": ["level", "pct_change_20d", "pct_change_60d"]},
    {"id": "DTWEXBGS", "name": "broad_dollar_index", "transforms": ["level", "pct_change_20d", "pct_change_60d"]},
]

DEFAULT_DERIVED = [
    {
        "name": "yield_curve_10y_2y",
        "operation": "subtract",
        "left": "dgs10",
        "right": "dgs2",
        "transforms": ["level", "change_20d", "change_60d"],
        "inverted_flag": True,
    }
]


@dataclass
class MacroFeatureResult:
    features: pd.DataFrame
    raw_observations: pd.DataFrame
    asof_observations: pd.DataFrame
    failures: pd.DataFrame
    coverage: dict[str, Any]

    @classmethod
    def empty(cls, paths: dict[str, Path]) -> "MacroFeatureResult":
        features = pd.DataFrame()
        raw = pd.DataFrame(columns=RAW_OBSERVATION_COLUMNS)
        asof = pd.DataFrame(columns=ASOF_OBSERVATION_COLUMNS)
        failures = pd.DataFrame(columns=MACRO_FAILURE_COLUMNS)
        if "macro_features" in paths:
            features.to_parquet(paths["macro_features"])
        if "macro_raw_observations" in paths:
            raw.to_parquet(paths["macro_raw_observations"])
        if "macro_asof_observations" in paths:
            asof.to_parquet(paths["macro_asof_observations"])
        if "macro_failures" in paths:
            failures.to_csv(paths["macro_failures"], index=False)
        return cls(features=features, raw_observations=raw, asof_observations=asof, failures=failures, coverage={})


class FredAlfredClient:
    def __init__(self, cache_dir: Path, *, api_key: str | None = None, request_sleep: float = 0.12) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key or os.environ.get("FRED_API_KEY")
        if not self.api_key:
            raise DataSourceUnavailable(FRED_UNAVAILABLE_MESSAGE)
        self.request_sleep = request_sleep

    def observations(
        self,
        series_id: str,
        *,
        observation_start: str,
        observation_end: str,
        realtime_start: str,
        realtime_end: str,
        output_type: int,
    ) -> list[dict[str, Any]]:
        cache_name = (
            f"observations_{series_id}_{observation_start}_{observation_end}_"
            f"{realtime_start}_{realtime_end}_output{output_type}.json"
        )
        cache_path = self.cache_dir / cache_name
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8")).get("observations", [])

        observations: list[dict[str, Any]] = []
        limit = 100000
        offset = 0
        while True:
            params = {
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "observation_start": observation_start,
                "observation_end": observation_end,
                "realtime_start": realtime_start,
                "realtime_end": realtime_end,
                "output_type": str(output_type),
                "limit": str(limit),
                "offset": str(offset),
                "sort_order": "asc",
            }
            response = requests.get(FRED_OBSERVATIONS_URL, params=params, timeout=30)
            response.raise_for_status()
            payload = response.json()
            page = payload.get("observations", [])
            observations.extend(page)
            count = int(payload.get("count", len(observations)))
            offset += len(page)
            if not page or offset >= count:
                break
            time.sleep(self.request_sleep)

        cache_path.write_text(
            json.dumps({"observations": observations}, ensure_ascii=False),
            encoding="utf-8",
        )
        time.sleep(self.request_sleep)
        return observations


def build_macro_feature_frame(
    universe: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
    *,
    client: Any | None = None,
) -> MacroFeatureResult:
    macro_config = config.get("macro_features", {})
    if not macro_config or not macro_config.get("enabled", False):
        return MacroFeatureResult.empty(paths)

    macro_client = client or FredAlfredClient(paths["macro_cache_dir"])
    builder = MacroFeatureBuilder(config, paths, macro_client)
    result = builder.build(universe)
    result.features.to_parquet(paths["macro_features"])
    result.raw_observations.to_parquet(paths["macro_raw_observations"])
    result.asof_observations.to_parquet(paths["macro_asof_observations"])
    result.failures.to_csv(paths["macro_failures"], index=False)
    return result


class MacroFeatureBuilder:
    def __init__(self, config: dict[str, Any], paths: dict[str, Path], client: Any) -> None:
        self.config = config
        self.paths = paths
        self.client = client
        self.macro_config = config.get("macro_features", {})
        self.series_specs = normalize_series_specs(self.macro_config.get("series", DEFAULT_SERIES))
        self.derived_specs = normalize_derived_specs(self.macro_config.get("derived", DEFAULT_DERIVED))
        self.output_type = int(self.macro_config.get("output_type", 4))
        self.effective_lag_trading_days = int(self.macro_config.get("effective_lag_trading_days", 1))
        self.history_buffer_days = int(self.macro_config.get("history_buffer_days", 370))
        self.realtime_start = str(self.macro_config.get("realtime_start", "1776-07-04"))
        self.realtime_end = str(self.macro_config.get("realtime_end", self.config["data"].get("end_date", "9999-12-31")))

    def build(self, universe: pd.DataFrame) -> MacroFeatureResult:
        calendar = load_trading_calendar(self.paths)
        instruments = sorted(universe["symbol"].astype(str).str.upper().dropna().unique())
        if calendar.empty or not instruments:
            return MacroFeatureResult.empty(self.paths)

        raw, failures = self.download_raw_observations()
        asof = build_asof_observations(raw, calendar, self.series_specs, self.effective_lag_trading_days)
        daily_features = build_daily_macro_features(asof, calendar, self.series_specs, self.derived_specs)
        features = broadcast_daily_features(daily_features, instruments)
        failure_frame = pd.DataFrame(failures, columns=MACRO_FAILURE_COLUMNS)
        return MacroFeatureResult(
            features=features,
            raw_observations=raw,
            asof_observations=asof,
            failures=failure_frame,
            coverage={
                "enabled": True,
                "source": self.macro_config.get("source", "fred_alfred"),
                "series_count": len(self.series_specs),
                "derived_count": len(self.derived_specs),
                "raw_observation_count": int(len(raw)),
                "asof_observation_count": int(len(asof)),
                "row_count": int(len(features)),
                "feature_count": int(features.shape[1]),
                "output_type": self.output_type,
                "effective_lag_trading_days": self.effective_lag_trading_days,
                "instrument_count": len(instruments),
            },
        )

    def download_raw_observations(self) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        start = (pd.Timestamp(self.config["data"]["start_date"]) - timedelta(days=self.history_buffer_days)).date().isoformat()
        end = pd.Timestamp(self.config["data"]["end_date"]).date().isoformat()
        frames = []
        failures: list[dict[str, Any]] = []
        for spec in self.series_specs:
            try:
                rows = self.client.observations(
                    spec["id"],
                    observation_start=start,
                    observation_end=end,
                    realtime_start=self.realtime_start,
                    realtime_end=self.realtime_end,
                    output_type=self.output_type,
                )
                frame = parse_observations(rows, spec)
                if frame.empty:
                    failures.append(
                        {
                            "series_id": spec["id"],
                            "name": spec["name"],
                            "error": "empty_observations",
                            "detail": f"{start} to {end}",
                        }
                    )
                    continue
                frames.append(frame)
            except Exception as exc:  # noqa: BLE001 - keep batch ingestion resumable.
                failures.append({"series_id": spec["id"], "name": spec["name"], "error": "api_or_parse_error", "detail": str(exc)})

        if not frames:
            return pd.DataFrame(columns=RAW_OBSERVATION_COLUMNS), failures
        raw = pd.concat(frames, ignore_index=True)
        raw = raw.sort_values(["series_id", "date", "realtime_start"]).reset_index(drop=True)
        return raw[RAW_OBSERVATION_COLUMNS], failures


def parse_observations(rows: list[dict[str, Any]], spec: dict[str, Any]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    for column in ["date", "realtime_start", "realtime_end", "value"]:
        if column not in frame:
            frame[column] = None
    frame["series_id"] = spec["id"]
    frame["name"] = spec["name"]
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce", format="%Y-%m-%d").dt.normalize()
    frame["realtime_start"] = pd.to_datetime(frame["realtime_start"], errors="coerce", format="%Y-%m-%d").dt.normalize()
    frame["realtime_end"] = pd.to_datetime(frame["realtime_end"], errors="coerce", format="%Y-%m-%d").dt.normalize()
    frame["value"] = pd.to_numeric(frame["value"].replace(".", pd.NA), errors="coerce")
    frame = frame.dropna(subset=["date", "realtime_start", "value"]).copy()
    return frame[RAW_OBSERVATION_COLUMNS]


def build_asof_observations(
    raw: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    specs: list[dict[str, Any]],
    effective_lag_trading_days: int,
) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=ASOF_OBSERVATION_COLUMNS)

    records: list[dict[str, Any]] = []
    calendar = pd.DatetimeIndex(pd.to_datetime(calendar).normalize()).drop_duplicates().sort_values()
    for spec in specs:
        series = raw[raw["series_id"] == spec["id"]].copy()
        if series.empty:
            continue
        series["effective_date"] = next_trading_dates(
            pd.to_datetime(series["realtime_start"]).dt.normalize(),
            calendar,
            effective_lag_trading_days,
        )
        series = series.dropna(subset=["effective_date"]).sort_values(["effective_date", "date", "realtime_start"])
        for trading_date in calendar:
            visible = series[series["effective_date"] <= trading_date]
            if visible.empty:
                records.append(empty_asof_record(trading_date, spec))
                continue
            latest_revision_by_observation = visible.drop_duplicates("date", keep="last")
            current = latest_revision_by_observation.loc[latest_revision_by_observation["date"].idxmax()]
            records.append(
                {
                    "datetime": trading_date,
                    "series_id": spec["id"],
                    "name": spec["name"],
                    "observation_date": current["date"],
                    "realtime_start": current["realtime_start"],
                    "realtime_end": current["realtime_end"],
                    "effective_date": current["effective_date"],
                    "value": current["value"],
                    "days_since_release": (trading_date - current["effective_date"]).days,
                    "observation_age_days": (trading_date - current["date"]).days,
                }
            )

    asof = pd.DataFrame(records, columns=ASOF_OBSERVATION_COLUMNS)
    return asof.sort_values(["series_id", "datetime"]).reset_index(drop=True)


def build_daily_macro_features(
    asof: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    series_specs: list[dict[str, Any]],
    derived_specs: list[dict[str, Any]],
) -> pd.DataFrame:
    calendar = pd.DatetimeIndex(pd.to_datetime(calendar).normalize()).drop_duplicates().sort_values()
    daily = pd.DataFrame(index=calendar)
    base_values: dict[str, pd.Series] = {}
    for spec in series_specs:
        name = spec["name"]
        rows = asof[asof["name"] == name].copy()
        if rows.empty:
            series = pd.Series(np.nan, index=calendar)
            days_since = pd.Series(np.nan, index=calendar)
            observation_age = pd.Series(np.nan, index=calendar)
        else:
            rows = rows.set_index("datetime").reindex(calendar)
            series = pd.to_numeric(rows["value"], errors="coerce")
            days_since = pd.to_numeric(rows["days_since_release"], errors="coerce")
            observation_age = pd.to_numeric(rows["observation_age_days"], errors="coerce")
        max_staleness = int(spec.get("max_staleness_days", 370))
        series = series.where(days_since <= max_staleness)
        base_values[name] = series
        daily = append_transforms(daily, name, series, spec.get("transforms", DEFAULT_TRANSFORMS))
        daily[f"macro_days_since_{name}_release"] = days_since
        daily[f"macro_{name}_observation_age_days"] = observation_age

    for spec in derived_specs:
        name = spec["name"]
        left = base_values.get(spec.get("left"))
        right = base_values.get(spec.get("right"))
        if left is None or right is None:
            continue
        if spec.get("operation") == "subtract":
            series = left - right
        else:
            continue
        daily = append_transforms(daily, name, series, spec.get("transforms", DEFAULT_TRANSFORMS))
        if spec.get("inverted_flag", False):
            daily[f"macro_{name}_inverted"] = (series < 0).astype(float).where(series.notna())

    daily.index.name = "datetime"
    return daily.apply(pd.to_numeric, errors="coerce")


def append_transforms(frame: pd.DataFrame, name: str, series: pd.Series, transforms: list[str]) -> pd.DataFrame:
    working = frame.copy()
    if "level" in transforms:
        working[f"macro_{name}"] = series
    for transform in transforms:
        if transform == "level":
            continue
        window = TRANSFORM_WINDOWS[transform]
        if transform.startswith("change_"):
            working[f"macro_{name}_{transform}"] = series - series.shift(window)
        elif transform.startswith("pct_change_") or transform == "yoy":
            working[f"macro_{name}_{transform}"] = series.pct_change(window, fill_method=None)
        elif transform == "zscore_60d":
            rolling = series.rolling(window, min_periods=window)
            working[f"macro_{name}_{transform}"] = (series - rolling.mean()) / rolling.std()
    return working


def broadcast_daily_features(daily: pd.DataFrame, instruments: list[str]) -> pd.DataFrame:
    if daily.empty or not instruments:
        index = pd.MultiIndex.from_arrays([[], []], names=["datetime", "instrument"])
        return pd.DataFrame(columns=daily.columns, index=index)
    dates = pd.DataFrame({"datetime": daily.index})
    values = dates.join(daily.reset_index(drop=True))
    values["_key"] = 1
    symbols = pd.DataFrame({"instrument": instruments, "_key": 1})
    frame = values.merge(symbols, on="_key", how="inner").drop(columns="_key")
    frame = frame.set_index(["datetime", "instrument"]).sort_index()
    return frame.apply(pd.to_numeric, errors="coerce")


def next_trading_dates(source_dates: pd.Series, calendar: pd.DatetimeIndex, lag_days: int) -> pd.Series:
    positions = calendar.searchsorted(pd.to_datetime(source_dates).dt.normalize(), side="right")
    positions = positions + max(lag_days - 1, 0)
    output = [calendar[position] if position < len(calendar) else pd.NaT for position in positions]
    return pd.Series(output, index=source_dates.index)


def empty_asof_record(trading_date: pd.Timestamp, spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "datetime": trading_date,
        "series_id": spec["id"],
        "name": spec["name"],
        "observation_date": pd.NaT,
        "realtime_start": pd.NaT,
        "realtime_end": pd.NaT,
        "effective_date": pd.NaT,
        "value": np.nan,
        "days_since_release": np.nan,
        "observation_age_days": np.nan,
    }


def load_trading_calendar(paths: dict[str, Path]) -> pd.DatetimeIndex:
    calendar_path = paths["qlib_dir"] / "calendars" / "day.txt"
    if calendar_path.exists():
        dates = pd.read_csv(calendar_path, header=None)[0]
        return pd.DatetimeIndex(pd.to_datetime(dates, errors="coerce").dropna().dt.normalize()).sort_values()
    source_dir = paths.get("source_dir")
    dates: list[pd.Timestamp] = []
    if source_dir and source_dir.exists():
        for csv_path in source_dir.glob("*.csv"):
            frame = pd.read_csv(csv_path, usecols=["date"])
            dates.extend(pd.to_datetime(frame["date"], errors="coerce").dropna().dt.normalize().tolist())
    return pd.DatetimeIndex(pd.Series(dates).dropna().drop_duplicates().sort_values()) if dates else pd.DatetimeIndex([])


def normalize_series_specs(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for spec in specs:
        series_id = str(spec["id"]).upper()
        name = str(spec.get("name", series_id.lower())).lower()
        transforms = [str(value) for value in spec.get("transforms", DEFAULT_TRANSFORMS)]
        invalid = set(transforms) - KNOWN_TRANSFORMS
        if invalid:
            raise ValueError(f"macro_features series {series_id} has unsupported transform(s): {', '.join(sorted(invalid))}")
        item = dict(spec)
        item["id"] = series_id
        item["name"] = name
        item["transforms"] = transforms
        normalized.append(item)
    return normalized


def normalize_derived_specs(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for spec in specs:
        transforms = [str(value) for value in spec.get("transforms", DEFAULT_TRANSFORMS)]
        invalid = set(transforms) - KNOWN_TRANSFORMS
        if invalid:
            raise ValueError(f"macro_features derived {spec.get('name')} has unsupported transform(s): {', '.join(sorted(invalid))}")
        item = dict(spec)
        item["name"] = str(item["name"]).lower()
        item["left"] = str(item.get("left", "")).lower()
        item["right"] = str(item.get("right", "")).lower()
        item["transforms"] = transforms
        normalized.append(item)
    return normalized
