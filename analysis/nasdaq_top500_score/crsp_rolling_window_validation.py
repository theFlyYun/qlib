"""Run and summarize CRSP rolling-window Alpha158 vs EDGAR mini-core experiments."""

from __future__ import annotations

import argparse
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

try:  # pragma: no cover - supports direct script execution.
    from crsp_signal_model_comparison import native, numeric, parse_report_metrics, read_stress
    from run_qlib_alpha158_lightgbm import build_paths, load_config
except ImportError:  # pragma: no cover
    from analysis.nasdaq_top500_score.crsp_signal_model_comparison import native, numeric, parse_report_metrics, read_stress
    from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import build_paths, load_config


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = Path("analysis/nasdaq_top500_score/configs/crsp_rolling_windows/manifest.yaml")
SUMMARY_COLUMNS = [
    "window_id",
    "window_label",
    "feature_set",
    "name",
    "status",
    "run_dir",
    "train_start",
    "train_end",
    "valid_start",
    "valid_end",
    "test_start",
    "test_end",
    "ic_mean",
    "rank_ic_mean",
    "best_iteration",
    "best_valid_l2",
    "global_annualized_return",
    "global_alpha_annualized",
    "global_beta",
    "global_max_drawdown",
    "global_stress_annualized_return_50bps",
    "sector_cap_2_annualized_return",
    "sector_cap_2_alpha_annualized",
    "sector_cap_2_beta",
    "sector_cap_2_max_drawdown",
    "sector_cap_2_stress_annualized_return_50bps",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--only-summary", action="store_true", help="Do not run missing experiments; only rebuild summaries.")
    parser.add_argument("--force", action="store_true", help="Run experiments even when outputs already exist.")
    parser.add_argument("--python", default=sys.executable, help="Python executable for experiment runs.")
    return parser.parse_args()


def resolve_path(path: str | Path) -> Path:
    value = Path(path).expanduser()
    return value if value.is_absolute() else WORKSPACE / value


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = yaml.safe_load(resolve_path(path).read_text(encoding="utf-8")) or {}
    if not manifest.get("windows") or not manifest.get("experiments"):
        raise ValueError("rolling manifest requires windows and experiments")
    return manifest


def manifest_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    entries = []
    for window in manifest["windows"]:
        for experiment in manifest["experiments"]:
            config_template = str(experiment["config"])
            config_path = Path(config_template.format(window_id=window["id"]))
            entries.append(
                {
                    "window_id": window["id"],
                    "window_label": window.get("label", window["id"]),
                    "feature_set": experiment["feature_set"],
                    "config": config_path,
                    "window": window,
                }
            )
    return entries


def run_crsp_rolling_window_validation(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    only_summary: bool = False,
    force: bool = False,
    python_executable: str = sys.executable,
) -> pd.DataFrame:
    manifest = load_manifest(manifest_path)
    entries = manifest_entries(manifest)
    output_dir = resolve_path(manifest.get("output_dir", "analysis/nasdaq_top500_score/runs/crsp_rolling_windows"))
    output_dir.mkdir(parents=True, exist_ok=True)

    if not only_summary:
        for entry in entries:
            config_path = resolve_path(entry["config"])
            if force or not experiment_complete(config_path):
                run_experiment(config_path, python_executable)

    rows = [summarize_entry(entry) for entry in entries]
    summary = pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
    summary.to_csv(output_dir / "crsp_rolling_window_summary.csv", index=False)
    yaml_summary = build_yaml_summary(summary)
    (output_dir / "crsp_rolling_window_comparison.yaml").write_text(
        yaml.safe_dump(yaml_summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    write_report(output_dir / "report.md", summary, yaml_summary)
    return summary


def experiment_complete(config_path: Path) -> bool:
    config = load_config(config_path)
    paths = build_paths(config)
    required = [paths["report_md"], paths["test_predictions_csv"], paths["strategy_comparison_csv"]]
    return all(path.exists() for path in required)


def run_experiment(config_path: Path, python_executable: str) -> None:
    command = [
        python_executable,
        "-u",
        str(WORKSPACE / "analysis/nasdaq_top500_score/run_qlib_alpha158_lightgbm.py"),
        "--config",
        str(config_path),
    ]
    subprocess.run(command, cwd=WORKSPACE, check=True)


def summarize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    config_path = resolve_path(entry["config"])
    config = load_config(config_path)
    paths = build_paths(config)
    split = config["split"]
    row: dict[str, Any] = {
        "window_id": entry["window_id"],
        "window_label": entry["window_label"],
        "feature_set": entry["feature_set"],
        "name": config["experiment"]["name"],
        "status": "ok",
        "run_dir": str(paths["output_dir"]),
        "train_start": split["train"]["start"],
        "train_end": split["train"]["end"],
        "valid_start": split["valid"]["start"],
        "valid_end": split["valid"]["end"],
        "test_start": split["test"]["start"],
        "test_end": split["test"]["end"],
    }
    required = [paths["report_md"], paths["backtest_summary"], paths["benchmark_summary"], paths["strategy_comparison_csv"]]
    missing = [path.name for path in required if not path.exists()]
    if missing:
        row["status"] = "missing_outputs:" + ",".join(missing)
        return row
    row.update(parse_report_metrics(paths["report_md"].read_text(encoding="utf-8")))
    row.update(read_training(paths["training_summary"]))
    row.update(read_global_metrics(paths))
    row.update(read_sector_cap2_metrics(paths))
    return row


def read_training(path: Path) -> dict[str, float]:
    if not path.exists():
        return {"best_iteration": math.nan, "best_valid_l2": math.nan}
    summary = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        "best_iteration": numeric(summary.get("best_iteration")),
        "best_valid_l2": numeric(summary.get("best_valid_l2")),
    }


def read_global_metrics(paths: dict[str, Path]) -> dict[str, float]:
    backtest = yaml.safe_load(paths["backtest_summary"].read_text(encoding="utf-8")) or {}
    benchmark = yaml.safe_load(paths["benchmark_summary"].read_text(encoding="utf-8")) or {}
    stress = read_stress(paths["backtest_stress_matrix"], backtest.get("annualized_return"))
    return {
        "global_annualized_return": numeric(backtest.get("annualized_return")),
        "global_alpha_annualized": numeric(benchmark.get("alpha_annualized")),
        "global_beta": numeric(benchmark.get("beta")),
        "global_max_drawdown": numeric(backtest.get("max_drawdown")),
        "global_stress_annualized_return_50bps": stress["stress_annualized_return_50bps"],
    }


def read_sector_cap2_metrics(paths: dict[str, Path]) -> dict[str, float]:
    empty = {
        "sector_cap_2_annualized_return": math.nan,
        "sector_cap_2_alpha_annualized": math.nan,
        "sector_cap_2_beta": math.nan,
        "sector_cap_2_max_drawdown": math.nan,
        "sector_cap_2_stress_annualized_return_50bps": math.nan,
    }
    if not paths["strategy_comparison_csv"].exists():
        return empty
    frame = pd.read_csv(paths["strategy_comparison_csv"])
    selected = frame[frame["name"].eq("sector_cap_2_top10")] if "name" in frame else pd.DataFrame()
    if selected.empty:
        return empty
    row = selected.iloc[0]
    stress_path = paths["strategy_comparison_dir"] / "sector_cap_2_top10" / "backtest_stress_matrix.csv"
    stress = read_stress(stress_path, row.get("annualized_return"))
    return {
        "sector_cap_2_annualized_return": numeric(row.get("annualized_return")),
        "sector_cap_2_alpha_annualized": numeric(row.get("alpha_annualized")),
        "sector_cap_2_beta": numeric(row.get("beta")),
        "sector_cap_2_max_drawdown": numeric(row.get("max_drawdown")),
        "sector_cap_2_stress_annualized_return_50bps": stress["stress_annualized_return_50bps"],
    }


def build_yaml_summary(summary: pd.DataFrame) -> dict[str, Any]:
    ok = summary[summary["status"].eq("ok")].copy()
    alpha = ok[ok["feature_set"].eq("alpha158_only")]
    edgar = ok[ok["feature_set"].eq("edgar_mini_core")]
    merged = alpha.merge(edgar, on="window_id", suffixes=("_alpha", "_edgar"))
    alpha_positive = int((pd.to_numeric(alpha["sector_cap_2_alpha_annualized"], errors="coerce") > 0).sum()) if not alpha.empty else 0
    edgar_beats = (
        pd.to_numeric(merged["sector_cap_2_alpha_annualized_edgar"], errors="coerce")
        >= pd.to_numeric(merged["sector_cap_2_alpha_annualized_alpha"], errors="coerce")
    )
    edgar_beat_count = int(edgar_beats.sum()) if not merged.empty else 0
    classification = classify_result(ok, alpha_positive, edgar_beat_count)
    return {
        "experiment_count": int(len(summary)),
        "completed_count": int(len(ok)),
        "alpha158_sector_cap_2_positive_alpha_windows": alpha_positive,
        "edgar_sector_cap_2_alpha_beats_alpha158_windows": edgar_beat_count,
        "classification": classification,
        "best_sector_cap_2_alpha": leader(ok, "sector_cap_2_alpha_annualized"),
        "best_rank_ic": leader(ok, "rank_ic_mean"),
        "status": summary[["window_id", "feature_set", "name", "status"]].to_dict("records"),
        "interpretation": "Alpha158 需至少 3/4 窗口 sector_cap_2 alpha 为正；EDGAR 需至少 3/4 窗口 sector_cap_2 alpha 不低于 Alpha158 才考虑替代。",
    }


def classify_result(ok: pd.DataFrame, alpha_positive: int, edgar_beat_count: int) -> str:
    if len(ok) < 8:
        return "incomplete"
    if alpha_positive >= 3 and edgar_beat_count >= 3:
        return "stable_default_with_edgar_candidate"
    if alpha_positive >= 3:
        return "stable_default_alpha158"
    if alpha_positive in {1, 2}:
        return "candidate_branch"
    return "unstable_observation"


def leader(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    if frame.empty or column not in frame:
        return {}
    usable = frame[pd.to_numeric(frame[column], errors="coerce").notna()]
    if usable.empty:
        return {}
    row = usable.sort_values(column, ascending=False).iloc[0]
    fields = ["window_id", "feature_set", "name", column, "ic_mean", "rank_ic_mean", "sector_cap_2_alpha_annualized"]
    return {field: native(row.get(field)) for field in fields if field in row}


def write_report(path: Path, summary: pd.DataFrame, yaml_summary: dict[str, Any]) -> None:
    lines = [
        "# CRSP Rolling Window Validation",
        "",
        "本报告比较 Alpha158-only 与 EDGAR mini-core 在多个测试窗口下的 `sector_cap_2_top10` 稳定性。",
        "",
        "```yaml",
        yaml.safe_dump(yaml_summary, allow_unicode=True, sort_keys=False).strip(),
        "```",
        "",
        "## Summary Table",
        "",
        dataframe_to_markdown(summary),
        "",
        "结果是学习研究材料，不是投资建议。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def dataframe_to_markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "N/A"
    display = frame[
        [
            "window_label",
            "feature_set",
            "status",
            "ic_mean",
            "rank_ic_mean",
            "sector_cap_2_annualized_return",
            "sector_cap_2_alpha_annualized",
            "sector_cap_2_max_drawdown",
        ]
    ].copy()
    columns = [str(column) for column in display.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in display.iterrows():
        lines.append("| " + " | ".join(format_cell(row[column]) for column in display.columns) + " |")
    return "\n".join(lines)


def format_cell(value: Any) -> str:
    if pd.isna(value):
        return "N/A"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value).replace("|", "\\|")


def main() -> None:
    args = parse_args()
    summary = run_crsp_rolling_window_validation(
        args.manifest,
        only_summary=args.only_summary,
        force=args.force,
        python_executable=args.python,
    )
    print(f"Rolling window rows: {len(summary)}")
    print(f"Output: {resolve_path(load_manifest(args.manifest).get('output_dir'))}")


if __name__ == "__main__":
    main()
