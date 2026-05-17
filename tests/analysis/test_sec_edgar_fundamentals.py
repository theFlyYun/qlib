from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from analysis.nasdaq_top500_score.fundamentals.sec_edgar import (
    SEC_UNAVAILABLE_MESSAGE,
    SecEdgarClient,
    build_sec_edgar_features,
    build_submissions_frame,
)
from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import combine_alpha_and_fundamental_raw


def make_config(tmp_path: Path) -> dict[str, Any]:
    return {
        "fundamentals": {
            "enabled": True,
            "source": "sec_edgar",
            "cache_dir": str(tmp_path / "edgar_cache"),
            "forms": ["10-K", "10-Q", "10-K/A", "10-Q/A"],
            "min_filing_count": 4,
            "enable_valuation": True,
            "recent_filing_days": 5,
        }
    }


def make_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "source_dir": tmp_path / "qlib_source_csv",
        "fundamental_features": tmp_path / "fundamental_features.parquet",
        "fundamental_failures": tmp_path / "fundamental_failures.csv",
        "edgar_cik_map": tmp_path / "edgar_cik_map.csv",
        "edgar_cache_dir": tmp_path / "edgar_cache",
    }


class FakeSecEdgarClient:
    def ticker_map(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"symbol": "AAA", "cik": 1001, "title": "AAA Corp", "exchange": "Nasdaq"},
                {"symbol": "NOPRICE", "cik": 1002, "title": "No Price Inc", "exchange": "Nasdaq"},
            ]
        )

    def submissions(self, cik: int) -> dict[str, Any]:
        return {
            "filings": {
                "recent": {
                    "accessionNumber": ["0001", "0002", "0003", "0004", "0005"],
                    "form": ["10-Q", "10-Q", "10-Q", "10-K", "10-Q/A"],
                    "filingDate": ["2020-04-30", "2020-07-30", "2020-10-30", "2021-02-15", "2021-04-30"],
                    "acceptanceDateTime": [
                        "2020-04-30T18:01:00.000Z",
                        "2020-07-30T18:01:00.000Z",
                        "2020-10-30T18:01:00.000Z",
                        "2021-02-15T18:01:00.000Z",
                        "2021-04-30T18:01:00.000Z",
                    ],
                    "reportDate": ["2020-03-31", "2020-06-30", "2020-09-30", "2020-12-31", "2021-03-31"],
                }
            }
        }

    def companyfacts(self, cik: int) -> dict[str, Any]:
        accessions = ["0001", "0002", "0003", "0004", "0005"]
        filed = ["2020-04-30", "2020-07-30", "2020-10-30", "2021-02-15", "2021-04-30"]
        ends = ["2020-03-31", "2020-06-30", "2020-09-30", "2020-12-31", "2021-03-31"]

        def facts(values: list[float], unit: str = "USD") -> dict[str, Any]:
            return {
                "units": {
                    unit: [
                        {"accn": accn, "form": "10-Q", "filed": file_date, "end": end, "val": value}
                        for accn, file_date, end, value in zip(accessions, filed, ends, values, strict=True)
                    ]
                }
            }

        return {
            "facts": {
                "us-gaap": {
                    "Revenues": facts([100.0, 110.0, 120.0, 130.0, 140.0]),
                    # GrossProfit is intentionally absent to verify missing field behavior.
                    "OperatingIncomeLoss": facts([20.0, 22.0, 24.0, 26.0, 28.0]),
                    "NetIncomeLoss": facts([10.0, 11.0, 12.0, 13.0, 14.0]),
                    "EarningsPerShareDiluted": facts([1.0, 1.1, 1.2, 1.3, 1.4], unit="USD/shares"),
                    "Assets": facts([500.0, 510.0, 520.0, 530.0, 540.0]),
                    "Liabilities": facts([250.0, 255.0, 260.0, 265.0, 270.0]),
                    "StockholdersEquity": facts([250.0, 255.0, 260.0, 265.0, 270.0]),
                    "CashAndCashEquivalentsAtCarryingValue": facts([50.0, 51.0, 52.0, 53.0, 54.0]),
                    "NetCashProvidedByUsedInOperatingActivities": facts([15.0, 16.0, 17.0, 18.0, 19.0]),
                    "PaymentsToAcquirePropertyPlantAndEquipment": facts([5.0, 5.0, 6.0, 6.0, 7.0]),
                    "WeightedAverageNumberOfDilutedSharesOutstanding": facts([10.0, 10.0, 10.0, 10.0, 10.0], unit="shares"),
                }
            }
        }


def write_price_csv(tmp_path: Path) -> None:
    source_dir = tmp_path / "qlib_source_csv"
    source_dir.mkdir()
    pd.DataFrame(
        [
            {"date": "2020-04-29", "symbol": "AAA", "open": 10, "high": 10, "low": 10, "close": 10, "vwap": 10, "volume": 1},
            {"date": "2020-04-30", "symbol": "AAA", "open": 11, "high": 11, "low": 11, "close": 11, "vwap": 11, "volume": 1},
            {"date": "2021-05-03", "symbol": "AAA", "open": 12, "high": 12, "low": 12, "close": 12, "vwap": 12, "volume": 1},
        ]
    ).to_csv(source_dir / "AAA.csv", index=False)


def test_build_submissions_frame_filters_10k_10q_and_amendments() -> None:
    submissions = FakeSecEdgarClient().submissions(1001)
    frame = build_submissions_frame(submissions, {"10-K", "10-Q", "10-K/A", "10-Q/A"})

    assert frame["accession"].tolist() == ["0001", "0002", "0003", "0004", "0005"]
    assert frame.iloc[-1]["form"] == "10-Q/A"


def test_sec_client_requires_user_agent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)

    try:
        SecEdgarClient(tmp_path / "cache")
    except Exception as exc:  # noqa: BLE001
        assert SEC_UNAVAILABLE_MESSAGE in str(exc)
    else:
        raise AssertionError("SecEdgarClient should require SEC_EDGAR_USER_AGENT")


def test_combine_alpha_and_fundamental_raw_preserves_feature_and_label_groups() -> None:
    index = pd.MultiIndex.from_tuples(
        [(pd.Timestamp("2020-01-02"), "AAA")],
        names=["datetime", "instrument"],
    )
    alpha_raw = pd.concat(
        {
            "feature": pd.DataFrame({"KMID": [0.1]}, index=index),
            "label": pd.DataFrame({"LABEL0": [0.02]}, index=index),
        },
        axis=1,
    )
    fundamentals = pd.DataFrame({"edgar_revenue_ttm": [pd.NA]}, index=index)

    combined = combine_alpha_and_fundamental_raw(alpha_raw, fundamentals)

    assert ("feature", "KMID") in combined.columns
    assert ("feature", "edgar_revenue_ttm") in combined.columns
    assert ("label", "LABEL0") in combined.columns
    assert pd.isna(combined.loc[(pd.Timestamp("2020-01-02"), "AAA"), ("feature", "edgar_revenue_ttm")])
    assert combined["feature"].dtypes["edgar_revenue_ttm"].kind == "f"


def test_sec_edgar_features_are_point_in_time_and_record_failures(tmp_path: Path) -> None:
    write_price_csv(tmp_path)
    universe = pd.DataFrame({"symbol": ["AAA", "NOPRICE", "MISSING"]})

    result = build_sec_edgar_features(universe, make_config(tmp_path), make_paths(tmp_path), client=FakeSecEdgarClient())

    features = result.features
    assert features.loc[(pd.Timestamp("2020-04-29"), "AAA"), "edgar_revenue_ttm"] != features.loc[
        (pd.Timestamp("2020-04-29"), "AAA"), "edgar_revenue_ttm"
    ]
    assert features.loc[(pd.Timestamp("2020-04-30"), "AAA"), "edgar_revenue_ttm"] == 100.0
    assert features.loc[(pd.Timestamp("2021-05-03"), "AAA"), "edgar_revenue_ttm"] == 500.0
    assert features.loc[(pd.Timestamp("2021-05-03"), "AAA"), "edgar_price_to_sales"] == 12 * 10 / 500
    assert features.loc[(pd.Timestamp("2021-05-03"), "AAA"), "edgar_is_amended_filing"] == 1

    failures = result.failures.set_index(["symbol", "error"])
    assert ("AAA", "missing_fields") in failures.index
    assert "gross_profit" in failures.loc[("AAA", "missing_fields"), "detail"]
    assert ("NOPRICE", "missing_price") in failures.index
    assert ("MISSING", "missing_cik") in failures.index

    assert (tmp_path / "fundamental_features.parquet").exists()
    assert (tmp_path / "fundamental_failures.csv").exists()
    assert (tmp_path / "edgar_cik_map.csv").exists()
