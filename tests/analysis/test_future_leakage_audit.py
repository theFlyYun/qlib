from __future__ import annotations

from pathlib import Path

import pandas as pd

from analysis.nasdaq_top500_score.future_leakage_audit import (
    build_risk_register,
    recalculate_backtest_periods,
    sample_macro_asof,
    sample_universe_selection,
)


def test_sample_universe_selection_flags_current_market_cap_as_high_risk(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "selection_status": "selected",
                "selection_as_of_date": "2023-12-31",
                "asof_close": 50.0,
                "latest_close_for_asof_estimate": 100.0,
                "current_market_cap": 1_000_000_000.0,
                "market_cap_asof_estimate": 500_000_000.0,
            }
        ]
    ).to_csv(run_dir / "universe_selection.csv", index=False)

    sample = sample_universe_selection(run_dir, 20)

    assert sample.iloc[0]["risk_level"] == "high"
    assert "current_market_cap" in sample.columns
    assert "latest_close_for_asof_estimate" in sample.columns


def test_sample_macro_asof_marks_future_effective_dates(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    pd.DataFrame(
        [
            {
                "datetime": "2024-01-03",
                "series_id": "DGS10",
                "name": "dgs10",
                "observation_date": "2024-01-02",
                "realtime_start": "2024-01-02",
                "realtime_end": "9999-12-31",
                "effective_date": "2024-01-04",
                "days_since_release": -1,
                "observation_age_days": 1,
                "value": 4.0,
            }
        ]
    ).to_parquet(run_dir / "macro_asof_observations.parquet")

    sample = sample_macro_asof(run_dir, 20)

    assert bool(sample.iloc[0]["effective_after_feature_date"]) is True


def test_recalculate_backtest_periods_recomputes_weighted_gross_return(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    variant_dir = run_dir / "strategy_comparison" / "sector_cap_2_top10"
    variant_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "period": 1,
                "signal_date": "2024-01-02",
                "entry_date": "2024-01-03",
                "exit_date": "2024-01-10",
                "symbol": "AAA",
                "weight": 0.5,
                "entry_price": 10.0,
                "exit_price": 11.0,
                "gross_return": 0.1,
            },
            {
                "period": 1,
                "signal_date": "2024-01-02",
                "entry_date": "2024-01-03",
                "exit_date": "2024-01-10",
                "symbol": "BBB",
                "weight": 0.5,
                "entry_price": 20.0,
                "exit_price": 20.0,
                "gross_return": 0.0,
            },
        ]
    ).to_csv(variant_dir / "backtest_positions.csv", index=False)
    pd.DataFrame(
        [
            {
                "period": 1,
                "signal_date": "2024-01-02",
                "entry_date": "2024-01-03",
                "exit_date": "2024-01-10",
                "gross_return": 0.05,
                "net_return": 0.049,
                "turnover": 1.0,
                "cost_return": 0.001,
            }
        ]
    ).to_csv(variant_dir / "backtest_nav.csv", index=False)

    sample = recalculate_backtest_periods(run_dir, "sector_cap_2_top10")

    assert bool(sample.iloc[0]["entry_after_signal"]) is True
    assert bool(sample.iloc[0]["exit_after_entry"]) is True
    assert sample.iloc[0]["gross_abs_diff"] < 1e-12


def test_build_risk_register_includes_high_universe_risks(tmp_path: Path) -> None:
    sample = pd.DataFrame([{"symbol": "AAA"}])
    register = build_risk_register(
        tmp_path,
        universe_sample=sample,
        macro_sample=pd.DataFrame(),
        market_sample=pd.DataFrame(),
        edgar_sample=pd.DataFrame(),
        backtest_sample=pd.DataFrame(),
    )

    high = register[register["severity"].eq("HIGH")]
    assert {"R1", "R2"}.issubset(set(high["risk_id"]))
