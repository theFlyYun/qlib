from __future__ import annotations

from pathlib import Path

import pandas as pd

from analysis.nasdaq_top500_score.crsp_2022_2023_failure_deep_dive import (
    build_ic_topk_divergence,
    identify_drawdown,
    run_crsp_2022_2023_failure_deep_dive,
)


def write_fake_run(run_dir: Path, *, symbols: list[str], scores: list[float], returns: list[float]) -> None:
    source_dir = run_dir / "qlib_source_csv"
    variant_dir = run_dir / "strategy_comparison" / "sector_cap_2_top10"
    source_dir.mkdir(parents=True, exist_ok=True)
    variant_dir.mkdir(parents=True, exist_ok=True)

    for symbol, label in zip(["P1", "P2", "P3", "P4"], [0.04, 0.03, -0.01, -0.02], strict=True):
        pd.DataFrame(
            [
                {"date": "2022-01-03", "symbol": symbol, "open": 1, "high": 1, "low": 1, "close": 1, "vwap": 1, "volume": 100, "label_10d_total_return": label},
                {"date": "2022-01-18", "symbol": symbol, "open": 1, "high": 1, "low": 1, "close": 1, "vwap": 1, "volume": 100, "label_10d_total_return": -label},
            ]
        ).to_csv(source_dir / f"{symbol}.csv", index=False)

    prediction_rows = []
    for date in ["2022-01-03", "2022-01-18"]:
        for symbol, score in zip(["P1", "P2", "P3", "P4"], [4.0, 3.0, 2.0, 1.0], strict=True):
            prediction_rows.append({"datetime": date, "instrument": symbol, "score": score})
    pd.DataFrame(prediction_rows).to_csv(run_dir / "test_predictions.csv", index=False)

    nav = pd.DataFrame(
        [
            {"period": 1, "signal_date": "2022-01-03", "entry_date": "2022-01-04", "exit_date": "2022-01-18", "gross_return": -0.10, "net_return": -0.10, "benchmark_return": -0.02, "excess_return": -0.08, "nav": 0.90},
            {"period": 2, "signal_date": "2022-01-18", "entry_date": "2022-01-19", "exit_date": "2022-02-02", "gross_return": -0.20, "net_return": -0.20, "benchmark_return": -0.03, "excess_return": -0.17, "nav": 0.72},
        ]
    )
    nav.to_csv(variant_dir / "backtest_nav.csv", index=False)

    rows = []
    for period, date in [(1, "2022-01-03"), (2, "2022-01-18")]:
        for rank, (symbol, score, ret) in enumerate(zip(symbols, scores, returns, strict=True), start=1):
            rows.append(
                {
                    "period": period,
                    "signal_date": date,
                    "entry_date": "2022-01-04",
                    "exit_date": "2022-01-18",
                    "symbol": symbol,
                    "selected_rank": rank,
                    "sector": "73" if symbol in {"P1", "P3"} else "28",
                    "industry": "7372" if symbol in {"P1", "P3"} else "2836",
                    "history_bucket": "full_10y",
                    "score": score,
                    "weight": 0.5,
                    "gross_return": ret,
                    "net_return": ret,
                    "gross_contribution": ret * 0.5,
                    "net_contribution": ret * 0.5,
                    "benchmark_contribution": -0.01,
                    "excess_contribution": ret * 0.5 + 0.01,
                }
            )
    pd.DataFrame(rows).to_csv(variant_dir / "backtest_positions.csv", index=False)


def test_ic_topk_divergence_flags_positive_ic_negative_topk() -> None:
    predictions = pd.DataFrame(
        [
            {"datetime": "2022-01-03", "instrument": "P1", "score": 4.0},
            {"datetime": "2022-01-03", "instrument": "P2", "score": 3.0},
            {"datetime": "2022-01-03", "instrument": "P3", "score": 2.0},
            {"datetime": "2022-01-03", "instrument": "P4", "score": 1.0},
        ]
    )
    predictions["datetime"] = pd.to_datetime(predictions["datetime"])
    labels = pd.DataFrame(
        [
            {"datetime": "2022-01-03", "instrument": "P1", "label": 0.04},
            {"datetime": "2022-01-03", "instrument": "P2", "label": 0.03},
            {"datetime": "2022-01-03", "instrument": "P3", "label": -0.01},
            {"datetime": "2022-01-03", "instrument": "P4", "label": -0.02},
        ]
    )
    labels["datetime"] = pd.to_datetime(labels["datetime"])
    nav = pd.DataFrame([{"period": 1, "signal_date": pd.Timestamp("2022-01-03"), "gross_return": -0.1, "net_return": -0.1, "benchmark_return": -0.02, "excess_return": -0.08}])
    positions = pd.DataFrame(
        [
            {"period": 1, "symbol": "P1", "gross_return": -0.1},
            {"period": 1, "symbol": "P2", "gross_return": -0.1},
        ]
    )

    result = build_ic_topk_divergence(predictions, labels, nav, positions, "alpha158_only")

    assert result.iloc[0]["ic"] > 0
    assert result.iloc[0]["rank_ic"] > 0
    assert result.iloc[0]["divergence_flag"] == "positive_ic_rank_ic_negative_topk"


def test_identify_drawdown_uses_peak_before_trough() -> None:
    nav = pd.DataFrame(
        [
            {"period": 1, "signal_date": pd.Timestamp("2022-01-03"), "nav": 1.1},
            {"period": 2, "signal_date": pd.Timestamp("2022-01-18"), "nav": 0.9},
            {"period": 3, "signal_date": pd.Timestamp("2022-02-01"), "nav": 0.7},
        ]
    )

    event = identify_drawdown(nav, "alpha158_only")

    assert event["peak_period"] == 1
    assert event["trough_period"] == 3
    assert event["max_drawdown"] < -0.36


def test_failure_deep_dive_outputs_expected_files(tmp_path: Path) -> None:
    alpha_run = tmp_path / "alpha"
    edgar_run = tmp_path / "edgar"
    write_fake_run(alpha_run, symbols=["P1", "P2"], scores=[1.0, 0.9], returns=[-0.10, -0.20])
    write_fake_run(edgar_run, symbols=["P1", "P3"], scores=[1.0, 0.8], returns=[-0.10, 0.05])
    pd.DataFrame(
        [
            {
                "datetime": pd.Timestamp("2022-01-03"),
                "instrument": "P3",
                "edgar_operating_margin": 0.2,
                "edgar_free_cash_flow_ttm": 10.0,
                "edgar_net_margin": 0.1,
                "edgar_fcf_margin": 0.15,
                "edgar_operating_cash_flow_ttm": 12.0,
            }
        ]
    ).set_index(["datetime", "instrument"]).to_parquet(edgar_run / "fundamental_features_cleaned.parquet")

    summary = run_crsp_2022_2023_failure_deep_dive(alpha_run, edgar_run, tmp_path / "review")

    assert summary["decision"]["topk_status"] == "failed_conversion"
    assert (tmp_path / "review" / "ic_topk_divergence_by_period.csv").exists()
    assert (tmp_path / "review" / "edgar_vs_alpha_2022_2023_delta.csv").exists()
    assert (tmp_path / "review" / "2022_2023_failure_deep_dive_report.md").exists()
    delta = pd.read_csv(tmp_path / "review" / "edgar_vs_alpha_2022_2023_delta.csv")
    assert {"added_by_edgar", "removed_by_edgar", "common"} <= set(delta["change_type"])
