"""CRSP SIC/NAICS coverage checks before using industry-aware strategies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

try:
    from .data_sources.crsp import sic_industry, sic_sector
except ImportError:  # pragma: no cover - supports script-style imports.
    from data_sources.crsp import sic_industry, sic_sector


@dataclass
class IndustryValidationResult:
    summary: dict[str, Any]
    checks: pd.DataFrame


def run_crsp_industry_validation(
    config: dict[str, Any],
    paths: dict[str, Path],
    prepared: Any,
) -> IndustryValidationResult:
    validation_config = config.get("industry_validation", {})
    if config.get("data", {}).get("source") != "crsp" or not validation_config.get("enabled", False):
        summary = {"enabled": False}
        empty = pd.DataFrame()
        write_outputs(paths, summary, empty, empty, empty, empty)
        return IndustryValidationResult(summary=summary, checks=empty)

    industry_master = read_optional_parquet(paths.get("industry_master"))
    if not industry_master.empty:
        membership = membership_from_industry_master(industry_master)
        monthly = monthly_coverage(membership)
        annual = annual_coverage(monthly)
        rebalance = rebalance_coverage(membership, config, paths)
        checks, summary = build_summary(
            config,
            validation_config,
            membership,
            annual,
            rebalance,
            fallback_to_security_master=False,
            source_counts=industry_source_counts(industry_master),
        )
        summary["source"] = "industry_master"
        write_outputs(paths, summary, checks, monthly, annual, rebalance)
        return IndustryValidationResult(summary=summary, checks=checks)

    membership = read_optional_csv(paths["membership_csv"])
    security_master = read_optional_csv(paths["security_master_csv"])
    fallback_to_security_master = "siccd" not in membership.columns and not security_master.empty
    membership = enrich_membership_with_industry(membership, security_master)

    monthly = monthly_coverage(membership)
    annual = annual_coverage(monthly)
    rebalance = rebalance_coverage(membership, config, paths)
    checks, summary = build_summary(
        config,
        validation_config,
        membership,
        annual,
        rebalance,
        fallback_to_security_master=fallback_to_security_master,
        source_counts={},
    )
    write_outputs(paths, summary, checks, monthly, annual, rebalance)
    return IndustryValidationResult(summary=summary, checks=checks)


def membership_from_industry_master(industry_master: pd.DataFrame) -> pd.DataFrame:
    frame = industry_master.copy()
    for column in ["effective_start", "effective_end"]:
        frame[column] = pd.to_datetime(frame[column], errors="coerce").dt.normalize()
    frame["symbol"] = frame["instrument"].astype(str).str.upper()
    frame["siccd"] = frame["raw_siccd"]
    frame["naics"] = frame["raw_naics"]
    frame["icb_industry"] = pd.NA
    frame["valid_sic2"] = frame["is_pit"].eq(True) & frame["sector"].ne("UNKNOWN")
    frame["valid_sic4"] = frame["is_pit"].eq(True) & frame["industry"].ne("UNKNOWN")
    frame["valid_naics"] = frame["is_pit"].eq(True) & frame["naics"].map(valid_naics)
    frame["valid_icb"] = False
    return frame


def industry_source_counts(industry_master: pd.DataFrame) -> dict[str, int]:
    if industry_master.empty:
        return {}
    return {
        "crsp_pit_rows": int(industry_master["source"].eq("crsp_monthly_row").sum()),
        "edgar_fallback_rows": int(industry_master["source"].eq("sec_edgar_sic").sum()),
        "unknown_rows": int(industry_master["sector"].eq("UNKNOWN").sum()),
        "non_pit_or_unverified_rows": int((~industry_master["is_pit"].eq(True) & industry_master["sector"].ne("UNKNOWN")).sum()),
    }


def enrich_membership_with_industry(membership: pd.DataFrame, security_master: pd.DataFrame) -> pd.DataFrame:
    if membership.empty:
        return membership
    working = membership.copy()
    if "symbol" not in working and "instrument" in working:
        working["symbol"] = working["instrument"]
    working["symbol"] = working["symbol"].astype(str).str.upper()
    if "siccd" not in working and not security_master.empty:
        master = security_master.copy()
        if "instrument" in master:
            master["symbol"] = master["instrument"].astype(str).str.upper()
        master_columns = [column for column in ["symbol", "siccd", "naics", "icb_industry"] if column in master.columns]
        if "symbol" in master_columns:
            working = working.merge(master[master_columns].drop_duplicates("symbol"), on="symbol", how="left")
    if "siccd" not in working:
        working["siccd"] = pd.NA
    if "naics" not in working:
        working["naics"] = pd.NA
    if "icb_industry" not in working:
        working["icb_industry"] = pd.NA
    working["sector"] = working["siccd"].map(sic_sector)
    working["industry"] = working["siccd"].map(sic_industry)
    working["valid_sic2"] = working["sector"].ne("UNKNOWN")
    working["valid_sic4"] = working["industry"].ne("UNKNOWN")
    working["valid_naics"] = working["naics"].map(valid_naics)
    working["valid_icb"] = working["icb_industry"].map(valid_icb)
    for column in ["month_end_date", "effective_start", "effective_end"]:
        if column in working:
            working[column] = pd.to_datetime(working[column], errors="coerce").dt.normalize()
    return working


def valid_naics(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    text = str(value).strip()
    if "." in text:
        text = text.split(".", 1)[0]
    digits = "".join(ch for ch in text if ch.isdigit())
    return bool(digits) and int(digits) != 0


def valid_icb(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    text = str(value).strip().upper()
    return bool(text) and text not in {"0", "NAN", "NONE", "NOAVAIL", "UNKNOWN"}


def monthly_coverage(membership: pd.DataFrame) -> pd.DataFrame:
    if membership.empty:
        return pd.DataFrame()
    date_column = "effective_start" if "effective_start" in membership else "month_end_date"
    frame = membership.copy()
    frame[date_column] = pd.to_datetime(frame[date_column], errors="coerce").dt.normalize()
    grouped = frame.dropna(subset=[date_column]).groupby(date_column)
    rows = []
    for date, group in grouped:
        rows.append(coverage_row(date, group))
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def annual_coverage(monthly: pd.DataFrame) -> pd.DataFrame:
    if monthly.empty:
        return pd.DataFrame()
    frame = monthly.copy()
    frame["year"] = pd.to_datetime(frame["date"]).dt.year
    return (
        frame.groupby("year", as_index=False)
        .agg(
            month_count=("date", "count"),
            min_sic2_coverage=("sic2_coverage", "min"),
            avg_sic2_coverage=("sic2_coverage", "mean"),
            min_sic4_coverage=("sic4_coverage", "min"),
            avg_sic4_coverage=("sic4_coverage", "mean"),
            min_naics_coverage=("naics_coverage", "min"),
            avg_naics_coverage=("naics_coverage", "mean"),
        )
        .sort_values("year")
        .reset_index(drop=True)
    )


def rebalance_coverage(membership: pd.DataFrame, config: dict[str, Any], paths: dict[str, Path]) -> pd.DataFrame:
    if membership.empty or "effective_start" not in membership or "effective_end" not in membership:
        return pd.DataFrame()
    split = config.get("split", {})
    if split.get("method") != "date":
        return pd.DataFrame()
    test_start = pd.Timestamp(split["test"]["start"]).normalize()
    test_end = pd.Timestamp(split["test"]["end"]).normalize()
    rebalance_days = int(config.get("backtest", {}).get("rebalance_days", 10))
    calendar = collect_source_calendar(paths.get("source_dir"))
    dates = [date for date in calendar if test_start <= date <= test_end]
    if not dates:
        dates = list(pd.date_range(test_start, test_end, freq=f"{rebalance_days}B"))
    rows = []
    for signal_date in dates[::rebalance_days]:
        active = membership[
            (membership["effective_start"] <= signal_date)
            & (membership["effective_end"].isna() | (membership["effective_end"] >= signal_date))
        ]
        if active.empty:
            continue
        row = coverage_row(signal_date, active)
        row["signal_date"] = row.pop("date")
        rows.append(row)
    return pd.DataFrame(rows).sort_values("signal_date").reset_index(drop=True)


def collect_source_calendar(source_dir: Path | None) -> list[pd.Timestamp]:
    if source_dir is None or not source_dir.exists():
        return []
    dates: set[pd.Timestamp] = set()
    for csv_path in sorted(source_dir.glob("*.csv")):
        try:
            frame = pd.read_csv(csv_path, usecols=["date"])
        except (ValueError, FileNotFoundError):
            continue
        dates.update(pd.to_datetime(frame["date"], errors="coerce").dt.normalize().dropna().tolist())
    return sorted(dates)


def coverage_row(date: Any, group: pd.DataFrame) -> dict[str, Any]:
    total = int(len(group))
    return {
        "date": pd.Timestamp(date).date().isoformat(),
        "sample_count": total,
        "sic2_valid_count": int(group["valid_sic2"].sum()),
        "sic4_valid_count": int(group["valid_sic4"].sum()),
        "naics_valid_count": int(group["valid_naics"].sum()),
        "icb_valid_count": int(group["valid_icb"].sum()),
        "sic2_coverage": ratio(group["valid_sic2"].sum(), total),
        "sic4_coverage": ratio(group["valid_sic4"].sum(), total),
        "naics_coverage": ratio(group["valid_naics"].sum(), total),
        "icb_coverage": ratio(group["valid_icb"].sum(), total),
        "unknown_sic2_count": int(total - group["valid_sic2"].sum()),
    }


def build_summary(
    config: dict[str, Any],
    validation_config: dict[str, Any],
    membership: pd.DataFrame,
    annual: pd.DataFrame,
    rebalance: pd.DataFrame,
    *,
    fallback_to_security_master: bool,
    source_counts: dict[str, int],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    train_start = pd.Timestamp(config["split"]["train"]["start"]).year
    train_end = pd.Timestamp(config["split"]["train"]["end"]).year
    train_annual = annual[(annual["year"] >= train_start) & (annual["year"] <= train_end)] if not annual.empty else annual
    min_train = float(train_annual["min_sic2_coverage"].min()) if not train_annual.empty else 0.0
    min_rebalance = float(rebalance["sic2_coverage"].min()) if not rebalance.empty else 0.0
    train_threshold = float(validation_config.get("min_train_annual_sic2_coverage", 0.80))
    rebalance_threshold = float(validation_config.get("min_test_rebalance_sic2_coverage", 0.85))
    train_pass = min_train >= train_threshold
    rebalance_pass = min_rebalance >= rebalance_threshold
    enabled_for_strategy = bool(train_pass and rebalance_pass)
    checks = pd.DataFrame(
        [
            {
                "check_id": "I1",
                "area": "industry_coverage",
                "status": "pass" if train_pass else "fail",
                "threshold": train_threshold,
                "observed": min_train,
                "finding": "训练期年度 SIC2 覆盖率满足阈值" if train_pass else "训练期年度 SIC2 覆盖率不足",
            },
            {
                "check_id": "I2",
                "area": "industry_coverage",
                "status": "pass" if rebalance_pass else "fail",
                "threshold": rebalance_threshold,
                "observed": min_rebalance,
                "finding": "测试期调仓日 SIC2 覆盖率满足阈值" if rebalance_pass else "测试期调仓日 SIC2 覆盖率不足",
            },
        ]
    )
    summary = {
        "enabled": True,
        "source": validation_config.get("source", "crsp_sic_naics"),
        "sector_definition": "SIC 2-digit",
        "industry_definition": "SIC 4-digit",
        "membership_rows": int(len(membership)),
        "fallback_to_security_master": bool(fallback_to_security_master),
        "crsp_pit_rows": int(source_counts.get("crsp_pit_rows", int(membership["valid_sic2"].sum()) if "valid_sic2" in membership else 0)),
        "edgar_fallback_rows": int(source_counts.get("edgar_fallback_rows", 0)),
        "unknown_rows": int(source_counts.get("unknown_rows", int((~membership["valid_sic2"]).sum()) if "valid_sic2" in membership else 0)),
        "non_pit_or_unverified_rows": int(source_counts.get("non_pit_or_unverified_rows", 0)),
        "train_min_annual_sic2_coverage": min_train,
        "test_min_rebalance_sic2_coverage": min_rebalance,
        "min_train_annual_sic2_coverage_required": train_threshold,
        "min_test_rebalance_sic2_coverage_required": rebalance_threshold,
        "industry_features_allowed": enabled_for_strategy,
        "industry_constraints_allowed": enabled_for_strategy,
        "conclusion": "industry_pit_validation_pass" if enabled_for_strategy else "industry_review_only_until_coverage_improves",
    }
    return checks, summary


def write_outputs(
    paths: dict[str, Path],
    summary: dict[str, Any],
    checks: pd.DataFrame,
    monthly: pd.DataFrame,
    annual: pd.DataFrame,
    rebalance: pd.DataFrame,
) -> None:
    checks.to_csv(paths["crsp_industry_validation"], index=False)
    monthly.to_csv(paths["crsp_industry_coverage_by_month"], index=False)
    annual.to_csv(paths["crsp_industry_coverage_by_year"], index=False)
    rebalance.to_csv(paths["crsp_industry_coverage_by_rebalance"], index=False)
    paths["crsp_industry_validation_summary"].write_text(
        yaml.safe_dump(summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def read_optional_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def read_optional_parquet(path: Path | None) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except (OSError, ValueError):
        return pd.DataFrame()


def ratio(numerator: Any, denominator: Any) -> float:
    denominator = int(denominator)
    if denominator == 0:
        return 0.0
    return float(numerator) / denominator
