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
import yaml

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
CIK_MAP_COLUMNS = [
    "symbol",
    "cik",
    "title",
    "exchange",
    "source",
    "lookup_symbol",
    "mapping_method",
    "evidence_date",
    "confidence",
]
TAG_RESOLUTION_COLUMNS = ["symbol", "cik", "accession", "field", "concept", "unit"]

FIELD_SPECS: dict[str, dict[str, Any]] = {
    "revenue": {
        "concepts": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
        "units": ["USD"],
    },
    "gross_profit": {"concepts": ["GrossProfit", "GrossProfitLoss"], "units": ["USD"]},
    "operating_income": {
        "concepts": [
            "OperatingIncomeLoss",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        ],
        "units": ["USD"],
    },
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
    "operating_cash_flow": {
        "concepts": [
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ],
        "units": ["USD"],
    },
    "capex": {
        "concepts": [
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
            "CapitalExpenditures",
        ],
        "units": ["USD"],
    },
    "shares_diluted": {
        "concepts": [
            "WeightedAverageNumberOfDilutedSharesOutstanding",
            "WeightedAverageNumberOfShareDiluted",
            "WeightedAverageNumberOfSharesOutstandingDiluted",
            "WeightedAverageDilutedSharesOutstanding",
            "EntityCommonStockSharesOutstanding",
        ],
        "units": ["shares"],
    },
}

FIELD_STALE_LIMITS: dict[str, int] = {
    "revenue": 540,
    "gross_profit": 540,
    "operating_income": 540,
    "net_income": 540,
    "eps_diluted": 540,
    "assets": 540,
    "liabilities": 540,
    "equity": 540,
    "cash": 540,
    "operating_cash_flow": 540,
    "capex": 540,
    "shares_diluted": 540,
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

COVERAGE_AWARE_FEATURE_COLUMNS = [
    "has_profitability_quality",
    "has_valuation",
    "has_growth",
    "has_balance_sheet_stability",
    "days_since_revenue",
    "days_since_net_income",
    "days_since_operating_cash_flow",
    "days_since_assets",
    "days_since_equity",
]

DEFAULT_FEATURE_GROUPS: dict[str, list[str]] = {
    "profitability_quality": [
        "gross_margin",
        "operating_margin",
        "net_margin",
        "roe",
        "roa",
        "operating_cash_flow_ttm",
        "free_cash_flow_ttm",
        "cfo_to_net_income",
        "fcf_margin",
    ],
    "growth": [
        "revenue_yoy_growth",
        "net_income_yoy_growth",
        "eps_yoy_growth",
        "assets_yoy_growth",
    ],
    "balance_sheet_stability": [
        "revenue_ttm",
        "assets",
        "equity",
        "cash",
        "shares_diluted",
        "liabilities_to_assets",
        "cash_to_assets",
    ],
    "valuation": [
        "price_to_sales",
        "price_to_book",
        "price_to_earnings",
        "market_cap_to_fcf",
    ],
    "filing_state": [
        "days_since_last_10q",
        "days_since_last_10k",
        "filing_lag_days",
        "is_recent_filing",
        "is_amended_filing",
    ],
    "coverage_state": [
        "has_profitability_quality",
        "has_valuation",
        "has_growth",
        "has_balance_sheet_stability",
        "days_since_revenue",
        "days_since_net_income",
        "days_since_operating_cash_flow",
        "days_since_assets",
        "days_since_equity",
    ],
}

STATIC_CLEANING_RULES: dict[str, dict[str, float]] = {
    "edgar_price_to_sales": {"min": 0.0, "max": 100.0},
    "edgar_price_to_book": {"min": 0.0, "max": 100.0},
    "edgar_price_to_earnings": {"min": 0.0, "max": 200.0},
    "edgar_market_cap_to_fcf": {"min": 0.0, "max": 200.0},
    "edgar_gross_margin": {"min": -2.0, "max": 2.0},
    "edgar_operating_margin": {"min": -2.0, "max": 2.0},
    "edgar_net_margin": {"min": -2.0, "max": 2.0},
    "edgar_roe": {"min": -5.0, "max": 5.0},
    "edgar_roa": {"min": -5.0, "max": 5.0},
    "edgar_revenue_yoy_growth": {"min": -5.0, "max": 5.0},
    "edgar_net_income_yoy_growth": {"min": -5.0, "max": 5.0},
    "edgar_eps_yoy_growth": {"min": -5.0, "max": 5.0},
    "edgar_assets_yoy_growth": {"min": -5.0, "max": 5.0},
    "edgar_cfo_to_net_income": {"min": -10.0, "max": 10.0},
    "edgar_fcf_margin": {"min": -5.0, "max": 5.0},
    "edgar_liabilities_to_assets": {"min": 0.0, "max": 5.0},
    "edgar_cash_to_assets": {"min": 0.0, "max": 5.0},
    "edgar_filing_lag_days": {"min": 0.0, "max": 730.0},
    "edgar_days_since_last_10q": {"min": 0.0, "max": 2000.0},
    "edgar_days_since_last_10k": {"min": 0.0, "max": 3000.0},
    "edgar_is_recent_filing": {"min": 0.0, "max": 1.0},
    "edgar_is_amended_filing": {"min": 0.0, "max": 1.0},
}


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
    if fundamentals.get("cleaning", {}).get("enabled", False):
        cleaned, cleaning_summary = clean_fundamental_features(result.features, fundamentals)
        cleaned = select_feature_groups(cleaned, fundamentals)
        cleaned.to_parquet(paths["fundamental_features_cleaned"])
        paths["fundamental_cleaning_summary"].write_text(
            yaml.safe_dump(cleaning_summary, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        result = FundamentalDataResult(features=cleaned, failures=result.failures, cik_map=result.cik_map)
    else:
        selected = select_feature_groups(result.features, fundamentals)
        if selected.shape[1] != result.features.shape[1]:
            selected.to_parquet(paths["fundamental_features_cleaned"])
            result = FundamentalDataResult(features=selected, failures=result.failures, cik_map=result.cik_map)
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
        self.field_level_fill = self.fundamentals.get("field_level_fill", {})
        self.coverage_features_enabled = bool(self.fundamentals.get("coverage_features", {}).get("enabled", False))
        default_price_source = "crsp_raw_close" if config.get("data", {}).get("source") == "crsp" else "qlib_close"
        self.valuation_price_source = str(self.fundamentals.get("valuation_price_source", default_price_source))
        self.price_loader = FundamentalPriceLoader(config, paths, self.valuation_price_source)
        self.tag_resolution_rows: list[dict[str, Any]] = []

    def build(self, universe: pd.DataFrame) -> FundamentalDataResult:
        ticker_map = self.client.ticker_map()
        cik_lookup = build_ticker_cik_lookup(ticker_map)
        universe_rows = build_universe_mapping_rows(universe)
        self.price_loader.prepare([row["symbol"] for row in universe_rows])
        failures: list[dict[str, Any]] = []
        cik_rows: list[dict[str, Any]] = []
        feature_frames: list[pd.DataFrame] = []

        for universe_row in universe_rows:
            symbol = universe_row["symbol"]
            mapping = resolve_cik_mapping(universe_row, cik_lookup)
            if mapping is None:
                failures.append(
                    {
                        "symbol": symbol,
                        "cik": None,
                        "error": "missing_cik",
                        "detail": "lookup candidates: " + ",".join(universe_row["lookup_candidates"]),
                    }
                )
                continue
            cik = int(mapping["cik"])
            cik_rows.append(
                {
                    "symbol": symbol,
                    "cik": cik,
                    "title": mapping.get("title"),
                    "exchange": mapping.get("exchange"),
                    "source": "sec_edgar",
                    "lookup_symbol": mapping.get("lookup_symbol"),
                    "mapping_method": mapping.get("mapping_method"),
                    "evidence_date": mapping.get("evidence_date"),
                    "confidence": mapping.get("confidence"),
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

        features = (
            pd.concat(feature_frames).sort_index()
            if feature_frames
            else empty_feature_frame(self.enable_valuation, self.coverage_features_enabled)
        )
        failures_frame = pd.DataFrame(failures, columns=FUNDAMENTAL_FAILURE_COLUMNS)
        cik_map = pd.DataFrame(cik_rows, columns=CIK_MAP_COLUMNS)
        if "edgar_tag_resolution_report" in self.paths:
            pd.DataFrame(self.tag_resolution_rows, columns=TAG_RESOLUTION_COLUMNS).to_csv(
                self.paths["edgar_tag_resolution_report"],
                index=False,
            )
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
                "accepted_at": filing.accepted,
                "effective_date": effective_date,
                "period_end": filing.report_date,
                "is_amended_filing": 1 if str(filing.form).endswith("/A") else 0,
            }
            for field_name, spec in FIELD_SPECS.items():
                match = extract_fact_match(companyfacts, filing.accession, spec)
                row[field_name] = None if match is None else match["value"]
                if match is not None:
                    self.tag_resolution_rows.append(
                        {
                            "symbol": symbol,
                            "cik": cik,
                            "accession": filing.accession,
                            "field": field_name,
                            "concept": match["concept"],
                            "unit": match["unit"],
                        }
                    )
            rows.append(row)

        events = pd.DataFrame(rows)
        if events.empty:
            return events
        events["accepted_at"] = to_naive_timestamp(events["accepted_at"])
        events["effective_date"] = to_naive_datetime(events["effective_date"])
        events["period_end"] = to_naive_datetime(events["period_end"])
        return events.dropna(subset=["effective_date"]).sort_values("effective_date").reset_index(drop=True)

    def expand_to_daily(
        self,
        symbol: str,
        cik: int,
        events: pd.DataFrame,
        failures: list[dict[str, Any]],
    ) -> pd.DataFrame:
        price = self.price_loader.price_frame(symbol)
        if price.empty:
            failures.append(
                {
                    "symbol": symbol,
                    "cik": cik,
                    "error": "missing_price",
                    "detail": f"no price calendar for valuation_price_source={self.valuation_price_source}",
                }
            )
            return pd.DataFrame()
        events = shift_events_to_next_trading_day(events, price["datetime"])
        if events.empty:
            failures.append(
                {
                    "symbol": symbol,
                    "cik": cik,
                    "error": "no_effective_filing_dates",
                    "detail": "no filing has a next trading day in the price calendar",
                }
            )
            return pd.DataFrame()
        events = apply_field_level_asof_fill(events, self.field_level_fill)
        events = compute_event_ratios(events)

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
        if self.coverage_features_enabled:
            daily = add_coverage_aware_features(daily, self.enable_valuation)

        feature_columns = (
            BASE_FEATURE_COLUMNS
            + (VALUATION_FEATURE_COLUMNS if self.enable_valuation else [])
            + (COVERAGE_AWARE_FEATURE_COLUMNS if self.coverage_features_enabled else [])
        )
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
    frame["accepted"] = to_naive_timestamp(frame["accepted"])
    frame["report_date"] = to_naive_datetime(frame["report_date"])
    return frame.dropna(subset=["accession"]).sort_values(["accepted", "filed"])


def build_ticker_cik_lookup(ticker_map: pd.DataFrame) -> pd.DataFrame:
    frame = ticker_map.copy()
    frame["symbol"] = frame["symbol"].map(normalize_ticker_text)
    frame = frame.dropna(subset=["symbol", "cik"]).drop_duplicates("symbol", keep="first")
    return frame.set_index("symbol", drop=False)


def build_universe_mapping_rows(universe: pd.DataFrame) -> list[dict[str, Any]]:
    if universe.empty or "symbol" not in universe:
        return []
    rows = []
    working = universe.copy()
    working["symbol"] = working["symbol"].astype(str).str.upper()
    working = working.drop_duplicates("symbol", keep="first")
    for row in working.to_dict("records"):
        symbol = str(row["symbol"]).upper()
        candidates = ticker_candidates(row)
        direct_cik = first_numeric_value(row, ["cik", "CIK", "cik_asof", "cik_security", "edgar_cik"])
        rows.append(
            {
                "symbol": symbol,
                "direct_cik": None if direct_cik is None else int(direct_cik),
                "lookup_candidates": candidates,
                "evidence_date": first_text_value(row, ["effective_start", "month_end_date", "first_membership_date"]),
            }
        )
    return rows


def ticker_candidates(row: dict[str, Any]) -> list[str]:
    raw_values: list[Any] = []
    symbol = str(row.get("symbol", "")).upper()
    if not is_crsp_instrument(symbol):
        raw_values.append(symbol)
    raw_values.extend(
        [
            row.get("ticker_asof"),
            row.get("trading_symbol_asof"),
            row.get("ticker_asof_security"),
            row.get("TradingSymbol"),
            row.get("Ticker"),
        ]
    )
    candidates: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        normalized = normalize_ticker_text(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            candidates.append(normalized)
        if normalized:
            for variant in ticker_variants(normalized):
                if variant and variant not in seen:
                    seen.add(variant)
                    candidates.append(variant)
    return candidates


def resolve_cik_mapping(row: dict[str, Any], cik_lookup: pd.DataFrame) -> dict[str, Any] | None:
    direct_cik = row.get("direct_cik")
    if direct_cik is not None:
        return {
            "cik": int(direct_cik),
            "title": None,
            "exchange": None,
            "lookup_symbol": None,
            "mapping_method": "direct_cik",
            "evidence_date": row.get("evidence_date"),
            "confidence": 1.0,
        }
    for candidate in row["lookup_candidates"]:
        if candidate in cik_lookup.index:
            cik_row = cik_lookup.loc[candidate]
            return {
                "cik": int(cik_row["cik"]),
                "title": cik_row.get("title"),
                "exchange": cik_row.get("exchange"),
                "lookup_symbol": candidate,
                "mapping_method": "ticker_asof",
                "evidence_date": row.get("evidence_date"),
                "confidence": 0.75,
            }
    return None


def first_numeric_value(row: dict[str, Any], keys: list[str]) -> int | None:
    for key in keys:
        if key not in row:
            continue
        value = pd.to_numeric(row.get(key), errors="coerce")
        if not pd.isna(value):
            return int(value)
    return None


def first_text_value(row: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is None or pd.isna(value):
            continue
        text = str(value).strip()
        if text and text.upper() not in {"NAN", "NONE", "NULL", "NOAVAIL"}:
            return text
    return None


def normalize_ticker_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().upper()
    if not text or text in {"NAN", "NONE", "NULL", "NOAVAIL"}:
        return None
    return text


def ticker_variants(ticker: str) -> list[str]:
    variants = []
    replacements = {
        ".": "-",
        "/": "-",
        " ": "",
    }
    for old, new in replacements.items():
        if old in ticker:
            variants.append(ticker.replace(old, new))
    return variants


def is_crsp_instrument(symbol: str) -> bool:
    return len(symbol) > 1 and symbol[0] == "P" and symbol[1:].isdigit()


def extract_fact_value(companyfacts: dict[str, Any], accession: str, spec: dict[str, Any]) -> float | None:
    match = extract_fact_match(companyfacts, accession, spec)
    return None if match is None else match["value"]


def extract_fact_match(companyfacts: dict[str, Any], accession: str, spec: dict[str, Any]) -> dict[str, Any] | None:
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
            value = pd.to_numeric(matches[-1].get("val"), errors="coerce")
            return {"value": value, "concept": concept, "unit": unit}
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
    events["revenue_yoy_growth"] = events["revenue"].pct_change(4, fill_method=None)
    events["net_income_yoy_growth"] = events["net_income"].pct_change(4, fill_method=None)
    events["eps_yoy_growth"] = events["eps_diluted"].pct_change(4, fill_method=None)
    events["assets_yoy_growth"] = events["assets"].pct_change(4, fill_method=None)
    events["cfo_to_net_income"] = safe_div(events["operating_cash_flow_ttm"], events["net_income_ttm"])
    events["fcf_margin"] = safe_div(events["free_cash_flow_ttm"], events["revenue_ttm"])
    events["liabilities_to_assets"] = safe_div(events["liabilities"], events["assets"])
    events["cash_to_assets"] = safe_div(events["cash"], events["assets"])

    return update_last_filing_dates(events)


def shift_events_to_next_trading_day(events: pd.DataFrame, calendar: pd.Series) -> pd.DataFrame:
    """Move EDGAR filing visibility to the next available trading date."""

    if events.empty:
        return events
    calendar_dates = pd.Series(pd.to_datetime(calendar, errors="coerce")).dropna().dt.normalize()
    calendar_index = pd.DatetimeIndex(calendar_dates.drop_duplicates().sort_values())
    if calendar_index.empty:
        return events.iloc[0:0].copy()

    shifted = events.copy()
    accepted = pd.to_datetime(
        shifted.get("accepted_at", pd.Series(pd.NaT, index=shifted.index)),
        errors="coerce",
    )
    source = accepted.where(accepted.notna(), pd.to_datetime(shifted.get("filed"), errors="coerce"))
    source = source.where(source.notna(), pd.to_datetime(shifted["effective_date"], errors="coerce"))
    source_dates = source.dt.normalize()
    shifted["effective_date"] = pd.NaT
    valid = source_dates.notna()
    positions = calendar_index.searchsorted(source_dates[valid], side="right")
    next_dates = [calendar_index[position] if position < len(calendar_index) else pd.NaT for position in positions]
    shifted.loc[valid, "effective_date"] = next_dates
    shifted = shifted.dropna(subset=["effective_date"]).sort_values("effective_date").reset_index(drop=True)
    return update_last_filing_dates(shifted)


def apply_field_level_asof_fill(events: pd.DataFrame, field_fill_config: dict[str, Any]) -> pd.DataFrame:
    if events.empty or not bool(field_fill_config.get("enabled", False)):
        return events
    default_limit = int(field_fill_config.get("default_max_stale_days", 540))
    configured_limits = {str(key): int(value) for key, value in field_fill_config.get("max_stale_days", {}).items()}
    working = events.sort_values("effective_date").reset_index(drop=True).copy()
    effective_dates = pd.to_datetime(working["effective_date"], errors="coerce").dt.normalize()
    for field in FIELD_SPECS:
        if field not in working:
            continue
        series = pd.to_numeric(working[field], errors="coerce")
        last_available_date = effective_dates.where(series.notna()).ffill()
        days_since = (effective_dates - last_available_date).dt.days
        limit = configured_limits.get(field, default_limit)
        filled = series.ffill().where(days_since.le(limit))
        working[field] = filled
        working[f"{field}_last_available_date"] = last_available_date
    return working


def update_last_filing_dates(events: pd.DataFrame) -> pd.DataFrame:
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


def add_coverage_aware_features(daily: pd.DataFrame, enable_valuation: bool) -> pd.DataFrame:
    working = daily.copy()
    working["has_profitability_quality"] = (
        working[["gross_margin", "operating_margin", "net_margin", "roe", "roa", "cfo_to_net_income", "fcf_margin"]]
        .notna()
        .any(axis=1)
        .astype(float)
    )
    working["has_growth"] = (
        working[["revenue_yoy_growth", "net_income_yoy_growth", "eps_yoy_growth", "assets_yoy_growth"]]
        .notna()
        .any(axis=1)
        .astype(float)
    )
    working["has_balance_sheet_stability"] = (
        working[["assets", "equity", "cash", "liabilities_to_assets", "cash_to_assets"]].notna().any(axis=1).astype(float)
    )
    valuation_columns = [column for column in VALUATION_FEATURE_COLUMNS if column in working]
    working["has_valuation"] = (
        working[valuation_columns].notna().any(axis=1).astype(float)
        if enable_valuation and valuation_columns
        else 0.0
    )
    for field in ["revenue", "net_income", "operating_cash_flow", "assets", "equity"]:
        source_column = f"{field}_last_available_date"
        output_column = f"days_since_{field}"
        if source_column in working:
            last_date = pd.to_datetime(working[source_column], errors="coerce").dt.normalize()
            working[output_column] = (pd.to_datetime(working["datetime"], errors="coerce").dt.normalize() - last_date).dt.days
        else:
            working[output_column] = pd.NA
    return working


class FundamentalPriceLoader:
    def __init__(self, config: dict[str, Any], paths: dict[str, Path], price_source: str) -> None:
        self.config = config
        self.paths = paths
        self.price_source = price_source
        self._crsp_prices: dict[str, pd.DataFrame] | None = None
        if self.price_source not in {"qlib_close", "crsp_raw_close"}:
            raise ValueError("fundamentals.valuation_price_source must be qlib_close or crsp_raw_close")

    def prepare(self, symbols: list[str]) -> None:
        if self.price_source != "crsp_raw_close":
            return
        self._crsp_prices = load_crsp_raw_close_frames(
            self.paths["crsp_warehouse_dir"],
            symbols,
            self.config["data"]["start_date"],
            self.config["data"]["end_date"],
        )

    def price_frame(self, symbol: str) -> pd.DataFrame:
        if self.price_source == "crsp_raw_close":
            if self._crsp_prices is None:
                self.prepare([symbol])
            return self._crsp_prices.get(symbol, pd.DataFrame()) if self._crsp_prices is not None else pd.DataFrame()
        return load_qlib_price_frame(self.paths["source_dir"], symbol)


def load_qlib_price_frame(source_dir: Path, symbol: str) -> pd.DataFrame:
    path = source_dir / f"{symbol}.csv"
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, usecols=["date", "close"])
    frame["datetime"] = pd.to_datetime(frame["date"]).dt.normalize()
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    return frame[["datetime", "close"]].dropna().sort_values("datetime")


def load_crsp_raw_close_frames(
    warehouse_dir: Path,
    symbols: list[str],
    start_date: Any,
    end_date: Any,
) -> dict[str, pd.DataFrame]:
    execution_dir = first_existing_path(
        [
            warehouse_dir / "crsp_execution_prices.parquet",
            warehouse_dir / "crsp_execution_prices",
        ]
    )
    if not execution_dir.exists():
        return {}
    selected = {str(symbol).upper() for symbol in symbols}
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    frames: list[pd.DataFrame] = []
    for parquet_path in sorted(path for path in execution_dir.rglob("*.parquet") if path.is_file()):
        frame = pd.read_parquet(parquet_path, columns=["date", "instrument", "DlyClose"])
        frame["instrument"] = frame["instrument"].astype(str).str.upper()
        frame = frame[frame["instrument"].isin(selected)].copy()
        if frame.empty:
            continue
        frame["datetime"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
        frame = frame[(frame["datetime"] >= start) & (frame["datetime"] <= end)].copy()
        frame["close"] = pd.to_numeric(frame["DlyClose"], errors="coerce").abs()
        frames.append(frame[["datetime", "instrument", "close"]].dropna())
    if not frames:
        return {}
    prices = pd.concat(frames, ignore_index=True).sort_values(["instrument", "datetime"])
    prices = prices.drop_duplicates(["instrument", "datetime"], keep="last")
    return {
        instrument: group[["datetime", "close"]].sort_values("datetime").reset_index(drop=True)
        for instrument, group in prices.groupby("instrument", sort=False)
    }


def first_existing_path(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def clean_fundamental_features(
    features: pd.DataFrame,
    fundamentals: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    cleaning = fundamentals.get("cleaning", {})
    mode = str(cleaning.get("mode", "static_rules"))
    if mode != "static_rules":
        raise ValueError("fundamentals.cleaning.mode currently supports static_rules")

    cleaned = features.copy()
    rows = []
    negative_policy = str(cleaning.get("negative_valuation_policy", "set_nan"))
    if negative_policy not in {"set_nan", "keep"}:
        raise ValueError("fundamentals.cleaning.negative_valuation_policy must be set_nan or keep")
    rules = {**STATIC_CLEANING_RULES, **cleaning.get("rules", {})}
    negative_valuation_columns = [
        "edgar_price_to_earnings",
        "edgar_market_cap_to_fcf",
    ]

    for column in cleaned.columns:
        if column not in rules and column not in negative_valuation_columns:
            continue
        series = pd.to_numeric(cleaned[column], errors="coerce")
        nan_before = int(series.isna().sum())
        set_nan_by_negative_policy = 0
        if negative_policy == "set_nan" and column in negative_valuation_columns:
            mask = series <= 0
            set_nan_by_negative_policy = int(mask.sum())
            series = series.mask(mask)

        rule = rules.get(column, {})
        lower = rule.get("min")
        upper = rule.get("max")
        clipped_low = int((series < lower).sum()) if lower is not None else 0
        clipped_high = int((series > upper).sum()) if upper is not None else 0
        if lower is not None or upper is not None:
            series = series.clip(lower=lower, upper=upper)
        cleaned[column] = series
        rows.append(
            {
                "column": column,
                "nan_before": nan_before,
                "nan_after": int(series.isna().sum()),
                "set_nan_by_negative_policy": set_nan_by_negative_policy,
                "clipped_low": clipped_low,
                "clipped_high": clipped_high,
                "min": lower,
                "max": upper,
            }
        )

    summary = {
        "enabled": True,
        "mode": mode,
        "negative_valuation_policy": negative_policy,
        "input_shape": list(features.shape),
        "output_shape": list(cleaned.shape),
        "columns_with_rules": len(rows),
        "total_set_nan_by_negative_policy": int(sum(row["set_nan_by_negative_policy"] for row in rows)),
        "total_clipped_low": int(sum(row["clipped_low"] for row in rows)),
        "total_clipped_high": int(sum(row["clipped_high"] for row in rows)),
        "columns": rows,
    }
    return cleaned, summary


def select_feature_groups(features: pd.DataFrame, fundamentals: dict[str, Any]) -> pd.DataFrame:
    if features.empty:
        return features
    include_features = requested_feature_columns(fundamentals.get("include_features", []))
    if include_features:
        missing = [column for column in include_features if column not in features.columns]
        if missing:
            raise ValueError(f"Unknown fundamentals include_features column(s): {', '.join(missing)}")
        return features[include_features].copy()
    groups = configured_feature_groups(fundamentals)
    include_groups = list(fundamentals.get("include_feature_groups", []) or groups.keys())
    drop_groups = set(fundamentals.get("drop_feature_groups", []) or [])
    unknown = sorted((set(include_groups) | drop_groups) - set(groups))
    if unknown:
        raise ValueError(f"Unknown fundamentals feature group(s): {', '.join(unknown)}")

    selected_names: list[str] = []
    seen: set[str] = set()
    for group in include_groups:
        if group in drop_groups:
            continue
        for raw_name in groups[group]:
            column = f"edgar_{raw_name}"
            if column in features.columns and column not in seen:
                seen.add(column)
                selected_names.append(column)
    return features[selected_names].copy()


def requested_feature_columns(values: list[Any]) -> list[str]:
    columns: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = str(value).strip()
        if not text:
            continue
        column = text if text.startswith("edgar_") else f"edgar_{text}"
        if column not in seen:
            seen.add(column)
            columns.append(column)
    return columns


def configured_feature_groups(fundamentals: dict[str, Any]) -> dict[str, list[str]]:
    groups = {key: list(value) for key, value in DEFAULT_FEATURE_GROUPS.items()}
    for key, value in fundamentals.get("feature_groups", {}).items():
        groups[str(key)] = list(value)
    return groups


def to_naive_datetime(value: Any) -> pd.Series:
    return pd.to_datetime(value, errors="coerce", utc=True, format="mixed").dt.tz_convert(None).dt.normalize()


def to_naive_timestamp(value: Any) -> pd.Series:
    return pd.to_datetime(value, errors="coerce", utc=True, format="mixed").dt.tz_convert(None)


def safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = denominator.replace(0, pd.NA)
    return numerator / denominator


def empty_feature_frame(enable_valuation: bool, coverage_features_enabled: bool = False) -> pd.DataFrame:
    columns = [f"edgar_{column}" for column in BASE_FEATURE_COLUMNS]
    if enable_valuation:
        columns.extend(f"edgar_{column}" for column in VALUATION_FEATURE_COLUMNS)
    if coverage_features_enabled:
        columns.extend(f"edgar_{column}" for column in COVERAGE_AWARE_FEATURE_COLUMNS)
    index = pd.MultiIndex.from_arrays([[], []], names=["datetime", "instrument"])
    return pd.DataFrame(columns=columns, index=index)
