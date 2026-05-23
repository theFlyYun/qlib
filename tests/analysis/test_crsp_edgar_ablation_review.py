from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from analysis.nasdaq_top500_score.crsp_edgar_ablation_review import run_crsp_edgar_ablation_review


def write_run(run_dir: Path, *, ic: float, rank_ic: float, annualized: float, alpha: float, beta: float, fund_cols: int, industry_cols: int) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "report.md").write_text(
        f"- Test 日均 IC：{ic:.6f}\n- Test 日均 Rank IC：{rank_ic:.6f}\n",
        encoding="utf-8",
    )
    (run_dir / "backtest_summary.yaml").write_text(
        yaml.safe_dump({"cumulative_return": 0.4, "annualized_return": annualized, "max_drawdown": -0.2, "avg_turnover": 1.0}),
        encoding="utf-8",
    )
    (run_dir / "benchmark_summary.yaml").write_text(
        yaml.safe_dump({"excess_cumulative_return": 0.1, "alpha_annualized": alpha, "beta": beta}),
        encoding="utf-8",
    )
    (run_dir / "training_summary.yaml").write_text(
        yaml.safe_dump({"best_iteration": 8, "best_valid_l2": 0.99}),
        encoding="utf-8",
    )
    pd.DataFrame([{"entry_lag_days": 1, "entry_price": "open", "cost_bps": 50, "annualized_return": annualized - 0.1}]).to_csv(
        run_dir / "backtest_stress_matrix.csv",
        index=False,
    )
    if fund_cols:
        pd.DataFrame([[1.0] * fund_cols], columns=[f"edgar_{i}" for i in range(fund_cols)]).to_parquet(
            run_dir / "fundamental_features_cleaned.parquet"
        )
        pd.DataFrame([{"symbol": "P1", "error": "missing_fields"}]).to_csv(run_dir / "fundamental_failures.csv", index=False)
        pd.DataFrame([{"symbol": "P1", "cik": 1}]).to_csv(run_dir / "edgar_cik_map.csv", index=False)
    if industry_cols:
        pd.DataFrame([[1.0] * industry_cols], columns=[f"industry_{i}" for i in range(industry_cols)]).to_parquet(
            run_dir / "industry_features.parquet"
        )


def test_crsp_edgar_ablation_review_summarizes_manifest(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    edgar = tmp_path / "edgar"
    relative = tmp_path / "relative"
    write_run(baseline, ic=0.01, rank_ic=0.02, annualized=0.1, alpha=0.03, beta=1.1, fund_cols=0, industry_cols=0)
    write_run(edgar, ic=0.02, rank_ic=0.01, annualized=0.2, alpha=0.04, beta=1.2, fund_cols=20, industry_cols=0)
    write_run(relative, ic=0.03, rank_ic=0.04, annualized=0.3, alpha=0.05, beta=1.3, fund_cols=20, industry_cols=12)
    manifest = {
        "output_dir": str(tmp_path / "review"),
        "experiments": [
            {"name": "alpha158_only_baseline", "feature_set": "alpha158_only", "config": "base.yaml", "run_dir": str(baseline)},
            {"name": "edgar_clean_all", "feature_set": "edgar_clean_all", "config": "edgar.yaml", "run_dir": str(edgar)},
            {"name": "edgar_clean_all_plus_relative", "feature_set": "edgar_clean_all_plus_relative", "config": "relative.yaml", "run_dir": str(relative)},
            {"name": "drop_valuation", "feature_set": "drop_valuation", "config": "drop.yaml", "run_dir": str(tmp_path / "missing")},
        ],
    }
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    summary = run_crsp_edgar_ablation_review(manifest_path)

    assert len(summary) == 4
    assert summary.loc[summary["name"].eq("edgar_clean_all"), "fundamental_feature_count"].iloc[0] == 20
    assert summary.loc[summary["name"].eq("edgar_clean_all_plus_relative"), "industry_feature_count"].iloc[0] == 12
    assert summary.loc[summary["name"].eq("drop_valuation"), "status"].iloc[0].startswith("missing_outputs")
    assert (tmp_path / "review" / "crsp_edgar_ablation_summary.csv").exists()
    assert (tmp_path / "review" / "report.md").exists()
