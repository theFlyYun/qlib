"""Sharadar / Nasdaq Data Link adapter for strict launch-PIT experiments."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import yaml

from .base import (
    DataSourceUnavailable,
    PreparedData,
    normalize_ohlcv_frame,
    reset_directory,
    write_failures,
)

SHARADAR_BASE_URL = "https://data.nasdaq.com/api/v3/datatables/SHARADAR"
DEFAULT_TABLES = ["TICKERS", "SEP", "SF1", "DAILY", "INDICATORS"]
REQUIRED_TABLES = ["TICKERS", "SEP", "SF1"]

SHARADAR_UNAVAILABLE_MESSAGE = (
    "data.source=sharadar requires NASDAQ_DATA_LINK_API_KEY or SHARADAR_API_KEY "
    "in the shell environment or an ignored .env/local_secrets.env file, plus a "
    "Nasdaq Data Link subscription that can access Sharadar tables."
)


@dataclass
class CapabilityProbeResult:
    summary: dict[str, Any]
    columns: pd.DataFrame

    @property
    def strict_pass(self) -> bool:
        return bool(self.summary.get("strict_capability_pass", False))


class SharadarClient:
    """Small Nasdaq Data Link Tables API client.

    The client deliberately stays HTTP-only instead of depending on a Nasdaq
    SDK. This keeps tests easy and makes failure modes explicit.
    """

    def __init__(self, api_key: str | None = None, session: requests.Session | None = None) -> None:
        self.api_key = api_key or os.environ.get("NASDAQ_DATA_LINK_API_KEY") or os.environ.get("SHARADAR_API_KEY")
        if not self.api_key:
            raise DataSourceUnavailable(SHARADAR_UNAVAILABLE_MESSAGE)
        self.session = session or requests.Session()

    def metadata(self, table: str) -> dict[str, Any]:
        url = f"{SHARADAR_BASE_URL}/{table}/metadata.json"
        return self._get_json(url, {"api_key": self.api_key})

    def table(self, table: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
        url = f"{SHARADAR_BASE_URL}/{table}.json"
        query = dict(params or {})
        query["api_key"] = self.api_key
        query.setdefault("qopts.per_page", 10000)
        frames: list[pd.DataFrame] = []
        cursor_id: str | None = None

        while True:
            page_query = dict(query)
            if cursor_id:
                page_query["qopts.cursor_id"] = cursor_id
            payload = self._get_json(url, page_query)
            datatable = payload.get("datatable", {})
            columns = [column["name"] for column in datatable.get("columns", [])]
            data = datatable.get("data", [])
            if columns and data:
                frames.append(pd.DataFrame(data, columns=columns))
            cursor_id = payload.get("meta", {}).get("next_cursor_id")
            if not cursor_id:
                break

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.session.get(url, params=params, timeout=60)
                if response.status_code in {401, 403}:
                    raise DataSourceUnavailable(
                        f"Sharadar table request is unauthorized or not subscribed: {url}. "
                        "Check Nasdaq Data Link API key and Sharadar subscription."
                    )
                response.raise_for_status()
                return response.json()
            except DataSourceUnavailable:
                raise
            except Exception as exc:  # noqa: BLE001 - remote APIs can be transient.
                last_error = exc
                time.sleep(1.5 * (attempt + 1))
        raise DataSourceUnavailable(f"failed to fetch Sharadar API {url}: {last_error}")


class SharadarDataSource:
    def __init__(self, config: dict[str, Any], paths: dict[str, Path], client: Any | None = None) -> None:
        self.config = config
        self.paths = paths
        self.client = client

    def prepare(self) -> PreparedData:
        source_dir = self.paths["source_dir"]
        reset_directory(source_dir)
        self.paths["sharadar_cache_dir"].mkdir(parents=True, exist_ok=True)

        try:
            self.client = self.client or SharadarClient()
        except DataSourceUnavailable as exc:
            write_unavailable_capability(self.paths, str(exc))
            self.write_empty_artifacts()
            raise

        probe = run_sharadar_capability_probe(self.config, self.paths, self.client)
        if not probe.strict_pass:
            self.write_empty_artifacts()
            raise DataSourceUnavailable(
                "Sharadar capability probe did not pass strict PIT requirements. "
                f"See {self.paths['provider_capability_summary']}."
            )

        candidates = self.load_candidate_universe()
        selected, diagnostics = self.select_launch_pit_universe(candidates)
        diagnostics.to_csv(self.paths["universe_selection_csv"], index=False)
        selected.to_csv(self.paths["universe_csv"], index=False)

        failures: list[dict[str, Any]] = []
        universe_rows: list[dict[str, Any]] = []
        print(f"Preparing Sharadar OHLCV for {len(selected)} selected symbols...")
        for index, row in enumerate(selected.to_dict("records"), start=1):
            symbol = str(row["symbol"]).upper()
            try:
                qlib_frame = self.download_symbol_prices(symbol)
            except Exception as exc:  # noqa: BLE001 - keep batch ingestion resumable.
                failures.append({"symbol": symbol, "rows": 0, "error": str(exc)})
                continue

            min_history_rows = int(self.config["universe"]["min_history_rows"])
            if len(qlib_frame) < min_history_rows:
                failures.append({"symbol": symbol, "rows": len(qlib_frame), "error": f"history < {min_history_rows} rows"})
                continue

            qlib_frame.to_csv(source_dir / f"{symbol}.csv", index=False)
            enriched = dict(row)
            enriched.update(
                {
                    "first_date": qlib_frame["date"].min(),
                    "last_date": qlib_frame["date"].max(),
                    "history_rows": len(qlib_frame),
                }
            )
            universe_rows.append(enriched)
            if index % 50 == 0 or index == len(selected):
                print(f"Prepared {index}/{len(selected)}; usable: {len(universe_rows)}; failures/skips: {len(failures)}")

        universe = pd.DataFrame(universe_rows)
        universe.to_csv(self.paths["universe_csv"], index=False)
        self.write_launch_membership(universe)
        failures_frame = write_failures(self.paths["failures_csv"], failures)
        return PreparedData(
            universe=universe,
            failures=failures_frame,
            metadata={
                "source": "sharadar",
                "mode": "launch_pit_2023",
                "provider_capability_summary": str(self.paths["provider_capability_summary"]),
            },
        )

    def write_empty_artifacts(self) -> None:
        pd.DataFrame().to_csv(self.paths["universe_csv"], index=False)
        pd.DataFrame().to_csv(self.paths["universe_candidates_csv"], index=False)
        pd.DataFrame(columns=["symbol", "date", "is_member"]).to_csv(self.paths["membership_csv"], index=False)
        write_failures(self.paths["failures_csv"], [])

    def load_candidate_universe(self) -> pd.DataFrame:
        tickers = fetch_table_frame(self.client, "TICKERS")
        if tickers.empty:
            raise DataSourceUnavailable("SHARADAR/TICKERS returned no rows")
        normalized = normalize_tickers_frame(tickers)
        normalized.to_csv(self.paths["security_master_csv"], index=False)

        as_of_trade_date = pd.Timestamp(self.config["universe"]["as_of_trade_date"]).normalize()
        exchange = self.config["universe"].get("exchange")
        candidates = normalized.copy()
        if exchange and "exchange" in candidates:
            candidates = candidates[candidates["exchange"].astype(str).str.upper().eq(str(exchange).upper())]
        candidates = candidates[candidates["symbol"].notna() & candidates["symbol"].astype(str).ne("")]
        candidates = candidates[candidates["is_common_equity"]]
        candidates = candidates[candidates["first_quoted_date"].isna() | (pd.to_datetime(candidates["first_quoted_date"]) <= as_of_trade_date)]
        candidates = candidates[candidates["last_quoted_date"].isna() | (pd.to_datetime(candidates["last_quoted_date"]) >= as_of_trade_date)]
        candidates = candidates.sort_values("symbol").reset_index(drop=True)
        candidates.to_csv(self.paths["universe_candidates_csv"], index=False)
        return candidates

    def select_launch_pit_universe(self, candidates: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        market_cap = self.load_daily_market_cap()
        if market_cap.empty:
            market_cap = self.load_sf1_shares_market_cap(candidates)
        if market_cap.empty:
            raise DataSourceUnavailable(
                "Sharadar did not provide DAILY marketcap or SF1 shares × SEP close for launch_pit_2023. "
                "Strict launch selection requires PIT market cap or an explicit shares-outstanding fallback."
            )

        diagnostics = candidates.merge(market_cap, on="symbol", how="left")
        diagnostics["selection_as_of_date"] = self.config["universe"]["as_of_date"]
        diagnostics["selection_as_of_trade_date"] = self.config["universe"]["as_of_trade_date"]
        diagnostics["selection_method"] = diagnostics["market_cap_source"].fillna("sharadar_pit_market_cap")
        diagnostics["selection_status"] = "candidate"
        diagnostics["selection_error"] = None
        missing = diagnostics["market_cap_asof"].isna() | (pd.to_numeric(diagnostics["market_cap_asof"], errors="coerce") <= 0)
        diagnostics.loc[missing, "selection_status"] = "excluded"
        diagnostics.loc[missing, "selection_error"] = "missing_or_invalid_pit_market_cap"

        eligible = diagnostics[diagnostics["selection_error"].isna()].copy()
        eligible = eligible.sort_values("market_cap_asof", ascending=False).head(int(self.config["universe"]["top_n_by_market_cap"]))
        diagnostics.loc[diagnostics["selection_error"].isna(), "selection_status"] = "not_selected_below_top_n"
        diagnostics.loc[eligible.index, "selection_status"] = "selected"
        selected = diagnostics.loc[eligible.index].copy().sort_values("market_cap_asof", ascending=False).reset_index(drop=True)
        selected["asof_market_cap_rank"] = range(1, len(selected) + 1)
        return selected, diagnostics

    def load_daily_market_cap(self) -> pd.DataFrame:
        daily = fetch_table_frame(
            self.client,
            "DAILY",
            {
                "date": self.config["universe"]["as_of_trade_date"],
                "qopts.columns": "ticker,date,marketcap",
            },
        )
        return normalize_daily_market_cap(daily)

    def load_sf1_shares_market_cap(self, candidates: pd.DataFrame) -> pd.DataFrame:
        sf1 = fetch_table_frame(
            self.client,
            "SF1",
            {
                "datekey.lte": self.config["universe"]["as_of_trade_date"],
                "dimension": self.config.get("sharadar", {}).get("sf1_dimension", "MRQ"),
                "qopts.columns": "ticker,datekey,marketcap,sharesbas,shareswa",
            },
        )
        sf1_market_cap = normalize_sf1_market_cap(sf1)
        if sf1_market_cap.empty:
            return sf1_market_cap
        sf1_market_cap = sf1_market_cap[sf1_market_cap["symbol"].isin(set(candidates["symbol"]))]
        direct_market_cap = sf1_market_cap[sf1_market_cap["market_cap_asof"].notna()].copy()
        share_rows = sf1_market_cap[sf1_market_cap["market_cap_asof"].isna() & sf1_market_cap["shares_outstanding"].notna()].copy()
        if share_rows.empty:
            return direct_market_cap

        prices = fetch_table_frame(
            self.client,
            "SEP",
            {
                "date": self.config["universe"]["as_of_trade_date"],
                "qopts.columns": "ticker,date,close",
            },
        )
        closes = normalize_sep_close(prices)
        if closes.empty:
            return direct_market_cap
        share_rows = share_rows.merge(closes, on="symbol", how="left")
        share_rows["market_cap_asof"] = share_rows["shares_outstanding"] * share_rows["asof_close"]
        share_rows["market_cap_source"] = "sharadar_sf1_shares_x_sep_close"
        share_rows["market_cap_asof_date"] = self.config["universe"]["as_of_trade_date"]
        frames = [frame for frame in [direct_market_cap, share_rows] if not frame.empty]
        combined = pd.concat(frames, ignore_index=True, sort=False) if frames else empty_market_cap_frame()
        combined = combined.dropna(subset=["market_cap_asof"])
        return combined[["symbol", "market_cap_asof", "market_cap_asof_date", "market_cap_source", "shares_outstanding", "shares_outstanding_date"]]

    def download_symbol_prices(self, symbol: str) -> pd.DataFrame:
        frame = fetch_table_frame(
            self.client,
            "SEP",
            {
                "ticker": symbol,
                "date.gte": self.config["data"]["start_date"],
                "date.lte": self.config["data"]["end_date"],
            },
        )
        return normalize_ohlcv_frame(frame, symbol, vwap_method=self.config["data"]["vwap_method"])

    def write_launch_membership(self, universe: pd.DataFrame) -> None:
        as_of_trade_date = self.config["universe"]["as_of_trade_date"]
        rows = [
            {
                "symbol": symbol,
                "date": as_of_trade_date,
                "is_member": 1,
                "membership_type": "launch_pit_2023",
            }
            for symbol in universe.get("symbol", pd.Series(dtype=str)).astype(str).str.upper().tolist()
        ]
        pd.DataFrame(rows, columns=["symbol", "date", "is_member", "membership_type"]).to_csv(
            self.paths["membership_csv"],
            index=False,
        )


def run_sharadar_capability_probe(config: dict[str, Any], paths: dict[str, Path], client: Any) -> CapabilityProbeResult:
    tables = config.get("sharadar", {}).get("tables", DEFAULT_TABLES)
    column_rows: list[dict[str, Any]] = []
    table_errors: dict[str, str] = {}

    for table in tables:
        try:
            metadata = fetch_metadata(client, table)
        except Exception as exc:  # noqa: BLE001 - write probe evidence instead of crashing immediately.
            table_errors[table] = str(exc)
            continue
        datatable = metadata.get("datatable", metadata)
        filters = set(datatable.get("filters", []) or [])
        primary_key = set(datatable.get("primary_key", []) or [])
        for column in datatable.get("columns", []) or []:
            name = str(column.get("name", ""))
            column_rows.append(
                {
                    "table": table,
                    "column": name,
                    "type": column.get("type"),
                    "filterable": name in filters,
                    "primary_key": name in primary_key,
                }
            )

    columns = pd.DataFrame(column_rows, columns=["table", "column", "type", "filterable", "primary_key"])
    checks = build_capability_checks(columns, table_errors)
    strict_pass = all(check["status"] == "pass" for check in checks if check["required_for_strict"])
    summary = {
        "enabled": True,
        "provider": "sharadar",
        "tables_checked": list(tables),
        "table_errors": table_errors,
        "strict_capability_pass": strict_pass,
        "checks": checks,
        "headline_note": (
            "Sharadar 具备做 launch_pit_2023 的关键前提时，才允许进入严格训练；"
            "字段或订阅不足时只能输出 not_strict_pit 诊断。"
        ),
    }

    paths["provider_table_columns"].parent.mkdir(parents=True, exist_ok=True)
    columns.to_csv(paths["provider_table_columns"], index=False)
    paths["provider_capability_summary"].write_text(
        yaml.safe_dump(summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    paths["provider_capability_report"].write_text(render_capability_report(summary, columns), encoding="utf-8")
    return CapabilityProbeResult(summary=summary, columns=columns)


def write_unavailable_capability(paths: dict[str, Path], error: str) -> None:
    columns = pd.DataFrame(columns=["table", "column", "type", "filterable", "primary_key"])
    summary = {
        "enabled": True,
        "provider": "sharadar",
        "tables_checked": DEFAULT_TABLES,
        "table_errors": {"authentication": error},
        "strict_capability_pass": False,
        "checks": [
            capability_check(
                "AUTH",
                "authentication",
                False,
                True,
                "NASDAQ_DATA_LINK_API_KEY or SHARADAR_API_KEY is required before checking Sharadar tables.",
            )
        ],
        "headline_note": "无 API key 时不会回退到 nasdaq_public；strict headline 被阻断。",
    }
    paths["provider_table_columns"].parent.mkdir(parents=True, exist_ok=True)
    columns.to_csv(paths["provider_table_columns"], index=False)
    paths["provider_capability_summary"].write_text(
        yaml.safe_dump(summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    paths["provider_capability_report"].write_text(render_capability_report(summary, columns), encoding="utf-8")


def fetch_metadata(client: Any, table: str) -> dict[str, Any]:
    if hasattr(client, "metadata"):
        return client.metadata(table)
    raise TypeError("Sharadar client must provide metadata(table)")


def fetch_table_frame(client: Any, table: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    if hasattr(client, "table"):
        frame = client.table(table, params or {})
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame(frame)
    raise TypeError("Sharadar client must provide table(table, params)")


def build_capability_checks(columns: pd.DataFrame, table_errors: dict[str, str]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for table in REQUIRED_TABLES:
        checks.append(
            capability_check(
                f"T_{table}",
                "table_access",
                "pass" if table in set(columns.get("table", [])) and table not in table_errors else "fail",
                True,
                f"SHARADAR/{table} must be accessible.",
            )
        )

    tickers = table_columns(columns, "TICKERS")
    sep = table_columns(columns, "SEP")
    sf1 = table_columns(columns, "SF1")
    daily = table_columns(columns, "DAILY")
    checks.extend(
        [
            capability_check("C1", "security_master", has_any(tickers, ["isdelisted", "delisted"]), True, "TICKERS needs active/delisted status."),
            capability_check("C2", "security_master", has_any(tickers, ["category", "type", "assettype", "securitytype"]), True, "TICKERS needs security type/category."),
            capability_check("C3", "security_master", has_any(tickers, ["exchange"]), True, "TICKERS needs exchange."),
            capability_check(
                "C4",
                "security_master",
                has_any(tickers, ["firstpricedate", "listingdate", "firstquoteddate"]) and has_any(tickers, ["lastpricedate", "delistingdate", "lastquoteddate"]),
                True,
                "TICKERS needs first/last quoted or listing/delisting dates.",
            ),
            capability_check("C5", "prices", has_all(sep, ["ticker", "date", "open", "high", "low", "close", "volume"]), True, "SEP needs daily OHLCV."),
            capability_check(
                "C6",
                "market_cap",
                has_any(daily, ["marketcap", "market_cap"]) or has_any(sf1, ["sharesbas", "shareswa", "marketcap"]),
                True,
                "launch_pit_2023 needs PIT market cap or shares outstanding.",
            ),
            capability_check("C7", "fundamentals", has_any(sf1, ["datekey", "filingdate"]) and has_any(sf1, ["reportperiod", "calendardate"]), True, "SF1 needs filing/datekey and report period dates."),
            capability_check("C8", "industry", has_any(tickers, ["sector", "industry", "sicsector", "sicindustry"]), False, "Industry columns are useful but not strict until PIT status is verified."),
        ]
    )
    return checks


def capability_check(check_id: str, area: str, passed: bool | str, required_for_strict: bool, finding: str) -> dict[str, Any]:
    status = passed if isinstance(passed, str) else "pass" if passed else "fail"
    return {
        "check_id": check_id,
        "area": area,
        "status": status,
        "required_for_strict": required_for_strict,
        "finding": finding,
    }


def table_columns(columns: pd.DataFrame, table: str) -> set[str]:
    if columns.empty:
        return set()
    subset = columns[columns["table"].astype(str).str.upper().eq(table.upper())]
    return {normalize_token(value) for value in subset["column"].dropna().astype(str)}


def has_any(columns: set[str], candidates: list[str]) -> bool:
    return any(normalize_token(candidate) in columns for candidate in candidates)


def has_all(columns: set[str], candidates: list[str]) -> bool:
    return all(normalize_token(candidate) in columns for candidate in candidates)


def normalize_token(value: Any) -> str:
    return str(value).strip().lower().replace("_", "").replace("-", "").replace(" ", "")


def render_capability_report(summary: dict[str, Any], columns: pd.DataFrame) -> str:
    lines = [
        "# Sharadar Provider Capability Report",
        "",
        "本报告只判断当前 API key / 订阅 / 表字段是否足以进入严格 `launch_pit_2023` 实验。",
        "",
        f"- Provider: `{summary['provider']}`",
        f"- Strict capability pass: `{summary['strict_capability_pass']}`",
        "",
        "## Checks",
        "",
        "| Check | Area | Required | Status | Finding |",
        "|---|---|---:|---|---|",
    ]
    for check in summary["checks"]:
        lines.append(
            f"| {check['check_id']} | {check['area']} | {check['required_for_strict']} | {check['status']} | {check['finding']} |"
        )
    if summary.get("table_errors"):
        lines.extend(["", "## Table Errors", "", "```yaml", yaml.safe_dump(summary["table_errors"], sort_keys=False).strip(), "```"])
    lines.extend(["", "## Tables", ""])
    if columns.empty:
        lines.append("- No columns discovered.")
    else:
        for table, group in columns.groupby("table"):
            lines.append(f"- `{table}`: {len(group)} columns")
    lines.extend(
        [
            "",
            "## Reading",
            "",
            "通过并不代表 Sharadar 是 CRSP/Compustat 级别的学术金标准；它只代表当前字段足够构建一个比 `nasdaq_public` 严格得多的个人研究级 launch PIT 股票池。",
            "",
            "学习研究，不是投资建议。",
        ]
    )
    return "\n".join(lines) + "\n"


def normalize_tickers_frame(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    rename = rename_by_candidates(
        working.columns,
        {
            "symbol": ["ticker", "symbol"],
            "name": ["name", "companyname", "securityname"],
            "exchange": ["exchange"],
            "category": ["category", "securitytype", "assettype", "type"],
            "is_delisted": ["isdelisted", "delisted"],
            "first_quoted_date": ["firstpricedate", "listingdate", "firstquoteddate"],
            "last_quoted_date": ["lastpricedate", "delistingdate", "lastquoteddate"],
            "sector": ["sector", "sicsector"],
            "industry": ["industry", "sicindustry", "famaindustry"],
        },
    )
    working = working.rename(columns=rename)
    if "symbol" not in working:
        raise DataSourceUnavailable("SHARADAR/TICKERS is missing ticker/symbol column")
    for column in ["name", "exchange", "category", "is_delisted", "first_quoted_date", "last_quoted_date", "sector", "industry"]:
        if column not in working:
            working[column] = pd.NA
    working["symbol"] = working["symbol"].astype(str).str.upper().str.strip()
    working["is_delisted"] = working["is_delisted"].map(parse_bool_like)
    working["asset_type"] = working["category"].astype(str)
    working["is_common_equity"] = working["asset_type"].map(is_common_equity_category)
    for column in ["first_quoted_date", "last_quoted_date"]:
        working[column] = pd.to_datetime(working[column], errors="coerce").dt.date.astype("string")
    return working[
        [
            "symbol",
            "name",
            "exchange",
            "asset_type",
            "is_common_equity",
            "is_delisted",
            "first_quoted_date",
            "last_quoted_date",
            "sector",
            "industry",
        ]
    ]


def normalize_daily_market_cap(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return empty_market_cap_frame()
    working = frame.copy()
    rename = rename_by_candidates(
        working.columns,
        {
            "symbol": ["ticker", "symbol"],
            "market_cap_asof_date": ["date", "calendardate"],
            "market_cap_asof": ["marketcap", "market_cap"],
        },
    )
    working = working.rename(columns=rename)
    missing = [column for column in ["symbol", "market_cap_asof", "market_cap_asof_date"] if column not in working]
    if missing:
        return empty_market_cap_frame()
    working["symbol"] = working["symbol"].astype(str).str.upper().str.strip()
    working["market_cap_asof"] = pd.to_numeric(working["market_cap_asof"], errors="coerce")
    working["market_cap_asof_date"] = pd.to_datetime(working["market_cap_asof_date"], errors="coerce").dt.date.astype("string")
    working["market_cap_source"] = "sharadar_daily_market_cap_asof"
    working["shares_outstanding"] = pd.NA
    working["shares_outstanding_date"] = pd.NA
    return working.dropna(subset=["symbol", "market_cap_asof"])[
        ["symbol", "market_cap_asof", "market_cap_asof_date", "market_cap_source", "shares_outstanding", "shares_outstanding_date"]
    ]


def normalize_sf1_market_cap(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return empty_market_cap_frame()
    working = frame.copy()
    rename = rename_by_candidates(
        working.columns,
        {
            "symbol": ["ticker", "symbol"],
            "shares_outstanding_date": ["datekey", "filingdate"],
            "market_cap_asof": ["marketcap", "market_cap"],
            "sharesbas": ["sharesbas"],
            "shareswa": ["shareswa"],
        },
    )
    working = working.rename(columns=rename)
    if "symbol" not in working or "shares_outstanding_date" not in working:
        return empty_market_cap_frame()
    working["symbol"] = working["symbol"].astype(str).str.upper().str.strip()
    working["shares_outstanding_date"] = pd.to_datetime(working["shares_outstanding_date"], errors="coerce")
    if "market_cap_asof" in working:
        working["market_cap_asof"] = pd.to_numeric(working["market_cap_asof"], errors="coerce")
    else:
        working["market_cap_asof"] = pd.NA
    shares_columns = [column for column in ["sharesbas", "shareswa"] if column in working]
    if shares_columns:
        working["shares_outstanding"] = pd.to_numeric(working[shares_columns[0]], errors="coerce")
        for column in shares_columns[1:]:
            working["shares_outstanding"] = working["shares_outstanding"].fillna(pd.to_numeric(working[column], errors="coerce"))
    else:
        working["shares_outstanding"] = pd.NA
    working = working.dropna(subset=["symbol", "shares_outstanding_date"]).sort_values(["symbol", "shares_outstanding_date"])
    working = working.groupby("symbol", as_index=False).tail(1).copy()
    working["market_cap_asof_date"] = working["shares_outstanding_date"].dt.date.astype("string")
    working["shares_outstanding_date"] = working["shares_outstanding_date"].dt.date.astype("string")
    working["market_cap_source"] = "sharadar_sf1_market_cap"
    return working[["symbol", "market_cap_asof", "market_cap_asof_date", "market_cap_source", "shares_outstanding", "shares_outstanding_date"]]


def normalize_sep_close(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["symbol", "asof_close"])
    working = frame.copy()
    rename = rename_by_candidates(working.columns, {"symbol": ["ticker", "symbol"], "asof_close": ["close", "closeadj"]})
    working = working.rename(columns=rename)
    if "symbol" not in working or "asof_close" not in working:
        return pd.DataFrame(columns=["symbol", "asof_close"])
    working["symbol"] = working["symbol"].astype(str).str.upper().str.strip()
    working["asof_close"] = pd.to_numeric(working["asof_close"], errors="coerce")
    return working.dropna(subset=["symbol", "asof_close"])[["symbol", "asof_close"]]


def empty_market_cap_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "symbol",
            "market_cap_asof",
            "market_cap_asof_date",
            "market_cap_source",
            "shares_outstanding",
            "shares_outstanding_date",
        ]
    )


def rename_by_candidates(columns: Any, mapping: dict[str, list[str]]) -> dict[Any, str]:
    reverse: dict[str, str] = {}
    for target, candidates in mapping.items():
        for candidate in candidates:
            reverse[normalize_token(candidate)] = target
    result: dict[Any, str] = {}
    for column in columns:
        target = reverse.get(normalize_token(column))
        if target and target not in result.values():
            result[column] = target
    return result


def parse_bool_like(value: Any) -> bool:
    text = str(value).strip().lower()
    return text in {"1", "true", "t", "yes", "y"}


def is_common_equity_category(value: Any) -> bool:
    text = str(value).lower()
    if any(token in text for token in ["warrant", "right", "unit", "preferred", "note", "bond", "debenture", "etf", "fund"]):
        return False
    return any(token in text for token in ["common", "ordinary", "adr", "ads", "share", "stock"])
