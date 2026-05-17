"""Nasdaq public endpoint adapter used by the current learning baseline."""

from __future__ import annotations

import concurrent.futures
import csv
import io
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from .base import PreparedData, parse_float, reset_directory, write_failures

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
NASDAQ_SCREENER_URL = "https://api.nasdaq.com/api/screener/stocks"
NASDAQ_HISTORICAL_URL = "https://api.nasdaq.com/api/quote/{symbol}/historical"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
}


def fetch_json(url: str, *, params: dict[str, str] | None = None, referer: str = "", retries: int = 3) -> dict:
    last_error: Exception | None = None
    headers = {**HEADERS}
    if referer:
        headers["Referer"] = referer
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 - public endpoints are occasionally flaky.
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def fetch_text(url: str, *, retries: int = 3) -> str:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as exc:  # noqa: BLE001 - public endpoints are occasionally flaky.
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


class NasdaqPublicDataSource:
    def __init__(self, config: dict[str, Any], paths: dict[str, Path]) -> None:
        self.config = config
        self.paths = paths

    def prepare(self) -> PreparedData:
        universe = self.load_top_universe()
        failures = self.prepare_source_csv(universe)
        pd.DataFrame(columns=["symbol", "date", "is_member"]).to_csv(self.paths["membership_csv"], index=False)
        return PreparedData(
            universe=universe,
            failures=failures,
            metadata={"source": "nasdaq_public", "membership_csv": None},
        )

    def load_top_universe(self) -> pd.DataFrame:
        listed_text = fetch_text(NASDAQ_LISTED_URL)
        listed_symbols = set()
        reader = csv.DictReader(io.StringIO(listed_text.replace("\r\n", "\n")), delimiter="|")
        for row in reader:
            symbol = row.get("Symbol", "")
            if not symbol or symbol == "File Creation Time":
                continue
            if self.config["universe"]["exclude_test_issue"] and row.get("Test Issue") != "N":
                continue
            if self.config["universe"]["exclude_etf"] and row.get("ETF") != "N":
                continue
            listed_symbols.add(symbol)

        screener = fetch_json(
            NASDAQ_SCREENER_URL,
            params={
                "tableonly": "true",
                "limit": "25",
                "offset": "0",
                "download": "true",
                "exchange": self.config["universe"]["exchange"],
            },
            referer="https://www.nasdaq.com/market-activity/stocks/screener",
        )
        frame = pd.DataFrame(screener["data"]["rows"])
        frame = frame[frame["symbol"].isin(listed_symbols)].copy()
        frame["market_cap"] = frame["marketCap"].map(parse_float)
        frame["last_sale"] = frame["lastsale"].map(parse_float)
        frame = frame[frame["market_cap"].notna() & (frame["market_cap"] > 0)]
        frame = frame.sort_values("market_cap", ascending=False).head(
            int(self.config["universe"]["top_n_by_market_cap"])
        )
        frame.to_csv(self.paths["universe_csv"], index=False)
        return frame

    def download_symbol_history(self, symbol: str) -> tuple[str, int, str | None]:
        from_date, to_date = nasdaq_history_window(self.config["data"])
        params = {
            "assetclass": "stocks",
            "fromdate": from_date,
            "todate": to_date,
            "limit": "9999",
        }
        data = fetch_json(
            NASDAQ_HISTORICAL_URL.format(symbol=symbol),
            params=params,
            referer=f"https://www.nasdaq.com/market-activity/stocks/{symbol.lower()}/historical",
        )
        rows = data.get("data", {}).get("tradesTable", {}).get("rows")
        if not rows:
            return symbol, 0, "no rows"

        parsed = []
        for row in rows:
            date = datetime.strptime(row["date"], "%m/%d/%Y").date().isoformat()
            open_ = parse_float(row.get("open"))
            high = parse_float(row.get("high"))
            low = parse_float(row.get("low"))
            close = parse_float(row.get("close"))
            volume = parse_float(row.get("volume"))
            if any(pd.isna(x) for x in [open_, high, low, close, volume]):
                continue
            parsed.append(
                {
                    "date": date,
                    "symbol": symbol,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "vwap": (open_ + high + low + close) / 4,
                    "volume": volume,
                }
            )

        min_history_rows = int(self.config["universe"]["min_history_rows"])
        if len(parsed) < min_history_rows:
            return symbol, len(parsed), f"history < {min_history_rows} rows"

        frame = pd.DataFrame(parsed).sort_values("date")
        frame.to_csv(self.paths["source_dir"] / f"{symbol}.csv", index=False)
        return symbol, len(frame), None

    def prepare_source_csv(self, universe: pd.DataFrame) -> pd.DataFrame:
        source_dir = self.paths["source_dir"]
        reset_directory(source_dir)

        failures = []
        symbols = list(universe["symbol"])
        print(f"Downloading Nasdaq historical OHLCV for {len(symbols)} symbols...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_symbol = {executor.submit(self.download_symbol_history, symbol): symbol for symbol in symbols}
            for index, future in enumerate(concurrent.futures.as_completed(future_to_symbol), start=1):
                symbol, rows, error = future.result()
                if error:
                    failures.append({"symbol": symbol, "rows": rows, "error": error})
                if index % 50 == 0 or index == len(symbols):
                    print(f"Downloaded {index}/{len(symbols)}; failures/skips: {len(failures)}")

        return write_failures(self.paths["failures_csv"], failures)


def nasdaq_history_window(data_config: dict[str, Any]) -> tuple[str, str]:
    if data_config.get("start_date") and data_config.get("end_date"):
        return normalize_date_text(data_config["start_date"]), normalize_date_text(data_config["end_date"])
    return (
        (datetime.now().date() - timedelta(days=int(data_config["lookback_days"]))).isoformat(),
        datetime.now().date().isoformat(),
    )


def normalize_date_text(value: Any) -> str:
    if isinstance(value, str):
        if value == "latest":
            return date.today().isoformat()
        return value
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
