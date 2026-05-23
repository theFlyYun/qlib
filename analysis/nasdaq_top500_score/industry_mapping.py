"""Build PIT-oriented industry mappings for CRSP dynamic universes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

try:
    from .data_sources.crsp import INDUSTRY_SCHEMA_VERSION, sic_industry, sic_sector
except ImportError:  # pragma: no cover - supports script-style imports.
    from data_sources.crsp import INDUSTRY_SCHEMA_VERSION, sic_industry, sic_sector


INDUSTRY_MASTER_COLUMNS = [
    "instrument",
    "permno",
    "effective_start",
    "effective_end",
    "sector_scheme",
    "sector",
    "industry_scheme",
    "industry",
    "raw_siccd",
    "raw_naics",
    "source",
    "is_pit",
    "confidence",
    "evidence_date",
]


@dataclass
class IndustryMappingResult:
    summary: dict[str, Any]
    master: pd.DataFrame
    coverage: pd.DataFrame
    failures: pd.DataFrame


def build_industry_mapping(config: dict[str, Any], paths: dict[str, Path]) -> IndustryMappingResult:
    mapping_config = config.get("industry_mapping", {})
    if config.get("data", {}).get("source") != "crsp" or not mapping_config.get("enabled", False):
        summary = {"enabled": False}
        empty = pd.DataFrame()
        write_industry_mapping_outputs(paths, summary, empty, empty, empty)
        return IndustryMappingResult(summary=summary, master=empty, coverage=empty, failures=empty)

    membership = read_optional_csv(paths["membership_csv"])
    edgar_fallback = load_edgar_sic_fallback(mapping_config, paths)
    master = build_master_from_membership(membership, mapping_config, edgar_fallback)
    coverage = build_coverage(master)
    failures = build_failures(master)
    summary = build_summary(config, mapping_config, master, coverage, edgar_fallback)
    write_industry_mapping_outputs(paths, summary, master, coverage, failures)
    return IndustryMappingResult(summary=summary, master=master, coverage=coverage, failures=failures)


def build_master_from_membership(
    membership: pd.DataFrame,
    mapping_config: dict[str, Any],
    edgar_fallback: pd.DataFrame,
) -> pd.DataFrame:
    if membership.empty:
        return pd.DataFrame(columns=INDUSTRY_MASTER_COLUMNS)
    frame = membership.copy()
    if "instrument" not in frame and "symbol" in frame:
        frame["instrument"] = frame["symbol"]
    if "symbol" not in frame and "instrument" in frame:
        frame["symbol"] = frame["instrument"]
    for column in ["siccd", "naics", "icb_industry", "permno", "effective_start", "effective_end", "month_end_date"]:
        if column not in frame:
            frame[column] = pd.NA
    for column in ["effective_start", "effective_end", "month_end_date"]:
        frame[column] = pd.to_datetime(frame[column], errors="coerce").dt.normalize()

    fallback_by_key = prepare_edgar_fallback_lookup(edgar_fallback)
    rows: list[dict[str, Any]] = []
    for row in frame.to_dict("records"):
        instrument = str(row.get("instrument") or row.get("symbol")).upper()
        permno = nullable_int(row.get("permno"))
        effective_start = pd.Timestamp(row.get("effective_start")).normalize() if pd.notna(row.get("effective_start")) else pd.NaT
        effective_end = pd.Timestamp(row.get("effective_end")).normalize() if pd.notna(row.get("effective_end")) else pd.NaT
        raw_sic = row.get("siccd")
        sector = sic_sector(raw_sic)
        industry = sic_industry(raw_sic)
        source = "crsp_monthly_row" if sector != "UNKNOWN" else "unknown"
        is_pit = bool(sector != "UNKNOWN")
        confidence = 1.0 if is_pit else 0.0
        evidence_date = row.get("month_end_date")
        raw_naics = row.get("naics")

        if sector == "UNKNOWN":
            fallback = find_edgar_fallback(fallback_by_key, instrument, permno, effective_start)
            if fallback:
                raw_sic = fallback.get("siccd")
                sector = sic_sector(raw_sic)
                industry = sic_industry(raw_sic)
                raw_naics = fallback.get("naics", raw_naics)
                source = "sec_edgar_sic"
                is_pit = bool(fallback.get("is_pit", False))
                confidence = float(fallback.get("confidence", 0.4))
                evidence_date = fallback.get("evidence_date")
                if sector == "UNKNOWN":
                    source = "unknown"
                    is_pit = False
                    confidence = 0.0

        rows.append(
            {
                "instrument": instrument,
                "permno": permno,
                "effective_start": format_date(effective_start),
                "effective_end": format_date(effective_end),
                "sector_scheme": str(mapping_config.get("sector_scheme", "sic2")),
                "sector": sector,
                "industry_scheme": str(mapping_config.get("industry_scheme", "sic4")),
                "industry": industry,
                "raw_siccd": normalize_raw(raw_sic),
                "raw_naics": normalize_raw(raw_naics),
                "source": source,
                "is_pit": bool(is_pit),
                "confidence": confidence,
                "evidence_date": format_date(evidence_date),
            }
        )
    return pd.DataFrame(rows, columns=INDUSTRY_MASTER_COLUMNS)


def load_edgar_sic_fallback(mapping_config: dict[str, Any], paths: dict[str, Path]) -> pd.DataFrame:
    configured = mapping_config.get("edgar_sic_map_path")
    if configured:
        path = Path(str(configured)).expanduser()
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
    else:
        path = paths.get("edgar_sic_map")
    if path is None or not path.exists() or path.is_dir():
        return pd.DataFrame()
    if path.suffix.lower() == ".parquet":
        frame = pd.read_parquet(path)
    else:
        frame = pd.read_csv(path)
    if frame.empty:
        return frame
    normalized = frame.copy()
    rename_map = {
        "symbol": "instrument",
        "ticker": "ticker_asof",
        "sic": "siccd",
        "sec_sic": "siccd",
        "date": "evidence_date",
        "filed": "evidence_date",
        "acceptanceDateTime": "evidence_date",
    }
    normalized = normalized.rename(columns={key: value for key, value in rename_map.items() if key in normalized.columns})
    if "siccd" not in normalized:
        return pd.DataFrame()
    if "evidence_date" not in normalized:
        normalized["evidence_date"] = pd.NaT
    if "is_pit" not in normalized:
        normalized["is_pit"] = False
    if "confidence" not in normalized:
        normalized["confidence"] = 0.4
    if "instrument" in normalized:
        normalized["instrument"] = normalized["instrument"].astype(str).str.upper()
    if "permno" in normalized:
        normalized["permno"] = pd.to_numeric(normalized["permno"], errors="coerce").astype("Int64")
    normalized["evidence_date"] = pd.to_datetime(normalized["evidence_date"], errors="coerce").dt.normalize()
    return normalized


def prepare_edgar_fallback_lookup(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    lookup: dict[str, pd.DataFrame] = {}
    if frame.empty:
        return lookup
    working = frame.copy()
    for column in ["instrument", "permno"]:
        if column not in working:
            continue
        for key, group in working.dropna(subset=[column]).groupby(column):
            lookup[f"{column}:{str(key).upper()}"] = group.sort_values("evidence_date")
    return lookup


def find_edgar_fallback(
    lookup: dict[str, pd.DataFrame],
    instrument: str,
    permno: int | None,
    as_of_date: pd.Timestamp,
) -> dict[str, Any] | None:
    candidates = []
    for key in [f"instrument:{instrument}", f"permno:{permno}" if permno is not None else ""]:
        if key and key in lookup:
            candidates.append(lookup[key])
    if not candidates:
        return None
    frame = pd.concat(candidates, ignore_index=True)
    if pd.notna(as_of_date) and "evidence_date" in frame:
        dated = frame[frame["evidence_date"].notna() & (frame["evidence_date"] <= as_of_date)]
        frame = dated if not dated.empty else frame[frame["evidence_date"].isna()]
    if frame.empty:
        return None
    return frame.sort_values("evidence_date", na_position="first").tail(1).iloc[0].to_dict()


def build_coverage(master: pd.DataFrame) -> pd.DataFrame:
    if master.empty:
        return pd.DataFrame()
    frame = master.copy()
    frame["effective_start"] = pd.to_datetime(frame["effective_start"], errors="coerce").dt.normalize()
    frame["strict_valid_sector"] = frame["is_pit"].eq(True) & frame["sector"].ne("UNKNOWN")
    frame["display_valid_sector"] = frame["sector"].ne("UNKNOWN")
    rows = []
    for date, group in frame.dropna(subset=["effective_start"]).groupby("effective_start"):
        total = int(len(group))
        crsp_pit = int(group["source"].eq("crsp_monthly_row").sum())
        edgar = int(group["source"].eq("sec_edgar_sic").sum())
        unknown = int(group["sector"].eq("UNKNOWN").sum())
        non_pit = int((~group["is_pit"].eq(True) & group["sector"].ne("UNKNOWN")).sum())
        rows.append(
            {
                "date": pd.Timestamp(date).date().isoformat(),
                "sample_count": total,
                "crsp_pit_rows": crsp_pit,
                "edgar_fallback_rows": edgar,
                "unknown_rows": unknown,
                "non_pit_or_unverified_rows": non_pit,
                "strict_sector_valid_count": int(group["strict_valid_sector"].sum()),
                "display_sector_valid_count": int(group["display_valid_sector"].sum()),
                "strict_sector_coverage": ratio(group["strict_valid_sector"].sum(), total),
                "display_sector_coverage": ratio(group["display_valid_sector"].sum(), total),
            }
        )
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def build_failures(master: pd.DataFrame) -> pd.DataFrame:
    if master.empty:
        return pd.DataFrame(columns=["instrument", "permno", "effective_start", "source", "reason"])
    failed = master[master["sector"].eq("UNKNOWN") | ~master["is_pit"].eq(True)].copy()
    if failed.empty:
        return pd.DataFrame(columns=["instrument", "permno", "effective_start", "source", "reason"])
    failed["reason"] = "missing_industry" 
    failed.loc[failed["sector"].ne("UNKNOWN") & ~failed["is_pit"].eq(True), "reason"] = "non_pit_or_unverified_fallback"
    return failed[["instrument", "permno", "effective_start", "source", "reason"]].reset_index(drop=True)


def build_summary(
    config: dict[str, Any],
    mapping_config: dict[str, Any],
    master: pd.DataFrame,
    coverage: pd.DataFrame,
    edgar_fallback: pd.DataFrame,
) -> dict[str, Any]:
    train_threshold = float(mapping_config.get("min_train_annual_sector_coverage", 0.80))
    test_threshold = float(mapping_config.get("min_test_rebalance_sector_coverage", 0.85))
    annual = annual_min_coverage(coverage)
    train_start = pd.Timestamp(config["split"]["train"]["start"]).year
    train_end = pd.Timestamp(config["split"]["train"]["end"]).year
    train_annual = annual[(annual["year"] >= train_start) & (annual["year"] <= train_end)] if not annual.empty else annual
    train_min = float(train_annual["min_strict_sector_coverage"].min()) if not train_annual.empty else 0.0
    test_start = pd.Timestamp(config["split"]["test"]["start"]).normalize()
    test_end = pd.Timestamp(config["split"]["test"]["end"]).normalize()
    test_coverage = coverage.copy()
    if not test_coverage.empty:
        test_coverage["_date"] = pd.to_datetime(test_coverage["date"], errors="coerce").dt.normalize()
        test_coverage = test_coverage[(test_coverage["_date"] >= test_start) & (test_coverage["_date"] <= test_end)]
    test_min = float(test_coverage["strict_sector_coverage"].min()) if not test_coverage.empty else 0.0
    crsp_pit_rows = int(master["source"].eq("crsp_monthly_row").sum()) if not master.empty else 0
    edgar_rows = int(master["source"].eq("sec_edgar_sic").sum()) if not master.empty else 0
    unknown_rows = int(master["sector"].eq("UNKNOWN").sum()) if not master.empty else 0
    non_pit_rows = int((~master["is_pit"].eq(True) & master["sector"].ne("UNKNOWN")).sum()) if not master.empty else 0
    pass_thresholds = bool(train_min >= train_threshold and test_min >= test_threshold)
    return {
        "enabled": True,
        "schema_version": int(mapping_config.get("schema_version", INDUSTRY_SCHEMA_VERSION)),
        "primary_source": mapping_config.get("primary_source", "crsp_monthly_row"),
        "fallbacks": mapping_config.get("fallbacks", []),
        "sector_scheme": mapping_config.get("sector_scheme", "sic2"),
        "industry_scheme": mapping_config.get("industry_scheme", "sic4"),
        "rows": int(len(master)),
        "crsp_pit_rows": crsp_pit_rows,
        "edgar_fallback_rows": edgar_rows,
        "unknown_rows": unknown_rows,
        "non_pit_or_unverified_rows": non_pit_rows,
        "edgar_fallback_records_available": int(len(edgar_fallback)),
        "train_min_annual_strict_sector_coverage": train_min,
        "test_min_strict_sector_coverage": test_min,
        "min_train_annual_sector_coverage_required": train_threshold,
        "min_test_rebalance_sector_coverage_required": test_threshold,
        "industry_features_allowed": pass_thresholds,
        "industry_constraints_allowed": pass_thresholds,
        "conclusion": "industry_mapping_pass" if pass_thresholds else "industry_review_only_until_coverage_improves",
    }


def annual_min_coverage(coverage: pd.DataFrame) -> pd.DataFrame:
    if coverage.empty:
        return pd.DataFrame()
    frame = coverage.copy()
    frame["year"] = pd.to_datetime(frame["date"], errors="coerce").dt.year
    return (
        frame.dropna(subset=["year"])
        .groupby("year", as_index=False)
        .agg(
            month_count=("date", "count"),
            min_strict_sector_coverage=("strict_sector_coverage", "min"),
            avg_strict_sector_coverage=("strict_sector_coverage", "mean"),
            min_display_sector_coverage=("display_sector_coverage", "min"),
            avg_display_sector_coverage=("display_sector_coverage", "mean"),
        )
    )


def write_industry_mapping_outputs(
    paths: dict[str, Path],
    summary: dict[str, Any],
    master: pd.DataFrame,
    coverage: pd.DataFrame,
    failures: pd.DataFrame,
) -> None:
    paths["industry_master"].parent.mkdir(parents=True, exist_ok=True)
    if master.empty:
        master = pd.DataFrame(columns=INDUSTRY_MASTER_COLUMNS)
    master.to_parquet(paths["industry_master"], index=False)
    coverage.to_csv(paths["industry_mapping_coverage"], index=False)
    failures.to_csv(paths["industry_mapping_failures"], index=False)
    paths["industry_mapping_summary"].write_text(
        yaml.safe_dump(summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def read_optional_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def ratio(numerator: Any, denominator: Any) -> float:
    denominator = int(denominator)
    return 0.0 if denominator == 0 else float(numerator) / denominator


def nullable_int(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def normalize_raw(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text or None


def format_date(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).date().isoformat()
