"""Review CRSP SIC/NAICS UNKNOWN coverage in a completed run directory."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

try:
    from .data_sources.crsp import sic_industry, sic_sector
    from .crsp_industry_validation import enrich_membership_with_industry, valid_icb, valid_naics
except ImportError:  # pragma: no cover - direct script execution
    from data_sources.crsp import sic_industry, sic_sector
    from crsp_industry_validation import enrich_membership_with_industry, valid_icb, valid_naics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, help="Run directory containing membership.csv")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dir = Path(args.run_dir).resolve()
    outputs = run_unknown_review(run_dir)
    print(f"CRSP industry UNKNOWN review: {outputs['summary']}")


def run_unknown_review(run_dir: Path) -> dict[str, Path]:
    membership_path = run_dir / "membership.csv"
    if not membership_path.exists():
        raise FileNotFoundError(f"membership.csv not found: {membership_path}")
    membership = pd.read_csv(membership_path)
    security_master = pd.read_csv(run_dir / "security_master.csv") if (run_dir / "security_master.csv").exists() else pd.DataFrame()
    membership = enrich_membership_with_industry(membership, security_master)
    review = build_unknown_review(membership)

    paths = {
        "year": run_dir / "crsp_industry_unknown_by_year.csv",
        "security": run_dir / "crsp_industry_unknown_by_security.csv",
        "type": run_dir / "crsp_industry_unknown_by_security_type.csv",
        "examples": run_dir / "crsp_industry_unknown_examples.csv",
        "summary": run_dir / "crsp_industry_unknown_review_summary.yaml",
    }
    review["by_year"].to_csv(paths["year"], index=False)
    review["by_security"].to_csv(paths["security"], index=False)
    review["by_security_type"].to_csv(paths["type"], index=False)
    review["examples"].to_csv(paths["examples"], index=False)
    paths["summary"].write_text(
        yaml.safe_dump(to_yaml_safe(review["summary"]), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return paths


def build_unknown_review(membership: pd.DataFrame) -> dict[str, Any]:
    frame = membership.copy()
    frame["effective_start"] = pd.to_datetime(frame["effective_start"], errors="coerce")
    frame["year"] = frame["effective_start"].dt.year
    frame["month"] = frame["effective_start"].dt.to_period("M").astype(str)
    if "sector" not in frame:
        frame["sector"] = frame.get("siccd", pd.Series(index=frame.index, dtype=object)).map(sic_sector)
    if "industry" not in frame:
        frame["industry"] = frame.get("siccd", pd.Series(index=frame.index, dtype=object)).map(sic_industry)
    frame["sic2_valid"] = frame["sector"].ne("UNKNOWN")
    frame["sic4_valid"] = frame["industry"].ne("UNKNOWN")

    by_year = coverage_table(frame, ["year"])
    by_security = security_table(frame)
    by_security_type = coverage_table(frame, ["primary_exchange", "security_type", "security_subtype", "trading_status"])
    unknown_examples = frame[~frame["sic2_valid"]].copy()
    examples = unknown_examples.sort_values(["effective_start", "symbol"]).head(100)
    unknown_naics_valid_share = float(unknown_examples["naics"].map(valid_naics).mean()) if len(unknown_examples) else 0.0
    unknown_icb_valid_share = float(unknown_examples["icb_industry"].map(valid_icb).mean()) if len(unknown_examples) else 0.0

    summary = {
        "membership_rows": int(len(frame)),
        "unknown_rows": int((~frame["sic2_valid"]).sum()),
        "sic2_coverage": float(frame["sic2_valid"].mean()) if len(frame) else 0.0,
        "unknown_naics_valid_share": unknown_naics_valid_share,
        "unknown_icb_valid_share": unknown_icb_valid_share,
        "min_year_sic2_coverage": float(by_year["sic2_coverage"].min()) if len(by_year) else 0.0,
        "worst_years": by_year.sort_values("sic2_coverage").head(5).to_dict("records"),
        "unknown_security_count": int(frame.loc[~frame["sic2_valid"], "symbol"].nunique()) if "symbol" in frame else 0,
        "top_unknown_securities": by_security.head(10).to_dict("records"),
        "top_unknown_security_types": by_security_type.sort_values("unknown_rows", ascending=False).head(10).to_dict("records"),
    }
    return {
        "by_year": by_year,
        "by_security": by_security,
        "by_security_type": by_security_type,
        "examples": examples,
        "summary": summary,
    }


def coverage_table(frame: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    table = (
        frame.groupby(group_cols, dropna=False)
        .agg(
            rows=("symbol", "size"),
            unknown_rows=("sic2_valid", lambda value: int((~value).sum())),
            sic2_coverage=("sic2_valid", "mean"),
            sic4_coverage=("sic4_valid", "mean"),
            unique_symbols=("symbol", "nunique"),
        )
        .reset_index()
    )
    table["unknown_share"] = table["unknown_rows"] / table["rows"]
    return table.sort_values(group_cols).reset_index(drop=True)


def security_table(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "symbol",
        "permno",
        "ticker_asof",
        "primary_exchange",
        "security_type",
        "security_subtype",
        "trading_status",
        "sector",
        "industry",
    ]
    available = [column for column in columns if column in frame]
    table = (
        frame.groupby(available, dropna=False)
        .agg(
            rows=("symbol", "size"),
            unknown_rows=("sic2_valid", lambda value: int((~value).sum())),
            first_effective_start=("effective_start", "min"),
            last_effective_start=("effective_start", "max"),
        )
        .reset_index()
    )
    table = table[table["unknown_rows"] > 0].copy()
    table["unknown_share"] = table["unknown_rows"] / table["rows"]
    return table.sort_values(["unknown_rows", "symbol"], ascending=[False, True]).reset_index(drop=True)


def to_yaml_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): to_yaml_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_yaml_safe(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


if __name__ == "__main__":
    main()
