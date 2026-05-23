from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from analysis.nasdaq_top500_score.crsp_signal_model_comparison import run_crsp_signal_model_comparison
from analysis.nasdaq_top500_score.crsp_edgar_mini_core_horizon_review import run_crsp_edgar_mini_core_horizon_review
from analysis.nasdaq_top500_score.data_sources.crsp import crsp_label_column
from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import load_config


def write_config(path: Path, run_dir: Path, *, name: str, horizon: int, conservative: bool) -> None:
    model_kwargs = {
        "loss": "mse",
        "learning_rate": 0.03 if conservative else 0.05,
        "num_leaves": 16 if conservative else 64,
        "max_depth": 4 if conservative else 8,
        "n_estimators": 300,
    }
    config = {
        "experiment": {"name": name, "output_dir": str(run_dir)},
        "universe": {"provider": "crsp", "mode": "monthly_dynamic_top500", "top_n_by_market_cap": 500, "min_history_rows": 180},
        "data": {
            "source": "crsp",
            "start_date": "2000-01-03",
            "end_date": "2025-12-31",
            "freq": "day",
            "price_adjustment": "crsp_ret_adjusted",
            "vwap_method": "ohlc_mean",
        },
        "crsp": {"raw_csv_path": "missing.csv", "warehouse_dir": "missing_warehouse", "label_horizon_days": horizon},
        "label": {"expression": f"${crsp_label_column(horizon)}", "name": "LABEL0"},
        "features": {"handler": "Alpha158", "instruments": "all"},
        "split": {
            "method": "date",
            "warmup_days": 60,
            "train": {"start": "2000-01-03", "end": "2021-12-31"},
            "valid": {"start": "2022-01-01", "end": "2023-12-31"},
            "test": {"start": "2024-01-01", "end": "2025-12-31"},
        },
        "model": {"class": "LGBModel", "kwargs": model_kwargs},
        "report": {"top_n": 10},
        "backtest": {
            "enabled": True,
            "top_n": 10,
            "holding_days": horizon,
            "rebalance_days": horizon,
            "entry_lag_days": 1,
            "price": "open",
            "cost_bps": 10,
            "min_positions": 5,
        },
        "benchmark": {"enabled": True, "source": "fred", "symbol": "SP500", "series_id": "SP500", "name": "S&P 500 Index"},
    }
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def write_run(run_dir: Path, *, ic: float, rank_ic: float, annualized: float, alpha: float, beta: float) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "report.md").write_text(
        f"- Test 日均 IC：{ic:.6f}\n- Test 日均 Rank IC：{rank_ic:.6f}\n",
        encoding="utf-8",
    )
    (run_dir / "backtest_summary.yaml").write_text(
        yaml.safe_dump(
            {
                "cumulative_return": 0.5,
                "annualized_return": annualized,
                "max_drawdown": -0.2,
                "avg_turnover": 1.5,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "benchmark_summary.yaml").write_text(
        yaml.safe_dump({"excess_cumulative_return": 0.1, "alpha_annualized": alpha, "beta": beta}),
        encoding="utf-8",
    )
    pd.DataFrame([{"variant": "current", "best_iteration": 42, "best_valid_l2": 0.99}]).to_csv(
        run_dir / "early_stopping_variants.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {"entry_lag_days": 1, "entry_price": "open", "cost_bps": 10, "annualized_return": annualized},
            {"entry_lag_days": 1, "entry_price": "open", "cost_bps": 50, "annualized_return": annualized - 0.1},
        ]
    ).to_csv(run_dir / "backtest_stress_matrix.csv", index=False)


def test_crsp_signal_model_comparison_summarizes_runs(tmp_path: Path) -> None:
    config1 = tmp_path / "a.yaml"
    config2 = tmp_path / "b.yaml"
    run1 = tmp_path / "run1"
    run2 = tmp_path / "run2"
    write_config(config1, run1, name="current_10d", horizon=10, conservative=False)
    write_config(config2, run2, name="conservative_20d", horizon=20, conservative=True)
    write_run(run1, ic=-0.01, rank_ic=-0.02, annualized=0.01, alpha=-0.1, beta=1.0)
    write_run(run2, ic=0.02, rank_ic=0.03, annualized=0.2, alpha=0.05, beta=0.9)

    summary = run_crsp_signal_model_comparison([config1, config2], tmp_path / "comparison")

    assert summary["status"].tolist() == ["ok", "ok"]
    assert summary.sort_values("rank_ic_mean").iloc[-1]["name"] == "conservative_20d"
    assert (tmp_path / "comparison" / "crsp_signal_model_comparison.csv").exists()
    assert (tmp_path / "comparison" / "crsp_signal_model_comparison_summary.yaml").exists()


def test_crsp_edgar_mini_core_horizon_review_summarizes_feature_sets(tmp_path: Path) -> None:
    config1 = tmp_path / "alpha.yaml"
    config2 = tmp_path / "edgar.yaml"
    run1 = tmp_path / "alpha_run"
    run2 = tmp_path / "edgar_run"
    write_config(config1, run1, name="alpha_20d", horizon=20, conservative=True)
    write_config(config2, run2, name="edgar_20d", horizon=20, conservative=True)
    config = yaml.safe_load(config2.read_text(encoding="utf-8"))
    config["fundamentals"] = {"enabled": True, "source": "sec_edgar", "cache_dir": "cache", "include_features": ["operating_margin"]}
    config2.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    write_run(run1, ic=0.01, rank_ic=0.01, annualized=0.1, alpha=0.02, beta=1.0)
    write_run(run2, ic=0.02, rank_ic=0.03, annualized=0.2, alpha=0.05, beta=0.9)
    pd.DataFrame(
        [
            {"name": "sector_cap_2_top10", "annualized_return": 0.25, "max_drawdown": -0.1, "alpha_annualized": 0.08, "beta": 0.95}
        ]
    ).to_csv(run2 / "strategy_comparison.csv", index=False)

    summary = run_crsp_edgar_mini_core_horizon_review([config1, config2], tmp_path / "review")

    assert summary["feature_set"].tolist() == ["alpha158_only", "edgar_mini_core"]
    assert summary.loc[summary["feature_set"].eq("edgar_mini_core"), "sector_cap_2_alpha_annualized"].iloc[0] == 0.08
    assert (tmp_path / "review" / "crsp_edgar_mini_core_horizon_summary.csv").exists()
    assert (tmp_path / "review" / "report.md").exists()


def test_crsp_conservative_configs_parse_and_align_horizon() -> None:
    for path in [
        Path("analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_5d_conservative_2000_2025.yaml"),
        Path("analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_10d_conservative_2000_2025.yaml"),
        Path("analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_20d_conservative_2000_2025.yaml"),
        Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_20d_conservative_2010_2025.yaml"),
        Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_60d_conservative_2010_2025.yaml"),
        Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_mini_core_10d_conservative_2010_2025.yaml"),
        Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_mini_core_20d_conservative_2010_2025.yaml"),
        Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_mini_core_60d_conservative_2010_2025.yaml"),
    ]:
        config = load_config(path)
        horizon = int(config["crsp"]["label_horizon_days"])
        assert config["label"]["expression"] == f"${crsp_label_column(horizon)}"
        assert int(config["backtest"]["holding_days"]) == horizon
        assert int(config["backtest"]["rebalance_days"]) == horizon
        assert int(config["model"]["kwargs"]["num_leaves"]) == 16
        assert int(config["model"]["kwargs"]["max_depth"]) == 4
        if "edgar_mini_core" in config["experiment"]["name"]:
            assert config["edgar_effectiveness_review"]["enabled"] is False
            assert config["fundamentals"]["include_features"] == [
                "operating_margin",
                "free_cash_flow_ttm",
                "net_margin",
                "fcf_margin",
                "operating_cash_flow_ttm",
            ]
