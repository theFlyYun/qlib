from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from analysis.nasdaq_top500_score.macro_ablation_review import run_macro_ablation_review
from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import load_config


def write_run(run_dir: Path, *, ic: float, rank_ic: float, annualized: float, alpha: float, beta: float) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "report.md").write_text(
        "\n".join(
            [
                f"- Test 日均 IC：{ic:.6f}",
                f"- Test 日均 Rank IC：{rank_ic:.6f}",
                "- 交互特征数量：2",
            ]
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "name": "sector_cap_2_top10",
                "cumulative_return": 0.5,
                "annualized_return": annualized,
                "max_drawdown": -0.2,
                "excess_cumulative_return": 0.1,
                "alpha_annualized": alpha,
                "beta": beta,
                "avg_sector_hhi": 0.2,
            }
        ]
    ).to_csv(run_dir / "strategy_comparison.csv", index=False)
    pd.DataFrame(
        [
            {
                "regime_key": "vix_level",
                "regime_value": "high_vix",
                "comparison_experiment": run_dir.name,
                "baseline_period_count": 10,
                "comparison_period_count": 10,
                "annualized_return_diff": annualized - 0.1,
                "alpha_annualized_diff": alpha - 0.01,
                "beta_diff": beta - 1.0,
                "max_drawdown_diff": 0.03,
            }
        ]
    ).to_csv(run_dir / "macro_regime_strategy_comparison.csv", index=False)


def write_main_backtest_run(run_dir: Path, *, ic: float, rank_ic: float, annualized: float, alpha: float, beta: float) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "report.md").write_text(
        "\n".join(
            [
                f"- Test 日均 IC：{ic:.6f}",
                f"- Test 日均 Rank IC：{rank_ic:.6f}",
                "- 交互特征数量：2",
            ]
        ),
        encoding="utf-8",
    )
    (run_dir / "backtest_summary.yaml").write_text(
        yaml.safe_dump(
            {
                "cumulative_return": annualized / 2,
                "annualized_return": annualized,
                "max_drawdown": -0.2,
                "avg_turnover": 1.4,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "benchmark_summary.yaml").write_text(
        yaml.safe_dump({"excess_cumulative_return": 0.1, "alpha_annualized": alpha, "beta": beta}),
        encoding="utf-8",
    )
    (run_dir / "training_summary.yaml").write_text(
        yaml.safe_dump({"best_iteration": 7, "best_valid_l2": 0.02}),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "entry_lag_days": 1,
                "entry_price": "open",
                "cost_bps": 50,
                "annualized_return": annualized - 0.03,
            }
        ]
    ).to_csv(run_dir / "backtest_stress_matrix.csv", index=False)
    pd.DataFrame(
        {
            "period": [0, 1],
            "signal_date": ["2024-01-02", "2024-01-12"],
            "entry_date": ["2024-01-03", "2024-01-16"],
            "exit_date": ["2024-01-12", "2024-01-26"],
            "net_return": [annualized / 20, annualized / 30],
            "benchmark_return": [0.01, -0.01],
            "excess_return": [annualized / 20 - 0.01, annualized / 30 + 0.01],
        }
    ).to_csv(run_dir / "backtest_nav.csv", index=False)
    pd.DataFrame(
        {
            "signal_date": ["2024-01-02", "2024-01-02"],
            "sector": ["Technology", "Finance"],
            "weight": [0.6, 0.4],
        }
    ).to_csv(run_dir / "backtest_positions.csv", index=False)


def write_main_backtest_macro_features(path: Path) -> None:
    dates = pd.to_datetime(["2023-12-01", "2023-12-15", "2024-01-02", "2024-01-12"])
    index = pd.MultiIndex.from_product([dates, ["AAA", "BBB"]], names=["datetime", "instrument"])
    daily_values = pd.DataFrame(
        {
            "macro_vix": [10, 40, 50, 12],
            "macro_vix_change_20d": [-1, 1, 2, -2],
            "macro_dgs10": [3.0, 3.6, 4.2, 2.8],
            "macro_dgs10_change_20d": [-0.1, 0.1, 0.2, -0.2],
            "macro_yield_curve_10y_2y_inverted": [0, 1, 1, 0],
            "macro_baa10y_credit_spread": [1.0, 1.6, 2.0, 0.9],
            "macro_broad_dollar_index_pct_change_20d": [-0.01, 0.03, 0.04, -0.02],
            "macro_wti_oil_pct_change_20d": [-0.02, 0.02, 0.03, -0.04],
        },
        index=dates,
    )
    features = daily_values.reindex(index.get_level_values("datetime")).set_index(index)
    path.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(path)


def test_macro_ablation_review_aggregates_runs(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    full = tmp_path / "full_interactions"
    drop = tmp_path / "drop_vix_interactions"
    write_run(baseline, ic=0.01, rank_ic=0.02, annualized=0.1, alpha=0.01, beta=1.0)
    write_run(full, ic=0.03, rank_ic=0.04, annualized=0.4, alpha=0.2, beta=0.9)
    write_run(drop, ic=0.02, rank_ic=0.03, annualized=0.2, alpha=0.08, beta=0.95)
    manifest = {
        "output_dir": str(tmp_path / "review"),
        "variant": "sector_cap_2_top10",
        "full_experiment": "full_interactions",
        "experiments": [
            {"name": "baseline", "run_dir": str(baseline), "regime_comparison_name": "baseline"},
            {"name": "full_interactions", "run_dir": str(full), "regime_comparison_name": "full_interactions"},
            {"name": "drop_vix_interactions", "run_dir": str(drop), "regime_comparison_name": "drop_vix_interactions"},
        ],
    }
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")

    result = run_macro_ablation_review(manifest_path)

    row = result.summary[result.summary["name"].eq("drop_vix_interactions")].iloc[0]
    assert row["annualized_return_delta_vs_full"] == -0.2
    assert row["rank_ic_delta_vs_full"] == pytest.approx(-0.01)
    assert (tmp_path / "review" / "macro_ablation_summary.csv").exists()
    assert not result.regime_summary.empty


def test_macro_ablation_review_supports_main_backtest_outputs(tmp_path: Path) -> None:
    baseline = tmp_path / "alpha158_only_baseline"
    full = tmp_path / "full_macro_interactions"
    drop = tmp_path / "drop_vix_interactions"
    macro_features = tmp_path / "macro_features.parquet"
    write_main_backtest_run(baseline, ic=0.01, rank_ic=0.02, annualized=0.1, alpha=0.01, beta=1.0)
    write_main_backtest_run(full, ic=0.03, rank_ic=0.04, annualized=0.4, alpha=0.2, beta=0.9)
    write_main_backtest_run(drop, ic=0.02, rank_ic=0.03, annualized=0.2, alpha=0.08, beta=0.95)
    write_main_backtest_macro_features(macro_features)
    manifest = {
        "output_dir": str(tmp_path / "review"),
        "output_prefix": "crsp_macro_ablation",
        "variant": "main_backtest",
        "baseline_experiment": "alpha158_only_baseline",
        "full_experiment": "full_macro_interactions",
        "macro_features_path": str(macro_features),
        "regime_min_periods": 1,
        "backtest": {"rebalance_days": 10, "periods_per_year": 25.2},
        "experiments": [
            {"name": "alpha158_only_baseline", "run_dir": str(baseline)},
            {"name": "full_macro_interactions", "run_dir": str(full)},
            {"name": "drop_vix_interactions", "run_dir": str(drop)},
        ],
    }
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")

    result = run_macro_ablation_review(manifest_path)

    row = result.summary[result.summary["name"].eq("drop_vix_interactions")].iloc[0]
    assert row["annualized_return_delta_vs_full"] == pytest.approx(-0.2)
    assert row["stress_annualized_return_50bps"] == pytest.approx(0.17)
    assert row["best_iteration"] == 7
    assert (tmp_path / "review" / "crsp_macro_ablation_summary.csv").exists()
    assert (tmp_path / "review" / "crsp_macro_ablation_regime_summary.csv").exists()
    assert (tmp_path / "review" / "report.md").exists()
    assert set(result.regime_summary["name"]) == {"full_macro_interactions", "drop_vix_interactions"}


def test_macro_ablation_config_extends_parseable() -> None:
    config = load_config(Path("analysis/nasdaq_top500_score/configs/macro_ablation/only_vix_interactions.yaml"))

    assert config["macro_features"]["append_to_model"] is False
    assert config["data"]["reuse_prepared_run"]
    assert len(config["macro_interactions"]["interactions"]) == 2


def test_crsp_macro_ablation_configs_are_parseable_and_market_only() -> None:
    config_dir = Path("analysis/nasdaq_top500_score/configs/crsp_macro_ablation")
    expected_counts = {
        "drop_vix_interactions.yaml": 6,
        "drop_rate_curve_interactions.yaml": 5,
        "drop_credit_interaction.yaml": 7,
        "drop_dollar_oil_interactions.yaml": 6,
        "only_vix_interactions.yaml": 2,
        "only_rate_curve_interactions.yaml": 3,
    }

    for filename, expected_count in expected_counts.items():
        config = load_config(config_dir / filename)
        interactions = config["macro_interactions"]["interactions"]
        right_features = {item["right"] for item in interactions if "right" in item}
        assert len(interactions) == expected_count
        assert config["fundamentals"]["enabled"] is False
        assert config["market_features"]["group_levels"] == []
        assert config["macro_features"]["append_to_model"] is False
        assert not any(value.startswith("edgar_") for value in right_features)
        assert not any("sector" in item for item in interactions)


def test_crsp_macro_ablation_manifest_has_exact_nine_experiments() -> None:
    manifest_path = Path("analysis/nasdaq_top500_score/configs/crsp_macro_ablation/manifest.yaml")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

    assert manifest["variant"] == "main_backtest"
    assert manifest["baseline_experiment"] == "alpha158_only_baseline"
    assert manifest["full_experiment"] == "full_macro_interactions"
    assert len(manifest["experiments"]) == 9
    assert [item["name"] for item in manifest["experiments"]] == [
        "alpha158_only_baseline",
        "raw_macro_direct",
        "full_macro_interactions",
        "drop_vix_interactions",
        "drop_rate_curve_interactions",
        "drop_credit_interaction",
        "drop_dollar_oil_interactions",
        "only_vix_interactions",
        "only_rate_curve_interactions",
    ]


def test_default_macro_interactions_remove_credit_quality_but_research_config_keeps_it() -> None:
    default_config = load_config(
        Path(
            "analysis/nasdaq_top500_score/configs/"
            "nasdaq_alpha158_edgar_macro_interactions_default_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml"
        )
    )
    research_config = load_config(
        Path(
            "analysis/nasdaq_top500_score/configs/"
            "nasdaq_alpha158_edgar_macro_interactions_lgbm_10y_frozen_2023_top500_5d_pit_safe.yaml"
        )
    )

    default_names = {item["name"] for item in default_config["macro_interactions"]["interactions"]}
    research_names = {item["name"] for item in research_config["macro_interactions"]["interactions"]}

    credit_names = {
        "macro_x_credit_change_liabilities_to_assets",
        "macro_x_credit_spread_cash_to_assets",
    }
    assert credit_names.isdisjoint(default_names)
    assert credit_names.issubset(research_names)
    assert len(default_names) == 8
