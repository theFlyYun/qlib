from __future__ import annotations

from pathlib import Path

import pandas as pd

from analysis.nasdaq_top500_score.macro_regime_review import run_macro_regime_review


def make_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "output_dir": tmp_path / "current",
        "macro_features": tmp_path / "current" / "macro_features.parquet",
        "macro_regime_daily_metrics": tmp_path / "current" / "macro_regime_daily_metrics.csv",
        "macro_regime_summary": tmp_path / "current" / "macro_regime_summary.csv",
        "macro_regime_strategy_comparison": tmp_path / "current" / "macro_regime_strategy_comparison.csv",
        "macro_regime_sector_exposure": tmp_path / "current" / "macro_regime_sector_exposure.csv",
        "macro_regime_contribution_summary": tmp_path / "current" / "macro_regime_contribution_summary.csv",
        "macro_regime_review_summary": tmp_path / "current" / "macro_regime_review_summary.yaml",
    }


def write_macro_features(path: Path) -> None:
    dates = pd.to_datetime(
        [
            "2023-12-01",
            "2023-12-08",
            "2023-12-15",
            "2023-12-22",
            "2024-01-02",
            "2024-01-09",
        ]
    )
    index = pd.MultiIndex.from_product([dates, ["AAA", "BBB"]], names=["datetime", "instrument"])
    daily_values = pd.DataFrame(
        {
            "macro_vix": [10, 20, 30, 40, 50, 12],
            "macro_vix_change_20d": [-1, -1, 1, 1, 2, -2],
            "macro_dgs10": [3.0, 3.2, 3.4, 3.6, 4.2, 2.8],
            "macro_dgs10_change_20d": [-0.1, 0.1, 0.1, 0.1, 0.2, -0.2],
            "macro_yield_curve_10y_2y_inverted": [0, 0, 1, 1, 1, 0],
            "macro_baa10y_credit_spread": [1.0, 1.2, 1.4, 1.6, 2.0, 0.9],
            "macro_broad_dollar_index_pct_change_20d": [-0.01, 0.01, 0.02, 0.03, 0.04, -0.02],
            "macro_wti_oil_pct_change_20d": [-0.02, -0.01, 0.01, 0.02, 0.03, -0.04],
        },
        index=dates,
    )
    features = daily_values.reindex(index.get_level_values("datetime")).set_index(index)
    path.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(path)


def write_variant_outputs(run_dir: Path, variant: str, net_returns: list[float]) -> None:
    variant_dir = run_dir / "strategy_comparison" / variant
    variant_dir.mkdir(parents=True, exist_ok=True)
    nav = pd.DataFrame(
        {
            "period": [0, 1],
            "signal_date": ["2024-01-02", "2024-01-09"],
            "entry_date": ["2024-01-03", "2024-01-10"],
            "exit_date": ["2024-01-09", "2024-01-16"],
            "net_return": net_returns,
            "benchmark_return": [0.01, -0.01],
            "excess_return": [net_returns[0] - 0.01, net_returns[1] + 0.01],
        }
    )
    nav.to_csv(variant_dir / "backtest_nav.csv", index=False)
    positions = pd.DataFrame(
        {
            "period": [0, 0, 1, 1],
            "signal_date": ["2024-01-02", "2024-01-02", "2024-01-09", "2024-01-09"],
            "symbol": ["AAA", "BBB", "AAA", "BBB"],
            "sector": ["Technology", "Finance", "Technology", "Finance"],
            "weight": [0.5, 0.5, 0.5, 0.5],
            "gross_contribution": [0.01, 0.02, -0.01, 0.01],
            "net_contribution": [0.009, 0.019, -0.011, 0.009],
            "excess_contribution": [0.004, 0.014, -0.006, 0.014],
        }
    )
    positions.to_csv(variant_dir / "backtest_positions.csv", index=False)


def write_main_backtest_outputs(run_dir: Path, net_returns: list[float]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    nav = pd.DataFrame(
        {
            "period": [0, 1],
            "signal_date": ["2024-01-02", "2024-01-09"],
            "entry_date": ["2024-01-03", "2024-01-10"],
            "exit_date": ["2024-01-09", "2024-01-16"],
            "net_return": net_returns,
            "benchmark_return": [0.01, -0.01],
            "excess_return": [net_returns[0] - 0.01, net_returns[1] + 0.01],
        }
    )
    nav.to_csv(run_dir / "backtest_nav.csv", index=False)
    positions = pd.DataFrame(
        {
            "period": [0, 0, 1, 1],
            "signal_date": ["2024-01-02", "2024-01-02", "2024-01-09", "2024-01-09"],
            "symbol": ["AAA", "BBB", "AAA", "BBB"],
            "sector": ["Technology", "Finance", "Technology", "Finance"],
            "weight": [0.5, 0.5, 0.5, 0.5],
            "gross_contribution": [0.01, 0.02, -0.01, 0.01],
            "net_contribution": [0.009, 0.019, -0.011, 0.009],
            "excess_contribution": [0.004, 0.014, -0.006, 0.014],
        }
    )
    positions.to_csv(run_dir / "backtest_positions.csv", index=False)


def test_macro_regime_review_uses_pretest_thresholds_and_compares_experiments(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    write_macro_features(paths["macro_features"])
    baseline = tmp_path / "baseline"
    direct_macro = tmp_path / "direct_macro"
    macro_interactions = paths["output_dir"]
    for run_dir, returns in [
        (baseline, [-0.02, 0.03]),
        (direct_macro, [0.02, 0.00]),
        (macro_interactions, [0.03, 0.01]),
    ]:
        write_variant_outputs(run_dir, "sector_cap_2_top10", returns)

    config = {
        "backtest": {"enabled": True, "rebalance_days": 5},
        "macro_regime_review": {
            "enabled": True,
            "variant": "sector_cap_2_top10",
            "baseline_experiment": "baseline",
            "experiments": [
                {"name": "baseline", "run_dir": str(baseline)},
                {"name": "direct_macro", "run_dir": str(direct_macro)},
                {"name": "macro_interactions", "run_dir": str(macro_interactions)},
            ],
        },
    }

    result = run_macro_regime_review(config, paths)

    high_vix = result.daily_metrics[result.daily_metrics["signal_date"] == pd.Timestamp("2024-01-02")]
    assert set(high_vix["vix_level"]) == {"high_vix"}
    assert set(result.strategy_comparison["comparison_experiment"]) == {"direct_macro", "macro_interactions"}
    direct_high = result.strategy_comparison[
        (result.strategy_comparison["comparison_experiment"] == "direct_macro")
        & (result.strategy_comparison["regime_key"] == "vix_level")
        & (result.strategy_comparison["regime_value"] == "high_vix")
    ].iloc[0]
    assert direct_high["cumulative_return_diff"] > 0
    assert paths["macro_regime_strategy_comparison"].exists()


def test_macro_regime_review_supports_main_backtest_outputs(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    write_macro_features(paths["macro_features"])
    baseline = tmp_path / "baseline"
    macro_interactions = paths["output_dir"]
    write_main_backtest_outputs(baseline, [-0.02, 0.03])
    write_main_backtest_outputs(macro_interactions, [0.03, 0.01])

    config = {
        "backtest": {"enabled": True, "rebalance_days": 10},
        "macro_regime_review": {
            "enabled": True,
            "variant": "main_backtest",
            "baseline_experiment": "baseline",
            "experiments": [
                {"name": "baseline", "run_dir": str(baseline)},
                {"name": "macro_interactions", "run_dir": str(macro_interactions)},
            ],
        },
    }

    result = run_macro_regime_review(config, paths)

    assert set(result.strategy_comparison["comparison_experiment"]) == {"macro_interactions"}
    assert not result.sector_exposure.empty
    assert paths["macro_regime_strategy_comparison"].exists()
