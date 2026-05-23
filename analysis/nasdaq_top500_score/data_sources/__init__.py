"""Data source adapters for Nasdaq/Qlib learning experiments."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import DataSourceUnavailable, PreparedData
from .crsp import CRSPDataSource
from .databento import DatabentoDataSource
from .nasdaq_public import NasdaqPublicDataSource
from .norgate import NorgateDataSource
from .sharadar import SharadarDataSource


def create_data_source(
    config: dict[str, Any],
    paths: dict[str, Path],
) -> NasdaqPublicDataSource | NorgateDataSource | SharadarDataSource | DatabentoDataSource | CRSPDataSource:
    source = config["data"]["source"]
    if source == "nasdaq_public":
        return NasdaqPublicDataSource(config, paths)
    if source == "crsp":
        return CRSPDataSource(config, paths)
    if source == "norgate":
        return NorgateDataSource(config, paths)
    if source == "sharadar":
        return SharadarDataSource(config, paths)
    if source == "databento":
        return DatabentoDataSource(config, paths)
    raise ValueError(f"unsupported data.source: {source}")


__all__ = [
    "DataSourceUnavailable",
    "CRSPDataSource",
    "DatabentoDataSource",
    "NorgateDataSource",
    "NasdaqPublicDataSource",
    "PreparedData",
    "SharadarDataSource",
    "create_data_source",
]
