from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import yaml

from analysis.nasdaq_top500_score.crsp_portfolio_repair import (
    RepairVariant,
    cap_and_renormalize,
    compute_symbol_risk_metrics,
    run_crsp_portfolio_repair,
    select_variant_positions,
)


def test_select_variant_positions_respects_sector_and_industry_caps() -> None:
    rows = []
    for sector_index, sector in enumerate(["10", "20", "30", "40", "50"]):
        for name_index in range(4):
            rows.append(
                {
                    "symbol": f"P{sector}{name_index}",
                    "score": 100 - sector_index * 10 - name_index,
                    "selection_score": 100 - sector_index * 10 - name_index,
                    "sector": sector,
                    "industry": f"{sector}{name_index}",
                    "risk_flag_count": 0,
                    "beta_120d": 1.0,
                }
            )
    day = pd.DataFrame(rows)

    selected, _ = select_variant_positions(day, RepairVariant("topk_width", "top10", 10))

    assert len(selected) == 10
    assert selected["sector"].value_counts().max() == 2
    assert selected["industry"].value_counts().max() == 1


def test_cap_and_renormalize_enforces_single_name_cap() -> None:
    weights = cap_and_renormalize(pd.Series([0.70, 0.20, 0.10]), 0.50)

    assert math.isclose(float(weights.sum()), 1.0, rel_tol=0, abs_tol=1e-12)
    assert float(weights.max()) <= 0.50 + 1e-12


def test_symbol_risk_metrics_do_not_use_future_crash() -> None:
    dates = pd.bdate_range("2024-01-02", periods=140)
    close = [100 + i * 0.1 for i in range(120)] + [20 for _ in range(20)]
    frame = pd.DataFrame(
        {
            "close": close,
            "execution_price": close,
            "volume": 1_000_000,
            "dollar_volume": [x * 1_000_000 for x in close],
        },
        index=dates,
    )
    benchmark = pd.Series(0.001, index=dates, name="benchmark")

    before_crash = compute_symbol_risk_metrics(frame, benchmark, dates[100])
    after_crash = compute_symbol_risk_metrics(frame, benchmark, dates[-1])

    assert before_crash["max_drawdown_60d"] > -0.05
    assert after_crash["max_drawdown_60d"] < -0.75


def write_config(path: Path, run_dir: Path, benchmark_csv: Path, *, name: str) -> None:
    config = {
        "experiment": {"name": name, "output_dir": str(run_dir)},
        "universe": {"top_n_by_market_cap": 500, "min_history_rows": 1},
        "data": {
            "source": "crsp",
            "start_date": "2010-01-01",
            "end_date": "2025-12-31",
            "freq": "day",
            "price_adjustment": "crsp_ret_adjusted",
            "vwap_method": "ohlc_mean",
        },
        "crsp": {"raw_csv_path": "missing.csv", "warehouse_dir": "missing", "label_horizon_days": 10},
        "label": {"expression": "$label_10d_total_return", "name": "LABEL0"},
        "features": {"handler": "Alpha158"},
        "split": {
            "method": "date",
            "train": {"start": "2010-01-01", "end": "2015-12-31"},
            "valid": {"start": "2016-01-01", "end": "2017-12-31"},
            "test": {"start": "2018-01-01", "end": "2019-12-31"},
        },
        "model": {"class": "LGBModel", "kwargs": {"num_leaves": 8}},
        "report": {"top_n": 10},
        "backtest": {
            "enabled": True,
            "top_n": 10,
            "holding_days": 2,
            "rebalance_days": 2,
            "entry_lag_days": 1,
            "price": "open",
            "cost_bps": 0,
            "min_positions": 1,
            "periods_per_year": 25.2,
            "point_in_time_filters": {"enabled": False},
        },
        "benchmark": {"enabled": True, "source": "csv", "path": str(benchmark_csv), "symbol": "SPY"},
    }
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def write_fake_run(run_dir: Path, symbols: list[str], dates: pd.DatetimeIndex) -> None:
    source_dir = run_dir / "qlib_source_csv"
    calendar_dir = run_dir / "qlib_data" / "calendars"
    source_dir.mkdir(parents=True)
    calendar_dir.mkdir(parents=True)
    pd.Series(dates.strftime("%Y-%m-%d")).to_csv(calendar_dir / "day.txt", index=False, header=False)
    universe_rows = []
    history_rows = []
    membership_rows = []
    prediction_rows = []
    for idx, symbol in enumerate(symbols):
        prices = [10 + idx + i * (0.1 + idx * 0.01) for i in range(len(dates))]
        pd.DataFrame(
            {
                "date": dates.strftime("%Y-%m-%d"),
                "symbol": symbol,
                "open": prices,
                "high": prices,
                "low": prices,
                "close": prices,
                "vwap": prices,
                "volume": 1_000_000,
                "label_10d_total_return": [0.01 * (idx + 1)] * len(dates),
            }
        ).to_csv(source_dir / f"{symbol}.csv", index=False)
        universe_rows.append({"symbol": symbol, "sector": str(idx % 4), "industry": str(idx)})
        history_rows.append({"symbol": symbol, "history_bucket": "full_10y", "history_rows": len(dates)})
        membership_rows.append({"symbol": symbol, "effective_start": dates[0].date().isoformat(), "effective_end": dates[-1].date().isoformat()})
        for date in dates[:8]:
            prediction_rows.append({"datetime": date.date().isoformat(), "instrument": symbol, "score": float(len(symbols) - idx)})
    pd.DataFrame(universe_rows).to_csv(run_dir / "universe.csv", index=False)
    pd.DataFrame(history_rows).to_csv(run_dir / "history_buckets.csv", index=False)
    pd.DataFrame(membership_rows).to_csv(run_dir / "membership.csv", index=False)
    pd.DataFrame(prediction_rows).to_csv(run_dir / "test_predictions.csv", index=False)


def test_crsp_portfolio_repair_generates_expected_outputs(tmp_path: Path) -> None:
    dates = pd.bdate_range("2018-01-02", periods=16)
    benchmark_csv = tmp_path / "benchmark.csv"
    pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "symbol": "SPY",
            "open": [100 + i for i in range(len(dates))],
            "high": [100 + i for i in range(len(dates))],
            "low": [100 + i for i in range(len(dates))],
            "close": [100 + i for i in range(len(dates))],
            "vwap": [100 + i for i in range(len(dates))],
            "volume": 1_000_000,
        }
    ).to_csv(benchmark_csv, index=False)
    alpha_run = tmp_path / "alpha_run"
    edgar_run = tmp_path / "edgar_run"
    write_fake_run(alpha_run, [f"P{i}" for i in range(1, 13)], dates)
    write_fake_run(edgar_run, [f"P{i}" for i in range(1, 13)], dates)
    alpha_config = tmp_path / "alpha.yaml"
    edgar_config = tmp_path / "edgar.yaml"
    write_config(alpha_config, alpha_run, benchmark_csv, name="alpha")
    write_config(edgar_config, edgar_run, benchmark_csv, name="edgar")
    manifest = {
        "windows": [{"id": "2018_2019", "label": "2018-2019"}],
        "experiments": [
            {"feature_set": "alpha158_only", "config": str(alpha_config)},
            {"feature_set": "edgar_mini_core", "config": str(edgar_config)},
        ],
    }
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    decision = run_crsp_portfolio_repair(manifest_path, tmp_path / "repair")

    assert decision["stage"] == "CRSP-19"
    assert (tmp_path / "repair" / "topk_width_comparison.csv").exists()
    assert (tmp_path / "repair" / "portfolio_weighting_comparison.csv").exists()
    assert (tmp_path / "repair" / "single_name_risk_filter_comparison.csv").exists()
    assert (tmp_path / "repair" / "beta_control_comparison.csv").exists()
    assert (tmp_path / "repair" / "crsp_portfolio_repair_report.md").exists()
