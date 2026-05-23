"""Small file-based caches for reusable experiment artifacts."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


def stable_hash(payload: dict[str, Any], *, length: int = 16) -> str:
    text = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def artifact_cache_enabled(config: dict[str, Any], section_name: str, *, default: bool = False) -> bool:
    section = config.get(section_name, {})
    cache_config = section.get("artifact_cache", {}) if isinstance(section, dict) else {}
    return bool(cache_config.get("enabled", default))


def artifact_cache_dir(config: dict[str, Any], paths: dict[str, Path], section_name: str) -> Path:
    section = config.get(section_name, {})
    cache_config = section.get("artifact_cache", {}) if isinstance(section, dict) else {}
    configured = cache_config.get("dir")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        return path
    return paths["output_dir"].parents[0] / "feature_cache" / section_name


def copy_to_cache(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def read_cached_feature_result(
    *,
    features_path: Path,
    failures_path: Path,
    coverage_path: Path,
    failure_columns: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]] | None:
    if not features_path.exists() or not failures_path.exists() or not coverage_path.exists():
        return None
    features = pd.read_parquet(features_path)
    failures = pd.read_csv(failures_path)
    for column in failure_columns:
        if column not in failures.columns:
            failures[column] = None
    coverage = yaml.safe_load(coverage_path.read_text(encoding="utf-8")) or {}
    coverage["cache_hit"] = True
    return features, failures[failure_columns], coverage


def write_cached_feature_result(
    *,
    features_source: Path,
    failures_source: Path,
    coverage: dict[str, Any],
    features_path: Path,
    failures_path: Path,
    coverage_path: Path,
) -> None:
    features_path.parent.mkdir(parents=True, exist_ok=True)
    copy_to_cache(features_source, features_path)
    copy_to_cache(failures_source, failures_path)
    cached_coverage = dict(coverage)
    cached_coverage["cache_hit"] = False
    coverage_path.write_text(
        yaml.safe_dump(cached_coverage, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
