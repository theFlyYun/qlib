"""Norgate Data adapter for historical constituent-aware Qlib source CSVs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .base import (
    DataSourceUnavailable,
    PreparedData,
    normalize_ohlcv_frame,
    reset_directory,
    write_failures,
)

NORGATE_UNAVAILABLE_MESSAGE = (
    "data.source=norgate requires Microsoft Windows, Norgate Data Updater running, "
    "an active Norgate subscription, and `pip install norgatedata`. This Mac setup can "
    "run adapter tests, but cannot validate the real Norgate API."
)


class NorgateClient:
    """Small wrapper that keeps the optional Windows-only dependency lazy."""

    def __init__(self) -> None:
        try:
            import norgatedata  # type: ignore[import-not-found]
        except ImportError as exc:
            raise DataSourceUnavailable(NORGATE_UNAVAILABLE_MESSAGE) from exc
        self.module = norgatedata

    def enum_value(self, enum_name: str, value_name: str) -> Any:
        enum_type = getattr(self.module, enum_name)
        return getattr(enum_type, value_name)

    def database_symbols(self, database_name: str) -> list[Any]:
        return list(self.module.database_symbols(database_name))

    def price_timeseries(self, symbol: str, **kwargs: Any) -> pd.DataFrame:
        return self.module.price_timeseries(symbol, **kwargs)

    def index_constituent_timeseries(self, symbol: str, index_name: str, **kwargs: Any) -> pd.DataFrame:
        return self.module.index_constituent_timeseries(symbol, index_name, **kwargs)

    def optional_value(self, function_name: str, symbol: str, **kwargs: Any) -> Any:
        function = getattr(self.module, function_name, None)
        if function is None:
            return None
        try:
            return function(symbol, **kwargs)
        except Exception:  # noqa: BLE001 - metadata should not block price ingestion.
            return None


class NorgateDataSource:
    def __init__(self, config: dict[str, Any], paths: dict[str, Path], client: Any | None = None) -> None:
        self.config = config
        self.paths = paths
        self.client = client or NorgateClient()

    def prepare(self) -> PreparedData:
        source_dir = self.paths["source_dir"]
        reset_directory(source_dir)

        candidates = self.load_candidates()
        failures: list[dict[str, Any]] = []
        universe_rows: list[dict[str, Any]] = []
        membership_rows: list[dict[str, Any]] = []

        print(f"Preparing Norgate OHLCV for {len(candidates)} candidate symbols...")
        for index, candidate in enumerate(candidates, start=1):
            symbol = candidate["symbol"]
            try:
                qlib_frame, universe_row, membership_frame = self.prepare_symbol(candidate)
            except Exception as exc:  # noqa: BLE001 - keep batch ingestion resumable.
                failures.append({"symbol": symbol, "rows": 0, "error": str(exc)})
                continue

            if qlib_frame.empty:
                failures.append({"symbol": symbol, "rows": 0, "error": "no historical constituent rows"})
                continue

            min_history_rows = int(self.config["universe"]["min_history_rows"])
            if len(qlib_frame) < min_history_rows:
                failures.append({"symbol": symbol, "rows": len(qlib_frame), "error": f"history < {min_history_rows} rows"})
                continue

            qlib_frame.to_csv(source_dir / f"{symbol}.csv", index=False)
            universe_rows.append(universe_row)
            membership_rows.extend(membership_frame.to_dict("records"))
            if index % 250 == 0 or index == len(candidates):
                print(f"Prepared {index}/{len(candidates)}; usable: {len(universe_rows)}; failures/skips: {len(failures)}")

        universe = pd.DataFrame(universe_rows)
        universe.to_csv(self.paths["universe_csv"], index=False)
        membership = pd.DataFrame(membership_rows)
        membership.to_csv(self.paths["membership_csv"], index=False)
        failures_frame = write_failures(self.paths["failures_csv"], failures)
        return PreparedData(
            universe=universe,
            failures=failures_frame,
            metadata={
                "source": "norgate",
                "membership_csv": str(self.paths["membership_csv"]),
                "candidate_count": len(candidates),
            },
        )

    def load_candidates(self) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for database_name in self.config["universe"]["candidate_databases"]:
            for item in self.client.database_symbols(database_name):
                symbol = self.extract_symbol(item)
                if not symbol:
                    continue
                seen.setdefault(
                    symbol,
                    {
                        "symbol": symbol,
                        "source_database": database_name,
                        "is_delisted": "delisted" in database_name.lower(),
                    },
                )
        return list(seen.values())

    @staticmethod
    def extract_symbol(item: Any) -> str:
        if isinstance(item, dict):
            value = item.get("symbol") or item.get("Symbol")
        else:
            value = item
        return str(value).strip() if value is not None else ""

    def prepare_symbol(self, candidate: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
        symbol = candidate["symbol"]
        price_frame = self.fetch_price_frame(symbol)
        if price_frame.empty:
            raise ValueError("no price rows")

        membership_frame = self.fetch_membership_frame(symbol, price_frame)
        member_column = self.find_membership_column(membership_frame)
        if member_column is None:
            raise ValueError("no historical constituent membership column")

        working = membership_frame.copy()
        working[member_column] = pd.to_numeric(working[member_column], errors="coerce").fillna(0).astype(int)
        member_dates = working[working[member_column] == 1]
        if member_dates.empty:
            raise ValueError("no S&P 500 membership rows")

        qlib_frame = normalize_ohlcv_frame(member_dates, symbol, vwap_method=self.config["data"]["vwap_method"])
        membership_sidecar = self.build_membership_sidecar(symbol, working, member_column)
        universe_row = self.build_universe_row(candidate, qlib_frame, membership_sidecar)
        return qlib_frame, universe_row, membership_sidecar

    def fetch_price_frame(self, symbol: str) -> pd.DataFrame:
        kwargs: dict[str, Any] = {
            "stock_price_adjustment_setting": self.enum_value("StockPriceAdjustmentType", self.config["data"]["price_adjustment"]),
            "padding_setting": self.enum_value("PaddingType", self.config["data"]["padding"]),
            "start_date": self.config["data"]["start_date"],
            "timeseriesformat": "pandas-dataframe",
        }
        end_date = self.config["data"].get("end_date")
        if end_date and end_date != "latest":
            kwargs["end_date"] = end_date
        return self.client.price_timeseries(symbol, **kwargs)

    def fetch_membership_frame(self, symbol: str, price_frame: pd.DataFrame) -> pd.DataFrame:
        index_name = self.config["universe"].get("index_name") or self.config["universe"]["index_symbol"]
        return self.client.index_constituent_timeseries(
            symbol,
            index_name,
            padding_setting=self.enum_value("PaddingType", self.config["data"]["padding"]),
            pandas_dataframe=price_frame,
            timeseriesformat="pandas-dataframe",
        )

    def enum_value(self, enum_name: str, value_name: str) -> Any:
        if hasattr(self.client, "enum_value"):
            return self.client.enum_value(enum_name, value_name)
        enum_type = getattr(self.client, enum_name)
        return getattr(enum_type, value_name)

    @staticmethod
    def find_membership_column(frame: pd.DataFrame) -> str | None:
        candidates = []
        for column in frame.columns:
            key = str(column).strip().lower().replace(" ", "_")
            if key in {"index_constituent", "index_constituent_timeseries", "in_index", "is_member", "member"}:
                candidates.append(column)
            elif "constituent" in key or "member" in key:
                candidates.append(column)
        if candidates:
            return str(candidates[-1])
        numeric_columns = [column for column in frame.columns if pd.api.types.is_numeric_dtype(frame[column])]
        for column in reversed(numeric_columns):
            values = set(pd.Series(frame[column]).dropna().astype(int).unique())
            if values.issubset({0, 1}):
                return str(column)
        return None

    @staticmethod
    def build_membership_sidecar(symbol: str, frame: pd.DataFrame, member_column: str) -> pd.DataFrame:
        working = frame.copy()
        if "date" not in working.columns:
            working = working.reset_index()
        date_column = next(
            column for column in working.columns if str(column).lower() in {"date", "datetime", "timestamp", "index"}
        )
        sidecar = pd.DataFrame(
            {
                "symbol": symbol,
                "date": pd.to_datetime(working[date_column]).dt.date.astype(str),
                "is_member": pd.to_numeric(working[member_column], errors="coerce").fillna(0).astype(int),
            }
        )
        return sidecar.sort_values("date").reset_index(drop=True)

    def build_universe_row(
        self,
        candidate: dict[str, Any],
        qlib_frame: pd.DataFrame,
        membership_sidecar: pd.DataFrame,
    ) -> dict[str, Any]:
        symbol = candidate["symbol"]
        member_dates = membership_sidecar[membership_sidecar["is_member"] == 1]["date"]
        return {
            "symbol": symbol,
            "assetid": self.optional_value("assetid", symbol),
            "name": self.optional_value("security_name", symbol),
            "exchange": self.optional_value("exchange_name", symbol),
            "source_database": candidate["source_database"],
            "is_delisted": candidate["is_delisted"],
            "first_quoted_date": self.optional_value("first_quoted_date", symbol, datetimeformat="iso"),
            "last_quoted_date": self.optional_value("last_quoted_date", symbol, datetimeformat="iso"),
            "membership_start": member_dates.min() if not member_dates.empty else None,
            "membership_end": member_dates.max() if not member_dates.empty else None,
            "rows": len(qlib_frame),
        }

    def optional_value(self, function_name: str, symbol: str, **kwargs: Any) -> Any:
        if hasattr(self.client, "optional_value"):
            return self.client.optional_value(function_name, symbol, **kwargs)
        function = getattr(self.client, function_name, None)
        if function is None:
            return None
        try:
            return function(symbol, **kwargs)
        except Exception:  # noqa: BLE001 - metadata should not block price ingestion.
            return None
