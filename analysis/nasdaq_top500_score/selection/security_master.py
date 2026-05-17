"""Security master classification and filtering for experiment universes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

SECURITY_MASTER_COLUMNS = [
    "symbol",
    "name",
    "security_name",
    "asset_type",
    "security_master_pass",
    "exclusion_reason",
    "is_common_equity",
    "is_adr_ads",
    "is_share_class",
    "share_class",
    "is_etf",
    "is_test_issue",
    "market_category",
    "financial_status",
    "round_lot_size",
    "sector",
    "industry",
    "market_cap",
    "last_sale",
]
SECURITY_MASTER_EXCLUSION_COLUMNS = [
    "symbol",
    "name",
    "security_name",
    "asset_type",
    "exclusion_reason",
    "market_cap",
]
DEFAULT_ALLOWED_ASSET_TYPES = ["common_stock", "ordinary_share", "adr_ads", "unknown_equity_like"]


def apply_security_master_filter(
    screener: pd.DataFrame,
    listed: pd.DataFrame,
    universe_config: dict[str, Any],
    paths: dict[str, Path],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    master_config = universe_config.get("security_master", {})
    if not master_config.get("enabled", False):
        return screener.copy(), empty_security_master(), empty_security_master_exclusions()

    master = build_security_master(screener, listed)
    master = evaluate_security_master(master, universe_config)
    exclusions = master[~master["security_master_pass"]].copy()
    exclusions = exclusions.reindex(columns=SECURITY_MASTER_EXCLUSION_COLUMNS)

    paths["security_master_csv"].parent.mkdir(parents=True, exist_ok=True)
    master.to_csv(paths["security_master_csv"], index=False)
    exclusions.to_csv(paths["security_master_exclusions_csv"], index=False)
    exclusions.rename(columns={"security_name": "listed_security_name"}).to_csv(
        paths["universe_exclusions_csv"],
        index=False,
    )

    keep_symbols = set(master[master["security_master_pass"]]["symbol"].astype(str))
    filtered = screener[screener["symbol"].astype(str).isin(keep_symbols)].copy()
    filtered = filtered.merge(
        master[
            [
                "symbol",
                "security_name",
                "asset_type",
                "is_common_equity",
                "is_adr_ads",
                "is_share_class",
                "share_class",
                "market_category",
                "financial_status",
                "round_lot_size",
            ]
        ],
        on="symbol",
        how="left",
    )
    return filtered, master, exclusions


def build_security_master(screener: pd.DataFrame, listed: pd.DataFrame) -> pd.DataFrame:
    working = screener.copy()
    listed_working = listed.copy()
    if not listed_working.empty:
        listed_columns = [
            "symbol",
            "security_name",
            "market_category",
            "test_issue",
            "financial_status",
            "round_lot_size",
            "etf",
        ]
        listed_working = listed_working.reindex(columns=listed_columns)
        working = working.merge(listed_working, on="symbol", how="left")

    rows = []
    for row in working.to_dict("records"):
        profile = classify_security(row)
        rows.append({**row, **profile})
    frame = pd.DataFrame(rows)
    for column in SECURITY_MASTER_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    return frame[SECURITY_MASTER_COLUMNS].sort_values("symbol").reset_index(drop=True)


def evaluate_security_master(master: pd.DataFrame, universe_config: dict[str, Any]) -> pd.DataFrame:
    config = universe_config.get("security_master", {})
    allowed_asset_types = set(config.get("allowed_asset_types", DEFAULT_ALLOWED_ASSET_TYPES))
    allow_adr_ads = bool(config.get("allow_adr_ads", True))
    require_not_etf = bool(config.get("require_not_etf", universe_config.get("exclude_etf", True)))
    require_not_test_issue = bool(config.get("require_not_test_issue", universe_config.get("exclude_test_issue", True)))

    working = master.copy()
    reasons = []
    passes = []
    for row in working.to_dict("records"):
        reason = None
        if require_not_test_issue and truthy_flag(row.get("is_test_issue")):
            reason = "security_master:test_issue"
        elif require_not_etf and truthy_flag(row.get("is_etf")):
            reason = "security_master:etf"
        elif not allow_adr_ads and truthy_flag(row.get("is_adr_ads")):
            reason = "security_master:adr_ads"
        elif row.get("asset_type") not in allowed_asset_types:
            reason = f"security_master:asset_type={row.get('asset_type')}"
        reasons.append(reason)
        passes.append(reason is None)

    working["security_master_pass"] = passes
    working["exclusion_reason"] = reasons
    return working


def classify_security(row: dict[str, Any]) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "").upper().strip()
    name = coalesce_text(row.get("name"), row.get("security_name"))
    security_name = coalesce_text(row.get("security_name"), row.get("name"))
    text = f"{name} {security_name}".lower()
    share_class = parse_share_class(text)
    asset_type = infer_asset_type(symbol, text)
    return {
        "asset_type": asset_type,
        "security_master_pass": True,
        "exclusion_reason": None,
        "is_common_equity": asset_type in {"common_stock", "ordinary_share", "adr_ads", "unknown_equity_like"},
        "is_adr_ads": asset_type == "adr_ads",
        "is_share_class": share_class is not None,
        "share_class": share_class,
        "is_etf": truthy_flag(row.get("etf")),
        "is_test_issue": truthy_flag(row.get("test_issue")),
    }


def infer_asset_type(symbol: str, text: str) -> str:
    if re.search(r"\bwarrants?\b", text, flags=re.IGNORECASE) or re.fullmatch(r".*W(S|T|W)?$", symbol):
        return "warrant"
    if re.search(r"\brights?\b", text, flags=re.IGNORECASE):
        return "right"
    if re.search(r"\bunits?\b", text, flags=re.IGNORECASE):
        return "unit"
    if re.search(r"\bpreferred\b|\bpreference\b", text, flags=re.IGNORECASE):
        return "preferred"
    if re.search(r"\bnotes?\b|\bbonds?\b|\bdebentures?\b", text, flags=re.IGNORECASE):
        return "debt"
    if "depositary shares" in text and "american depositary shares" not in text:
        return "depositary_share"
    if "american depositary shares" in text or re.search(r"\badr\b", text, flags=re.IGNORECASE):
        return "adr_ads"
    if "ordinary shares" in text or "ordinary share" in text:
        return "ordinary_share"
    if "common stock" in text:
        return "common_stock"
    return "unknown_equity_like"


def parse_share_class(text: str) -> str | None:
    match = re.search(r"\bclass\s+([a-z])\b", text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).upper()


def truthy_flag(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    return str(value).strip().upper() in {"Y", "YES", "TRUE", "1"}


def coalesce_text(*values: Any) -> str:
    for value in values:
        if value is not None and not pd.isna(value) and str(value).strip():
            return str(value).strip()
    return ""


def empty_security_master() -> pd.DataFrame:
    return pd.DataFrame(columns=SECURITY_MASTER_COLUMNS)


def empty_security_master_exclusions() -> pd.DataFrame:
    return pd.DataFrame(columns=SECURITY_MASTER_EXCLUSION_COLUMNS)
