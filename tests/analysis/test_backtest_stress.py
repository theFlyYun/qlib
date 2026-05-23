from __future__ import annotations

from pathlib import Path

import pandas as pd

import analysis.nasdaq_top500_score.backtest_stress as stress_module
from analysis.nasdaq_top500_score.backtest_stress import run_backtest_stress_tests


def write_price_csv(source_dir: Path, symbol: str, dates: pd.DatetimeIndex) -> None:
    pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "symbol": symbol,
            "open": [10, 11, 12, 13, 14, 15],
            "high": [11, 12, 13, 14, 15, 16],
            "low": [9, 10, 11, 12, 13, 14],
            "close": [10, 12, 13, 14, 15, 16],
            "vwap": [10, 11.5, 12.5, 13.5, 14.5, 15.5],
            "volume": [1_000_000] * len(dates),
        }
    ).to_csv(source_dir / f"{symbol}.csv", index=False)


def test_backtest_stress_reuses_predictions_and_varies_entry_price_and_cost(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "qlib_source_csv"
    qlib_dir = tmp_path / "qlib_data"
    (qlib_dir / "calendars").mkdir(parents=True)
    source_dir.mkdir()
    dates = pd.bdate_range("2024-01-02", periods=6)
    pd.Series(dates.strftime("%Y-%m-%d")).to_csv(qlib_dir / "calendars/day.txt", index=False, header=False)
    write_price_csv(source_dir, "AAA", dates)
    pd.DataFrame(
        [{"symbol": "AAA", "history_rows": 2400, "history_bucket": "full_10y"}]
    ).to_csv(tmp_path / "history_buckets.csv", index=False)
    predictions = pd.DataFrame([{"datetime": dates[0], "instrument": "AAA", "score": 1.0}])
    universe = pd.DataFrame([{"symbol": "AAA", "sector": "Technology", "industry": "Software"}])
    config = {
        "report": {"top_n": 1},
        "bucket_ranking": {
            "enabled": True,
            "quotas": {"full_10y": 1, "5_10y": 0, "2_5y": 0, "lt_2y": 0},
            "refill_order": ["full_10y", "5_10y", "2_5y", "lt_2y"],
        },
        "industry_constraints": {"enabled": False},
        "backtest": {
            "enabled": True,
            "top_n": 1,
            "holding_days": 2,
            "rebalance_days": 1,
            "entry_lag_days": 1,
            "price": "close",
            "cost_bps": 0,
            "min_positions": 1,
        },
        "benchmark": {"enabled": False},
        "attribution": {"enabled": False},
        "backtest_stress": {
            "enabled": True,
            "baseline": {"entry_lag_days": 1, "entry_price": "close", "cost_bps": 0},
            "entry_lag_days": [1],
            "entry_prices": ["close", "open", "vwap_proxy"],
            "cost_bps": [0, 50],
        },
    }
    paths = {
        "source_dir": source_dir,
        "qlib_dir": qlib_dir,
        "history_buckets_csv": tmp_path / "history_buckets.csv",
        "backtest_stress_dir": tmp_path / "backtest_stress",
        "backtest_stress_matrix": tmp_path / "backtest_stress_matrix.csv",
        "backtest_stress_summary": tmp_path / "backtest_stress_summary.yaml",
    }
    load_calls = []
    original_load_market_data = stress_module.load_market_data

    def counting_load_market_data(source_dir_arg: Path, price_column: str):
        load_calls.append(price_column)
        return original_load_market_data(source_dir_arg, price_column)

    monkeypatch.setattr(stress_module, "load_market_data", counting_load_market_data)

    summary = run_backtest_stress_tests(predictions, universe, config, paths)
    matrix = pd.read_csv(paths["backtest_stress_matrix"])

    assert summary["enabled"] is True
    assert len(matrix) == 6
    assert set(matrix["entry_price"]) == {"close", "open", "vwap_proxy"}
    assert set(matrix["backtest_price"]) == {"close", "open", "vwap"}
    assert sorted(load_calls) == ["close", "open", "vwap"]
    assert matrix[matrix["cost_bps"].eq(50)]["cumulative_return"].max() < matrix[matrix["cost_bps"].eq(0)]["cumulative_return"].max()
