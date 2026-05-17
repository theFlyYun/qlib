"""Clean stock pools and allocate ranked predictions by history bucket."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

BUCKET_ORDER = ["full_10y", "5_10y", "2_5y", "lt_2y"]
DEFAULT_BUCKET_THRESHOLDS = {
    "full_10y": 2400,
    "5_10y": 1260,
    "2_5y": 504,
    "lt_2y": 180,
}
DEFAULT_EXCLUDE_NAME_PATTERNS = {
    "warrant": r"\bwarrants?\b",
    "right": r"\brights?\b",
    "unit": r"\bunits?\b",
    "preferred": r"\bpreferred\b|\bpreference\b",
    "notes": r"\bnotes?\b",
    "bond": r"\bbonds?\b",
    "debenture": r"\bdebentures?\b",
}
DEFAULT_EXCLUDE_SYMBOL_REGEXES = [r".*W$", r".*WS$", r".*WT$", r".*WW$"]
UNIVERSE_EXCLUSION_COLUMNS = ["symbol", "name", "market_cap", "exclusion_reason"]
HISTORY_BUCKET_COLUMNS = ["symbol", "history_rows", "first_date", "last_date", "history_bucket"]


def clean_stock_universe(
    universe: pd.DataFrame,
    universe_config: dict[str, Any],
    output_path: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    filter_config = universe_config.get("security_filter", {})
    if not filter_config.get("enabled", False):
        exclusions = pd.DataFrame(columns=UNIVERSE_EXCLUSION_COLUMNS)
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            exclusions.to_csv(output_path, index=False)
        return universe.copy(), exclusions

    rows = []
    keep_mask = []
    for row in universe.itertuples(index=False):
        data = row._asdict()
        reason = security_exclusion_reason(data, filter_config)
        keep_mask.append(reason is None)
        if reason is not None:
            rows.append(
                {
                    "symbol": data.get("symbol"),
                    "name": data.get("name"),
                    "market_cap": data.get("market_cap"),
                    "exclusion_reason": reason,
                }
            )

    cleaned = universe.loc[keep_mask].copy()
    exclusions = pd.DataFrame(rows, columns=UNIVERSE_EXCLUSION_COLUMNS)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        exclusions.to_csv(output_path, index=False)
    return cleaned, exclusions


def security_exclusion_reason(row: dict[str, Any], filter_config: dict[str, Any]) -> str | None:
    symbol = str(row.get("symbol") or "").upper()
    name = str(row.get("name") or "").lower()

    for label, pattern in DEFAULT_EXCLUDE_NAME_PATTERNS.items():
        if re.search(pattern, name, flags=re.IGNORECASE):
            return f"name:{label}"

    if "depositary shares" in name and "american depositary shares" not in name:
        return "name:depositary_shares"

    for pattern in filter_config.get("exclude_symbol_regexes", DEFAULT_EXCLUDE_SYMBOL_REGEXES):
        if re.fullmatch(pattern, symbol, flags=re.IGNORECASE):
            return f"symbol:{pattern}"

    return None


def build_history_buckets(source_dir: Path, output_path: Path, config: dict[str, Any]) -> pd.DataFrame:
    bucket_config = config.get("history_buckets", {})
    if not bucket_config.get("enabled", False):
        frame = pd.DataFrame(columns=HISTORY_BUCKET_COLUMNS)
        frame.to_csv(output_path, index=False)
        return frame

    rows = []
    for csv_path in sorted(source_dir.glob("*.csv")):
        symbol = csv_path.stem.upper()
        price = pd.read_csv(csv_path, usecols=["date"])
        dates = pd.to_datetime(price["date"], errors="coerce").dropna().sort_values()
        if dates.empty:
            continue
        history_rows = int(len(dates))
        rows.append(
            {
                "symbol": symbol,
                "history_rows": history_rows,
                "first_date": dates.iloc[0].date().isoformat(),
                "last_date": dates.iloc[-1].date().isoformat(),
                "history_bucket": assign_history_bucket(history_rows, bucket_config),
            }
        )

    frame = pd.DataFrame(rows, columns=HISTORY_BUCKET_COLUMNS).sort_values(["history_bucket", "symbol"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    return frame


def assign_history_bucket(history_rows: int, bucket_config: dict[str, Any]) -> str:
    thresholds = {**DEFAULT_BUCKET_THRESHOLDS, **bucket_config.get("thresholds", {})}
    for bucket in BUCKET_ORDER:
        if history_rows >= int(thresholds[bucket]):
            return bucket
    return "below_minimum"


def apply_bucket_ranking(
    predictions: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    ranking_config = config.get("bucket_ranking", {})
    if not ranking_config.get("enabled", False):
        top_n = int(config["report"]["top_n"])
        return predictions.head(top_n).copy(), {
            "bucket_ranking_enabled": False,
            "bucket_counts": {},
            "bucket_quotas": {},
            "selected_bucket_counts": {},
            "industry_constraints_enabled": False,
            "industry_constraints": {},
            "selected_sector_counts": {},
            "selected_industry_counts": {},
        }

    history = pd.read_csv(paths["history_buckets_csv"])
    ranked = predictions.merge(history, on="symbol", how="left")
    ranked["history_bucket"] = ranked["history_bucket"].fillna("missing_history")
    ranked["global_rank"] = range(1, len(ranked) + 1)
    ranked["bucket_rank"] = ranked.groupby("history_bucket")["score"].rank(method="first", ascending=False).astype(int)
    ranked.to_csv(paths["bucketed_predictions_csv"], index=False)

    industry_constraints = config.get("industry_constraints", {})
    selected = select_bucketed_top(ranked, ranking_config, int(config["report"]["top_n"]), industry_constraints)
    selected.to_csv(paths["selected_top10_csv"], index=False)

    return selected, {
        "bucket_ranking_enabled": True,
        "bucket_counts": ranked["history_bucket"].value_counts().to_dict(),
        "bucket_quotas": normalized_quotas(ranking_config),
        "selected_bucket_counts": selected["history_bucket"].value_counts().to_dict(),
        "industry_constraints_enabled": bool(industry_constraints.get("enabled", False)),
        "industry_constraints": industry_constraints if industry_constraints.get("enabled", False) else {},
        "selected_sector_counts": normalized_group_counts(selected, "sector"),
        "selected_industry_counts": normalized_group_counts(selected, "industry"),
    }


def select_bucketed_top(
    predictions: pd.DataFrame,
    ranking_config: dict[str, Any],
    top_n: int,
    industry_constraints: dict[str, Any] | None = None,
) -> pd.DataFrame:
    quotas = normalized_quotas(ranking_config)
    selected_parts = []
    selected_symbols: set[str] = set()
    selected_rows: list[pd.Series] = []
    industry_constraints = industry_constraints or {}

    for bucket in BUCKET_ORDER:
        quota = int(quotas.get(bucket, 0))
        candidates = bucket_candidates(predictions, bucket, selected_symbols)
        chosen = choose_with_constraints(candidates, quota, selected_rows, industry_constraints)
        selected_parts.append(chosen)
        selected_symbols.update(chosen["symbol"].astype(str))
        selected_rows.extend(row for _, row in chosen.iterrows())

    selected = pd.concat(selected_parts, ignore_index=True) if selected_parts else predictions.head(0).copy()
    shortfall = top_n - len(selected)
    if shortfall > 0:
        for bucket in ranking_config.get("refill_order", BUCKET_ORDER):
            if shortfall <= 0:
                break
            candidates = bucket_candidates(predictions, bucket, selected_symbols)
            chosen = choose_with_constraints(candidates, shortfall, selected_rows, industry_constraints)
            if chosen.empty:
                continue
            selected = pd.concat([selected, chosen], ignore_index=True)
            selected_symbols.update(chosen["symbol"].astype(str))
            selected_rows.extend(row for _, row in chosen.iterrows())
            shortfall = top_n - len(selected)

    selected = selected.sort_values("score", ascending=False).head(top_n).reset_index(drop=True)
    selected["selected_rank"] = range(1, len(selected) + 1)
    return selected


def choose_with_constraints(
    candidates: pd.DataFrame,
    limit: int,
    selected_rows: list[pd.Series],
    industry_constraints: dict[str, Any],
) -> pd.DataFrame:
    if limit <= 0 or candidates.empty:
        return candidates.head(0).copy()

    chosen = []
    for _, row in candidates.iterrows():
        if violates_industry_constraints(row, [*selected_rows, *chosen], industry_constraints):
            continue
        chosen.append(row)
        if len(chosen) >= limit:
            break
    if not chosen:
        return candidates.head(0).copy()
    return pd.DataFrame(chosen)


def violates_industry_constraints(
    candidate: pd.Series,
    selected_rows: list[pd.Series],
    industry_constraints: dict[str, Any],
) -> bool:
    if not industry_constraints.get("enabled", False):
        return False

    max_sector = industry_constraints.get("max_sector")
    max_industry = industry_constraints.get("max_industry")
    sector = group_value(candidate, "sector")
    industry = group_value(candidate, "industry")

    if max_sector is not None and sector is not None:
        sector_count = sum(1 for row in selected_rows if group_value(row, "sector") == sector)
        if sector_count >= int(max_sector):
            return True
    if max_industry is not None and industry is not None:
        industry_count = sum(1 for row in selected_rows if group_value(row, "industry") == industry)
        if industry_count >= int(max_industry):
            return True
    return False


def group_value(row: pd.Series, column: str) -> str | None:
    if column not in row:
        return None
    value = row.get(column)
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def normalized_group_counts(frame: pd.DataFrame, column: str) -> dict[str, int]:
    if column not in frame:
        return {}
    values = frame[column].map(
        lambda value: "UNKNOWN" if pd.isna(value) or not str(value).strip() else str(value).strip()
    )
    return values.value_counts().to_dict()


def bucket_candidates(predictions: pd.DataFrame, bucket: str, selected_symbols: set[str]) -> pd.DataFrame:
    candidates = predictions[predictions["history_bucket"] == bucket].copy()
    if selected_symbols:
        candidates = candidates[~candidates["symbol"].astype(str).isin(selected_symbols)]
    return candidates.sort_values("score", ascending=False)


def normalized_quotas(ranking_config: dict[str, Any]) -> dict[str, int]:
    return {bucket: int(value) for bucket, value in ranking_config.get("quotas", {}).items()}
