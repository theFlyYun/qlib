"""PIT data-quality validation for Nasdaq/Qlib research runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


VALIDATION_COLUMNS = [
    "check_id",
    "area",
    "severity",
    "status",
    "required_for_strict",
    "finding",
    "recommendation",
    "evidence",
]


class DataQualityError(RuntimeError):
    """Raised when a strict PIT run fails data-quality validation."""


@dataclass
class DataQualityResult:
    pit_universe: pd.DataFrame
    security_master: pd.DataFrame
    market_cap: pd.DataFrame
    summary: dict[str, Any]


def run_data_quality_validation(config: dict[str, Any], paths: dict[str, Path], prepared: Any) -> DataQualityResult:
    """Write strict PIT validation artifacts and optionally block unsafe strict runs."""
    strict_config = config.get("strict_pit", {})
    pit_universe = validate_pit_universe(config, paths, prepared)
    security_master = validate_security_master(config, paths, prepared)
    market_cap = validate_market_cap(config, paths, prepared)
    all_checks = pd.concat([pit_universe, security_master, market_cap], ignore_index=True)
    summary = build_data_quality_summary(config, all_checks)

    pit_universe.to_csv(paths["pit_universe_validation"], index=False)
    security_master.to_csv(paths["security_master_validation"], index=False)
    market_cap.to_csv(paths["market_cap_validation"], index=False)
    paths["data_quality_summary"].write_text(
        yaml.safe_dump(summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    if strict_config.get("enabled", False) and strict_config.get("enforcement", "fail") == "fail":
        blocking = all_checks[all_checks["required_for_strict"] & all_checks["status"].isin(["fail", "not_available"])]
        if not blocking.empty:
            failed = ", ".join(blocking["check_id"].astype(str).tolist())
            raise DataQualityError(
                f"strict PIT data validation failed: {failed}. "
                f"See {paths['data_quality_summary']} and {paths['pit_universe_validation']}."
            )

    return DataQualityResult(
        pit_universe=pit_universe,
        security_master=security_master,
        market_cap=market_cap,
        summary=summary,
    )


def validate_pit_universe(config: dict[str, Any], paths: dict[str, Path], prepared: Any) -> pd.DataFrame:
    source = config["data"]["source"]
    selection = config.get("universe", {}).get("selection", {})
    membership = read_optional_csv(paths["membership_csv"])
    universe = prepared.universe.copy()
    metadata = getattr(prepared, "metadata", {}) or {}
    has_delisted_database = any("delisted" in str(value).lower() for value in config.get("universe", {}).get("candidate_databases", []))
    has_delisted_rows = any(
        column in universe
        and universe[column].astype(str).str.lower().isin(["true", "1"]).any()
        for column in ["is_delisted", "is_delisted_later"]
    )
    has_delisted_capable_source = (
        source in {"sharadar", "databento"} and bool(config.get("universe", {}).get("include_delisted", False))
    ) or source == "crsp"
    has_point_membership = not membership.empty and {"symbol", "date", "is_member"}.issubset(membership.columns)
    has_interval_membership = not membership.empty and {"symbol", "effective_start", "effective_end"}.issubset(membership.columns)
    has_membership = has_point_membership or has_interval_membership

    rows = [
        validation_row(
            "U1",
            "股票池",
            "HIGH",
            "fail" if selection.get("method") == "approximate_market_cap_asof" else "pass",
            True,
            "严格实验不得用 current_market_cap * asof_close / latest_close 反推历史市值。",
            "使用历史 shares/market cap 或 vendor PIT market cap；否则只能标记为学习实验。",
            "universe_selection.csv" if selection.get("method") else "",
        ),
        validation_row(
            "U2",
            "股票池",
            "HIGH",
            "fail" if source == "nasdaq_public" else "pass",
            True,
            "`nasdaq_public` 是当前快照数据源，缺少退市股票和历史证券主数据。",
            "严格实验使用 Databento/Sharadar/Norgate/CRSP/同级 PIT 数据源。",
            "data.source",
        ),
        validation_row(
            "U3",
            "股票池",
            "HIGH",
            "pass" if has_delisted_database or has_delisted_rows or has_delisted_capable_source else "fail",
            True,
            "股票池需要包含退市、并购、转板等历史失败证券以降低幸存者偏差。",
            "接入包含退市证券的历史数据库，并在 universe 输出 is_delisted/source_database。",
            "universe.csv",
        ),
        validation_row(
            "U4",
            "历史成分",
            "MEDIUM",
            "pass" if has_membership else "warning",
            False,
            "动态历史成分需要 membership.csv 记录 symbol/date/is_member。",
            "launch 固定股票池可不依赖日级 membership；full dynamic 研究必须提供。",
            "membership.csv",
        ),
        validation_row(
            "U5",
            "价格口径",
            "MEDIUM",
            "pass" if source in {"norgate", "sharadar", "databento", "crsp"} and config["data"].get("price_adjustment") else "warning",
            False,
            "严格报告必须记录价格复权口径。",
            "默认使用 split/capital adjusted OHLCV；分红 total return 单独做收益版本。",
            "resolved_config.yaml",
        ),
    ]
    if source == "norgate":
        rows.append(
            validation_row(
                "U6",
                "数据源",
                "LOW",
                "pass",
                False,
                f"Norgate adapter metadata source={metadata.get('source', 'norgate')}，可承载历史成分和退市证券。",
                "真实 Norgate 环境跑通后仍需检查订阅等级和 membership 覆盖。",
                "membership.csv",
            )
        )
    if source == "sharadar":
        rows.append(
            validation_row(
                "U6",
                "数据源",
                "LOW",
                "pass",
                False,
                f"Sharadar adapter metadata source={metadata.get('source', 'sharadar')}，可承载 launch PIT 股票池、退市证券和历史价格。",
                "仍需 provider_capability_summary.yaml 证明当前 API key/订阅字段足够。",
                "provider_capability_summary.yaml",
            )
        )
    if source == "databento":
        rows.append(
            validation_row(
                "U6",
                "数据源",
                "LOW",
                "pass",
                False,
                f"Databento adapter metadata source={metadata.get('source', 'databento')}，可承载 launch PIT 股票池、退市证券、PIT security master 和历史 OHLCV。",
                "仍需 provider_capability_summary.yaml 证明当前 API key/entitlement 字段足够，尤其是 shares outstanding、corporate actions 和 EQUS.SUMMARY。",
                "provider_capability_summary.yaml",
            )
        )
    if source == "crsp":
        rows.append(
            validation_row(
                "U6",
                "数据源",
                "LOW",
                "pass",
                False,
                "CRSP adapter 使用本地 daily 数据、PERMNO、DlyCap 和月度动态 membership，可承载 full PIT dynamic 股票池。",
                "继续抽样核对 delisting、DlyCap 和 membership effective_start，EDGAR/行业分类另行验收。",
                "crsp_inventory_report.md",
            )
        )
    return pd.DataFrame(rows, columns=VALIDATION_COLUMNS)


def validate_security_master(config: dict[str, Any], paths: dict[str, Path], prepared: Any) -> pd.DataFrame:
    universe = prepared.universe.copy()
    security_master = read_optional_csv(paths["security_master_csv"])
    source = config["data"]["source"]
    has_asset_type = "asset_type" in security_master.columns or source in {"norgate", "sharadar", "databento", "crsp"}
    has_listing_dates = any(
        column in universe.columns
        for column in ["first_quoted_date", "listing_date", "first_date", "security_beg_date", "first_membership_date"]
    )
    has_delisting_dates = any(
        column in universe.columns
        for column in ["last_quoted_date", "delisting_date", "last_date", "security_end_date", "last_membership_date"]
    )
    has_pit_industry = bool(config.get("strict_pit", {}).get("pit_industry_classification", False))

    rows = [
        validation_row(
            "S1",
            "证券主数据",
            "MEDIUM",
            "pass" if has_asset_type else "warning",
            False,
            "证券类型需要能区分普通股、ADR、ETF、权证、优先股等。",
            "严格股票池只保留可投资权益证券，并输出 asset_type。",
            "security_master.csv",
        ),
        validation_row(
            "S2",
            "证券主数据",
            "HIGH",
            "pass" if has_listing_dates else "fail",
            True,
            "严格 PIT 股票池需要历史上市日期或 first quoted date。",
            "接入 vendor security master 的 listing/first_quoted_date。",
            "universe.csv",
        ),
        validation_row(
            "S3",
            "证券主数据",
            "HIGH",
            "pass" if has_delisting_dates else "fail",
            True,
            "严格 PIT 股票池需要退市日期或 last quoted date。",
            "接入 vendor security master 的 delisting/last_quoted_date。",
            "universe.csv",
        ),
        validation_row(
            "S4",
            "行业分类",
            "MEDIUM",
            "pass" if has_pit_industry else "warning",
            False,
            "当前 Nasdaq sector/industry 不是历史 PIT 行业分类。",
            "没有 PIT 行业分类前，行业只做事后复盘，不进入 strict headline 模型或选股约束。",
            "universe.csv",
        ),
    ]
    return pd.DataFrame(rows, columns=VALIDATION_COLUMNS)


def validate_market_cap(config: dict[str, Any], paths: dict[str, Path], prepared: Any) -> pd.DataFrame:
    universe = prepared.universe.copy()
    selection = read_optional_csv(paths["universe_selection_csv"])
    has_proxy = "market_cap_asof_estimate" in selection.columns or "market_cap_asof_estimate" in universe.columns
    has_historical_market_cap = any(
        column in universe.columns
        for column in ["historical_market_cap", "market_cap_asof", "market_cap_pit", "shares_outstanding", "dlycap", "market_cap"]
    )
    has_market_cap_date = any(
        column in universe.columns
        for column in ["market_cap_date", "shares_outstanding_date", "market_cap_asof_date", "month_end_date", "effective_start"]
    )
    rows = [
        validation_row(
            "M1",
            "市值口径",
            "HIGH",
            "fail" if has_proxy else "pass",
            True,
            "`market_cap_asof_estimate` 是当前市值反推历史市值，严格实验禁用。",
            "使用历史 shares outstanding × 当时价格，或 vendor 直接提供的 PIT market cap。",
            "universe_selection.csv",
        ),
        validation_row(
            "M2",
            "市值口径",
            "HIGH",
            "pass" if has_historical_market_cap else "fail",
            True,
            "严格 launch 股票池需要历史市值或历史 shares outstanding。",
            "补充 historical_market_cap / market_cap_asof / shares_outstanding 字段。",
            "universe.csv",
        ),
        validation_row(
            "M3",
            "市值口径",
            "MEDIUM",
            "pass" if has_market_cap_date else "warning",
            False,
            "历史市值需要可追溯的 as-of 日期。",
            "输出 market_cap_date 或 shares_outstanding_date。",
            "universe.csv",
        ),
    ]
    return pd.DataFrame(rows, columns=VALIDATION_COLUMNS)


def build_data_quality_summary(config: dict[str, Any], checks: pd.DataFrame) -> dict[str, Any]:
    strict_config = config.get("strict_pit", {})
    strict_enabled = bool(strict_config.get("enabled", False))
    blocking = checks[checks["required_for_strict"] & checks["status"].isin(["fail", "not_available"])]
    status = "strict_pit_pass" if strict_enabled and blocking.empty else "strict_pit_failed" if strict_enabled else "not_strict_pit"
    survivorship = "high" if is_failed(checks, "U2") or is_failed(checks, "U3") else "low"
    market_cap_proxy = "high" if is_failed(checks, "U1") or is_failed(checks, "M1") else "low"
    return {
        "enabled": True,
        "strict_pit": strict_config,
        "data_source": config["data"]["source"],
        "strict_result_status": status,
        "strict_headline_allowed": strict_enabled and blocking.empty,
        "learning_research_only": not (strict_enabled and blocking.empty),
        "blocking_check_ids": blocking["check_id"].astype(str).tolist(),
        "survivorship_risk": survivorship,
        "market_cap_proxy_risk": market_cap_proxy,
        "pit_industry_status": "verified" if strict_config.get("pit_industry_classification", False) else "not_verified",
        "check_counts": checks.groupby(["severity", "status"]).size().reset_index(name="count").to_dict("records"),
        "headline_note": (
            "严格结果优先于高收益结果；未通过 PIT 数据验收的实验只能作为学习观察。"
        ),
    }


def validation_row(
    check_id: str,
    area: str,
    severity: str,
    status: str,
    required_for_strict: bool,
    finding: str,
    recommendation: str,
    evidence: str = "",
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "area": area,
        "severity": severity,
        "status": status,
        "required_for_strict": required_for_strict,
        "finding": finding,
        "recommendation": recommendation,
        "evidence": evidence,
    }


def read_optional_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def is_failed(checks: pd.DataFrame, check_id: str) -> bool:
    row = checks[checks["check_id"].eq(check_id)]
    return not row.empty and row.iloc[0]["status"] == "fail"
