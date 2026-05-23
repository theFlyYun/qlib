"""CRSP local daily adapter for dynamic PIT US common equity experiments."""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

try:
    from ..artifact_cache import stable_hash
except ImportError:  # pragma: no cover - supports script-style imports.
    from artifact_cache import stable_hash

from .base import PreparedData, reset_directory, write_failures

CRSP_REQUIRED_COLUMNS = [
    "PERMNO",
    "YYYYMMDD",
    "DlyCalDt",
    "DlyCap",
    "DlyRet",
    "DlyRetx",
    "DlyClose",
    "DlyOpen",
    "DlyHigh",
    "DlyLow",
    "DlyVol",
]

INDUSTRY_SCHEMA_VERSION = 1

CRSP_MONTHLY_MEMBERSHIP_REQUIRED_COLUMNS = [
    "month_end_date",
    "effective_start",
    "effective_end",
    "permno",
    "instrument",
    "symbol",
    "ticker_asof",
    "rank",
    "dlycap",
    "primary_exchange",
    "security_type",
    "security_subtype",
    "trading_status",
    "siccd",
    "naics",
    "icb_industry",
    "sector",
    "industry",
]

CRSP_WAREHOUSE_COLUMNS = [
    "PERMNO",
    "PERMCO",
    "SecInfoStartDt",
    "SecInfoEndDt",
    "SecurityBegDt",
    "SecurityEndDt",
    "SecurityHdrFlg",
    "CUSIP",
    "CUSIP9",
    "CIK",
    "PrimaryExch",
    "ConditionalType",
    "ExchangeTier",
    "TradingStatusFlg",
    "SecurityNm",
    "ShareClass",
    "USIncFlg",
    "IssuerType",
    "SecurityType",
    "SecuritySubType",
    "ShareType",
    "SecurityActiveFlg",
    "DelActionType",
    "DelStatusType",
    "DelReasonType",
    "DelPaymentType",
    "Ticker",
    "TradingSymbol",
    "SICCD",
    "NAICS",
    "ICBIndustry",
    "IssuerNm",
    "YYYYMMDD",
    "DlyCalDt",
    "DlyDelFlg",
    "DlyPrc",
    "DlyCap",
    "DlyRet",
    "DlyRetx",
    "DlyVol",
    "DlyClose",
    "DlyLow",
    "DlyHigh",
    "DlyOpen",
    "ShrOut",
    "ShrAdrFlg",
]

NUMERIC_COLUMNS = [
    "PERMNO",
    "PERMCO",
    "YYYYMMDD",
    "CIK",
    "DlyPrc",
    "DlyCap",
    "DlyRet",
    "DlyRetx",
    "DlyVol",
    "DlyClose",
    "DlyLow",
    "DlyHigh",
    "DlyOpen",
    "ShrOut",
]

SECURITY_MASTER_COLUMNS = [
    "permno",
    "instrument",
    "permco",
    "ticker_asof",
    "trading_symbol_asof",
    "cusip",
    "cusip9",
    "cik",
    "issuer_name",
    "security_name",
    "primary_exchange",
    "security_type",
    "security_subtype",
    "issuer_type",
    "share_type",
    "us_incorporated",
    "siccd",
    "naics",
    "icb_industry",
    "first_date",
    "last_date",
    "security_beg_date",
    "security_end_date",
    "security_active_flag",
    "delisting_reason",
]


@dataclass
class CRSPWarehousePaths:
    root: Path
    daily_dir: Path
    security_master: Path
    monthly_membership: Path
    instrument_map: Path
    returns: Path
    execution_prices: Path
    inventory_report: Path
    inventory_summary: Path


class CRSPDataSource:
    """Prepare Qlib source CSV files from a local CRSP daily Parquet warehouse."""

    def __init__(self, config: dict[str, Any], paths: dict[str, Path]) -> None:
        self.config = config
        self.paths = paths
        self.crsp_config = config.get("crsp", {})
        self.warehouse = crsp_warehouse_paths(resolve_config_path(self.crsp_config["warehouse_dir"]))

    def prepare(self) -> PreparedData:
        ensure_crsp_warehouse(self.config, self.warehouse, self.paths)
        ensure_monthly_membership(self.config, self.warehouse)
        if crsp_prepared_dataset_enabled(self.config):
            return self.prepare_with_dataset_cache()

        return self.build_run_prepared_data(self.paths, metadata_extra={})

    def prepare_with_dataset_cache(self) -> PreparedData:
        prepared_root = crsp_prepared_dataset_root(self.config, self.warehouse)
        prepared_key = crsp_prepared_dataset_key(self.config)
        prepared_dir = prepared_root / prepared_key
        prepared_config = self.config.get("crsp", {}).get("prepared_dataset", {})
        force = bool(prepared_config.get("force_rebuild", False))
        copy_mode = str(prepared_config.get("copy_mode", "symlink"))
        self.paths["prepared_dataset_dir"] = prepared_dir
        self.paths["prepared_qlib_dir"] = prepared_dir / "qlib_data"

        if not prepared_dataset_complete(prepared_dir) or force:
            tmp_dir = prepared_root / f".{prepared_key}.tmp"
            remove_path(tmp_dir)
            tmp_paths = crsp_prepared_paths(self.paths, tmp_dir)
            self.build_run_prepared_data(
                tmp_paths,
                metadata_extra={"prepared_dataset_key": prepared_key, "prepared_dataset_dir": str(prepared_dir)},
            )
            write_prepared_manifest(self.config, tmp_dir, prepared_key)
            remove_path(prepared_dir)
            prepared_root.mkdir(parents=True, exist_ok=True)
            os.replace(tmp_dir, prepared_dir)

        return materialize_prepared_dataset(
            prepared_dir,
            self.paths,
            copy_mode=copy_mode,
            metadata_extra={"prepared_dataset_key": prepared_key, "prepared_dataset_dir": str(prepared_dir)},
        )

    def build_run_prepared_data(self, output_paths: dict[str, Path], *, metadata_extra: dict[str, Any]) -> PreparedData:
        source_dir = self.paths["source_dir"]
        if output_paths is not self.paths:
            source_dir = output_paths["source_dir"]
        reset_directory(source_dir)

        membership = pd.read_parquet(self.warehouse.monthly_membership)
        membership = filter_membership_to_data_window(membership, self.config)
        membership.to_csv(output_paths["membership_csv"], index=False)
        security_master = read_optional_parquet(self.warehouse.security_master)
        universe = build_universe_from_membership(membership, security_master)
        universe.to_csv(output_paths["universe_csv"], index=False)
        membership.to_csv(output_paths["universe_candidates_csv"], index=False)
        membership.to_csv(output_paths["universe_selection_csv"], index=False)
        security_master.to_csv(output_paths["security_master_csv"], index=False)
        copy_inventory_report(self.warehouse, output_paths)

        failures = write_crsp_qlib_source_csv(self.config, self.warehouse, membership, source_dir)
        failures_frame = write_failures(output_paths["failures_csv"], failures)

        metadata = {
            "source": "crsp",
            "warehouse_dir": str(self.warehouse.root),
            "membership": str(self.warehouse.monthly_membership),
            "price_adjustment": self.config["data"].get("price_adjustment", "crsp_ret_adjusted"),
            "dynamic_membership": True,
        }
        metadata.update(metadata_extra)
        return PreparedData(
            universe=universe,
            failures=failures_frame,
            metadata=metadata,
        )


def crsp_label_column(label_horizon: int) -> str:
    return f"label_{int(label_horizon)}d_total_return"


def resolve_config_path(path_text: str | Path) -> Path:
    path = Path(path_text).expanduser()
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[3] / path


def crsp_warehouse_paths(root: Path) -> CRSPWarehousePaths:
    return CRSPWarehousePaths(
        root=root,
        daily_dir=root / "crsp_daily",
        security_master=root / "crsp_security_master.parquet",
        monthly_membership=root / "crsp_monthly_top500_membership.parquet",
        instrument_map=root / "crsp_instrument_map.parquet",
        returns=root / "crsp_returns.parquet",
        execution_prices=root / "crsp_execution_prices.parquet",
        inventory_report=root / "crsp_inventory_report.md",
        inventory_summary=root / "crsp_inventory_summary.yaml",
    )


def crsp_prepared_dataset_enabled(config: dict[str, Any]) -> bool:
    prepared = config.get("crsp", {}).get("prepared_dataset", {})
    return bool(prepared.get("enabled", True))


def crsp_prepared_dataset_root(config: dict[str, Any], warehouse: CRSPWarehousePaths) -> Path:
    prepared = config.get("crsp", {}).get("prepared_dataset", {})
    configured = prepared.get("root_dir")
    if configured:
        return resolve_config_path(configured)
    return warehouse.root.parent / "crsp_prepared_datasets"


def crsp_prepared_dataset_key(config: dict[str, Any]) -> str:
    crsp_config = config.get("crsp", {})
    industry_mapping = config.get("industry_mapping", {})
    payload = {
        "data": {
            key: config.get("data", {}).get(key)
            for key in ["source", "start_date", "end_date", "freq", "price_adjustment", "vwap_method"]
        },
        "universe": {
            key: config.get("universe", {}).get(key)
            for key in ["provider", "mode", "top_n_by_market_cap", "min_history_rows"]
        },
        "crsp": {
            key: crsp_config.get(key)
            for key in [
                "raw_csv_path",
                "warehouse_dir",
                "label_horizon_days",
                "label_only_member_dates",
                "major_exchanges",
                "exclude_name_terms",
            ]
        },
        "industry_mapping": {
            "schema_version": industry_mapping.get("schema_version", INDUSTRY_SCHEMA_VERSION),
            "enabled": industry_mapping.get("enabled", False),
            "primary_source": industry_mapping.get("primary_source"),
            "fallbacks": industry_mapping.get("fallbacks", []),
            "sector_scheme": industry_mapping.get("sector_scheme"),
            "industry_scheme": industry_mapping.get("industry_scheme"),
        },
    }
    return f"crsp_{stable_hash(payload)}"


def crsp_prepared_paths(base_paths: dict[str, Path], prepared_dir: Path) -> dict[str, Path]:
    paths = dict(base_paths)
    paths.update(
        {
            "output_dir": prepared_dir,
            "source_dir": prepared_dir / "qlib_source_csv",
            "qlib_dir": prepared_dir / "qlib_data",
            "universe_csv": prepared_dir / "universe.csv",
            "universe_candidates_csv": prepared_dir / "universe_candidates.csv",
            "universe_selection_csv": prepared_dir / "universe_selection.csv",
            "universe_exclusions_csv": prepared_dir / "universe_exclusions.csv",
            "security_master_csv": prepared_dir / "security_master.csv",
            "security_master_exclusions_csv": prepared_dir / "security_master_exclusions.csv",
            "failures_csv": prepared_dir / "download_failures.csv",
            "membership_csv": prepared_dir / "membership.csv",
            "crsp_inventory_report": prepared_dir / "crsp_inventory_report.md",
        }
    )
    return paths


def prepared_dataset_complete(prepared_dir: Path) -> bool:
    required = [
        prepared_dir / "prepared_dataset_summary.yaml",
        prepared_dir / "universe.csv",
        prepared_dir / "download_failures.csv",
        prepared_dir / "membership.csv",
        prepared_dir / "security_master.csv",
        prepared_dir / "qlib_source_csv",
    ]
    return all(path.exists() for path in required)


def write_prepared_manifest(config: dict[str, Any], prepared_dir: Path, prepared_key: str) -> None:
    industry_mapping = config.get("industry_mapping", {})
    manifest = {
        "prepared_dataset_key": prepared_key,
        "data_source": "crsp",
        "data": config.get("data", {}),
        "universe": config.get("universe", {}),
        "crsp": {
            key: config.get("crsp", {}).get(key)
            for key in [
                "raw_csv_path",
                "warehouse_dir",
                "label_horizon_days",
                "label_only_member_dates",
                "major_exchanges",
                "exclude_name_terms",
            ]
        },
        "industry_mapping": {
            "schema_version": industry_mapping.get("schema_version", INDUSTRY_SCHEMA_VERSION),
            "enabled": industry_mapping.get("enabled", False),
            "primary_source": industry_mapping.get("primary_source"),
            "fallbacks": industry_mapping.get("fallbacks", []),
            "sector_scheme": industry_mapping.get("sector_scheme"),
            "industry_scheme": industry_mapping.get("industry_scheme"),
        },
    }
    prepared_dir.mkdir(parents=True, exist_ok=True)
    prepared_dir.joinpath("prepared_dataset_summary.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def materialize_prepared_dataset(
    prepared_dir: Path,
    paths: dict[str, Path],
    *,
    copy_mode: str,
    metadata_extra: dict[str, Any],
) -> PreparedData:
    key_map = {
        "universe.csv": "universe_csv",
        "universe_candidates.csv": "universe_candidates_csv",
        "universe_selection.csv": "universe_selection_csv",
        "universe_exclusions.csv": "universe_exclusions_csv",
        "security_master.csv": "security_master_csv",
        "security_master_exclusions.csv": "security_master_exclusions_csv",
        "download_failures.csv": "failures_csv",
        "membership.csv": "membership_csv",
        "crsp_inventory_report.md": "crsp_inventory_report",
    }
    file_map = {file_name: paths[target_key] for file_name, target_key in key_map.items() if target_key in paths}
    for file_name, target in file_map.items():
        source = prepared_dir / file_name
        if source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        elif file_name in {"universe_exclusions.csv", "security_master_exclusions.csv"}:
            target.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame().to_csv(target, index=False)

    materialize_directory(prepared_dir / "qlib_source_csv", paths["source_dir"], copy_mode)
    qlib_dir = prepared_dir / "qlib_data"
    qlib_data_ready = qlib_data_complete(qlib_dir)
    if qlib_data_ready:
        materialize_directory(qlib_dir, paths["qlib_dir"], copy_mode)

    universe = pd.read_csv(paths["universe_csv"])
    failures = pd.read_csv(paths["failures_csv"])
    metadata = {
        "source": "crsp",
        "prepared_dataset_reused": True,
        "prepared_dataset_dir": str(prepared_dir),
        "qlib_data_ready": qlib_data_ready,
        "materialization_mode": copy_mode,
    }
    metadata.update(metadata_extra)
    return PreparedData(universe=universe, failures=failures, metadata=metadata)


def materialize_directory(source: Path, target: Path, copy_mode: str) -> None:
    remove_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if copy_mode == "copy":
        shutil.copytree(source, target)
        return
    try:
        target.symlink_to(source.resolve(), target_is_directory=True)
    except OSError:
        shutil.copytree(source, target)


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def qlib_data_complete(qlib_dir: Path) -> bool:
    return (qlib_dir / "calendars" / "day.txt").exists() and (qlib_dir / "features").exists()


def filter_membership_to_data_window(membership: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    start = pd.Timestamp(config["data"]["start_date"]).normalize()
    end = pd.Timestamp(config["data"]["end_date"]).normalize()
    frame = membership.copy()
    frame["_effective_start"] = pd.to_datetime(frame["effective_start"], errors="coerce").dt.normalize()
    frame["_effective_end"] = pd.to_datetime(frame["effective_end"], errors="coerce").dt.normalize()
    frame = frame[(frame["_effective_start"] <= end) & (frame["_effective_end"] >= start)].copy()
    frame = frame.drop(columns=["_effective_start", "_effective_end"])
    return frame.reset_index(drop=True)


def ensure_crsp_warehouse(config: dict[str, Any], warehouse: CRSPWarehousePaths, paths: dict[str, Path] | None = None) -> None:
    crsp_config = config.get("crsp", {})
    force = bool(crsp_config.get("force_rebuild_warehouse", False))
    if warehouse.daily_dir.exists() and warehouse.security_master.exists() and not force:
        return
    if force and warehouse.root.exists():
        shutil.rmtree(warehouse.root)
    raw_csv = resolve_config_path(crsp_config["raw_csv_path"])
    if not raw_csv.exists():
        raise FileNotFoundError(f"CRSP raw CSV does not exist: {raw_csv}")
    build_crsp_warehouse_from_csv(raw_csv, warehouse, config, paths)


def build_crsp_warehouse_from_csv(
    raw_csv: Path,
    warehouse: CRSPWarehousePaths,
    config: dict[str, Any],
    paths: dict[str, Path] | None = None,
) -> None:
    header = pd.read_csv(raw_csv, nrows=0).columns.tolist()
    missing = sorted(set(CRSP_REQUIRED_COLUMNS) - set(header))
    if missing:
        raise ValueError(f"CRSP raw CSV missing required column(s): {', '.join(missing)}")

    warehouse.root.mkdir(parents=True, exist_ok=True)
    reset_directory(warehouse.daily_dir)
    reset_directory(warehouse.returns)
    reset_directory(warehouse.execution_prices)

    usecols = [column for column in CRSP_WAREHOUSE_COLUMNS if column in header]
    chunk_rows = int(config.get("crsp", {}).get("chunk_rows", 250_000))
    start = pd.Timestamp(config["data"]["start_date"]).normalize()
    end = pd.Timestamp(config["data"]["end_date"]).normalize()

    security_frames: list[pd.DataFrame] = []
    part_index = 0
    row_count = 0
    date_min: pd.Timestamp | None = None
    date_max: pd.Timestamp | None = None
    exchange_counts: dict[str, int] = {}
    security_type_counts: dict[str, int] = {}

    for chunk in pd.read_csv(raw_csv, usecols=usecols, chunksize=chunk_rows, low_memory=False):
        normalized = normalize_crsp_chunk(chunk)
        normalized = normalized[(normalized["date"] >= start) & (normalized["date"] <= end)].copy()
        if normalized.empty:
            continue

        row_count += len(normalized)
        current_min = normalized["date"].min()
        current_max = normalized["date"].max()
        date_min = current_min if date_min is None else min(date_min, current_min)
        date_max = current_max if date_max is None else max(date_max, current_max)
        update_counts(exchange_counts, normalized.get("PrimaryExch", pd.Series(dtype=object)))
        update_counts(security_type_counts, normalized.get("SecurityType", pd.Series(dtype=object)))

        for year, year_frame in normalized.groupby(normalized["date"].dt.year):
            year_dir = warehouse.daily_dir / f"year={int(year)}"
            year_dir.mkdir(parents=True, exist_ok=True)
            year_frame.to_parquet(year_dir / f"part-{part_index:06d}.parquet", index=False)

        returns = normalized[["date", "instrument", "DlyRet", "DlyRetx"]].copy()
        returns.to_parquet(warehouse.returns / f"part-{part_index:06d}.parquet", index=False)
        execution = normalized[["date", "instrument", "DlyOpen", "DlyClose", "DlyHigh", "DlyLow", "DlyVol"]].copy()
        execution.to_parquet(warehouse.execution_prices / f"part-{part_index:06d}.parquet", index=False)

        security_frames.append(security_master_rows_from_chunk(normalized))
        part_index += 1

    if row_count == 0:
        raise ValueError("CRSP warehouse build found no rows inside configured data.start_date/data.end_date")

    security_master = finalize_security_master(security_frames)
    security_master.to_parquet(warehouse.security_master, index=False)
    security_master[["permno", "instrument", "ticker_asof", "cusip", "cusip9", "permco", "issuer_name"]].to_parquet(
        warehouse.instrument_map,
        index=False,
    )
    write_inventory_report(
        warehouse,
        raw_csv=raw_csv,
        row_count=row_count,
        date_min=date_min,
        date_max=date_max,
        exchange_counts=exchange_counts,
        security_type_counts=security_type_counts,
        security_master=security_master,
    )
    if paths and "crsp_inventory_report" in paths:
        copy_inventory_report(warehouse, paths)


def normalize_crsp_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    frame = chunk.copy()
    for column in NUMERIC_COLUMNS:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["date"] = pd.to_datetime(frame.get("DlyCalDt"), errors="coerce").dt.normalize()
    missing_dates = frame["date"].isna()
    if missing_dates.any() and "YYYYMMDD" in frame:
        frame.loc[missing_dates, "date"] = pd.to_datetime(
            frame.loc[missing_dates, "YYYYMMDD"].astype("Int64").astype(str),
            format="%Y%m%d",
            errors="coerce",
        )
    frame = frame.dropna(subset=["PERMNO", "date"]).copy()
    frame["PERMNO"] = frame["PERMNO"].astype(int)
    frame["instrument"] = "P" + frame["PERMNO"].astype(str)
    return frame.sort_values(["instrument", "date"]).reset_index(drop=True)


def update_counts(target: dict[str, int], series: pd.Series) -> None:
    for key, value in series.fillna("UNKNOWN").astype(str).value_counts().to_dict().items():
        target[key] = target.get(key, 0) + int(value)


def security_master_rows_from_chunk(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=SECURITY_MASTER_COLUMNS)
    grouped = frame.sort_values("date").groupby("instrument", as_index=False)
    latest = grouped.tail(1).copy()
    first_dates = grouped["date"].min().rename(columns={"date": "first_date"})
    last_dates = grouped["date"].max().rename(columns={"date": "last_date"})
    latest = latest.merge(first_dates, on="instrument", how="left").merge(last_dates, on="instrument", how="left")
    output = pd.DataFrame(
        {
            "permno": latest["PERMNO"].astype(int),
            "instrument": latest["instrument"].astype(str),
            "permco": latest.get("PERMCO"),
            "ticker_asof": latest.get("Ticker"),
            "trading_symbol_asof": latest.get("TradingSymbol"),
            "cusip": latest.get("CUSIP"),
            "cusip9": latest.get("CUSIP9"),
            "cik": latest.get("CIK"),
            "issuer_name": latest.get("IssuerNm"),
            "security_name": latest.get("SecurityNm"),
            "primary_exchange": latest.get("PrimaryExch"),
            "security_type": latest.get("SecurityType"),
            "security_subtype": latest.get("SecuritySubType"),
            "issuer_type": latest.get("IssuerType"),
            "share_type": latest.get("ShareType"),
            "us_incorporated": latest.get("USIncFlg"),
            "siccd": latest.get("SICCD"),
            "naics": latest.get("NAICS"),
            "icb_industry": latest.get("ICBIndustry"),
            "first_date": latest["first_date"],
            "last_date": latest["last_date"],
            "security_beg_date": latest.get("SecurityBegDt"),
            "security_end_date": latest.get("SecurityEndDt"),
            "security_active_flag": latest.get("SecurityActiveFlg"),
            "delisting_reason": latest.get("DelReasonType"),
        }
    )
    return output


def finalize_security_master(frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame(columns=SECURITY_MASTER_COLUMNS)
    frame = pd.concat(frames, ignore_index=True)
    frame["first_date"] = pd.to_datetime(frame["first_date"], errors="coerce")
    frame["last_date"] = pd.to_datetime(frame["last_date"], errors="coerce")
    latest_idx = frame.groupby("instrument")["last_date"].idxmax()
    latest = frame.loc[latest_idx].copy()
    first = frame.groupby("instrument")["first_date"].min().rename("first_date_full")
    last = frame.groupby("instrument")["last_date"].max().rename("last_date_full")
    latest = latest.merge(first, on="instrument", how="left").merge(last, on="instrument", how="left")
    latest["first_date"] = latest["first_date_full"]
    latest["last_date"] = latest["last_date_full"]
    latest = latest.drop(columns=["first_date_full", "last_date_full"])
    return latest[SECURITY_MASTER_COLUMNS].sort_values("instrument").reset_index(drop=True)


def ensure_monthly_membership(config: dict[str, Any], warehouse: CRSPWarehousePaths) -> None:
    force = bool(config.get("crsp", {}).get("force_rebuild_membership", False))
    if warehouse.monthly_membership.exists() and not force and monthly_membership_schema_complete(warehouse.monthly_membership):
        return
    membership = build_monthly_top500_membership(config, warehouse.daily_dir)
    membership.to_parquet(warehouse.monthly_membership, index=False)


def monthly_membership_schema_complete(path: Path) -> bool:
    try:
        frame = pd.read_parquet(path, columns=CRSP_MONTHLY_MEMBERSHIP_REQUIRED_COLUMNS)
    except (FileNotFoundError, ValueError, KeyError, OSError):
        return False
    return set(CRSP_MONTHLY_MEMBERSHIP_REQUIRED_COLUMNS).issubset(frame.columns)


def build_monthly_top500_membership(config: dict[str, Any], daily_dir: Path) -> pd.DataFrame:
    calendar = collect_crsp_calendar(daily_dir)
    if not calendar:
        raise ValueError(f"no CRSP daily parquet rows found in {daily_dir}")
    calendar_index = {date: index for index, date in enumerate(calendar)}
    month_end_dates = pd.Series(calendar).groupby(pd.Series(calendar).dt.to_period("M")).max()
    month_end_set = set(pd.to_datetime(month_end_dates).dt.normalize())

    candidate_frames = []
    for parquet_path in iter_parquet_files(daily_dir):
        frame = pd.read_parquet(parquet_path)
        frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
        frame = frame[frame["date"].isin(month_end_set)].copy()
        if frame.empty:
            continue
        frame = filter_crsp_common_equity(frame, config.get("crsp", {}))
        frame["dlycap"] = pd.to_numeric(frame["DlyCap"], errors="coerce")
        frame = frame[frame["dlycap"].notna() & (frame["dlycap"] > 0)].copy()
        if not frame.empty:
            frame = frame.sort_values(["date", "instrument", "dlycap"], ascending=[True, True, False])
            frame = frame.drop_duplicates(["date", "instrument"], keep="first")
            candidate_frames.append(frame)
    if not candidate_frames:
        raise ValueError("CRSP monthly membership build found no eligible common equity rows")

    candidates = pd.concat(candidate_frames, ignore_index=True)
    top_n = int(config["universe"].get("top_n_by_market_cap", config.get("crsp", {}).get("top_n", 500)))
    rows = []
    for month_end_date, month_frame in candidates.groupby("date"):
        month_frame = month_frame.sort_values(["dlycap", "instrument"], ascending=[False, True]).head(top_n).copy()
        month_frame["rank"] = range(1, len(month_frame) + 1)
        next_index = calendar_index.get(pd.Timestamp(month_end_date)) + 1 if pd.Timestamp(month_end_date) in calendar_index else None
        if next_index is None or next_index >= len(calendar):
            continue
        effective_start = calendar[next_index]
        for row in month_frame.to_dict("records"):
            rows.append(
                {
                    "month_end_date": pd.Timestamp(month_end_date),
                    "effective_start": effective_start,
                    "effective_end": pd.NaT,
                    "permno": int(row["PERMNO"]),
                    "instrument": row["instrument"],
                    "symbol": row["instrument"],
                    "ticker_asof": row.get("Ticker"),
                    "cik": row.get("CIK"),
                    "rank": int(row["rank"]),
                    "dlycap": float(row["dlycap"]),
                    "primary_exchange": row.get("PrimaryExch"),
                    "security_type": row.get("SecurityType"),
                    "security_subtype": row.get("SecuritySubType"),
                    "trading_status": row.get("TradingStatusFlg"),
                    "siccd": row.get("SICCD"),
                    "naics": row.get("NAICS"),
                    "icb_industry": row.get("ICBIndustry"),
                    "sector": sic_sector(row.get("SICCD")),
                    "industry": sic_industry(row.get("SICCD")),
                    "is_delisted_later": bool(str(row.get("SecurityActiveFlg", "")).upper() not in {"Y", "1", "TRUE"}),
                }
            )

    membership = pd.DataFrame(rows)
    if membership.empty:
        raise ValueError("CRSP monthly membership build produced no effective rows")
    membership = membership.sort_values(["month_end_date", "rank"]).reset_index(drop=True)
    starts = sorted(pd.to_datetime(membership["effective_start"]).dropna().unique())
    start_to_end = {}
    for index, start in enumerate(starts):
        if index + 1 < len(starts):
            next_start_index = calendar_index[pd.Timestamp(starts[index + 1])]
            start_to_end[pd.Timestamp(start)] = calendar[max(0, next_start_index - 1)]
        else:
            start_to_end[pd.Timestamp(start)] = calendar[-1]
    membership["effective_end"] = pd.to_datetime(membership["effective_start"]).map(start_to_end)
    for column in ["month_end_date", "effective_start", "effective_end"]:
        membership[column] = pd.to_datetime(membership[column]).dt.strftime("%Y-%m-%d")
    return membership


def filter_crsp_common_equity(frame: pd.DataFrame, crsp_config: dict[str, Any]) -> pd.DataFrame:
    major_exchanges = {str(value).upper() for value in crsp_config.get("major_exchanges", ["N", "Q", "A"])}
    working = frame.copy()
    masks = [
        text_column(working, "SecurityType").str.upper().eq("EQTY"),
        text_column(working, "SecuritySubType").str.upper().eq("COM"),
        text_column(working, "IssuerType").str.upper().eq("CORP"),
        text_column(working, "USIncFlg").str.upper().eq("Y"),
        text_column(working, "TradingStatusFlg").str.upper().eq("A"),
        text_column(working, "PrimaryExch").str.upper().isin(major_exchanges),
        ~text_column(working, "ShareType").str.upper().eq("AD"),
        ~text_column(working, "ShrAdrFlg").str.upper().eq("Y"),
    ]
    name = text_column(working, "SecurityNm").str.lower()
    excluded_terms = crsp_config.get(
        "exclude_name_terms",
        ["warrant", "right", "unit", "preferred", "depositary", "note", "bond", "debenture", "fund"],
    )
    if excluded_terms:
        masks.append(~name.str.contains("|".join(excluded_terms), regex=True, na=False))
    mask = masks[0]
    for item in masks[1:]:
        mask &= item
    return working[mask].copy()


def text_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series("", index=frame.index, dtype=object)
    return frame[column].fillna("").astype(str)


def normalize_industry_code(value: Any, *, width: int) -> str:
    if value is None or pd.isna(value):
        return "UNKNOWN"
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "noavail", "unknown"}:
        return "UNKNOWN"
    if "." in text:
        text = text.split(".", 1)[0]
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits or int(digits) == 0:
        return "UNKNOWN"
    return digits.zfill(width)[:width]


def sic_industry(value: Any) -> str:
    return normalize_industry_code(value, width=4)


def sic_sector(value: Any) -> str:
    industry = sic_industry(value)
    if industry == "UNKNOWN":
        return "UNKNOWN"
    return industry[:2]


def collect_crsp_calendar(daily_dir: Path) -> list[pd.Timestamp]:
    dates = []
    for parquet_path in iter_parquet_files(daily_dir):
        frame = pd.read_parquet(parquet_path, columns=["date"])
        dates.extend(pd.to_datetime(frame["date"]).dt.normalize().dropna().unique().tolist())
    return sorted(set(pd.Timestamp(date).normalize() for date in dates))


def write_crsp_qlib_source_csv(
    config: dict[str, Any],
    warehouse: CRSPWarehousePaths,
    membership: pd.DataFrame,
    source_dir: Path,
) -> list[dict[str, Any]]:
    selected = set(membership["instrument"].astype(str).str.upper())
    start = pd.Timestamp(config["data"]["start_date"]).normalize()
    end = pd.Timestamp(config["data"]["end_date"]).normalize()
    frames = []
    columns = [
        "date",
        "instrument",
        "DlyRet",
        "DlyRetx",
        "DlyOpen",
        "DlyHigh",
        "DlyLow",
        "DlyClose",
        "DlyPrc",
        "DlyVol",
    ]
    for parquet_path in iter_parquet_files(warehouse.daily_dir):
        frame = pd.read_parquet(parquet_path, columns=columns)
        frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
        frame = frame[(frame["date"] >= start) & (frame["date"] <= end)].copy()
        frame["instrument"] = frame["instrument"].astype(str).str.upper()
        frame = frame[frame["instrument"].isin(selected)].copy()
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return [{"symbol": "CRSP", "rows": 0, "error": "no selected membership instruments in warehouse"}]

    prices = pd.concat(frames, ignore_index=True)
    membership_intervals = build_membership_intervals(membership)
    min_history_rows = int(config["universe"].get("min_history_rows", 180))
    label_horizon = int(config.get("crsp", {}).get("label_horizon_days", 10))
    label_column = crsp_label_column(label_horizon)
    only_member_dates = bool(config.get("crsp", {}).get("label_only_member_dates", True))
    failures = []

    for instrument, group in prices.groupby("instrument"):
        qlib_frame = build_adjusted_qlib_frame(
            group.sort_values("date"),
            str(instrument),
            label_horizon=label_horizon,
            label_column=label_column,
            intervals=membership_intervals.get(str(instrument), []),
            label_only_member_dates=only_member_dates,
        )
        if qlib_frame.empty:
            failures.append({"symbol": str(instrument), "rows": 0, "error": "no usable rows inside configured data window"})
            continue
        usable_history = int(qlib_frame[["open", "high", "low", "close", "volume"]].dropna().shape[0])
        if usable_history < min_history_rows:
            failures.append({"symbol": str(instrument), "rows": usable_history, "error": f"history < {min_history_rows} rows"})
            continue
        qlib_frame.to_csv(source_dir / f"{instrument}.csv", index=False)
    return failures


def build_adjusted_qlib_frame(
    frame: pd.DataFrame,
    instrument: str,
    *,
    label_horizon: int,
    label_column: str | None = None,
    intervals: list[tuple[pd.Timestamp, pd.Timestamp]],
    label_only_member_dates: bool,
) -> pd.DataFrame:
    working = frame.copy()
    working = working.sort_values("date")
    working["_valid_price_count"] = working[["DlyOpen", "DlyHigh", "DlyLow", "DlyClose", "DlyPrc"]].notna().sum(axis=1)
    working = working.sort_values(["date", "_valid_price_count"], ascending=[True, False])
    working = working.drop_duplicates("date", keep="first").drop(columns=["_valid_price_count"])
    for column in ["DlyRet", "DlyRetx", "DlyOpen", "DlyHigh", "DlyLow", "DlyClose", "DlyPrc", "DlyVol"]:
        working[column] = pd.to_numeric(working[column], errors="coerce")
    raw_close = working["DlyClose"].fillna(working["DlyPrc"]).abs()
    working = working[raw_close.notna() & (raw_close > 0)].copy()
    raw_close = raw_close.loc[working.index]
    if working.empty:
        return pd.DataFrame()

    retx = working["DlyRetx"]
    raw_growth = raw_close / raw_close.shift(1)
    growth = (1.0 + retx).where(retx.notna(), raw_growth)
    growth.iloc[0] = 1.0
    growth = growth.replace([np.inf, -np.inf], np.nan).fillna(1.0)
    adjusted_close = float(raw_close.iloc[0]) * growth.cumprod()
    scale = adjusted_close / raw_close

    open_price = working["DlyOpen"].abs().fillna(raw_close) * scale
    high_price = working["DlyHigh"].abs().fillna(raw_close) * scale
    low_price = working["DlyLow"].abs().fillna(raw_close) * scale
    close_price = adjusted_close
    label_column = label_column or crsp_label_column(label_horizon)
    total_return = forward_compound_return(working["DlyRet"], label_horizon)
    if label_only_member_dates:
        member_mask = membership_mask(working["date"], intervals)
        total_return = total_return.where(member_mask, np.nan)

    output = pd.DataFrame(
        {
            "date": working["date"].dt.strftime("%Y-%m-%d"),
            "symbol": instrument,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "vwap": pd.concat([open_price, high_price, low_price, close_price], axis=1).mean(axis=1),
            "volume": pd.to_numeric(working["DlyVol"], errors="coerce"),
            label_column: total_return,
        }
    )
    return output.sort_values("date").reset_index(drop=True)


def forward_compound_return(returns: pd.Series, horizon: int) -> pd.Series:
    future = (1.0 + pd.to_numeric(returns, errors="coerce")).shift(-1)
    compounded = future.iloc[::-1].rolling(horizon, min_periods=horizon).apply(np.prod, raw=True).iloc[::-1] - 1.0
    return compounded.replace([np.inf, -np.inf], np.nan)


def build_membership_intervals(membership: pd.DataFrame) -> dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]]:
    intervals: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = {}
    if membership.empty:
        return intervals
    for row in membership.to_dict("records"):
        symbol = str(row.get("symbol") or row.get("instrument")).upper()
        start = pd.Timestamp(row["effective_start"]).normalize()
        end = pd.Timestamp(row["effective_end"]).normalize()
        intervals.setdefault(symbol, []).append((start, end))
    return intervals


def membership_mask(dates: pd.Series, intervals: list[tuple[pd.Timestamp, pd.Timestamp]]) -> pd.Series:
    if not intervals:
        return pd.Series(False, index=dates.index)
    normalized = pd.to_datetime(dates).dt.normalize()
    mask = pd.Series(False, index=dates.index)
    for start, end in intervals:
        mask |= (normalized >= start) & (normalized <= end)
    return mask


def build_universe_from_membership(membership: pd.DataFrame, security_master: pd.DataFrame) -> pd.DataFrame:
    latest = membership.sort_values(["month_end_date", "rank"]).groupby("symbol", as_index=False).tail(1).copy()
    first = membership.groupby("symbol").agg(
        first_membership_date=("effective_start", "min"),
        last_membership_date=("effective_end", "max"),
        membership_months=("month_end_date", "nunique"),
    )
    latest = latest.merge(first, on="symbol", how="left")
    if not security_master.empty:
        latest = latest.merge(security_master, left_on="symbol", right_on="instrument", how="left", suffixes=("", "_security"))
    latest["market_cap"] = latest["dlycap"]
    latest["current_market_cap_rank"] = latest["rank"]
    sic_source = latest.get("siccd", latest.get("siccd_security", pd.Series(index=latest.index, dtype=object)))
    latest["sector"] = sic_source.map(sic_sector)
    latest["industry"] = sic_source.map(sic_industry)
    return latest.sort_values("symbol").reset_index(drop=True)


def read_optional_parquet(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def iter_parquet_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    for parquet_path in sorted(path.rglob("*.parquet")):
        yield parquet_path


def write_inventory_report(
    warehouse: CRSPWarehousePaths,
    *,
    raw_csv: Path,
    row_count: int,
    date_min: pd.Timestamp | None,
    date_max: pd.Timestamp | None,
    exchange_counts: dict[str, int],
    security_type_counts: dict[str, int],
    security_master: pd.DataFrame,
) -> None:
    summary = {
        "raw_csv": str(raw_csv),
        "row_count": int(row_count),
        "date_min": None if date_min is None else date_min.strftime("%Y-%m-%d"),
        "date_max": None if date_max is None else date_max.strftime("%Y-%m-%d"),
        "instrument_count": int(security_master["instrument"].nunique()) if not security_master.empty else 0,
        "primary_exchange_counts": exchange_counts,
        "security_type_counts": security_type_counts,
    }
    warehouse.inventory_summary.write_text(yaml.safe_dump(summary, sort_keys=False), encoding="utf-8")
    lines = [
        "# CRSP Inventory Report",
        "",
        f"- Raw CSV: `{raw_csv}`",
        f"- Rows in configured window: `{row_count}`",
        f"- Date range: `{summary['date_min']}` to `{summary['date_max']}`",
        f"- Instrument count: `{summary['instrument_count']}`",
        "",
        "## Primary Exchange Counts",
        "",
    ]
    for key, value in sorted(exchange_counts.items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Security Type Counts", ""])
    for key, value in sorted(security_type_counts.items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This report is generated from locally archived CRSP daily data.",
            "- Large warehouse files live under ignored `runs/` paths and should not be committed.",
            "- Results are for learning and research, not investment advice.",
        ]
    )
    warehouse.inventory_report.write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_inventory_report(warehouse: CRSPWarehousePaths, paths: dict[str, Path]) -> None:
    target = paths.get("crsp_inventory_report")
    if target is None:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if warehouse.inventory_report.exists():
        shutil.copy2(warehouse.inventory_report, target)
    else:
        target.write_text("# CRSP Inventory Report\n\nWarehouse inventory report has not been generated yet.\n", encoding="utf-8")
