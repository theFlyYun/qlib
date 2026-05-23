"""Databento adapter for strict launch-PIT US equity experiments."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yaml

from .base import (
    DataSourceUnavailable,
    PreparedData,
    normalize_ohlcv_frame,
    reset_directory,
    write_failures,
)

DATABENTO_UNAVAILABLE_MESSAGE = (
    "data.source=databento requires the `databento` Python package and DATABENTO_API_KEY "
    "in the shell environment or an ignored .env/local_secrets.env file. Install with "
    "`.venv/bin/python -m pip install databento`, then add DATABENTO_API_KEY to `.env`."
)

DEFAULT_DATASET = "EQUS.SUMMARY"
DEFAULT_SCHEMA = "ohlcv-1d"
DEFAULT_SECURITY_MASTER_START = "2016-05-17"
DEFAULT_SECURITY_MASTER_END = "2026-05-18"


@dataclass
class DatabentoCapabilityProbeResult:
    summary: dict[str, Any]
    columns: pd.DataFrame

    @property
    def strict_pass(self) -> bool:
        return bool(self.summary.get("strict_capability_pass", False))


class DatabentoClient:
    """Lazy wrapper around the official Databento Python client."""

    def __init__(self, api_key: str | None = None, module: Any | None = None, timeout_seconds: int = 30) -> None:
        self.api_key = api_key or os.environ.get("DATABENTO_API_KEY")
        if not self.api_key:
            raise DataSourceUnavailable(DATABENTO_UNAVAILABLE_MESSAGE)
        try:
            self.module = module or __import__("databento")
        except ImportError as exc:
            raise DataSourceUnavailable(DATABENTO_UNAVAILABLE_MESSAGE) from exc
        self.reference = self.module.Reference(key=self.api_key)
        self.historical = self.module.Historical(key=self.api_key)
        self.timeout_seconds = timeout_seconds
        self.reference.security_master.TIMEOUT = timeout_seconds
        self.historical.timeseries.TIMEOUT = timeout_seconds
        if hasattr(self.historical, "metadata"):
            self.historical.metadata.TIMEOUT = timeout_seconds
        for endpoint_name in ["corporate_actions", "adjustment_factors"]:
            endpoint = getattr(self.reference, endpoint_name, None)
            if endpoint is not None and hasattr(endpoint, "TIMEOUT"):
                endpoint.TIMEOUT = timeout_seconds

    def security_master_range(self, **kwargs: Any) -> pd.DataFrame:
        return to_frame(self.reference.security_master.get_range(**kwargs))

    def ohlcv_1d(self, **kwargs: Any) -> pd.DataFrame:
        return to_frame(self.historical.timeseries.get_range(**kwargs))

    def corporate_actions_sample(self, **kwargs: Any) -> pd.DataFrame:
        actions = getattr(self.reference, "corporate_actions", None)
        if actions is None or not hasattr(actions, "get_range"):
            return pd.DataFrame()
        return to_frame(actions.get_range(**kwargs))

    def adjustment_factors_sample(self, **kwargs: Any) -> pd.DataFrame:
        factors = getattr(self.reference, "adjustment_factors", None)
        if factors is None or not hasattr(factors, "get_range"):
            return pd.DataFrame()
        return to_frame(factors.get_range(**kwargs))


class DatabentoDataSource:
    def __init__(self, config: dict[str, Any], paths: dict[str, Path], client: Any | None = None) -> None:
        self.config = config
        self.paths = paths
        self.client = client

    def prepare(self) -> PreparedData:
        source_dir = self.paths["source_dir"]
        reset_directory(source_dir)
        self.paths["databento_cache_dir"].mkdir(parents=True, exist_ok=True)

        try:
            self.client = self.client or DatabentoClient(timeout_seconds=int(self.databento_config().get("timeout_seconds", 30)))
        except DataSourceUnavailable as exc:
            write_unavailable_capability(self.paths, str(exc))
            self.write_empty_artifacts()
            raise

        probe = run_databento_capability_probe(self.config, self.paths, self.client)
        if not probe.strict_pass:
            self.write_empty_artifacts()
            raise DataSourceUnavailable(
                "Databento capability probe did not pass strict PIT requirements. "
                f"See {self.paths['provider_capability_summary']}."
            )

        candidates = self.load_candidate_universe()
        selected, diagnostics = self.select_launch_pit_universe(candidates)
        diagnostics.to_csv(self.paths["universe_selection_csv"], index=False)
        selected.to_csv(self.paths["universe_csv"], index=False)

        failures: list[dict[str, Any]] = []
        universe_rows: list[dict[str, Any]] = []
        print(f"Preparing Databento OHLCV for {len(selected)} selected symbols...")
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
            enriched.update({"first_date": qlib_frame["date"].min(), "last_date": qlib_frame["date"].max(), "history_rows": len(qlib_frame)})
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
                "source": "databento",
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
        frame = fetch_security_master_frame(
            self.client,
            start=self.databento_config().get("security_master_start", self.config["data"]["start_date"]),
            end=self.databento_config().get("security_master_end", DEFAULT_SECURITY_MASTER_END),
            countries=self.databento_config().get("countries", ["US"]),
            exchanges=self.databento_config().get("exchanges"),
            security_types=self.databento_config().get("security_types"),
            stype_in=self.databento_config().get("stype_in", "raw_symbol"),
        )
        if frame.empty:
            raise DataSourceUnavailable("Databento security master returned no rows")
        normalized = normalize_security_master_frame(frame, self.config["universe"]["as_of_trade_date"])
        normalized.to_csv(self.paths["security_master_csv"], index=False)

        as_of_trade_date = pd.Timestamp(self.config["universe"]["as_of_trade_date"]).normalize()
        exchange = self.config["universe"].get("exchange")
        candidates = normalized.copy()
        if exchange:
            candidates = candidates[
                candidates[["exchange", "primary_exchange", "operating_mic"]]
                .astype(str)
                .apply(lambda row: any(str(value).upper() in {str(exchange).upper(), "XNAS", "NASDAQ"} for value in row), axis=1)
            ]
        candidates = candidates[candidates["symbol"].notna() & candidates["symbol"].astype(str).ne("")]
        candidates = candidates[candidates["is_common_equity"]]
        candidates = candidates[candidates["first_quoted_date"].isna() | (pd.to_datetime(candidates["first_quoted_date"]) <= as_of_trade_date)]
        candidates = candidates[candidates["last_quoted_date"].isna() | (pd.to_datetime(candidates["last_quoted_date"]) >= as_of_trade_date)]
        candidates = candidates.sort_values("symbol").reset_index(drop=True)
        candidates.to_csv(self.paths["universe_candidates_csv"], index=False)
        return candidates

    def select_launch_pit_universe(self, candidates: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        closes = self.load_asof_closes(candidates["symbol"].astype(str).str.upper().tolist())
        diagnostics = candidates.merge(closes, on="symbol", how="left")
        diagnostics["selection_as_of_date"] = self.config["universe"]["as_of_date"]
        diagnostics["selection_as_of_trade_date"] = self.config["universe"]["as_of_trade_date"]
        diagnostics["selection_method"] = "databento_security_master_shares_x_ohlcv_close"
        diagnostics["selection_status"] = "candidate"
        diagnostics["selection_error"] = None
        diagnostics["market_cap_source"] = "databento_shares_outstanding_x_asof_close"
        diagnostics["market_cap_asof_date"] = self.config["universe"]["as_of_trade_date"]
        diagnostics["market_cap_asof"] = pd.to_numeric(diagnostics["shares_outstanding"], errors="coerce") * pd.to_numeric(
            diagnostics["asof_close"],
            errors="coerce",
        )
        missing = diagnostics["market_cap_asof"].isna() | (diagnostics["market_cap_asof"] <= 0)
        diagnostics.loc[missing, "selection_status"] = "excluded"
        diagnostics.loc[missing, "selection_error"] = "missing_or_invalid_pit_market_cap"

        eligible = diagnostics[diagnostics["selection_error"].isna()].copy()
        eligible = eligible.sort_values("market_cap_asof", ascending=False).head(int(self.config["universe"]["top_n_by_market_cap"]))
        diagnostics.loc[diagnostics["selection_error"].isna(), "selection_status"] = "not_selected_below_top_n"
        diagnostics.loc[eligible.index, "selection_status"] = "selected"
        selected = diagnostics.loc[eligible.index].copy().sort_values("market_cap_asof", ascending=False).reset_index(drop=True)
        selected["asof_market_cap_rank"] = range(1, len(selected) + 1)
        return selected, diagnostics

    def load_asof_closes(self, symbols: list[str]) -> pd.DataFrame:
        rows: list[pd.DataFrame] = []
        for batch in chunked(symbols, int(self.databento_config().get("batch_size", 1000))):
            frame = fetch_ohlcv_frame(
                self.client,
                dataset=self.databento_config().get("dataset", DEFAULT_DATASET),
                schema=self.databento_config().get("schema", DEFAULT_SCHEMA),
                symbols=batch,
                start=self.config["universe"]["as_of_trade_date"],
                end=asof_ohlcv_end_date(self.config["universe"]["as_of_trade_date"]),
                stype_out=self.databento_config().get("stype_out", "raw_symbol"),
            )
            normalized = normalize_databento_ohlcv_frame(frame)
            if not normalized.empty:
                rows.append(normalized)
        if not rows:
            return pd.DataFrame(columns=["symbol", "asof_close"])
        prices = pd.concat(rows, ignore_index=True)
        as_of = pd.Timestamp(self.config["universe"]["as_of_trade_date"]).normalize()
        prices = prices[pd.to_datetime(prices["date"]) <= as_of].sort_values(["symbol", "date"])
        latest = prices.groupby("symbol", as_index=False).tail(1).copy()
        latest = latest.rename(columns={"close": "asof_close"})
        return latest[["symbol", "asof_close"]]

    def download_symbol_prices(self, symbol: str) -> pd.DataFrame:
        frame = fetch_ohlcv_frame(
            self.client,
            dataset=self.databento_config().get("dataset", DEFAULT_DATASET),
            schema=self.databento_config().get("schema", DEFAULT_SCHEMA),
            symbols=[symbol],
            start=self.config["data"]["start_date"],
            end=self.config["data"]["end_date"],
            stype_out=self.databento_config().get("stype_out", "raw_symbol"),
        )
        normalized = normalize_databento_ohlcv_frame(frame)
        normalized = normalized[normalized["symbol"].astype(str).str.upper().eq(symbol.upper())]
        return normalize_ohlcv_frame(normalized, symbol, vwap_method=self.config["data"]["vwap_method"])

    def write_launch_membership(self, universe: pd.DataFrame) -> None:
        rows = [
            {"symbol": symbol, "date": self.config["universe"]["as_of_trade_date"], "is_member": 1, "membership_type": "launch_pit_2023"}
            for symbol in universe.get("symbol", pd.Series(dtype=str)).astype(str).str.upper().tolist()
        ]
        pd.DataFrame(rows, columns=["symbol", "date", "is_member", "membership_type"]).to_csv(self.paths["membership_csv"], index=False)

    def databento_config(self) -> dict[str, Any]:
        return self.config.get("databento", {})


def run_databento_capability_probe(config: dict[str, Any], paths: dict[str, Path], client: Any) -> DatabentoCapabilityProbeResult:
    column_rows: list[dict[str, Any]] = []
    table_errors: dict[str, str] = {}
    samples: dict[str, pd.DataFrame] = {}

    sample_calls = {
        "security_master": lambda: fetch_security_master_frame(
            client,
            start=config["universe"]["as_of_trade_date"],
            end=asof_ohlcv_end_date(config["universe"]["as_of_trade_date"]),
            countries=config.get("databento", {}).get("countries", ["US"]),
            symbols=config.get("databento", {}).get("probe_symbols", ["AAPL"]),
            stype_in=config.get("databento", {}).get("stype_in", "raw_symbol"),
        ),
        "ohlcv_1d": lambda: fetch_ohlcv_frame(
            client,
            dataset=config.get("databento", {}).get("dataset", DEFAULT_DATASET),
            schema=config.get("databento", {}).get("schema", DEFAULT_SCHEMA),
            symbols=config.get("databento", {}).get("probe_symbols", ["AAPL"]),
            start=config["universe"]["as_of_trade_date"],
            end=asof_ohlcv_end_date(config["universe"]["as_of_trade_date"]),
            stype_out=config.get("databento", {}).get("stype_out", "raw_symbol"),
        ),
        "corporate_actions": lambda: fetch_corporate_actions_sample(client, config),
        "adjustment_factors": lambda: fetch_adjustment_factors_sample(client, config),
    }
    for component, call in sample_calls.items():
        try:
            frame = call()
            samples[component] = frame
        except Exception as exc:  # noqa: BLE001 - probe should record entitlement/API failures.
            table_errors[component] = str(exc)
            frame = pd.DataFrame()
        for column in frame.columns:
            column_rows.append({"table": component, "column": column, "type": str(frame[column].dtype), "filterable": None, "primary_key": None})
        if (
            component == "security_master"
            and component in table_errors
            and config.get("databento", {}).get("stop_probe_on_security_master_error", True)
        ):
            for skipped_component in ["ohlcv_1d", "corporate_actions", "adjustment_factors"]:
                table_errors.setdefault(skipped_component, "skipped because security_master failed; strict PIT launch universe is unavailable")
            break

    columns = pd.DataFrame(column_rows, columns=["table", "column", "type", "filterable", "primary_key"])
    checks = build_capability_checks(columns, table_errors)
    strict_pass = all(check["status"] == "pass" for check in checks if check["required_for_strict"])
    summary = {
        "enabled": True,
        "provider": "databento",
        "tables_checked": list(sample_calls),
        "table_errors": table_errors,
        "strict_capability_pass": strict_pass,
        "checks": checks,
        "headline_note": "Databento 只有在 security master、OHLCV、shares outstanding 和 corporate actions 能力通过后，才允许进入 strict launch PIT 训练。",
    }
    write_capability_outputs(paths, summary, columns)
    return DatabentoCapabilityProbeResult(summary=summary, columns=columns)


def write_unavailable_capability(paths: dict[str, Path], error: str) -> None:
    columns = pd.DataFrame(columns=["table", "column", "type", "filterable", "primary_key"])
    summary = {
        "enabled": True,
        "provider": "databento",
        "tables_checked": ["security_master", "ohlcv_1d", "corporate_actions", "adjustment_factors"],
        "table_errors": {"authentication": error},
        "strict_capability_pass": False,
        "checks": [
            capability_check(
                "AUTH",
                "authentication",
                False,
                True,
                "DATABENTO_API_KEY and the databento Python package are required before checking Databento datasets.",
            )
        ],
        "headline_note": "无 Databento key/package 时不会回退到 nasdaq_public；strict headline 被阻断。",
    }
    write_capability_outputs(paths, summary, columns)


def write_capability_outputs(paths: dict[str, Path], summary: dict[str, Any], columns: pd.DataFrame) -> None:
    paths["provider_table_columns"].parent.mkdir(parents=True, exist_ok=True)
    columns.to_csv(paths["provider_table_columns"], index=False)
    paths["provider_capability_summary"].write_text(yaml.safe_dump(summary, allow_unicode=True, sort_keys=False), encoding="utf-8")
    paths["provider_capability_report"].write_text(render_capability_report(summary, columns), encoding="utf-8")


def build_capability_checks(columns: pd.DataFrame, table_errors: dict[str, str]) -> list[dict[str, Any]]:
    security_master = table_columns(columns, "security_master")
    ohlcv = table_columns(columns, "ohlcv_1d")
    corporate_actions = table_columns(columns, "corporate_actions")
    adjustment_factors = table_columns(columns, "adjustment_factors")
    return [
        capability_check("D1", "security_master", "security_master" not in table_errors and bool(security_master), True, "Reference security_master must be accessible."),
        capability_check("D2", "security_master", has_any(security_master, ["listing_date", "start_date", "open_date"]) and has_any(security_master, ["delisting_date", "end_date", "close_date"]), True, "Security master needs listing and delisting dates."),
        capability_check("D3", "security_master", has_any(security_master, ["security_type"]) and has_any(security_master, ["exchange", "primary_exchange", "operating_mic"]), True, "Security master needs security type and exchange/listing venue."),
        capability_check("D4", "market_cap", has_any(security_master, ["new_shares_outstanding", "shares_outstanding", "old_shares_outstanding"]), True, "launch_pit_2023 needs PIT shares outstanding."),
        capability_check("D5", "prices", "ohlcv_1d" not in table_errors and has_all(ohlcv, ["open", "high", "low", "close", "volume"]), True, "EQUS.SUMMARY ohlcv-1d needs daily OHLCV."),
        capability_check("D6", "corporate_actions", "corporate_actions" not in table_errors and bool(corporate_actions), True, "Corporate actions should be accessible for split/dividend/delisting audit."),
        capability_check("D7", "adjustment_factors", "adjustment_factors" not in table_errors and bool(adjustment_factors), False, "Adjustment factors are useful for price口径 audit; first version can continue with explicit unadjusted/summary price note."),
    ]


def capability_check(check_id: str, area: str, passed: bool | str, required_for_strict: bool, finding: str) -> dict[str, Any]:
    status = passed if isinstance(passed, str) else "pass" if passed else "fail"
    return {"check_id": check_id, "area": area, "status": status, "required_for_strict": required_for_strict, "finding": finding}


def fetch_security_master_frame(client: Any, **kwargs: Any) -> pd.DataFrame:
    if hasattr(client, "security_master_range"):
        compacted = compact_kwargs(kwargs)
        symbols = compacted.get("symbols")
        if isinstance(symbols, list) and len(symbols) == 1:
            compacted["symbols"] = symbols[0]
        return to_frame(client.security_master_range(**compacted))
    raise TypeError("Databento client must provide security_master_range(**kwargs)")


def fetch_ohlcv_frame(client: Any, **kwargs: Any) -> pd.DataFrame:
    if hasattr(client, "ohlcv_1d"):
        return to_frame(client.ohlcv_1d(**compact_kwargs(kwargs)))
    raise TypeError("Databento client must provide ohlcv_1d(**kwargs)")


def fetch_corporate_actions_sample(client: Any, config: dict[str, Any]) -> pd.DataFrame:
    if not hasattr(client, "corporate_actions_sample"):
        return pd.DataFrame()
    return to_frame(
        client.corporate_actions_sample(
            symbols=config.get("databento", {}).get("probe_symbols", ["AAPL"]),
            countries=config.get("databento", {}).get("countries", ["US"]),
            start=config["universe"]["as_of_trade_date"],
            end=config["data"]["end_date"],
        )
    )


def fetch_adjustment_factors_sample(client: Any, config: dict[str, Any]) -> pd.DataFrame:
    if not hasattr(client, "adjustment_factors_sample"):
        return pd.DataFrame()
    return to_frame(
        client.adjustment_factors_sample(
            symbols=config.get("databento", {}).get("probe_symbols", ["AAPL"]),
            countries=config.get("databento", {}).get("countries", ["US"]),
            start=config["universe"]["as_of_trade_date"],
            end=config["data"]["end_date"],
        )
    )


def to_frame(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if hasattr(value, "to_df"):
        return value.to_df().reset_index()
    if value is None:
        return pd.DataFrame()
    return pd.DataFrame(value)


def compact_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value is not None}


def asof_ohlcv_end_date(as_of_trade_date: str) -> str:
    """Request only a tiny date window when computing launch-day market cap."""
    return (pd.Timestamp(as_of_trade_date).normalize() + pd.Timedelta(days=7)).date().isoformat()


def normalize_security_master_frame(frame: pd.DataFrame, as_of_trade_date: str) -> pd.DataFrame:
    if frame.empty:
        return empty_security_master_frame()
    working = frame.copy()
    rename = rename_by_candidates(
        working.columns,
        {
            "symbol": ["nasdaq_symbol", "symbol", "raw_symbol", "local_code"],
            "name": ["issuer_name", "security_description", "name"],
            "exchange": ["exchange"],
            "primary_exchange": ["primary_exchange"],
            "operating_mic": ["operating_mic", "segment_mic"],
            "asset_type": ["security_type"],
            "first_quoted_date": ["listing_date", "start_date", "open_date"],
            "last_quoted_date": ["delisting_date", "end_date", "close_date"],
            "listing_status": ["listing_status", "global_status"],
            "shares_outstanding": ["new_shares_outstanding", "shares_outstanding", "old_shares_outstanding"],
            "shares_outstanding_date": ["new_outstanding_date", "old_outstanding_date", "effective_date", "event_date"],
            "cik": ["cik"],
            "naics": ["naics"],
        },
    )
    working = working.rename(columns=rename)
    for column in [
        "symbol",
        "name",
        "exchange",
        "primary_exchange",
        "operating_mic",
        "asset_type",
        "first_quoted_date",
        "last_quoted_date",
        "listing_status",
        "shares_outstanding",
        "shares_outstanding_date",
        "cik",
        "naics",
    ]:
        if column not in working:
            working[column] = pd.NA
    working["symbol"] = working["symbol"].astype(str).str.upper().str.strip()
    working["shares_outstanding"] = pd.to_numeric(working["shares_outstanding"], errors="coerce")
    for column in ["first_quoted_date", "last_quoted_date", "shares_outstanding_date"]:
        working[column] = pd.to_datetime(working[column], errors="coerce")
    as_of = pd.Timestamp(as_of_trade_date).normalize()
    if "ts_record" in working:
        working["sort_ts"] = pd.to_datetime(working["ts_record"], errors="coerce")
    elif "effective_date" in working:
        working["sort_ts"] = pd.to_datetime(working["effective_date"], errors="coerce")
    else:
        working["sort_ts"] = working["shares_outstanding_date"]
    working = working[working["symbol"].notna() & working["symbol"].ne("")]
    working = working[working["sort_ts"].isna() | (working["sort_ts"] <= as_of)]
    working = working.sort_values(["symbol", "sort_ts"]).groupby("symbol", as_index=False).tail(1).copy()
    working["is_delisted"] = working["last_quoted_date"].notna() | working["listing_status"].astype(str).str.lower().str.contains("delist|inactive|terminated|deleted", regex=True, na=False)
    working["is_common_equity"] = working["asset_type"].map(is_common_equity_type)
    for column in ["first_quoted_date", "last_quoted_date", "shares_outstanding_date"]:
        working[column] = working[column].dt.date.astype("string")
    return working[
        [
            "symbol",
            "name",
            "exchange",
            "primary_exchange",
            "operating_mic",
            "asset_type",
            "is_common_equity",
            "is_delisted",
            "first_quoted_date",
            "last_quoted_date",
            "shares_outstanding",
            "shares_outstanding_date",
            "cik",
            "naics",
        ]
    ]


def normalize_databento_ohlcv_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["date", "symbol", "open", "high", "low", "close", "vwap", "volume"])
    working = frame.copy().reset_index(drop=True)
    rename = rename_by_candidates(
        working.columns,
        {
            "date": ["date", "ts_event", "timestamp", "index"],
            "symbol": ["symbol", "raw_symbol", "nasdaq_symbol", "instrument_id"],
            "open": ["open"],
            "high": ["high"],
            "low": ["low"],
            "close": ["close"],
            "volume": ["volume"],
        },
    )
    working = working.rename(columns=rename)
    missing = [column for column in ["date", "symbol", "open", "high", "low", "close", "volume"] if column not in working]
    if missing:
        raise ValueError(f"Databento OHLCV missing column(s): {', '.join(missing)}")
    working["date"] = pd.to_datetime(working["date"], errors="coerce").dt.date.astype("string")
    working["symbol"] = working["symbol"].astype(str).str.upper().str.strip()
    for column in ["open", "high", "low", "close", "volume"]:
        working[column] = pd.to_numeric(working[column], errors="coerce")
    working = working.dropna(subset=["date", "symbol", "open", "high", "low", "close", "volume"])
    working["vwap"] = working[["open", "high", "low", "close"]].mean(axis=1)
    return working[["date", "symbol", "open", "high", "low", "close", "vwap", "volume"]]


def render_capability_report(summary: dict[str, Any], columns: pd.DataFrame) -> str:
    lines = [
        "# Databento Provider Capability Report",
        "",
        "本报告只判断当前 `DATABENTO_API_KEY`、Python client 和 entitlement 是否足以进入严格 `launch_pit_2023` 实验。",
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
        lines.append(f"| {check['check_id']} | {check['area']} | {check['required_for_strict']} | {check['status']} | {check['finding']} |")
    if summary.get("table_errors"):
        lines.extend(["", "## Table Errors", "", "```yaml", yaml.safe_dump(summary["table_errors"], sort_keys=False).strip(), "```"])
    lines.extend(["", "## Components", ""])
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
            "Databento 在本项目中先作为股票池、证券主数据、OHLCV 和历史市值底座；EDGAR/FRED 仍负责财报和宏观。",
            "",
            "学习研究，不是投资建议。",
        ]
    )
    return "\n".join(lines) + "\n"


def empty_security_master_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "symbol",
            "name",
            "exchange",
            "primary_exchange",
            "operating_mic",
            "asset_type",
            "is_common_equity",
            "is_delisted",
            "first_quoted_date",
            "last_quoted_date",
            "shares_outstanding",
            "shares_outstanding_date",
            "cik",
            "naics",
        ]
    )


def table_columns(columns: pd.DataFrame, table: str) -> set[str]:
    if columns.empty:
        return set()
    subset = columns[columns["table"].astype(str).str.upper().eq(table.upper())]
    return {normalize_token(value) for value in subset["column"].dropna().astype(str)}


def has_any(columns: set[str], candidates: list[str]) -> bool:
    return any(normalize_token(candidate) in columns for candidate in candidates)


def has_all(columns: set[str], candidates: list[str]) -> bool:
    return all(normalize_token(candidate) in columns for candidate in candidates)


def rename_by_candidates(columns: Iterable[Any], mapping: dict[str, list[str]]) -> dict[Any, str]:
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


def normalize_token(value: Any) -> str:
    return str(value).strip().lower().replace("_", "").replace("-", "").replace(" ", "")


def is_common_equity_type(value: Any) -> bool:
    text = str(value).lower()
    if any(token in text for token in ["etf", "fund", "warrant", "right", "unit", "preferred", "bond", "note", "option"]):
        return False
    return any(token in text for token in ["stock", "common", "ordinary", "equity", "share", "adr", "ads"])


def chunked(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]
