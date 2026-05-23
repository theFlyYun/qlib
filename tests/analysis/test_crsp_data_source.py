from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from analysis.nasdaq_top500_score.backtest import filter_day_by_membership
from analysis.nasdaq_top500_score.data_sources.crsp import (
    CRSPDataSource,
    build_adjusted_qlib_frame,
    crsp_prepared_dataset_key,
    crsp_label_column,
    filter_membership_to_data_window,
    forward_compound_return,
)
from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import load_config


def make_crsp_config(tmp_path: Path, raw_csv: Path) -> dict[str, Any]:
    return {
        "experiment": {"name": "crsp_fixture", "output_dir": str(tmp_path / "run")},
        "universe": {"provider": "crsp", "mode": "monthly_dynamic_top500", "top_n_by_market_cap": 2, "min_history_rows": 2},
        "data": {
            "source": "crsp",
            "start_date": "2020-01-30",
            "end_date": "2020-03-05",
            "freq": "day",
            "price_adjustment": "crsp_ret_adjusted",
            "vwap_method": "ohlc_mean",
        },
        "crsp": {
            "raw_csv_path": str(raw_csv),
            "warehouse_dir": str(tmp_path / "warehouse"),
            "prepared_dataset": {
                "enabled": True,
                "root_dir": str(tmp_path / "prepared"),
                "copy_mode": "copy",
            },
            "chunk_rows": 4,
            "label_horizon_days": 2,
            "label_only_member_dates": True,
            "major_exchanges": ["N", "Q", "A"],
        },
        "label": {"expression": "$label_2d_total_return", "name": "LABEL0"},
        "features": {"handler": "Alpha158", "instruments": "all"},
        "split": {
            "method": "date",
            "warmup_days": 1,
            "train": {"start": "2020-01-30", "end": "2020-02-05"},
            "valid": {"start": "2020-02-06", "end": "2020-02-28"},
            "test": {"start": "2020-03-02", "end": "2020-03-05"},
        },
        "model": {"class": "LGBModel", "kwargs": {}},
        "report": {"top_n": 2},
    }


def make_paths(tmp_path: Path) -> dict[str, Path]:
    run = tmp_path / "run"
    run.mkdir(parents=True)
    return {
        "output_dir": run,
        "source_dir": run / "qlib_source_csv",
        "qlib_dir": run / "qlib_data",
        "universe_csv": run / "universe.csv",
        "universe_candidates_csv": run / "universe_candidates.csv",
        "universe_selection_csv": run / "universe_selection.csv",
        "security_master_csv": run / "security_master.csv",
        "failures_csv": run / "download_failures.csv",
        "membership_csv": run / "membership.csv",
        "crsp_inventory_report": run / "crsp_inventory_report.md",
    }


def write_fixture_crsp_csv(path: Path) -> None:
    rows = []
    dates = pd.to_datetime(["2020-01-30", "2020-01-31", "2020-02-03", "2020-02-28", "2020-03-02", "2020-03-03", "2020-03-04", "2020-03-05"])
    caps = {
        10001: {"ticker": "AAA", "caps": {"2020-01-31": 1000, "2020-02-28": 1000}},
        10002: {"ticker": "BBB", "caps": {"2020-01-31": 2000, "2020-02-28": 2000}},
        10003: {"ticker": "CCC", "caps": {"2020-01-31": 500, "2020-02-28": 3000}},
    }
    for permno, info in caps.items():
        price = 10 + (permno - 10000)
        for index, date in enumerate(dates):
            date_text = date.strftime("%Y-%m-%d")
            cap = info["caps"].get(date_text, info["caps"].get("2020-01-31", 1000))
            rows.append(
                {
                    "PERMNO": permno,
                    "PERMCO": permno + 50000,
                    "SecInfoStartDt": "2000-01-01",
                    "SecInfoEndDt": "",
                    "SecurityBegDt": "2000-01-01",
                    "SecurityEndDt": "" if permno != 10002 else "2021-01-01",
                    "SecurityHdrFlg": "Y",
                    "CUSIP": f"{permno}00",
                    "CUSIP9": f"{permno}0000",
                    "PrimaryExch": "Q" if permno != 10001 else "N",
                    "ConditionalType": "",
                    "ExchangeTier": "",
                    "TradingStatusFlg": "A",
                    "SecurityNm": f"{info['ticker']} Common Stock",
                    "ShareClass": "",
                    "USIncFlg": "Y",
                    "IssuerType": "CORP",
                    "SecurityType": "EQTY",
                    "SecuritySubType": "COM",
                    "ShareType": "NS",
                    "SecurityActiveFlg": "N" if permno == 10002 else "Y",
                    "DelActionType": "",
                    "DelStatusType": "",
                    "DelReasonType": "MERGER" if permno == 10002 else "",
                    "DelPaymentType": "",
                    "Ticker": info["ticker"],
                    "TradingSymbol": info["ticker"],
                    "SICCD": "7372",
                    "NAICS": "511210",
                    "IssuerNm": f"{info['ticker']} Inc",
                    "YYYYMMDD": int(date.strftime("%Y%m%d")),
                    "DlyCalDt": date_text,
                    "DlyDelFlg": "",
                    "DlyPrc": price + index,
                    "DlyCap": cap + index,
                    "DlyRet": 0.01,
                    "DlyRetx": 0.01,
                    "DlyVol": 1000 + index,
                    "DlyClose": price + index,
                    "DlyLow": price + index - 0.5,
                    "DlyHigh": price + index + 0.5,
                    "DlyOpen": price + index - 0.2,
                    "ShrOut": 100,
                    "ShrAdrFlg": "N",
                }
            )
    pd.DataFrame(rows).to_csv(path, index=False)


def test_crsp_data_source_builds_warehouse_membership_and_source_csv(tmp_path: Path) -> None:
    raw_csv = tmp_path / "crsp.csv"
    write_fixture_crsp_csv(raw_csv)
    config = make_crsp_config(tmp_path, raw_csv)
    paths = make_paths(tmp_path)

    prepared = CRSPDataSource(config, paths).prepare()

    assert prepared.metadata["source"] == "crsp"
    assert (tmp_path / "warehouse" / "crsp_daily").exists()
    assert (tmp_path / "warehouse" / "crsp_monthly_top500_membership.parquet").exists()
    assert paths["crsp_inventory_report"].exists()
    assert set(prepared.universe["symbol"]) == {"P10001", "P10002", "P10003"}

    membership = pd.read_csv(paths["membership_csv"])
    for column in ["siccd", "naics", "icb_industry", "sector", "industry"]:
        assert column in membership.columns
    jan_members = membership[membership["month_end_date"].eq("2020-01-31")]
    assert jan_members["symbol"].tolist() == ["P10002", "P10001"]
    assert jan_members["effective_start"].unique().tolist() == ["2020-02-03"]

    source = pd.read_csv(paths["source_dir"] / "P10002.csv")
    assert "label_2d_total_return" in source.columns
    assert source["symbol"].eq("P10002").all()
    assert prepared.metadata["prepared_dataset_key"].startswith("crsp_")
    assert (tmp_path / "prepared" / prepared.metadata["prepared_dataset_key"] / "qlib_source_csv").exists()


def test_crsp_prepared_dataset_key_is_stable_and_changes_with_label_horizon(tmp_path: Path) -> None:
    raw_csv = tmp_path / "crsp.csv"
    config = make_crsp_config(tmp_path, raw_csv)
    same = make_crsp_config(tmp_path, raw_csv)
    changed = make_crsp_config(tmp_path, raw_csv)
    changed["crsp"]["label_horizon_days"] = 5
    changed["label"]["expression"] = "$label_5d_total_return"

    assert crsp_prepared_dataset_key(config) == crsp_prepared_dataset_key(same)
    assert crsp_prepared_dataset_key(config) != crsp_prepared_dataset_key(changed)


def test_crsp_prepared_dataset_key_changes_with_industry_schema(tmp_path: Path) -> None:
    raw_csv = tmp_path / "crsp.csv"
    config = make_crsp_config(tmp_path, raw_csv)
    changed = make_crsp_config(tmp_path, raw_csv)
    changed["industry_mapping"] = {"enabled": True, "schema_version": 2, "primary_source": "crsp_monthly_row"}

    assert crsp_prepared_dataset_key(config) != crsp_prepared_dataset_key(changed)


def test_crsp_prepared_dataset_reuse_does_not_rebuild_source_csv(tmp_path: Path) -> None:
    raw_csv = tmp_path / "crsp.csv"
    write_fixture_crsp_csv(raw_csv)
    config = make_crsp_config(tmp_path, raw_csv)
    first_paths = make_paths(tmp_path / "first")
    second_paths = make_paths(tmp_path / "second")

    first = CRSPDataSource(config, first_paths).prepare()
    marker = Path(first.metadata["prepared_dataset_dir"]) / "qlib_source_csv" / "CACHE_MARKER.txt"
    marker.write_text("cache-hit", encoding="utf-8")
    second = CRSPDataSource(config, second_paths).prepare()

    assert second.metadata["prepared_dataset_reused"] is True
    assert (second_paths["source_dir"] / "CACHE_MARKER.txt").read_text(encoding="utf-8") == "cache-hit"


def test_crsp_prepared_dataset_filters_reused_warehouse_to_config_window(tmp_path: Path) -> None:
    raw_csv = tmp_path / "crsp.csv"
    write_fixture_crsp_csv(raw_csv)
    full_config = make_crsp_config(tmp_path, raw_csv)
    full_paths = make_paths(tmp_path / "full")
    CRSPDataSource(full_config, full_paths).prepare()

    window_config = make_crsp_config(tmp_path, raw_csv)
    window_config["experiment"]["output_dir"] = str(tmp_path / "window" / "run")
    window_config["data"]["start_date"] = "2020-02-03"
    window_config["split"]["train"]["start"] = "2020-02-03"
    window_paths = make_paths(tmp_path / "window")
    prepared = CRSPDataSource(window_config, window_paths).prepare()

    assert prepared.metadata["prepared_dataset_key"] != crsp_prepared_dataset_key(full_config)
    membership = pd.read_csv(window_paths["membership_csv"])
    assert membership["effective_end"].min() >= "2020-02-28"
    source = pd.read_csv(window_paths["source_dir"] / "P10002.csv")
    assert source["date"].min() >= "2020-02-03"


def test_filter_membership_to_data_window_keeps_overlapping_intervals(tmp_path: Path) -> None:
    config = make_crsp_config(tmp_path, tmp_path / "crsp.csv")
    config["data"]["start_date"] = "2020-02-03"
    config["data"]["end_date"] = "2020-02-28"
    membership = pd.DataFrame(
        [
            {"symbol": "P1", "effective_start": "2020-01-02", "effective_end": "2020-01-31"},
            {"symbol": "P2", "effective_start": "2020-01-31", "effective_end": "2020-02-28"},
            {"symbol": "P3", "effective_start": "2020-03-02", "effective_end": "2020-03-31"},
        ]
    )

    filtered = filter_membership_to_data_window(membership, config)

    assert filtered["symbol"].tolist() == ["P2"]


def test_crsp_membership_filter_limits_signal_day_candidates() -> None:
    predictions = pd.DataFrame(
        [
            {"symbol": "P10003", "score": 0.9},
            {"symbol": "P10002", "score": 0.8},
            {"symbol": "P10001", "score": 0.7},
        ]
    )
    membership = pd.DataFrame(
        [
            {"symbol": "P10002", "effective_start": "2020-02-03", "effective_end": "2020-02-28"},
            {"symbol": "P10001", "effective_start": "2020-02-03", "effective_end": "2020-02-28"},
            {"symbol": "P10003", "effective_start": "2020-03-02", "effective_end": "2020-03-31"},
        ]
    )

    filtered = filter_day_by_membership(predictions, pd.Timestamp("2020-02-10"), membership)

    assert filtered["symbol"].tolist() == ["P10002", "P10001"]


def test_crsp_forward_label_uses_future_returns_only() -> None:
    returns = pd.Series([0.99, 0.01, 0.02, 0.03])

    labels = forward_compound_return(returns, 2)

    assert round(float(labels.iloc[0]), 6) == round((1.01 * 1.02) - 1.0, 6)
    assert round(float(labels.iloc[1]), 6) == round((1.02 * 1.03) - 1.0, 6)
    assert pd.isna(labels.iloc[2])


def test_adjusted_frame_masks_labels_outside_membership() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-31", "2020-02-03", "2020-02-03", "2020-02-04", "2020-02-05"]),
            "DlyRet": [0.0, 0.01, 0.50, 0.02, 0.03],
            "DlyRetx": [0.0, 0.01, 0.50, 0.02, 0.03],
            "DlyOpen": [10, 11, pd.NA, 12, 13],
            "DlyHigh": [11, 12, pd.NA, 13, 14],
            "DlyLow": [9, 10, pd.NA, 11, 12],
            "DlyClose": [10, 11, pd.NA, 12, 13],
            "DlyPrc": [10, 11, 99, 12, 13],
            "DlyVol": [100, 100, 100, 100, 100],
        }
    )

    output = build_adjusted_qlib_frame(
        frame,
        "P10001",
        label_horizon=2,
        intervals=[(pd.Timestamp("2020-02-03"), pd.Timestamp("2020-02-05"))],
        label_only_member_dates=True,
    )

    assert pd.isna(output.loc[output["date"].eq("2020-01-31"), "label_2d_total_return"].iloc[0])
    assert pd.notna(output.loc[output["date"].eq("2020-02-03"), "label_2d_total_return"].iloc[0])
    assert output["date"].is_unique


def test_crsp_label_column_names_follow_horizon() -> None:
    assert crsp_label_column(5) == "label_5d_total_return"
    assert crsp_label_column(20) == "label_20d_total_return"


def test_crsp_configs_parse() -> None:
    for path in [
        Path("analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_10d_2000_2025.yaml"),
        Path("analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_macro_10d_2000_2025.yaml"),
    ]:
        config = load_config(path)
        assert config["data"]["source"] == "crsp"
        assert config["data"]["start_date"] == "2000-01-03"
        assert config["data"]["end_date"] == "2025-12-31"
        horizon = int(config["crsp"]["label_horizon_days"])
        assert config["backtest"]["rebalance_days"] == horizon
        assert config["label"]["expression"] == f"${crsp_label_column(horizon)}"
