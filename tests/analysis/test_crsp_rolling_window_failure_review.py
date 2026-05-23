from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from analysis.nasdaq_top500_score.crsp_rolling_window_failure_review import (
    build_drawdown_event,
    load_run_record,
    run_crsp_rolling_window_failure_review,
)


def write_config(path: Path, run_dir: Path, *, name: str) -> None:
    config = {
        "experiment": {"name": name, "output_dir": str(run_dir)},
        "universe": {"provider": "crsp", "mode": "monthly_dynamic_top500", "top_n_by_market_cap": 500, "min_history_rows": 180},
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
        "report": {"top_n": 10},
        "split": {
            "method": "date",
            "train": {"start": "2010-01-01", "end": "2015-12-31"},
            "valid": {"start": "2016-01-01", "end": "2017-12-31"},
            "test": {"start": "2018-01-01", "end": "2019-12-31"},
        },
        "model": {"class": "LGBModel", "kwargs": {"num_leaves": 16}},
        "backtest": {
            "enabled": True,
            "top_n": 10,
            "min_positions": 1,
            "holding_days": 10,
            "rebalance_days": 10,
            "entry_lag_days": 1,
            "price": "open",
            "cost_bps": 0,
            "periods_per_year": 25.2,
        },
        "benchmark": {"enabled": True, "symbol": "SP500"},
        "strategy_comparison": {
            "enabled": True,
            "variants": [
                {"name": "global_top10", "industry_constraints": {"enabled": False}},
                {"name": "sector_cap_2_top10", "industry_constraints": {"enabled": True, "max_sector": 2, "max_industry": 2}},
            ],
        },
    }
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def write_variant_run(run_dir: Path, *, alpha: float, symbols: list[str]) -> None:
    variant_dir = run_dir / "strategy_comparison" / "sector_cap_2_top10"
    variant_dir.mkdir(parents=True, exist_ok=True)
    nav = pd.DataFrame(
        [
            {"period": 1, "signal_date": "2018-01-02", "entry_date": "2018-01-03", "exit_date": "2018-01-17", "position_count": 2, "gross_return": 0.10, "turnover": 1.0, "cost_return": 0.0, "net_return": 0.10, "nav": 1.10, "benchmark_return": 0.02},
            {"period": 2, "signal_date": "2018-01-16", "entry_date": "2018-01-17", "exit_date": "2018-01-31", "position_count": 2, "gross_return": -0.30, "turnover": 1.0, "cost_return": 0.0, "net_return": -0.30, "nav": 0.77, "benchmark_return": -0.05},
            {"period": 3, "signal_date": "2018-01-30", "entry_date": "2018-01-31", "exit_date": "2018-02-14", "position_count": 2, "gross_return": 0.05, "turnover": 0.5, "cost_return": 0.0, "net_return": 0.05, "nav": 0.8085, "benchmark_return": 0.01},
        ]
    )
    nav["benchmark_nav"] = (1.0 + nav["benchmark_return"]).cumprod()
    nav["excess_return"] = nav["net_return"] - nav["benchmark_return"]
    nav["relative_nav"] = nav["nav"] / nav["benchmark_nav"]
    nav.to_csv(variant_dir / "backtest_nav.csv", index=False)
    positions = pd.DataFrame(
        [
            {"period": 1, "signal_date": "2018-01-02", "entry_date": "2018-01-03", "exit_date": "2018-01-17", "symbol": symbols[0], "selected_rank": 1, "sector": "73", "industry": "7372", "history_bucket": "full_10y", "score": 1.0, "weight": 0.5, "gross_return": 0.1, "net_contribution": 0.05, "gross_contribution": 0.05, "excess_contribution": 0.04},
            {"period": 1, "signal_date": "2018-01-02", "entry_date": "2018-01-03", "exit_date": "2018-01-17", "symbol": symbols[1], "selected_rank": 2, "sector": "48", "industry": "4812", "history_bucket": "full_10y", "score": 0.9, "weight": 0.5, "gross_return": -0.2, "net_contribution": -0.1, "gross_contribution": -0.1, "excess_contribution": -0.11},
        ]
    )
    positions.to_csv(variant_dir / "backtest_positions.csv", index=False)
    (variant_dir / "backtest_summary.yaml").write_text(
        yaml.safe_dump({"annualized_return": -0.2, "max_drawdown": -0.3, "avg_turnover": 0.83}),
        encoding="utf-8",
    )
    (variant_dir / "benchmark_summary.yaml").write_text(
        yaml.safe_dump({"alpha_annualized": alpha, "beta": 1.4, "correlation": 0.7, "relative_information_ratio": -0.5}),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {"sector": "73", "holding_count": 1, "period_count": 1, "net_contribution_sum": 0.05, "excess_contribution_sum": 0.04},
            {"sector": "48", "holding_count": 1, "period_count": 1, "net_contribution_sum": -0.10, "excess_contribution_sum": -0.11},
        ]
    ).to_csv(variant_dir / "contribution_by_sector.csv", index=False)
    pd.DataFrame(
        [
            {"symbol": symbols[0], "holding_count": 1, "period_count": 1, "net_contribution_sum": 0.05, "excess_contribution_sum": 0.04},
            {"symbol": symbols[1], "holding_count": 1, "period_count": 1, "net_contribution_sum": -0.10, "excess_contribution_sum": -0.11},
        ]
    ).to_csv(variant_dir / "contribution_by_symbol.csv", index=False)
    pd.DataFrame([{"sector": "73", "avg_weight": 0.5, "max_weight": 0.5, "period_count": 1}]).to_csv(
        variant_dir / "exposure_by_sector.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {
                "name": "sector_cap_2_top10",
                "annualized_return": -0.2,
                "alpha_annualized": alpha,
                "beta": 1.4,
                "max_drawdown": -0.3,
                "max_avg_sector": "73",
                "max_avg_sector_exposure": 0.5,
                "max_sector_weight_any_period": 0.5,
                "avg_sector_hhi": 0.5,
            }
        ]
    ).to_csv(run_dir / "strategy_comparison.csv", index=False)


def test_crsp_rolling_window_failure_review_outputs_stress_and_edgar_delta(tmp_path: Path) -> None:
    alpha_config = tmp_path / "alpha.yaml"
    edgar_config = tmp_path / "edgar.yaml"
    alpha_run = tmp_path / "alpha_run"
    edgar_run = tmp_path / "edgar_run"
    write_config(alpha_config, alpha_run, name="alpha")
    write_config(edgar_config, edgar_run, name="edgar")
    write_variant_run(alpha_run, alpha=-0.05, symbols=["P1", "P2"])
    write_variant_run(edgar_run, alpha=0.02, symbols=["P1", "P3"])
    fundamentals = pd.DataFrame(
        [
            {
                "datetime": pd.Timestamp("2018-01-02"),
                "instrument": "P3",
                "edgar_operating_margin": 0.2,
                "edgar_free_cash_flow_ttm": 10.0,
                "edgar_net_margin": 0.1,
                "edgar_fcf_margin": 0.15,
                "edgar_operating_cash_flow_ttm": 12.0,
            }
        ]
    ).set_index(["datetime", "instrument"])
    fundamentals.to_parquet(edgar_run / "fundamental_features_cleaned.parquet")
    manifest = {
        "windows": [{"id": "2018_2019", "label": "2018-2019"}],
        "experiments": [
            {"feature_set": "alpha158_only", "config": str(alpha_config)},
            {"feature_set": "edgar_mini_core", "config": str(edgar_config)},
        ],
    }
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    summary = run_crsp_rolling_window_failure_review(
        manifest_path,
        tmp_path / "review",
        refresh_rolling_summary=False,
    )

    stress = pd.read_csv(tmp_path / "review" / "sector_cap_2_stress_matrix.csv")
    delta = pd.read_csv(tmp_path / "review" / "rolling_edgar_delta_by_window.csv")
    failure = pd.read_csv(tmp_path / "review" / "rolling_window_failure_summary.csv")

    assert summary["current_mainline_status"] == "unstable_default_candidate"
    assert set(stress["cost_bps"]) == {0.0, 25.0, 50.0}
    assert (edgar_run / "strategy_comparison" / "sector_cap_2_top10" / "backtest_stress_matrix.csv").exists()
    assert delta.iloc[0]["added_rows"] == 1
    assert delta.iloc[0]["removed_rows"] == 1
    assert delta.iloc[0]["added_edgar_operating_margin_mean"] == 0.2
    assert "stress_50bps_annualized_return" in failure.columns
    assert (tmp_path / "review" / "rolling_window_failure_review.md").exists()


def test_drawdown_event_identifies_peak_and_trough(tmp_path: Path) -> None:
    config_path = tmp_path / "alpha.yaml"
    run_dir = tmp_path / "alpha_run"
    write_config(config_path, run_dir, name="alpha")
    write_variant_run(run_dir, alpha=-0.05, symbols=["P1", "P2"])
    record = load_run_record(
        {
            "window_id": "2018_2019",
            "window_label": "2018-2019",
            "feature_set": "alpha158_only",
            "config": config_path,
        },
        "sector_cap_2_top10",
    )

    event = build_drawdown_event(record)

    assert event["peak_date"] == "2018-01-02"
    assert event["trough_date"] == "2018-01-16"
    assert event["max_drawdown"] < -0.25
