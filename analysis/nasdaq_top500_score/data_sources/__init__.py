"""Data source adapters for Nasdaq/Qlib learning experiments."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import DataSourceUnavailable, PreparedData
from .nasdaq_public import NasdaqPublicDataSource
from .norgate import NorgateDataSource


def create_data_source(config: dict[str, Any], paths: dict[str, Path]) -> NasdaqPublicDataSource | NorgateDataSource:
    source = config["data"]["source"]
    if source == "nasdaq_public":
        return NasdaqPublicDataSource(config, paths)
    if source == "norgate":
        return NorgateDataSource(config, paths)
    raise ValueError(f"unsupported data.source: {source}")


__all__ = [
    "DataSourceUnavailable",
    "NorgateDataSource",
    "NasdaqPublicDataSource",
    "PreparedData",
    "create_data_source",
]
