"""Fundamental data adapters for Nasdaq/Qlib learning experiments."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .sec_edgar import FundamentalDataResult, build_sec_edgar_features


def build_fundamental_features(
    universe: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
    *,
    client: Any | None = None,
) -> FundamentalDataResult:
    fundamentals = config.get("fundamentals", {})
    if not fundamentals or not fundamentals.get("enabled", False):
        return FundamentalDataResult.empty(paths)
    if fundamentals.get("source") == "sec_edgar":
        return build_sec_edgar_features(universe, config, paths, client=client)
    raise ValueError(f"unsupported fundamentals.source: {fundamentals.get('source')}")


__all__ = ["FundamentalDataResult", "build_fundamental_features", "build_sec_edgar_features"]
