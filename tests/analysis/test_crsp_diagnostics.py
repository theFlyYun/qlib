from __future__ import annotations

from pathlib import Path

import pandas as pd

from analysis.nasdaq_top500_score.crsp_diagnostics import (
    build_horizon_labels,
    cross_section_zscore,
    label_distribution_by_year,
    run_membership_diagnostics,
    run_price_adjustment_diagnostics,
    sample_label_rows,
)


def test_build_horizon_labels_uses_future_returns_and_membership() -> None:
    daily = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-06"]),
            "instrument": ["P1"] * 4,
            "DlyRet": [0.99, 0.01, 0.02, 0.03],
        }
    )
    membership = pd.DataFrame(
        [
            {
                "symbol": "P1",
                "instrument": "P1",
                "month_end_date": "2019-12-31",
                "effective_start": "2020-01-02",
                "effective_end": "2020-01-06",
            }
        ]
    )
    labels = build_horizon_labels(daily, membership, [2])[2]

    assert pd.isna(labels.loc[(pd.Timestamp("2020-01-01"), "P1")])
    assert round(float(labels.loc[(pd.Timestamp("2020-01-02"), "P1")]), 6) == round((1.02 * 1.03) - 1.0, 6)


def test_price_adjustment_diagnostics_compares_adjusted_close_to_retx(tmp_path: Path) -> None:
    source_dir = tmp_path / "qlib_source_csv"
    source_dir.mkdir()
    pd.DataFrame(
        {
            "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
            "symbol": ["P1", "P1", "P1"],
            "open": [10.0, 11.0, 12.1],
            "high": [10.0, 11.0, 12.1],
            "low": [10.0, 11.0, 12.1],
            "close": [10.0, 11.0, 12.1],
            "volume": [100, 100, 100],
        }
    ).to_csv(source_dir / "P1.csv", index=False)
    daily = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"]),
            "instrument": ["P1", "P1", "P1"],
            "DlyRetx": [0.0, 0.1, 0.1],
        }
    )

    summary = run_price_adjustment_diagnostics(tmp_path, source_dir, daily, ["P1"])

    assert summary["max_abs_retx_diff"] < 1e-12
    assert (tmp_path / "price_adjustment_diagnostics.csv").exists()


def test_membership_diagnostics_detects_non_member_labels(tmp_path: Path) -> None:
    labels = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2020-01-01", "2020-01-02"]),
            "instrument": ["P1", "P1"],
            "label_10d_total_return": [0.1, 0.2],
        }
    )
    membership = pd.DataFrame(
        [
            {
                "symbol": "P1",
                "instrument": "P1",
                "month_end_date": pd.Timestamp("2019-12-31"),
                "effective_start": pd.Timestamp("2020-01-02"),
                "effective_end": pd.Timestamp("2020-01-31"),
                "rank": 1,
            }
        ]
    )
    config = {"universe": {"top_n_by_market_cap": 1}}

    summary = run_membership_diagnostics(config, tmp_path, labels, membership, ["P1"])

    assert summary["non_member_label_fail_count"] == 1
    assert (tmp_path / "membership_diagnostics.csv").exists()


def test_label_distribution_and_sampling_are_stable() -> None:
    labels = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2020-01-01", "2020-01-02", "2022-01-03"]),
            "instrument": ["P1", "P1", "P2"],
            "label_10d_total_return": [0.1, None, -0.2],
            "recomputed_label": [0.1, None, -0.2],
        }
    )
    labels["diff"] = labels["label_10d_total_return"] - labels["recomputed_label"]
    labels["abs_diff"] = labels["diff"].abs()
    config = {
        "split": {
            "train": {"start": "2020-01-01", "end": "2021-12-31"},
            "valid": {"start": "2022-01-01", "end": "2022-12-31"},
            "test": {"start": "2023-01-01", "end": "2023-12-31"},
        }
    }

    sample = sample_label_rows(labels, instruments=2, dates_per_instrument=2)
    dist = label_distribution_by_year(labels, config)

    assert sample["match"].all()
    assert set(dist["segment"]) == {"train", "valid"}


def test_cross_section_zscore_is_per_date() -> None:
    index = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2020-01-01"), "P1"),
            (pd.Timestamp("2020-01-01"), "P2"),
            (pd.Timestamp("2020-01-02"), "P1"),
            (pd.Timestamp("2020-01-02"), "P2"),
        ],
        names=["datetime", "instrument"],
    )
    values = pd.Series([1.0, 3.0, 10.0, 14.0], index=index)

    z = cross_section_zscore(values)

    assert z.loc[(pd.Timestamp("2020-01-01"), "P1")] == -1.0
    assert z.loc[(pd.Timestamp("2020-01-02"), "P2")] == 1.0
