"""Summarize CRSP EDGAR feature group ablation runs."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

try:  # pragma: no cover - supports direct script execution.
    from crsp_signal_model_comparison import native, numeric, parse_report_metrics, read_stress
except ImportError:  # pragma: no cover
    from analysis.nasdaq_top500_score.crsp_signal_model_comparison import native, numeric, parse_report_metrics, read_stress


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = Path("analysis/nasdaq_top500_score/configs/crsp_edgar_ablation/manifest.yaml")
SUMMARY_COLUMNS = [
    "name",
    "status",
    "feature_set",
    "config",
    "run_dir",
    "ic_mean",
    "rank_ic_mean",
    "best_iteration",
    "best_valid_l2",
    "fundamental_feature_count",
    "industry_feature_count",
    "fundamental_failure_count",
    "cik_mapped_count",
    "cumulative_return",
    "annualized_return",
    "max_drawdown",
    "excess_cumulative_return",
    "alpha_annualized",
    "beta",
    "avg_turnover",
    "stress_annualized_return_50bps",
    "stress_annualized_drop_50bps",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args()


def resolve_path(path: str | Path) -> Path:
    value = Path(path).expanduser()
    return value if value.is_absolute() else WORKSPACE / value


def run_crsp_edgar_ablation_review(manifest_path: Path = DEFAULT_MANIFEST) -> pd.DataFrame:
    manifest = yaml.safe_load(resolve_path(manifest_path).read_text(encoding="utf-8")) or {}
    output_dir = resolve_path(manifest.get("output_dir", "analysis/nasdaq_top500_score/runs/crsp_edgar_ablation_review"))
    output_dir.mkdir(parents=True, exist_ok=True)
    experiments = manifest.get("experiments", [])
    rows = [summarize_experiment(experiment) for experiment in experiments]
    summary = pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
    summary.to_csv(output_dir / "crsp_edgar_ablation_summary.csv", index=False)
    yaml_summary = build_yaml_summary(summary)
    (output_dir / "crsp_edgar_ablation_review_summary.yaml").write_text(
        yaml.safe_dump(yaml_summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    write_markdown_report(output_dir / "report.md", summary, yaml_summary)
    return summary


def summarize_experiment(experiment: dict[str, Any]) -> dict[str, Any]:
    run_dir = resolve_path(experiment["run_dir"])
    row = {
        "name": experiment["name"],
        "status": "ok",
        "feature_set": experiment.get("feature_set", experiment["name"]),
        "config": experiment.get("config"),
        "run_dir": str(run_dir),
    }
    required = [run_dir / "report.md", run_dir / "backtest_summary.yaml", run_dir / "benchmark_summary.yaml"]
    missing = [path.name for path in required if not path.exists()]
    if missing:
        row["status"] = "missing_outputs:" + ",".join(missing)
        row.update(artifact_counts(run_dir))
        return row

    row.update(parse_report_metrics((run_dir / "report.md").read_text(encoding="utf-8")))
    backtest = yaml.safe_load((run_dir / "backtest_summary.yaml").read_text(encoding="utf-8")) or {}
    benchmark = yaml.safe_load((run_dir / "benchmark_summary.yaml").read_text(encoding="utf-8")) or {}
    row.update(
        {
            "cumulative_return": numeric(backtest.get("cumulative_return")),
            "annualized_return": numeric(backtest.get("annualized_return")),
            "max_drawdown": numeric(backtest.get("max_drawdown")),
            "avg_turnover": numeric(backtest.get("avg_turnover")),
            "excess_cumulative_return": numeric(benchmark.get("excess_cumulative_return")),
            "alpha_annualized": numeric(benchmark.get("alpha_annualized")),
            "beta": numeric(benchmark.get("beta")),
        }
    )
    row.update(read_training_summary(run_dir / "training_summary.yaml"))
    row.update(read_stress(run_dir / "backtest_stress_matrix.csv", row.get("annualized_return")))
    row.update(artifact_counts(run_dir))
    return row


def read_training_summary(path: Path) -> dict[str, float]:
    if not path.exists():
        return {"best_iteration": math.nan, "best_valid_l2": math.nan}
    summary = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        "best_iteration": numeric(summary.get("best_iteration")),
        "best_valid_l2": numeric(summary.get("best_valid_l2")),
    }


def artifact_counts(run_dir: Path) -> dict[str, float]:
    return {
        "fundamental_feature_count": parquet_column_count(run_dir / "fundamental_features_cleaned.parquet")
        or parquet_column_count(run_dir / "fundamental_features.parquet"),
        "industry_feature_count": parquet_column_count(run_dir / "industry_features.parquet"),
        "fundamental_failure_count": csv_row_count(run_dir / "fundamental_failures.csv"),
        "cik_mapped_count": csv_row_count(run_dir / "edgar_cik_map.csv"),
    }


def parquet_column_count(path: Path) -> float:
    if not path.exists():
        return 0.0
    try:
        return float(pd.read_parquet(path).shape[1])
    except Exception:
        return math.nan


def csv_row_count(path: Path) -> float:
    if not path.exists():
        return 0.0
    try:
        return float(len(pd.read_csv(path)))
    except Exception:
        return math.nan


def build_yaml_summary(summary: pd.DataFrame) -> dict[str, Any]:
    ok = summary[summary["status"].eq("ok")].copy()
    return {
        "experiment_count": int(len(summary)),
        "completed_count": int(len(ok)),
        "best_rank_ic": leader(ok, "rank_ic_mean", higher=True),
        "best_annualized_return": leader(ok, "annualized_return", higher=True),
        "best_alpha": leader(ok, "alpha_annualized", higher=True),
        "feature_sets": summary[["name", "feature_set", "status"]].to_dict("records"),
        "interpretation_rule": "收益改善但 IC/Rank IC 未改善时，只能标记为组合收益改善，不能认定横截面预测力增强。",
    }


def leader(frame: pd.DataFrame, column: str, *, higher: bool) -> dict[str, Any]:
    if frame.empty or column not in frame:
        return {}
    usable = frame[pd.to_numeric(frame[column], errors="coerce").notna()]
    if usable.empty:
        return {}
    row = usable.sort_values(column, ascending=not higher).iloc[0]
    fields = ["name", "feature_set", column, "ic_mean", "rank_ic_mean", "annualized_return", "alpha_annualized", "beta"]
    return {field: native(row.get(field)) for field in fields if field in row}


def write_markdown_report(path: Path, summary: pd.DataFrame, yaml_summary: dict[str, Any]) -> None:
    lines = [
        "# CRSP EDGAR Ablation Review",
        "",
        "本报告汇总 Alpha158-only、EDGAR quality core、cleaned EDGAR、行业内 EDGAR 相对特征和 EDGAR feature group drop 实验。",
        "",
        "## Summary",
        "",
        *format_yaml_block(yaml_summary),
        "",
        "## Experiments",
        "",
    ]
    if summary.empty:
        lines.append("- No experiments.")
    else:
        lines.extend(
            [
                "| Name | Status | IC | Rank IC | Annualized | Alpha | Max DD | Beta | Fundamental Features | Industry Features |",
                "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in summary.to_dict("records"):
            lines.append(
                "| {name} | {status} | {ic} | {rank_ic} | {ann} | {alpha} | {dd} | {beta} | {fund} | {industry} |".format(
                    name=row.get("name"),
                    status=row.get("status"),
                    ic=fmt(row.get("ic_mean")),
                    rank_ic=fmt(row.get("rank_ic_mean")),
                    ann=pct(row.get("annualized_return")),
                    alpha=pct(row.get("alpha_annualized")),
                    dd=pct(row.get("max_drawdown")),
                    beta=fmt(row.get("beta")),
                    fund=fmt(row.get("fundamental_feature_count"), 0),
                    industry=fmt(row.get("industry_feature_count"), 0),
                )
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def format_yaml_block(value: Any) -> list[str]:
    return ["```yaml", yaml.safe_dump(value, allow_unicode=True, sort_keys=False).strip(), "```"]


def fmt(value: Any, digits: int = 4) -> str:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if math.isnan(numeric_value):
        return "N/A"
    return f"{numeric_value:.{digits}f}"


def pct(value: Any) -> str:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if math.isnan(numeric_value):
        return "N/A"
    return f"{numeric_value:.2%}"


def main() -> None:
    args = parse_args()
    summary = run_crsp_edgar_ablation_review(args.manifest)
    print(f"EDGAR ablation rows: {len(summary)}")


if __name__ == "__main__":
    main()
