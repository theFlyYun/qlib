"""Compare CRSP Alpha158 and EDGAR mini-core runs across 10/20/60 day labels."""

from __future__ import annotations

import argparse
import math
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
DEFAULT_CONFIGS = [
    Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_10d_conservative_2010_2025.yaml"),
    Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_mini_core_10d_conservative_2010_2025.yaml"),
    Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_20d_conservative_2010_2025.yaml"),
    Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_mini_core_20d_conservative_2010_2025.yaml"),
    Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_60d_conservative_2010_2025.yaml"),
    Path("analysis/nasdaq_top500_score/configs/crsp_2010/crsp_alpha158_edgar_mini_core_60d_conservative_2010_2025.yaml"),
]
DEFAULT_OUTPUT_DIR = Path("analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_horizon_review")
SUMMARY_COLUMNS = [
    "name",
    "status",
    "feature_set",
    "horizon_days",
    "run_dir",
    "ic_mean",
    "rank_ic_mean",
    "best_iteration",
    "best_valid_l2",
    "annualized_return",
    "max_drawdown",
    "alpha_annualized",
    "beta",
    "stress_annualized_return_50bps",
    "sector_cap_2_annualized_return",
    "sector_cap_2_max_drawdown",
    "sector_cap_2_alpha_annualized",
    "sector_cap_2_beta",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configs", nargs="*", type=Path, default=DEFAULT_CONFIGS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def resolve_path(path: str | Path) -> Path:
    value = Path(path).expanduser()
    return value if value.is_absolute() else WORKSPACE / value


def run_crsp_edgar_mini_core_horizon_review(
    configs: list[Path] | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> pd.DataFrame:
    configs = configs or DEFAULT_CONFIGS
    output = resolve_path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rows = [summarize_config(path) for path in configs]
    summary = pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
    summary.to_csv(output / "crsp_edgar_mini_core_horizon_summary.csv", index=False)
    yaml_summary = build_yaml_summary(summary)
    (output / "crsp_edgar_mini_core_horizon_review.yaml").write_text(
        yaml.safe_dump(yaml_summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    write_markdown_report(output / "report.md", summary, yaml_summary)
    return summary


def summarize_config(config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    paths = build_paths(config)
    run_dir = paths["output_dir"]
    row: dict[str, Any] = {
        "name": config["experiment"]["name"],
        "status": "ok",
        "feature_set": feature_set(config),
        "horizon_days": int(config["crsp"]["label_horizon_days"]),
        "run_dir": str(run_dir),
    }
    required = [paths["report_md"], paths["backtest_summary"], paths["benchmark_summary"]]
    missing = [path.name for path in required if not path.exists()]
    if missing:
        row["status"] = "missing_outputs:" + ",".join(missing)
        return row
    row.update(parse_report_metrics(paths["report_md"].read_text(encoding="utf-8")))
    row.update(read_main_backtest(paths))
    row.update(read_stress(paths["backtest_stress_matrix"], row.get("annualized_return")))
    row.update(read_training(paths["training_summary"]))
    row.update(read_sector_cap2(paths["strategy_comparison_csv"]))
    return row


def feature_set(config: dict[str, Any]) -> str:
    return "edgar_mini_core" if config.get("fundamentals", {}).get("enabled", False) else "alpha158_only"


def read_main_backtest(paths: dict[str, Path]) -> dict[str, float]:
    backtest = yaml.safe_load(paths["backtest_summary"].read_text(encoding="utf-8")) or {}
    benchmark = yaml.safe_load(paths["benchmark_summary"].read_text(encoding="utf-8")) or {}
    return {
        "annualized_return": numeric(backtest.get("annualized_return")),
        "max_drawdown": numeric(backtest.get("max_drawdown")),
        "alpha_annualized": numeric(benchmark.get("alpha_annualized")),
        "beta": numeric(benchmark.get("beta")),
    }


def read_training(path: Path) -> dict[str, float]:
    if not path.exists():
        return {"best_iteration": math.nan, "best_valid_l2": math.nan}
    summary = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        "best_iteration": numeric(summary.get("best_iteration")),
        "best_valid_l2": numeric(summary.get("best_valid_l2")),
    }


def read_sector_cap2(path: Path) -> dict[str, float]:
    empty = {
        "sector_cap_2_annualized_return": math.nan,
        "sector_cap_2_max_drawdown": math.nan,
        "sector_cap_2_alpha_annualized": math.nan,
        "sector_cap_2_beta": math.nan,
    }
    if not path.exists():
        return empty
    frame = pd.read_csv(path)
    selected = frame[frame["name"].eq("sector_cap_2_top10")] if "name" in frame else pd.DataFrame()
    if selected.empty:
        return empty
    row = selected.iloc[0]
    return {
        "sector_cap_2_annualized_return": numeric(row.get("annualized_return")),
        "sector_cap_2_max_drawdown": numeric(row.get("max_drawdown")),
        "sector_cap_2_alpha_annualized": numeric(row.get("alpha_annualized")),
        "sector_cap_2_beta": numeric(row.get("beta")),
    }


def build_yaml_summary(summary: pd.DataFrame) -> dict[str, Any]:
    ok = summary[summary["status"].eq("ok")].copy()
    return {
        "experiment_count": int(len(summary)),
        "completed_count": int(len(ok)),
        "best_rank_ic": leader(ok, "rank_ic_mean", higher=True),
        "best_sector_cap_2_alpha": leader(ok, "sector_cap_2_alpha_annualized", higher=True),
        "best_global_alpha": leader(ok, "alpha_annualized", higher=True),
        "status": summary[["name", "status"]].to_dict("records"),
        "interpretation_rule": "EDGAR mini-core 只有在 Rank IC、alpha 或 sector_cap_2 稳定性改善时才考虑进入默认主线。",
    }


def leader(frame: pd.DataFrame, column: str, *, higher: bool) -> dict[str, Any]:
    if frame.empty or column not in frame:
        return {}
    usable = frame[pd.to_numeric(frame[column], errors="coerce").notna()]
    if usable.empty:
        return {}
    row = usable.sort_values(column, ascending=not higher).iloc[0]
    fields = ["name", "feature_set", "horizon_days", column, "ic_mean", "rank_ic_mean", "annualized_return", "alpha_annualized"]
    return {field: native(row.get(field)) for field in fields if field in row}


def write_markdown_report(path: Path, summary: pd.DataFrame, yaml_summary: dict[str, Any]) -> None:
    lines = [
        "# CRSP EDGAR Mini-Core Horizon Review",
        "",
        "本报告比较 Alpha158-only 与 EDGAR mini-core 在 10/20/60 日标签下的表现。",
        "",
        "```yaml",
        yaml.safe_dump(yaml_summary, allow_unicode=True, sort_keys=False).strip(),
        "```",
        "",
        "| Name | Status | Horizon | Feature Set | IC | Rank IC | Global Ann. | Global Alpha | Sector Cap2 Ann. | Sector Cap2 Alpha |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary.to_dict("records"):
        lines.append(
            "| {name} | {status} | {horizon} | {features} | {ic} | {rank_ic} | {ann} | {alpha} | {cap_ann} | {cap_alpha} |".format(
                name=row.get("name"),
                status=row.get("status"),
                horizon=row.get("horizon_days"),
                features=row.get("feature_set"),
                ic=fmt(row.get("ic_mean")),
                rank_ic=fmt(row.get("rank_ic_mean")),
                ann=pct(row.get("annualized_return")),
                alpha=pct(row.get("alpha_annualized")),
                cap_ann=pct(row.get("sector_cap_2_annualized_return")),
                cap_alpha=pct(row.get("sector_cap_2_alpha_annualized")),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def fmt(value: Any, digits: int = 4) -> str:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "N/A"
    return "N/A" if math.isnan(numeric_value) else f"{numeric_value:.{digits}f}"


def pct(value: Any) -> str:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "N/A"
    return "N/A" if math.isnan(numeric_value) else f"{numeric_value:.2%}"


def main() -> None:
    args = parse_args()
    summary = run_crsp_edgar_mini_core_horizon_review(args.configs, args.output_dir)
    print(f"Mini-core horizon rows: {len(summary)}")
    print(f"Output: {resolve_path(args.output_dir)}")


if __name__ == "__main__":
    main()
