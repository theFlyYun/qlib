from __future__ import annotations

import builtins
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from analysis.nasdaq_top500_score.data_sources.base import QLIB_SOURCE_COLUMNS, DataSourceUnavailable
from analysis.nasdaq_top500_score.data_sources.norgate import NorgateClient, NorgateDataSource


def make_config() -> dict[str, Any]:
    return {
        "universe": {
            "index_name": "S&P 500",
            "index_symbol": "$SPX",
            "candidate_databases": ["US Equities", "US Equities Delisted"],
            "min_history_rows": 2,
        },
        "data": {
            "source": "norgate",
            "start_date": "2020-01-01",
            "end_date": "latest",
            "freq": "day",
            "price_adjustment": "TOTALRETURN",
            "padding": "NONE",
            "vwap_method": "ohlc_mean",
        },
    }


def make_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "source_dir": tmp_path / "qlib_source_csv",
        "universe_csv": tmp_path / "universe.csv",
        "membership_csv": tmp_path / "membership.csv",
        "failures_csv": tmp_path / "download_failures.csv",
    }


class FakeNorgateClient:
    def __init__(self) -> None:
        self.price_calls: list[str] = []

    def enum_value(self, enum_name: str, value_name: str) -> str:
        return f"{enum_name}.{value_name}"

    def database_symbols(self, database_name: str) -> list[str]:
        if database_name == "US Equities":
            return ["AAA", "BBB"]
        if database_name == "US Equities Delisted":
            return ["DDD", "BAD"]
        return []

    def price_timeseries(self, symbol: str, **kwargs: Any) -> pd.DataFrame:
        self.price_calls.append(symbol)
        if symbol == "BBB":
            return pd.DataFrame()
        dates = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-06"])
        return pd.DataFrame(
            {
                "Open": [10.0, 11.0, 12.0, 13.0],
                "High": [11.0, 12.0, 13.0, 14.0],
                "Low": [9.0, 10.0, 11.0, 12.0],
                "Close": [10.5, 11.5, 12.5, 13.5],
                "Volume": [1000, 1100, 1200, 1300],
            },
            index=pd.Index(dates, name="Date"),
        )

    def index_constituent_timeseries(self, symbol: str, index_name: str, **kwargs: Any) -> pd.DataFrame:
        frame = kwargs["pandas_dataframe"].copy()
        membership = {
            "AAA": [0, 1, 1, 0],
            "DDD": [1, 1, 0, 0],
            "BAD": [0, 0, 0, 0],
        }[symbol]
        frame["S&P 500 Constituent"] = membership
        return frame

    def optional_value(self, function_name: str, symbol: str, **kwargs: Any) -> Any:
        values = {
            "assetid": f"asset-{symbol}",
            "security_name": f"{symbol} Corp",
            "exchange_name": "NYSE",
            "first_quoted_date": "2010-01-01",
            "last_quoted_date": "2020-01-06" if symbol == "DDD" else None,
        }
        return values.get(function_name)


def test_norgate_adapter_filters_historical_membership_and_writes_qlib_csv(tmp_path: Path) -> None:
    source = NorgateDataSource(make_config(), make_paths(tmp_path), client=FakeNorgateClient())

    prepared = source.prepare()

    assert set(prepared.universe["symbol"]) == {"AAA", "DDD"}
    assert bool(prepared.universe.set_index("symbol").loc["DDD", "is_delisted"]) is True

    aaa = pd.read_csv(tmp_path / "qlib_source_csv" / "AAA.csv")
    assert list(aaa.columns) == QLIB_SOURCE_COLUMNS
    assert aaa["date"].tolist() == ["2020-01-02", "2020-01-03"]
    assert aaa["vwap"].tolist() == [11.125, 12.125]

    membership = pd.read_csv(tmp_path / "membership.csv")
    assert set(membership.columns) == {"symbol", "date", "is_member"}
    assert set(membership["symbol"]) == {"AAA", "DDD"}

    failures = pd.read_csv(tmp_path / "download_failures.csv")
    assert set(failures["symbol"]) == {"BBB", "BAD"}
    assert "no price rows" in failures.set_index("symbol").loc["BBB", "error"]
    assert "no S&P 500 membership rows" in failures.set_index("symbol").loc["BAD", "error"]


def test_norgate_client_reports_readable_error_when_package_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "norgatedata":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(DataSourceUnavailable, match="Windows"):
        NorgateClient()
