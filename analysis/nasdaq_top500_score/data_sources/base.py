"""Shared helpers for experiment data source adapters."""

from __future__ import annotations

import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

QLIB_SOURCE_COLUMNS = ["date", "symbol", "open", "high", "low", "close", "vwap", "volume"]
FAILURE_COLUMNS = ["symbol", "rows", "error"]


class DataSourceUnavailable(RuntimeError):
    """Raised when an optional data vendor is not available in this environment."""


@dataclass
class PreparedData:
    universe: pd.DataFrame
    failures: pd.DataFrame
    metadata: dict[str, Any] = field(default_factory=dict)


def reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def empty_failures() -> pd.DataFrame:
    return pd.DataFrame(columns=FAILURE_COLUMNS)


def write_failures(path: Path, failures: list[dict[str, Any]] | pd.DataFrame) -> pd.DataFrame:
    if isinstance(failures, pd.DataFrame):
        frame = failures.copy()
    else:
        frame = pd.DataFrame(failures, columns=FAILURE_COLUMNS)
    for column in FAILURE_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    frame = frame[FAILURE_COLUMNS]
    frame.to_csv(path, index=False)
    return frame


def parse_float(value: Any) -> float:
    if value is None:
        return math.nan
    text = str(value).replace("$", "").replace(",", "").strip()
    if not text or text in {"--", "N/A"}:
        return math.nan
    try:
        return float(text)
    except ValueError:
        return math.nan


def normalize_date_column(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    if "date" not in working.columns:
        candidates = [column for column in working.columns if str(column).lower() in {"date", "datetime", "timestamp"}]
        if candidates:
            working = working.rename(columns={candidates[0]: "date"})
        else:
            working = working.reset_index()
            candidates = [
                column
                for column in working.columns
                if str(column).lower() in {"date", "datetime", "timestamp", "index"}
            ]
            if candidates:
                working = working.rename(columns={candidates[0]: "date"})
    if "date" not in working.columns:
        raise ValueError("missing date column")
    working["date"] = pd.to_datetime(working["date"]).dt.date.astype(str)
    return working


def normalize_ohlcv_frame(frame: pd.DataFrame, symbol: str, *, vwap_method: str) -> pd.DataFrame:
    if frame.empty:
        raise ValueError("no price rows")
    if vwap_method != "ohlc_mean":
        raise ValueError(f"unsupported vwap_method: {vwap_method}")

    working = normalize_date_column(frame)
    rename_map = {}
    for column in working.columns:
        key = str(column).strip().lower().replace(" ", "").replace("_", "")
        if key in {"open"}:
            rename_map[column] = "open"
        elif key in {"high"}:
            rename_map[column] = "high"
        elif key in {"low"}:
            rename_map[column] = "low"
        elif key in {"close"}:
            rename_map[column] = "close"
        elif key in {"volume", "vol"}:
            rename_map[column] = "volume"
        elif key in {"vwap"}:
            rename_map[column] = "vwap"
    working = working.rename(columns=rename_map)

    required = ["open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in working.columns]
    if missing:
        raise ValueError(f"missing OHLCV column(s): {', '.join(missing)}")

    for column in required:
        working[column] = pd.to_numeric(working[column], errors="coerce")
    working = working.dropna(subset=required)
    if "vwap" not in working.columns:
        working["vwap"] = working[["open", "high", "low", "close"]].mean(axis=1)
    else:
        working["vwap"] = pd.to_numeric(working["vwap"], errors="coerce")
        working["vwap"] = working["vwap"].fillna(working[["open", "high", "low", "close"]].mean(axis=1))

    working["symbol"] = symbol
    return working[QLIB_SOURCE_COLUMNS].sort_values("date").reset_index(drop=True)
