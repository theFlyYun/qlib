from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import yaml

from analysis.nasdaq_top500_score.backtest import run_topk_backtest


def write_price_csv(source_dir: Path, symbol: str, dates: pd.DatetimeIndex, close: list[float]) -> None:
    pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "symbol": symbol,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "vwap": close,
            "volume": 1_000_000,
        }
    ).to_csv(source_dir / f"{symbol}.csv", index=False)


def test_topk_backtest_uses_signal_entry_exit_costs_and_writes_outputs(tmp_path: Path) -> None:
    source_dir = tmp_path / "qlib_source_csv"
    qlib_dir = tmp_path / "qlib_data"
    calendar_dir = qlib_dir / "calendars"
    source_dir.mkdir()
    calendar_dir.mkdir(parents=True)
    dates = pd.bdate_range("2024-01-02", periods=10)
    pd.Series(dates.strftime("%Y-%m-%d")).to_csv(calendar_dir / "day.txt", index=False, header=False)

    write_price_csv(source_dir, "AAA", dates, [10, 10, 10.5, 11, 11, 11, 11, 11, 11, 11])
    write_price_csv(source_dir, "BBB", dates, [20, 20, 20, 20, 20, 20, 20, 20, 20, 20])
    write_price_csv(source_dir, "CCC", dates, [30, 30, 30, 29, 29, 29, 29, 29, 29, 29])

    pd.DataFrame(
        [
            {"symbol": "AAA", "history_rows": 2400, "first_date": "2016-05-17", "last_date": "2026-05-15", "history_bucket": "full_10y"},
            {"symbol": "BBB", "history_rows": 2400, "first_date": "2016-05-17", "last_date": "2026-05-15", "history_bucket": "full_10y"},
            {"symbol": "CCC", "history_rows": 2400, "first_date": "2016-05-17", "last_date": "2026-05-15", "history_bucket": "full_10y"},
        ]
    ).to_csv(tmp_path / "history_buckets.csv", index=False)

    predictions = pd.DataFrame(
        [
            {"datetime": date, "instrument": "AAA", "score": 0.9}
            for date in dates[:6]
        ]
        + [{"datetime": date, "instrument": "BBB", "score": 0.8} for date in dates[:6]]
        + [{"datetime": date, "instrument": "CCC", "score": 0.1} for date in dates[:6]]
    )
    universe = pd.DataFrame(
        [
            {"symbol": "AAA", "sector": "Technology", "industry": "Software"},
            {"symbol": "BBB", "sector": "Health Care", "industry": "Biotech"},
            {"symbol": "CCC", "sector": "Industrials", "industry": "Machinery"},
        ]
    )
    config = {
        "report": {"top_n": 2},
        "bucket_ranking": {
            "enabled": True,
            "quotas": {"full_10y": 2, "5_10y": 0, "2_5y": 0, "lt_2y": 0},
            "refill_order": ["full_10y", "5_10y", "2_5y", "lt_2y"],
        },
        "industry_constraints": {"enabled": False},
        "backtest": {
            "enabled": True,
            "strategy": "bucketed_topk",
            "top_n": 2,
            "holding_days": 2,
            "rebalance_days": 2,
            "entry_lag_days": 1,
            "price": "close",
            "cost_bps": 10,
            "min_positions": 1,
        },
    }
    paths = {
        "source_dir": source_dir,
        "qlib_dir": qlib_dir,
        "history_buckets_csv": tmp_path / "history_buckets.csv",
        "backtest_nav_csv": tmp_path / "backtest_nav.csv",
        "backtest_positions_csv": tmp_path / "backtest_positions.csv",
        "backtest_summary": tmp_path / "backtest_summary.yaml",
    }

    result = run_topk_backtest(predictions, universe, config, paths)

    assert result.summary["enabled"] is True
    assert result.summary["period_count"] > 0
    assert set(result.positions[result.positions["period"] == 1]["symbol"]) == {"AAA", "BBB"}
    assert math.isclose(float(result.nav.iloc[0]["gross_return"]), 0.05, rel_tol=0, abs_tol=1e-9)
    assert math.isclose(float(result.nav.iloc[0]["cost_return"]), 0.001, rel_tol=0, abs_tol=1e-9)
    assert math.isclose(float(result.nav.iloc[0]["net_return"]), 0.049, rel_tol=0, abs_tol=1e-9)
    assert paths["backtest_nav_csv"].exists()
    assert paths["backtest_positions_csv"].exists()
    summary = yaml.safe_load(paths["backtest_summary"].read_text(encoding="utf-8"))
    assert summary["period_count"] == result.summary["period_count"]
