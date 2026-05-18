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

try:
    from analysis.nasdaq_top500_score.selection import apply_security_master_filter, clean_stock_universe
except ImportError:  # pragma: no cover - supports direct script execution.
    from selection import apply_security_master_filter, clean_stock_universe

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
        universe = self.finalize_universe_after_download(universe)
        pd.DataFrame(columns=["symbol", "date", "is_member"]).to_csv(self.paths["membership_csv"], index=False)
        return PreparedData(
            universe=universe,
            failures=failures,
            metadata={"source": "nasdaq_public", "membership_csv": None},
        )

    def load_top_universe(self) -> pd.DataFrame:
        listed_text = fetch_text(NASDAQ_LISTED_URL)
        listed = parse_listed_securities(listed_text)
        if self.config["universe"].get("security_master", {}).get("enabled", False):
            listed_symbols = set(listed["symbol"])
        else:
            eligible_listed = listed.copy()
            if self.config["universe"]["exclude_test_issue"]:
                eligible_listed = eligible_listed[eligible_listed["test_issue"] == "N"]
            if self.config["universe"]["exclude_etf"]:
                eligible_listed = eligible_listed[eligible_listed["etf"] == "N"]
            listed_symbols = set(eligible_listed["symbol"])

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
        if self.config["universe"].get("security_master", {}).get("enabled", False):
            frame, _, _ = apply_security_master_filter(frame, listed, self.config["universe"], self.paths)
        else:
            frame, _ = clean_stock_universe(frame, self.config["universe"], self.paths.get("universe_exclusions_csv"))
        frame = frame.sort_values("market_cap", ascending=False).reset_index(drop=True)
        frame["current_market_cap_rank"] = range(1, len(frame) + 1)
        target_top_n = int(self.config["universe"]["top_n_by_market_cap"])
        selection = self.config["universe"].get("selection", {})
        if selection.get("method") == "approximate_market_cap_asof":
            candidate_top_n = int(selection.get("candidate_top_n_by_current_market_cap", target_top_n))
            frame = frame.head(candidate_top_n)
        else:
            frame = frame.head(target_top_n)
        if "universe_candidates_csv" in self.paths:
            frame.to_csv(self.paths["universe_candidates_csv"], index=False)
        frame.to_csv(self.paths["universe_csv"], index=False)
        return frame

    def finalize_universe_after_download(self, universe: pd.DataFrame) -> pd.DataFrame:
        selection = self.config["universe"].get("selection", {})
        if selection.get("method") != "approximate_market_cap_asof":
            return universe

        selected, diagnostics = select_approximate_asof_universe(
            universe,
            self.paths["source_dir"],
            selection,
            int(self.config["universe"]["top_n_by_market_cap"]),
        )
        if "universe_selection_csv" in self.paths:
            diagnostics.to_csv(self.paths["universe_selection_csv"], index=False)
        selected.to_csv(self.paths["universe_csv"], index=False)
        prune_source_csvs(self.paths["source_dir"], set(selected["symbol"].astype(str).str.upper()))
        return selected

    def download_symbol_history(self, symbol: str) -> tuple[str, int, str | None]:
        from_date, to_date = nasdaq_history_window(self.config["data"])
        start_ts = pd.Timestamp(from_date)
        end_ts = pd.Timestamp(to_date)
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

        frame = pd.DataFrame(parsed).sort_values("date")
        dates = pd.to_datetime(frame["date"])
        frame = frame[(dates >= start_ts) & (dates <= end_ts)]
        min_history_rows = int(self.config["universe"]["min_history_rows"])
        if len(frame) < min_history_rows:
            return symbol, len(frame), f"history < {min_history_rows} rows"

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


def parse_listed_securities(text: str) -> pd.DataFrame:
    rows = []
    reader = csv.DictReader(io.StringIO(text.replace("\r\n", "\n")), delimiter="|")
    for row in reader:
        symbol = row.get("Symbol", "")
        if not symbol or symbol == "File Creation Time":
            continue
        rows.append(
            {
                "symbol": symbol,
                "security_name": row.get("Security Name"),
                "market_category": row.get("Market Category"),
                "test_issue": row.get("Test Issue"),
                "financial_status": row.get("Financial Status"),
                "round_lot_size": row.get("Round Lot Size"),
                "etf": row.get("ETF"),
                "nextshares": row.get("NextShares"),
            }
        )
    return pd.DataFrame(rows)


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


def select_approximate_asof_universe(
    universe: pd.DataFrame,
    source_dir: Path,
    selection: dict[str, Any],
    top_n: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    as_of_date = pd.Timestamp(selection["as_of_date"]).normalize()
    rows: list[dict[str, Any]] = []
    for row in universe.itertuples(index=False):
        symbol = str(getattr(row, "symbol")).upper()
        diagnostics = {
            "symbol": symbol,
            "selection_as_of_date": as_of_date.date().isoformat(),
            "selection_status": "selected_candidate",
            "selection_error": None,
            "asof_close_date": None,
            "asof_close": None,
            "latest_close_for_asof_estimate": None,
            "current_market_cap": getattr(row, "market_cap", pd.NA),
            "market_cap_asof_estimate": pd.NA,
        }
        path = source_dir / f"{symbol}.csv"
        if not path.exists():
            diagnostics["selection_status"] = "excluded"
            diagnostics["selection_error"] = "missing_price_csv"
            rows.append(diagnostics)
            continue
        try:
            price = pd.read_csv(path, usecols=["date", "close"])
            price["date"] = pd.to_datetime(price["date"], errors="coerce").dt.normalize()
            price["close"] = pd.to_numeric(price["close"], errors="coerce")
            price = price.dropna(subset=["date", "close"]).sort_values("date")
        except Exception as exc:  # noqa: BLE001 - keep selection diagnostics resumable.
            diagnostics["selection_status"] = "excluded"
            diagnostics["selection_error"] = f"price_parse_error: {exc}"
            rows.append(diagnostics)
            continue
        asof_price = price[price["date"] <= as_of_date]
        if asof_price.empty:
            diagnostics["selection_status"] = "excluded"
            diagnostics["selection_error"] = "no_price_on_or_before_asof"
            rows.append(diagnostics)
            continue
        latest_row = price.iloc[-1]
        asof_row = asof_price.iloc[-1]
        latest_close = float(latest_row["close"])
        asof_close = float(asof_row["close"])
        current_market_cap = pd.to_numeric(diagnostics["current_market_cap"], errors="coerce")
        if pd.isna(current_market_cap) or current_market_cap <= 0 or latest_close <= 0 or asof_close <= 0:
            diagnostics["selection_status"] = "excluded"
            diagnostics["selection_error"] = "invalid_market_cap_or_price"
            rows.append(diagnostics)
            continue
        diagnostics.update(
            {
                "asof_close_date": asof_row["date"].date().isoformat(),
                "asof_close": asof_close,
                "latest_close_for_asof_estimate": latest_close,
                "current_market_cap": float(current_market_cap),
                "market_cap_asof_estimate": float(current_market_cap) * asof_close / latest_close,
            }
        )
        rows.append(diagnostics)

    diagnostics_frame = pd.DataFrame(rows)
    eligible = diagnostics_frame[diagnostics_frame["selection_error"].isna()].copy()
    eligible = eligible.sort_values("market_cap_asof_estimate", ascending=False).head(top_n)
    diagnostics_frame.loc[diagnostics_frame["selection_error"].isna(), "selection_status"] = "not_selected_below_top_n"
    eligible["selection_status"] = "selected"
    diagnostics_frame.loc[eligible.index, "selection_status"] = "selected"
    universe_with_selection = universe.merge(
        eligible[
            [
                "symbol",
                "selection_as_of_date",
                "asof_close_date",
                "asof_close",
                "latest_close_for_asof_estimate",
                "market_cap_asof_estimate",
            ]
        ],
        on="symbol",
        how="inner",
    )
    universe_with_selection = universe_with_selection.sort_values("market_cap_asof_estimate", ascending=False).reset_index(drop=True)
    universe_with_selection["asof_market_cap_rank"] = range(1, len(universe_with_selection) + 1)
    universe_with_selection["selection_method"] = "approximate_market_cap_asof"
    return universe_with_selection, diagnostics_frame


def prune_source_csvs(source_dir: Path, selected_symbols: set[str]) -> None:
    for path in source_dir.glob("*.csv"):
        if path.stem.upper() not in selected_symbols:
            path.unlink()
