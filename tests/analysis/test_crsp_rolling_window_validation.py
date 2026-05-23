from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from analysis.nasdaq_top500_score.crsp_rolling_window_validation import (
    load_manifest,
    manifest_entries,
    run_crsp_rolling_window_validation,
)
from analysis.nasdaq_top500_score.data_sources.crsp import crsp_label_column
from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import load_config


def write_config(path: Path, run_dir: Path, *, name: str, test_start: str, test_end: str) -> None:
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
        "label": {"expression": f"${crsp_label_column(10)}", "name": "LABEL0"},
        "features": {"handler": "Alpha158", "instruments": "all"},
        "report": {"top_n": 10},
        "split": {
            "method": "date",
            "warmup_days": 60,
            "train": {"start": "2010-01-01", "end": "2015-12-31"},
            "valid": {"start": "2016-01-01", "end": "2017-12-31"},
            "test": {"start": test_start, "end": test_end},
        },
        "model": {"class": "LGBModel", "kwargs": {"num_leaves": 16, "max_depth": 4}},
        "backtest": {
            "enabled": True,
            "top_n": 10,
            "holding_days": 10,
            "rebalance_days": 10,
            "entry_lag_days": 1,
            "price": "open",
            "min_positions": 5,
        },
        "strategy_comparison": {
            "enabled": True,
            "variants": [
                {"name": "global_top10", "industry_constraints": {"enabled": False}},
                {"name": "sector_cap_2_top10", "industry_constraints": {"enabled": True, "max_sector": 2, "max_industry": 2}},
            ],
        },
    }
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def write_run(run_dir: Path, *, ic: float, rank_ic: float, cap2_alpha: float) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.md").write_text(
        f"- Test 日均 IC：{ic:.6f}\n- Test 日均 Rank IC：{rank_ic:.6f}\n",
        encoding="utf-8",
    )
    pd.DataFrame([{"datetime": "2018-01-02", "instrument": "P1", "score": 1.0}]).to_csv(
        run_dir / "test_predictions.csv",
        index=False,
    )
    (run_dir / "backtest_summary.yaml").write_text(
        yaml.safe_dump({"annualized_return": 0.2, "max_drawdown": -0.1}),
        encoding="utf-8",
    )
    (run_dir / "benchmark_summary.yaml").write_text(
        yaml.safe_dump({"alpha_annualized": 0.03, "beta": 1.1}),
        encoding="utf-8",
    )
    (run_dir / "training_summary.yaml").write_text(
        yaml.safe_dump({"best_iteration": 12, "best_valid_l2": 0.99}),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {"entry_lag_days": 1, "entry_price": "open", "cost_bps": 50, "annualized_return": 0.15},
        ]
    ).to_csv(run_dir / "backtest_stress_matrix.csv", index=False)
    pd.DataFrame(
        [
            {"name": "global_top10", "annualized_return": 0.2, "alpha_annualized": 0.03, "beta": 1.1, "max_drawdown": -0.1},
            {"name": "sector_cap_2_top10", "annualized_return": 0.25, "alpha_annualized": cap2_alpha, "beta": 1.0, "max_drawdown": -0.08},
        ]
    ).to_csv(run_dir / "strategy_comparison.csv", index=False)


def test_crsp_rolling_window_validation_summarizes_fake_runs(tmp_path: Path) -> None:
    alpha_config = tmp_path / "alpha.yaml"
    edgar_config = tmp_path / "edgar.yaml"
    alpha_run = tmp_path / "alpha_run"
    edgar_run = tmp_path / "edgar_run"
    write_config(alpha_config, alpha_run, name="alpha", test_start="2018-01-01", test_end="2019-12-31")
    write_config(edgar_config, edgar_run, name="edgar", test_start="2018-01-01", test_end="2019-12-31")
    write_run(alpha_run, ic=0.01, rank_ic=0.02, cap2_alpha=0.04)
    write_run(edgar_run, ic=0.02, rank_ic=0.03, cap2_alpha=0.05)
    manifest = {
        "output_dir": str(tmp_path / "rolling"),
        "windows": [{"id": "2018_2019", "label": "2018-2019"}],
        "experiments": [
            {"feature_set": "alpha158_only", "config": str(alpha_config)},
            {"feature_set": "edgar_mini_core", "config": str(edgar_config)},
        ],
    }
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    summary = run_crsp_rolling_window_validation(manifest_path, only_summary=True)

    assert summary["status"].tolist() == ["ok", "ok"]
    assert summary.loc[summary["feature_set"].eq("edgar_mini_core"), "sector_cap_2_alpha_annualized"].iloc[0] == 0.05
    assert (tmp_path / "rolling" / "crsp_rolling_window_summary.csv").exists()
    assert (tmp_path / "rolling" / "crsp_rolling_window_comparison.yaml").exists()
    assert (tmp_path / "rolling" / "report.md").exists()


def test_crsp_rolling_window_configs_parse_and_match_manifest() -> None:
    manifest = load_manifest(Path("analysis/nasdaq_top500_score/configs/crsp_rolling_windows/manifest.yaml"))
    entries = manifest_entries(manifest)
    assert len(entries) == 8
    expected_tests = {window["id"]: window["test"] for window in manifest["windows"]}
    for entry in entries:
        config = load_config(entry["config"])
        split = config["split"]
        assert split["test"] == expected_tests[entry["window_id"]]
        assert split["train"]["end"] < split["valid"]["start"]
        assert split["valid"]["end"] < split["test"]["start"]
        assert int(config["crsp"]["label_horizon_days"]) == 10
        assert config["label"]["expression"] == f"${crsp_label_column(10)}"
        assert int(config["backtest"]["holding_days"]) == 10
        assert int(config["backtest"]["rebalance_days"]) == 10
        variants = {variant["name"]: variant for variant in config["strategy_comparison"]["variants"]}
        assert set(variants) == {"global_top10", "sector_cap_2_top10"}
        assert variants["sector_cap_2_top10"]["industry_constraints"]["max_sector"] == 2
