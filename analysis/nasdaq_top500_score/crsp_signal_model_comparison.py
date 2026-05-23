"""Compare CRSP Alpha158 signal model runs across model and label choices."""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

try:  # pragma: no cover - supports direct script execution.
    from run_qlib_alpha158_lightgbm import build_paths, load_config
except ImportError:  # pragma: no cover - supports importing this module in tests.
    from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import build_paths, load_config


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_CONFIGS = [
    Path("analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_10d_2000_2025.yaml"),
    Path("analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_5d_conservative_2000_2025.yaml"),
    Path("analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_10d_conservative_2000_2025.yaml"),
    Path("analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_20d_conservative_2000_2025.yaml"),
]
DEFAULT_OUTPUT_DIR = Path("analysis/nasdaq_top500_score/runs/crsp_signal_model_comparison")
SUMMARY_COLUMNS = [
    "name",
    "status",
    "run_dir",
    "horizon_days",
    "model_profile",
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


def run_crsp_signal_model_comparison(
    configs: list[Path] | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> pd.DataFrame:
    configs = configs or DEFAULT_CONFIGS
    output = resolve_path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rows = [summarize_config(path) for path in configs]
    summary = pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
    summary.to_csv(output / "crsp_signal_model_comparison.csv", index=False)
    yaml_summary = build_yaml_summary(summary)
    (output / "crsp_signal_model_comparison_summary.yaml").write_text(
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
        "horizon_days": int(config["crsp"]["label_horizon_days"]),
        "model_profile": model_profile(config),
    }
    required = [paths["report_md"], paths["backtest_summary"], paths["benchmark_summary"]]
    missing = [path.name for path in required if not path.exists()]
    if missing:
        row["status"] = "missing_outputs:" + ",".join(missing)
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
    row.update(read_early_stopping(paths["output_dir"] / "early_stopping_variants.csv"))
    row.update(read_stress(paths["output_dir"] / "backtest_stress_matrix.csv", row.get("annualized_return")))
    return row


def model_profile(config: dict[str, Any]) -> str:
    kwargs = config.get("model", {}).get("kwargs", {})
    if int(kwargs.get("num_leaves", 0)) <= 16 and int(kwargs.get("max_depth", 99)) <= 4:
        return "conservative"
    return "current"


def parse_report_metrics(report_text: str) -> dict[str, float]:
    return {
        "ic_mean": extract_float(report_text, r"Test 日均 IC：([+-]?\d+(?:\.\d+)?)"),
        "rank_ic_mean": extract_float(report_text, r"Test 日均 Rank IC：([+-]?\d+(?:\.\d+)?)"),
    }


def read_early_stopping(path: Path) -> dict[str, float]:
    if not path.exists():
        return {"best_iteration": math.nan, "best_valid_l2": math.nan}
    frame = pd.read_csv(path)
    current = frame[frame["variant"].eq("current")] if "variant" in frame else frame
    if current.empty:
        current = frame
    row = current.iloc[0]
    return {
        "best_iteration": numeric(row.get("best_iteration")),
        "best_valid_l2": numeric(row.get("best_valid_l2")),
    }


def read_stress(path: Path, annualized_return: Any) -> dict[str, float]:
    if not path.exists():
        return {"stress_annualized_return_50bps": math.nan, "stress_annualized_drop_50bps": math.nan}
    frame = pd.read_csv(path)
    selected = frame[
        frame["entry_lag_days"].eq(1)
        & frame["entry_price"].eq("open")
        & pd.to_numeric(frame["cost_bps"], errors="coerce").eq(50)
    ]
    if selected.empty:
        return {"stress_annualized_return_50bps": math.nan, "stress_annualized_drop_50bps": math.nan}
    stressed = numeric(selected.iloc[0].get("annualized_return"))
    base = numeric(annualized_return)
    return {
        "stress_annualized_return_50bps": stressed,
        "stress_annualized_drop_50bps": stressed - base if not math.isnan(base) else math.nan,
    }


def build_yaml_summary(summary: pd.DataFrame) -> dict[str, Any]:
    ok = summary[summary["status"].eq("ok")].copy()
    return {
        "experiment_count": int(len(summary)),
        "completed_count": int(len(ok)),
        "best_rank_ic": leader(ok, "rank_ic_mean", higher=True),
        "best_annualized_return": leader(ok, "annualized_return", higher=True),
        "best_alpha": leader(ok, "alpha_annualized", higher=True),
        "latest_run_status": summary[["name", "status"]].to_dict("records"),
    }


def leader(frame: pd.DataFrame, column: str, *, higher: bool) -> dict[str, Any]:
    if frame.empty or column not in frame:
        return {}
    usable = frame[pd.to_numeric(frame[column], errors="coerce").notna()]
    if usable.empty:
        return {}
    row = usable.sort_values(column, ascending=not higher).iloc[0]
    fields = ["name", "horizon_days", "model_profile", column, "ic_mean", "rank_ic_mean", "annualized_return", "alpha_annualized", "beta"]
    return {field: native(row.get(field)) for field in fields if field in row}


def extract_float(text: str, pattern: str) -> float:
    match = re.search(pattern, text)
    return float(match.group(1)) if match else math.nan


def numeric(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def native(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):  # type: ignore[name-defined]
        return value.item()
    return value


def main() -> None:
    args = parse_args()
    summary = run_crsp_signal_model_comparison(args.configs, args.output_dir)
    print(f"Comparison rows: {len(summary)}")
    print(f"Output: {resolve_path(args.output_dir)}")


if __name__ == "__main__":
    main()
