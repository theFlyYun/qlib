from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from analysis.nasdaq_top500_score.crsp_macro_conservative_comparison import (
    run_crsp_macro_conservative_comparison,
)
from analysis.nasdaq_top500_score.data_sources.crsp import crsp_label_column
from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import load_config


def write_config(path: Path, run_dir: Path, *, name: str, feature_set: str) -> None:
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
        "crsp": {"raw_csv_path": "missing.csv", "warehouse_dir": "missing_warehouse", "label_horizon_days": 10},
        "label": {"expression": f"${crsp_label_column(10)}", "name": "LABEL0"},
        "features": {"handler": "Alpha158", "instruments": "all"},
        "split": {
            "method": "date",
            "warmup_days": 60,
            "train": {"start": "2000-01-03", "end": "2021-12-31"},
            "valid": {"start": "2022-01-01", "end": "2023-12-31"},
            "test": {"start": "2024-01-01", "end": "2025-12-31"},
        },
        "model": {
            "class": "LGBModel",
            "kwargs": {"loss": "mse", "learning_rate": 0.03, "num_leaves": 16, "max_depth": 4, "n_estimators": 300},
        },
        "macro_features": {"enabled": False},
        "market_features": {"enabled": False},
        "macro_interactions": {"enabled": False},
        "report": {"top_n": 10},
        "backtest": {
            "enabled": True,
            "top_n": 10,
            "holding_days": 10,
            "rebalance_days": 10,
            "entry_lag_days": 1,
            "price": "open",
            "cost_bps": 10,
            "min_positions": 5,
        },
        "benchmark": {"enabled": True, "source": "fred", "symbol": "SP500", "series_id": "SP500", "name": "S&P 500 Index"},
    }
    if feature_set == "direct_macro":
        config["macro_features"] = {
            "enabled": True,
            "source": "fred_alfred",
            "effective_lag_trading_days": 1,
            "append_to_model": True,
            "series": [{"id": "VIXCLS", "name": "vix"}],
        }
    if feature_set == "macro_interactions":
        config["macro_features"] = {
            "enabled": True,
            "source": "fred_alfred",
            "effective_lag_trading_days": 1,
            "append_to_model": False,
            "series": [{"id": "VIXCLS", "name": "vix"}],
        }
        config["market_features"] = {"enabled": True, "source": "qlib_source_csv", "group_levels": [], "relative_features": []}
        config["macro_interactions"] = {
            "enabled": True,
            "interactions": [{"name": "vix_x_mom", "left": "macro_vix", "right": "market_momentum_20d"}],
        }
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def write_run(run_dir: Path, *, ic: float, rank_ic: float, annualized: float, alpha: float, beta: float, macro_cols: int = 0, interaction_cols: int = 0) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "report.md").write_text(
        f"- Test 日均 IC：{ic:.6f}\n- Test 日均 Rank IC：{rank_ic:.6f}\n",
        encoding="utf-8",
    )
    (run_dir / "backtest_summary.yaml").write_text(
        yaml.safe_dump({"cumulative_return": 0.5, "annualized_return": annualized, "max_drawdown": -0.2, "avg_turnover": 1.5}),
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
    (run_dir / "training_summary.yaml").write_text(
        yaml.safe_dump({"best_iteration": 24, "best_valid_l2": 0.98}),
        encoding="utf-8",
    )
    pd.DataFrame([{"entry_lag_days": 1, "entry_price": "open", "cost_bps": 50, "annualized_return": annualized - 0.1}]).to_csv(
        run_dir / "backtest_stress_matrix.csv",
        index=False,
    )
    if macro_cols:
        pd.DataFrame([[1.0] * macro_cols], columns=[f"macro_{i}" for i in range(macro_cols)]).to_parquet(run_dir / "macro_features.parquet")
        pd.DataFrame([], columns=["symbol", "error"]).to_csv(run_dir / "macro_failures.csv", index=False)
    if interaction_cols:
        pd.DataFrame([[1.0] * interaction_cols], columns=[f"interaction_{i}" for i in range(interaction_cols)]).to_parquet(
            run_dir / "macro_interaction_features.parquet"
        )
        pd.DataFrame([], columns=["name", "error"]).to_csv(run_dir / "macro_interaction_failures.csv", index=False)


def test_crsp_macro_conservative_comparison_summarizes_three_feature_sets(tmp_path: Path) -> None:
    configs = []
    for feature_set, annualized in [
        ("alpha158_only", 0.1),
        ("direct_macro", 0.2),
        ("macro_interactions", 0.3),
    ]:
        config_path = tmp_path / f"{feature_set}.yaml"
        run_dir = tmp_path / f"run_{feature_set}"
        write_config(config_path, run_dir, name=feature_set, feature_set=feature_set)
        write_run(
            run_dir,
            ic=0.01,
            rank_ic=0.02,
            annualized=annualized,
            alpha=annualized / 2,
            beta=1.0,
            macro_cols=3 if feature_set != "alpha158_only" else 0,
            interaction_cols=8 if feature_set == "macro_interactions" else 0,
        )
        configs.append(config_path)

    summary = run_crsp_macro_conservative_comparison(configs, tmp_path / "comparison")

    assert summary["feature_set"].tolist() == ["alpha158_only", "direct_macro", "macro_interactions"]
    assert summary["best_iteration"].tolist() == [24.0, 24.0, 24.0]
    assert summary.loc[summary["feature_set"].eq("macro_interactions"), "macro_interaction_feature_count"].iloc[0] == 8
    assert (tmp_path / "comparison" / "crsp_macro_conservative_comparison.csv").exists()


def test_crsp_macro_conservative_configs_parse_and_stay_clean() -> None:
    direct = load_config(Path("analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_macro_10d_conservative_2000_2025.yaml"))
    interactions = load_config(
        Path("analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_macro_interactions_10d_conservative_2000_2025.yaml")
    )

    for config in [direct, interactions]:
        assert int(config["model"]["kwargs"]["num_leaves"]) == 16
        assert int(config["model"]["kwargs"]["max_depth"]) == 4
        assert config["fundamentals"]["enabled"] is False
        assert config["industry_constraints"]["enabled"] is False

    assert direct["macro_features"]["append_to_model"] is True
    assert interactions["macro_features"]["append_to_model"] is False
    assert interactions["market_features"]["append_to_model"] is False
    assert interactions["market_features"]["group_levels"] == []
    for spec in interactions["macro_interactions"]["interactions"]:
        assert "sector" not in spec
        assert "sectors" not in spec
        assert not str(spec["right"]).startswith("edgar_")
        assert "sector_pct" not in str(spec["right"])
        assert "industry_pct" not in str(spec["right"])
