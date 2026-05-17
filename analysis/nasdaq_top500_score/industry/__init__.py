"""Industry feature builders for Nasdaq/Qlib learning experiments."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .features import IndustryFeatureResult, build_industry_features


def build_industry_feature_frame(
    universe: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
    base_features: pd.DataFrame,
) -> IndustryFeatureResult:
    industry = config.get("industry", {})
    if not industry or not industry.get("enabled", False):
        return IndustryFeatureResult.empty(paths)
    return build_industry_features(universe, config, paths, base_features)


__all__ = ["IndustryFeatureResult", "build_industry_feature_frame", "build_industry_features"]
