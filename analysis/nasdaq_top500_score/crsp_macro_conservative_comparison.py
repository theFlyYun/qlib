"""Compare CRSP conservative baseline, raw macro, and macro interaction runs."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

try:  # pragma: no cover - supports direct script execution.
    from crsp_signal_model_comparison import (
        model_profile,
        native,
        numeric,
        parse_report_metrics,
        read_early_stopping,
        read_stress,
    )
    from run_qlib_alpha158_lightgbm import build_paths, load_config
except ImportError:  # pragma: no cover - supports importing this module in tests.
    from analysis.nasdaq_top500_score.crsp_signal_model_comparison import (
        model_profile,
        native,
        numeric,
        parse_report_metrics,
        read_early_stopping,
        read_stress,
    )
    from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import build_paths, load_config


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_CONFIGS = [
    Path("analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_10d_conservative_2000_2025.yaml"),
    Path("analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_macro_10d_conservative_2000_2025.yaml"),
    Path("analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_macro_interactions_10d_conservative_2000_2025.yaml"),
]
DEFAULT_OUTPUT_DIR = Path("analysis/nasdaq_top500_score/runs/crsp_macro_conservative_comparison")
SUMMARY_COLUMNS = [
    "name",
    "status",
    "run_dir",
    "feature_set",
    "horizon_days",
    "model_profile",
    "macro_append_to_model",
    "macro_feature_count",
    "macro_failure_count",
    "macro_interaction_feature_count",
    "macro_interaction_failure_count",
    "ic_mean",
    "rank_ic_mean",
    "best_iteration",
    "best_valid_l2",
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
    parser.add_argument("--configs", nargs="*", type=Path, default=DEFAULT_CONFIGS, help="CRSP config files to compare.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Comparison output directory.")
    return parser.parse_args()


def resolve_path(path: str | Path) -> Path:
    value = Path(path).expanduser()
    return value if value.is_absolute() else WORKSPACE / value


def run_crsp_macro_conservative_comparison(
    configs: list[Path] | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> pd.DataFrame:
    configs = configs or DEFAULT_CONFIGS
    output = resolve_path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rows = [summarize_config(path) for path in configs]
    summary = pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
    summary.to_csv(output / "crsp_macro_conservative_comparison.csv", index=False)
    yaml_summary = build_yaml_summary(summary)
    (output / "crsp_macro_conservative_comparison_summary.yaml").write_text(
        yaml.safe_dump(yaml_summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return summary


def summarize_config(config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    paths = build_paths(config)
    run_dir = paths["output_dir"]
    row: dict[str, Any] = {
        "name": config["experiment"]["name"],
        "status": "ok",
        "run_dir": str(run_dir),
        "feature_set": feature_set(config),
        "horizon_days": int(config["crsp"]["label_horizon_days"]),
        "model_profile": model_profile(config),
        "macro_append_to_model": bool(config.get("macro_features", {}).get("append_to_model", True)),
    }
    required = [paths["report_md"], paths["backtest_summary"], paths["benchmark_summary"]]
    missing = [path.name for path in required if not path.exists()]
    if missing:
        row["status"] = "missing_outputs:" + ",".join(missing)
        row.update(feature_artifact_counts(paths))
        return row

    row.update(parse_report_metrics(paths["report_md"].read_text(encoding="utf-8")))
    backtest = yaml.safe_load(paths["backtest_summary"].read_text(encoding="utf-8")) or {}
    benchmark = yaml.safe_load(paths["benchmark_summary"].read_text(encoding="utf-8")) or {}
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
    row.update(read_training_summary(paths["output_dir"] / "training_summary.yaml"))
    if pd.isna(row.get("best_iteration")):
        row.update(read_early_stopping(paths["output_dir"] / "early_stopping_variants.csv"))
    row.update(read_stress(paths["output_dir"] / "backtest_stress_matrix.csv", row.get("annualized_return")))
    row.update(feature_artifact_counts(paths))
    return row


def feature_set(config: dict[str, Any]) -> str:
    if config.get("macro_interactions", {}).get("enabled", False):
        return "macro_interactions"
    if config.get("macro_features", {}).get("enabled", False) and config.get("macro_features", {}).get("append_to_model", True):
        return "direct_macro"
    return "alpha158_only"


def read_training_summary(path: Path) -> dict[str, float]:
    if not path.exists():
        return {"best_iteration": math.nan, "best_valid_l2": math.nan}
    summary = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        "best_iteration": numeric(summary.get("best_iteration")),
        "best_valid_l2": numeric(summary.get("best_valid_l2")),
    }


def feature_artifact_counts(paths: dict[str, Path]) -> dict[str, float]:
    return {
        "macro_feature_count": parquet_column_count(paths["macro_features"]),
        "macro_failure_count": csv_row_count(paths["macro_failures"]),
        "macro_interaction_feature_count": parquet_column_count(paths["macro_interaction_features"]),
        "macro_interaction_failure_count": csv_row_count(paths["macro_interaction_failures"]),
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
        "macro_feature_sets": summary[["name", "feature_set", "status"]].to_dict("records"),
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


def main() -> None:
    args = parse_args()
    summary = run_crsp_macro_conservative_comparison(args.configs, args.output_dir)
    print(f"Comparison rows: {len(summary)}")
    print(f"Output: {resolve_path(args.output_dir)}")


if __name__ == "__main__":
    main()
