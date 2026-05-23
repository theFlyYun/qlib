from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from analysis.nasdaq_top500_score.crsp_edgar_mini_core_position_diff import (
    run_crsp_edgar_mini_core_position_diff,
)


def write_positions(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def test_crsp_edgar_mini_core_position_diff_classifies_and_summarizes(tmp_path: Path) -> None:
    alpha_run = tmp_path / "alpha"
    edgar_run = tmp_path / "edgar"
    variant = "sector_cap_2_top10"
    base = {
        "period": 1,
        "signal_date": "2024-01-02",
        "entry_date": "2024-01-03",
        "exit_date": "2024-01-18",
        "sector": "73",
        "industry": "7372",
        "history_bucket": "full_10y",
        "weight": 0.5,
        "cost_return": 0.0,
        "benchmark_return": 0.01,
        "excess_contribution": 0.0,
    }
    write_positions(
        alpha_run / "strategy_comparison" / variant / "backtest_positions.csv",
        [
            {**base, "symbol": "P1", "selected_rank": 1, "score": 0.9, "gross_return": 0.10, "net_return": 0.10, "gross_contribution": 0.05, "net_contribution": 0.05},
            {**base, "symbol": "P2", "selected_rank": 2, "score": 0.8, "gross_return": -0.20, "net_return": -0.20, "gross_contribution": -0.10, "net_contribution": -0.10},
        ],
    )
    write_positions(
        edgar_run / "strategy_comparison" / variant / "backtest_positions.csv",
        [
            {**base, "symbol": "P1", "selected_rank": 1, "score": 0.7, "gross_return": 0.10, "net_return": 0.10, "gross_contribution": 0.05, "net_contribution": 0.05},
            {**base, "symbol": "P3", "selected_rank": 2, "score": 0.6, "gross_return": 0.30, "net_return": 0.30, "gross_contribution": 0.15, "net_contribution": 0.15},
        ],
    )
    fundamentals = pd.DataFrame(
        [
            {
                "datetime": pd.Timestamp("2024-01-02"),
                "instrument": "P3",
                "edgar_operating_margin": 0.2,
                "edgar_free_cash_flow_ttm": 100.0,
                "edgar_net_margin": 0.1,
                "edgar_fcf_margin": 0.15,
                "edgar_operating_cash_flow_ttm": 120.0,
            }
        ]
    ).set_index(["datetime", "instrument"])
    fundamentals.to_parquet(edgar_run / "fundamental_features_cleaned.parquet")

    summary = run_crsp_edgar_mini_core_position_diff(alpha_run, edgar_run, tmp_path / "review", variant=variant)

    diff = pd.read_csv(tmp_path / "review" / "edgar_mini_core_position_diff.csv")
    assert set(diff["change_type"]) == {"common", "added_by_edgar", "removed_by_edgar"}
    added = diff[diff["change_type"].eq("added_by_edgar")].iloc[0]
    assert added["symbol"] == "P3"
    assert added["edgar_operating_margin"] == 0.2
    assert summary["added_edgar_net_contribution_sum"] == 0.15
    assert summary["removed_alpha_net_contribution_sum"] == -0.10
    assert (tmp_path / "review" / "edgar_mini_core_added_removed_summary.csv").exists()
    assert (tmp_path / "review" / "edgar_mini_core_contribution_diff.csv").exists()
    assert (tmp_path / "review" / "report.md").exists()


def test_crsp_edgar_mini_core_position_diff_handles_missing_fundamentals(tmp_path: Path) -> None:
    alpha_run = tmp_path / "alpha"
    edgar_run = tmp_path / "edgar"
    variant = "sector_cap_2_top10"
    row = {
        "period": 1,
        "signal_date": "2024-01-02",
        "entry_date": "2024-01-03",
        "exit_date": "2024-01-18",
        "symbol": "P1",
        "selected_rank": 1,
        "sector": "73",
        "industry": "7372",
        "history_bucket": "full_10y",
        "score": 0.9,
        "weight": 1.0,
        "gross_return": 0.1,
        "net_return": 0.1,
        "gross_contribution": 0.1,
        "net_contribution": 0.1,
        "excess_contribution": 0.0,
    }
    write_positions(alpha_run / "strategy_comparison" / variant / "backtest_positions.csv", [row])
    write_positions(edgar_run / "strategy_comparison" / variant / "backtest_positions.csv", [row])

    run_crsp_edgar_mini_core_position_diff(alpha_run, edgar_run, tmp_path / "review", variant=variant)

    saved_summary = yaml.safe_load((tmp_path / "review" / "edgar_mini_core_position_diff_summary.yaml").read_text())
    assert saved_summary["changed_position_rows"] == 0
    diff = pd.read_csv(tmp_path / "review" / "edgar_mini_core_position_diff.csv")
    assert "edgar_operating_margin" in diff.columns
