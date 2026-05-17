"""SEC EDGAR fundamental feature adapter.

The adapter converts structured XBRL facts into daily point-in-time features.
It intentionally avoids filing text NLP in v1.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import requests

try:
    from analysis.nasdaq_top500_score.data_sources.base import DataSourceUnavailable
except ImportError:  # pragma: no cover - supports direct script execution.
    from data_sources.base import DataSourceUnavailable

SEC_TICKER_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

SEC_UNAVAILABLE_MESSAGE = (
    "SEC EDGAR access requires SEC_EDGAR_USER_AGENT, for example "
    "`export SEC_EDGAR_USER_AGENT='your-name your-email@example.com'`."
)

FUNDAMENTAL_FAILURE_COLUMNS = ["symbol", "cik", "error", "detail"]
CIK_MAP_COLUMNS = ["symbol", "cik", "title", "exchange", "source"]

FIELD_SPECS: dict[str, dict[str, Any]] = {
    "revenue": {
        "concepts": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
        "units": ["USD"],
    },
    "gross_profit": {"concepts": ["GrossProfit"], "units": ["USD"]},
    "operating_income": {"concepts": ["OperatingIncomeLoss"], "units": ["USD"]},
    "net_income": {"concepts": ["NetIncomeLoss", "ProfitLoss"], "units": ["USD"]},
    "eps_diluted": {"concepts": ["EarningsPerShareDiluted"], "units": ["USD/shares", "USD/share"]},
    "assets": {"concepts": ["Assets"], "units": ["USD"]},
    "liabilities": {"concepts": ["Liabilities"], "units": ["USD"]},
    "equity": {
        "concepts": [
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ],
        "units": ["USD"],
    },
    "cash": {"concepts": ["CashAndCashEquivalentsAtCarryingValue", "Cash"], "units": ["USD"]},
    "operating_cash_flow": {"concepts": ["NetCashProvidedByUsedInOperatingActivities"], "units": ["USD"]},
    "capex": {"concepts": ["PaymentsToAcquirePropertyPlantAndEquipment"], "units": ["USD"]},
    "shares_diluted": {
        "concepts": [
            "WeightedAverageNumberOfDilutedSharesOutstanding",
            "WeightedAverageNumberOfShareDiluted",
            "EntityCommonStockSharesOutstanding",
        ],
        "units": ["shares"],
    },
}

BASE_FEATURE_COLUMNS = [
    "revenue_ttm",
    "assets",
    "equity",
    "cash",
    "shares_diluted",
    "gross_margin",
    "operating_margin",
    "net_margin",
    "roe",
    "roa",
    "revenue_yoy_growth",
    "net_income_yoy_growth",
    "eps_yoy_growth",
    "assets_yoy_growth",
    "operating_cash_flow_ttm",
    "free_cash_flow_ttm",
    "cfo_to_net_income",
    "fcf_margin",
    "liabilities_to_assets",
    "cash_to_assets",
    "days_since_last_10q",
    "days_since_last_10k",
    "filing_lag_days",
    "is_recent_filing",
    "is_amended_filing",
]

VALUATION_FEATURE_COLUMNS = ["price_to_sales", "price_to_book", "price_to_earnings", "market_cap_to_fcf"]


@dataclass
class FundamentalDataResult:
    features: pd.DataFrame
    failures: pd.DataFrame
    cik_map: pd.DataFrame

    @classmethod
    def empty(cls, paths: dict[str, Path]) -> "FundamentalDataResult":
        features = pd.DataFrame()
        failures = pd.DataFrame(columns=FUNDAMENTAL_FAILURE_COLUMNS)
        cik_map = pd.DataFrame(columns=CIK_MAP_COLUMNS)
        if "fundamental_features" in paths:
            features.to_parquet(paths["fundamental_features"])
        if "fundamental_failures" in paths:
            failures.to_csv(paths["fundamental_failures"], index=False)
        if "edgar_cik_map" in paths:
            cik_map.to_csv(paths["edgar_cik_map"], index=False)
        return cls(features=features, failures=failures, cik_map=cik_map)


class SecEdgarClient:
    def __init__(self, cache_dir: Path, *, user_agent: str | None = None, request_sleep: float = 0.12) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent = user_agent or os.environ.get("SEC_EDGAR_USER_AGENT")
        if not self.user_agent:
            raise DataSourceUnavailable(SEC_UNAVAILABLE_MESSAGE)
        self.request_sleep = request_sleep

    def _get_json(self, url: str, cache_name: str) -> dict[str, Any]:
        cache_path = self.cache_dir / cache_name
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))

        headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Host": url.split("/")[2],
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        time.sleep(self.request_sleep)
        return data

    def ticker_map(self) -> pd.DataFrame:
        data = self._get_json(SEC_TICKER_URL, "company_tickers_exchange.json")
        fields = data.get("fields")
        rows = data.get("data")
        if fields and rows:
            frame = pd.DataFrame(rows, columns=fields)
        else:
            frame = pd.DataFrame(data.values())
        frame = frame.rename(columns={"ticker": "symbol", "cik": "cik", "name": "title"})
        frame["symbol"] = frame["symbol"].astype(str).str.upper()
        frame["cik"] = pd.to_numeric(frame["cik"], errors="coerce").astype("Int64")
        if "exchange" not in frame.columns:
            frame["exchange"] = None
        return frame[["symbol", "cik", "title", "exchange"]].dropna(subset=["cik"])

    def submissions(self, cik: int) -> dict[str, Any]:
        return self._get_json(SEC_SUBMISSIONS_URL.format(cik=int(cik)), f"submissions_CIK{int(cik):010d}.json")

    def companyfacts(self, cik: int) -> dict[str, Any]:
        return self._get_json(SEC_COMPANYFACTS_URL.format(cik=int(cik)), f"companyfacts_CIK{int(cik):010d}.json")


def build_sec_edgar_features(
    universe: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
    *,
    client: Any | None = None,
) -> FundamentalDataResult:
    fundamentals = config["fundamentals"]
    edgar_client = client or SecEdgarClient(paths["edgar_cache_dir"])
    builder = SecEdgarFeatureBuilder(config, paths, edgar_client)
    result = builder.build(universe)
    result.features.to_parquet(paths["fundamental_features"])
    result.failures.to_csv(paths["fundamental_failures"], index=False)
    result.cik_map.to_csv(paths["edgar_cik_map"], index=False)
    return result


class SecEdgarFeatureBuilder:
    def __init__(self, config: dict[str, Any], paths: dict[str, Path], client: Any) -> None:
        self.config = config
        self.paths = paths
        self.client = client
        self.fundamentals = config["fundamentals"]
        self.forms = set(self.fundamentals.get("forms", ["10-K", "10-Q", "10-K/A", "10-Q/A"]))
        self.min_filing_count = int(self.fundamentals.get("min_filing_count", 4))
        self.enable_valuation = bool(self.fundamentals.get("enable_valuation", True))
        self.recent_filing_days = int(self.fundamentals.get("recent_filing_days", 5))

    def build(self, universe: pd.DataFrame) -> FundamentalDataResult:
        ticker_map = self.client.ticker_map()
        cik_lookup = ticker_map.drop_duplicates("symbol").set_index("symbol")
        failures: list[dict[str, Any]] = []
        cik_rows: list[dict[str, Any]] = []
        feature_frames: list[pd.DataFrame] = []

        for symbol in universe["symbol"].astype(str).str.upper().dropna().unique():
            if symbol not in cik_lookup.index:
                failures.append({"symbol": symbol, "cik": None, "error": "missing_cik", "detail": "ticker not found in SEC map"})
                continue
            cik_row = cik_lookup.loc[symbol]
            cik = int(cik_row["cik"])
            cik_rows.append(
                {
                    "symbol": symbol,
                    "cik": cik,
                    "title": cik_row.get("title"),
                    "exchange": cik_row.get("exchange"),
                    "source": "sec_edgar",
                }
            )

            try:
                submissions = self.client.submissions(cik)
                companyfacts = self.client.companyfacts(cik)
                events = self.build_event_features(symbol, cik, submissions, companyfacts)
                if len(events) < self.min_filing_count:
                    failures.append(
                        {
                            "symbol": symbol,
                            "cik": cik,
                            "error": "insufficient_filings",
                            "detail": f"{len(events)} < {self.min_filing_count}",
                        }
                    )
                    continue
                missing_fields = [field for field in FIELD_SPECS if field not in events.columns or events[field].isna().all()]
                if missing_fields:
                    failures.append(
                        {
                            "symbol": symbol,
                            "cik": cik,
                            "error": "missing_fields",
                            "detail": ",".join(missing_fields),
                        }
                    )
                daily = self.expand_to_daily(symbol, cik, events, failures)
                if not daily.empty:
                    feature_frames.append(daily)
            except Exception as exc:  # noqa: BLE001 - keep batch ingestion resumable.
                failures.append({"symbol": symbol, "cik": cik, "error": "api_or_parse_error", "detail": str(exc)})

        features = pd.concat(feature_frames).sort_index() if feature_frames else empty_feature_frame(self.enable_valuation)
        failures_frame = pd.DataFrame(failures, columns=FUNDAMENTAL_FAILURE_COLUMNS)
        cik_map = pd.DataFrame(cik_rows, columns=CIK_MAP_COLUMNS)
        return FundamentalDataResult(features=features, failures=failures_frame, cik_map=cik_map)

    def build_event_features(
        self,
        symbol: str,
        cik: int,
        submissions: dict[str, Any],
        companyfacts: dict[str, Any],
    ) -> pd.DataFrame:
        filings = build_submissions_frame(submissions, self.forms)
        if filings.empty:
            return pd.DataFrame()

        rows = []
        for filing in filings.itertuples(index=False):
            effective_date = filing.accepted if pd.notna(filing.accepted) else filing.filed
            row = {
                "symbol": symbol,
                "cik": cik,
                "accession": filing.accession,
                "form": filing.form,
                "filed": filing.filed,
                "accepted": filing.accepted,
                "effective_date": effective_date,
                "period_end": filing.report_date,
                "is_amended_filing": 1 if str(filing.form).endswith("/A") else 0,
            }
            for field_name, spec in FIELD_SPECS.items():
                row[field_name] = extract_fact_value(companyfacts, filing.accession, spec)
            rows.append(row)

        events = pd.DataFrame(rows)
        if events.empty:
            return events
        events["effective_date"] = to_naive_datetime(events["effective_date"])
        events["period_end"] = to_naive_datetime(events["period_end"])
        events = events.dropna(subset=["effective_date"]).sort_values("effective_date").reset_index(drop=True)
        events = compute_event_ratios(events)
        return events

    def expand_to_daily(
        self,
        symbol: str,
        cik: int,
        events: pd.DataFrame,
        failures: list[dict[str, Any]],
    ) -> pd.DataFrame:
        price = load_price_frame(self.paths["source_dir"], symbol)
        if price.empty:
            failures.append({"symbol": symbol, "cik": cik, "error": "missing_price", "detail": "no Qlib source CSV"})
            return pd.DataFrame()

        daily = pd.merge_asof(
            price.sort_values("datetime"),
            events.sort_values("effective_date"),
            left_on="datetime",
            right_on="effective_date",
            direction="backward",
        )
        daily["instrument"] = symbol
        daily["days_since_last_filing"] = (daily["datetime"] - daily["effective_date"]).dt.days
        daily["days_since_last_10q"] = (daily["datetime"] - daily["last_10q_date"]).dt.days
        daily["days_since_last_10k"] = (daily["datetime"] - daily["last_10k_date"]).dt.days
        daily["is_recent_filing"] = (daily["days_since_last_filing"] <= self.recent_filing_days).astype(float)
        daily["filing_lag_days"] = (daily["effective_date"] - daily["period_end"]).dt.days

        if self.enable_valuation:
            daily = compute_valuation_features(daily)

        feature_columns = BASE_FEATURE_COLUMNS + (VALUATION_FEATURE_COLUMNS if self.enable_valuation else [])
        prefixed = {column: f"edgar_{column}" for column in feature_columns}
        daily = daily.rename(columns=prefixed)
        daily = daily.set_index(["datetime", "instrument"])
        return daily[list(prefixed.values())]


def build_submissions_frame(submissions: dict[str, Any], forms: set[str]) -> pd.DataFrame:
    recent = submissions.get("filings", {}).get("recent", {})
    if not recent:
        return pd.DataFrame(columns=["accession", "form", "filed", "accepted", "report_date"])
    frame = pd.DataFrame(recent)
    required = ["accessionNumber", "form", "filingDate", "acceptanceDateTime", "reportDate"]
    for column in required:
        if column not in frame.columns:
            frame[column] = None
    frame = frame.rename(
        columns={
            "accessionNumber": "accession",
            "filingDate": "filed",
            "acceptanceDateTime": "accepted",
            "reportDate": "report_date",
        }
    )
    frame = frame[frame["form"].isin(forms)].copy()
    frame["filed"] = to_naive_datetime(frame["filed"])
    frame["accepted"] = to_naive_datetime(frame["accepted"])
    frame["report_date"] = to_naive_datetime(frame["report_date"])
    return frame.dropna(subset=["accession"]).sort_values(["accepted", "filed"])


def extract_fact_value(companyfacts: dict[str, Any], accession: str, spec: dict[str, Any]) -> float | None:
    us_gaap = companyfacts.get("facts", {}).get("us-gaap", {})
    for concept in spec["concepts"]:
        concept_data = us_gaap.get(concept)
        if not concept_data:
            continue
        for unit in spec["units"]:
            facts = concept_data.get("units", {}).get(unit)
            if not facts:
                continue
            matches = [fact for fact in facts if fact.get("accn") == accession and "val" in fact]
            if not matches:
                continue
            matches = sorted(matches, key=lambda fact: (fact.get("end") or "", fact.get("filed") or ""))
            return pd.to_numeric(matches[-1].get("val"), errors="coerce")
    return None


def compute_event_ratios(events: pd.DataFrame) -> pd.DataFrame:
    numeric_columns = list(FIELD_SPECS)
    for column in numeric_columns:
        events[column] = pd.to_numeric(events[column], errors="coerce")

    events["free_cash_flow"] = events["operating_cash_flow"] - events["capex"]
    for column in ["revenue", "net_income", "operating_cash_flow", "free_cash_flow"]:
        events[f"{column}_ttm"] = events[column].rolling(4, min_periods=1).sum()

    events["gross_margin"] = safe_div(events["gross_profit"], events["revenue"])
    events["operating_margin"] = safe_div(events["operating_income"], events["revenue"])
    events["net_margin"] = safe_div(events["net_income"], events["revenue"])
    events["roe"] = safe_div(events["net_income_ttm"], events["equity"])
    events["roa"] = safe_div(events["net_income_ttm"], events["assets"])
    events["revenue_yoy_growth"] = events["revenue"].pct_change(4)
    events["net_income_yoy_growth"] = events["net_income"].pct_change(4)
    events["eps_yoy_growth"] = events["eps_diluted"].pct_change(4)
    events["assets_yoy_growth"] = events["assets"].pct_change(4)
    events["cfo_to_net_income"] = safe_div(events["operating_cash_flow_ttm"], events["net_income_ttm"])
    events["fcf_margin"] = safe_div(events["free_cash_flow_ttm"], events["revenue_ttm"])
    events["liabilities_to_assets"] = safe_div(events["liabilities"], events["assets"])
    events["cash_to_assets"] = safe_div(events["cash"], events["assets"])

    events["last_10q_date"] = events["effective_date"].where(events["form"].str.contains("10-Q", regex=False)).ffill()
    events["last_10k_date"] = events["effective_date"].where(events["form"].str.contains("10-K", regex=False)).ffill()
    return events


def compute_valuation_features(daily: pd.DataFrame) -> pd.DataFrame:
    daily["market_cap"] = daily["close"] * daily["shares_diluted"]
    daily["price_to_sales"] = safe_div(daily["market_cap"], daily["revenue_ttm"])
    daily["price_to_book"] = safe_div(daily["market_cap"], daily["equity"])
    daily["price_to_earnings"] = safe_div(daily["market_cap"], daily["net_income_ttm"])
    daily["market_cap_to_fcf"] = safe_div(daily["market_cap"], daily["free_cash_flow_ttm"])
    return daily


def load_price_frame(source_dir: Path, symbol: str) -> pd.DataFrame:
    path = source_dir / f"{symbol}.csv"
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, usecols=["date", "close"])
    frame["datetime"] = pd.to_datetime(frame["date"]).dt.normalize()
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    return frame[["datetime", "close"]].dropna().sort_values("datetime")


def to_naive_datetime(value: Any) -> pd.Series:
    return pd.to_datetime(value, errors="coerce", utc=True).dt.tz_convert(None).dt.normalize()


def safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = denominator.replace(0, pd.NA)
    return numerator / denominator


def empty_feature_frame(enable_valuation: bool) -> pd.DataFrame:
    columns = [f"edgar_{column}" for column in BASE_FEATURE_COLUMNS]
    if enable_valuation:
        columns.extend(f"edgar_{column}" for column in VALUATION_FEATURE_COLUMNS)
    index = pd.MultiIndex.from_arrays([[], []], names=["datetime", "instrument"])
    return pd.DataFrame(columns=columns, index=index)
