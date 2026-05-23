"""Aggregate macro interaction ablation experiments."""

from __future__ import annotations

import argparse
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

try:  # pragma: no cover - supports direct script execution.
    from macro_regime_review import build_thresholds, classify_regimes, compare_experiments, summarize_by_regime
except ImportError:  # pragma: no cover - supports importing as a package.
    from analysis.nasdaq_top500_score.macro_regime_review import (
        build_thresholds,
        classify_regimes,
        compare_experiments,
        summarize_by_regime,
    )


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = Path(__file__).resolve().parent / "configs" / "macro_ablation" / "manifest.yaml"
SUMMARY_COLUMNS = [
    "name",
    "description",
    "run_dir",
    "status",
    "ic_mean",
    "rank_ic_mean",
    "macro_interaction_feature_count",
    "best_iteration",
    "best_valid_l2",
    "cumulative_return",
    "annualized_return",
    "max_drawdown",
    "excess_cumulative_return",
    "alpha_annualized",
    "beta",
    "avg_turnover",
    "avg_sector_hhi",
    "stress_annualized_return_50bps",
    "stress_annualized_drop_50bps",
    "annualized_return_delta_vs_full",
    "rank_ic_delta_vs_full",
    "alpha_annualized_delta_vs_full",
    "beta_delta_vs_full",
]
REGIME_COLUMNS = [
    "name",
    "regime_key",
    "regime_value",
    "baseline_period_count",
    "comparison_period_count",
    "annualized_return_diff",
    "alpha_annualized_diff",
    "beta_diff",
    "max_drawdown_diff",
]


@dataclass
class MacroAblationReviewResult:
    summary: pd.DataFrame
    regime_summary: pd.DataFrame
    yaml_summary: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help=f"Macro ablation manifest. Defaults to {DEFAULT_MANIFEST}",
    )
    return parser.parse_args()


def resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else WORKSPACE / path


def load_manifest(path: Path) -> dict[str, Any]:
    resolved = resolve_path(path)
    with resolved.open("r", encoding="utf-8") as file:
        manifest = yaml.safe_load(file) or {}
    manifest["_manifest_path"] = str(resolved)
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> None:
    if not manifest.get("output_dir"):
        raise ValueError("macro ablation manifest requires output_dir")
    if not manifest.get("variant"):
        raise ValueError("macro ablation manifest requires variant")
    experiments = manifest.get("experiments", [])
    if not experiments:
        raise ValueError("macro ablation manifest requires experiments")
    names = [str(experiment.get("name", "")).strip() for experiment in experiments]
    if any(not name for name in names):
        raise ValueError("macro ablation experiments require non-empty name")
    if len(names) != len(set(names)):
        raise ValueError("macro ablation experiment names must be unique")
    for experiment in experiments:
        if not experiment.get("run_dir"):
            raise ValueError(f"macro ablation experiment {experiment.get('name')} requires run_dir")
    full = str(manifest.get("full_experiment", "full_interactions"))
    if full not in names:
        raise ValueError("macro ablation full_experiment must be present in experiments")


def run_macro_ablation_review(manifest_path: Path = DEFAULT_MANIFEST) -> MacroAblationReviewResult:
    manifest = load_manifest(manifest_path)
    output_dir = resolve_path(manifest["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    variant = str(manifest["variant"])
    output_prefix = str(manifest.get("output_prefix", "macro_ablation"))

    rows = [experiment_summary(experiment, variant) for experiment in manifest["experiments"]]
    summary = pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
    summary = add_full_deltas(summary, str(manifest.get("full_experiment", "full_interactions")))
    regime_summary = build_regime_summary(manifest)
    yaml_summary = build_yaml_summary(summary, regime_summary, manifest)

    summary.to_csv(output_dir / f"{output_prefix}_summary.csv", index=False)
    regime_summary.to_csv(output_dir / f"{output_prefix}_regime_summary.csv", index=False)
    (output_dir / f"{output_prefix}_review_summary.yaml").write_text(
        yaml.safe_dump(yaml_summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    write_markdown_report(output_dir / "report.md", summary, regime_summary, yaml_summary, manifest)
    return MacroAblationReviewResult(summary=summary, regime_summary=regime_summary, yaml_summary=yaml_summary)


def experiment_summary(experiment: dict[str, Any], variant: str) -> dict[str, Any]:
    name = str(experiment["name"])
    run_dir = resolve_path(experiment["run_dir"])
    row: dict[str, Any] = {
        "name": name,
        "description": str(experiment.get("description", "")),
        "run_dir": str(run_dir),
        "status": "ok",
    }
    report_path = run_dir / "report.md"
    if variant == "main_backtest":
        summary_path = run_dir / "backtest_summary.yaml"
        if not report_path.exists() or not summary_path.exists():
            row.update({"status": "missing_outputs"})
            return row
        row.update(parse_report_metrics(report_path.read_text(encoding="utf-8")))
        row.update(read_main_backtest_metrics(run_dir))
        return row

    strategy_path = run_dir / "strategy_comparison.csv"
    if not report_path.exists() or not strategy_path.exists():
        row.update({"status": "missing_outputs"})
        return row

    report_text = report_path.read_text(encoding="utf-8")
    row.update(parse_report_metrics(report_text))
    strategy = pd.read_csv(strategy_path)
    selected = strategy[strategy["name"].eq(variant)]
    if selected.empty:
        row.update({"status": f"missing_variant:{variant}"})
        return row
    strategy_row = selected.iloc[0]
    for column in [
        "cumulative_return",
        "annualized_return",
        "max_drawdown",
        "excess_cumulative_return",
        "alpha_annualized",
        "beta",
        "avg_turnover",
        "avg_sector_hhi",
    ]:
        row[column] = numeric(strategy_row.get(column))
    row.update(read_training_summary(run_dir))
    row.update(read_stress_metrics(run_dir, row.get("annualized_return")))
    return row


def parse_report_metrics(report_text: str) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "ic_mean": extract_float(report_text, r"Test 日均 IC：([+-]?\d+(?:\.\d+)?)"),
        "rank_ic_mean": extract_float(report_text, r"Test 日均 Rank IC：([+-]?\d+(?:\.\d+)?)"),
        "macro_interaction_feature_count": extract_float(report_text, r"交互特征数量：(\d+)"),
    }
    if math.isnan(metrics["macro_interaction_feature_count"]):
        metrics["macro_interaction_feature_count"] = 0
    return metrics


def extract_float(text: str, pattern: str) -> float:
    match = re.search(pattern, text)
    if not match:
        return math.nan
    return float(match.group(1))


def numeric(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def read_main_backtest_metrics(run_dir: Path) -> dict[str, Any]:
    backtest = read_yaml(run_dir / "backtest_summary.yaml")
    benchmark = read_yaml(run_dir / "benchmark_summary.yaml") or backtest.get("benchmark", {})
    metrics = {
        "cumulative_return": numeric(backtest.get("cumulative_return")),
        "annualized_return": numeric(backtest.get("annualized_return")),
        "max_drawdown": numeric(backtest.get("max_drawdown")),
        "avg_turnover": numeric(backtest.get("avg_turnover")),
        "excess_cumulative_return": numeric(benchmark.get("excess_cumulative_return")),
        "alpha_annualized": numeric(benchmark.get("alpha_annualized")),
        "beta": numeric(benchmark.get("beta")),
        "avg_sector_hhi": average_sector_hhi(run_dir / "backtest_positions.csv"),
    }
    metrics.update(read_training_summary(run_dir))
    metrics.update(read_stress_metrics(run_dir, metrics.get("annualized_return")))
    return metrics


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def read_training_summary(run_dir: Path) -> dict[str, float]:
    summary = read_yaml(run_dir / "training_summary.yaml")
    best_iteration = numeric(summary.get("best_iteration"))
    best_valid_l2 = numeric(summary.get("best_valid_l2"))
    if not math.isnan(best_iteration) or not math.isnan(best_valid_l2):
        return {"best_iteration": best_iteration, "best_valid_l2": best_valid_l2}
    path = run_dir / "early_stopping_variants.csv"
    if not path.exists():
        return {"best_iteration": math.nan, "best_valid_l2": math.nan}
    frame = pd.read_csv(path)
    selected = frame[frame["variant"].eq("current")] if "variant" in frame.columns else frame
    if selected.empty:
        selected = frame
    row = selected.iloc[0]
    return {
        "best_iteration": numeric(row.get("best_iteration")),
        "best_valid_l2": numeric(row.get("best_valid_l2")),
    }


def read_stress_metrics(run_dir: Path, annualized_return: Any) -> dict[str, float]:
    path = run_dir / "backtest_stress_matrix.csv"
    if not path.exists():
        return {"stress_annualized_return_50bps": math.nan, "stress_annualized_drop_50bps": math.nan}
    frame = pd.read_csv(path)
    selected = frame[
        frame["entry_lag_days"].astype(str).eq("1")
        & frame["entry_price"].astype(str).eq("open")
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


def average_sector_hhi(path: Path) -> float:
    if not path.exists():
        return math.nan
    positions = pd.read_csv(path, usecols=lambda column: column in {"signal_date", "sector", "weight"})
    if positions.empty or "sector" not in positions.columns or "weight" not in positions.columns:
        return math.nan
    weights = positions.assign(sector=positions["sector"].fillna("UNKNOWN")).groupby(["signal_date", "sector"])["weight"].sum()
    hhi = weights.pow(2).groupby(level="signal_date").sum()
    return float(hhi.mean()) if not hhi.empty else math.nan


def add_full_deltas(summary: pd.DataFrame, full_name: str) -> pd.DataFrame:
    output = summary.copy()
    full_rows = output[output["name"].eq(full_name)]
    if full_rows.empty:
        return output
    full = full_rows.iloc[0]
    delta_columns = {
        "annualized_return": "annualized_return_delta_vs_full",
        "rank_ic_mean": "rank_ic_delta_vs_full",
        "alpha_annualized": "alpha_annualized_delta_vs_full",
        "beta": "beta_delta_vs_full",
    }
    for column, delta_column in delta_columns.items():
        output[delta_column] = pd.to_numeric(output[column], errors="coerce") - numeric(full.get(column))
    return output


def build_regime_summary(manifest: dict[str, Any]) -> pd.DataFrame:
    if str(manifest.get("variant")) == "main_backtest" and manifest.get("macro_features_path"):
        return build_main_backtest_regime_summary(manifest)

    rows = []
    min_periods = int(manifest.get("regime_min_periods", 5))
    for experiment in manifest["experiments"]:
        run_dir = resolve_path(experiment["run_dir"])
        path = run_dir / "macro_regime_strategy_comparison.csv"
        if not path.exists():
            continue
        comparison_name = str(experiment.get("regime_comparison_name", experiment["name"]))
        frame = pd.read_csv(path)
        frame = frame[frame["comparison_experiment"].eq(comparison_name)].copy()
        if frame.empty:
            continue
        frame = frame[
            (pd.to_numeric(frame["baseline_period_count"], errors="coerce") >= min_periods)
            & (pd.to_numeric(frame["comparison_period_count"], errors="coerce") >= min_periods)
        ]
        frame["name"] = experiment["name"]
        rows.append(frame.reindex(columns=REGIME_COLUMNS))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=REGIME_COLUMNS)


def build_main_backtest_regime_summary(manifest: dict[str, Any]) -> pd.DataFrame:
    macro_features_path = resolve_path(manifest["macro_features_path"])
    if not macro_features_path.exists():
        return pd.DataFrame(columns=REGIME_COLUMNS)

    frames = []
    for experiment in manifest["experiments"]:
        nav_path = resolve_path(experiment["run_dir"]) / "backtest_nav.csv"
        if not nav_path.exists():
            continue
        nav = pd.read_csv(nav_path)
        nav["experiment"] = str(experiment["name"])
        frames.append(nav)
    if not frames:
        return pd.DataFrame(columns=REGIME_COLUMNS)

    nav_all = pd.concat(frames, ignore_index=True)
    nav_all["signal_date"] = pd.to_datetime(nav_all["signal_date"], errors="coerce").dt.normalize()
    nav_all = nav_all[nav_all["signal_date"].notna()].copy()
    if nav_all.empty:
        return pd.DataFrame(columns=REGIME_COLUMNS)

    macro_daily = read_macro_daily(macro_features_path)
    threshold_history = macro_daily[macro_daily.index < nav_all["signal_date"].min()]
    thresholds = build_thresholds(threshold_history)
    regimes = classify_regimes(macro_daily, thresholds)
    daily = nav_all.merge(regimes.reset_index().rename(columns={"datetime": "signal_date"}), on="signal_date", how="left")
    summary = summarize_by_regime(daily, {"backtest": manifest.get("backtest", {})})
    comparison = compare_experiments(summary, {"baseline_experiment": manifest.get("baseline_experiment", "baseline")})
    if comparison.empty:
        return pd.DataFrame(columns=REGIME_COLUMNS)
    min_periods = int(manifest.get("regime_min_periods", 5))
    comparison = comparison[
        (pd.to_numeric(comparison["baseline_period_count"], errors="coerce") >= min_periods)
        & (pd.to_numeric(comparison["comparison_period_count"], errors="coerce") >= min_periods)
    ].copy()
    comparison["name"] = comparison["comparison_experiment"]
    return comparison.reindex(columns=REGIME_COLUMNS).reset_index(drop=True)


def read_macro_daily(path: Path) -> pd.DataFrame:
    macro = pd.read_parquet(path)
    if isinstance(macro.index, pd.MultiIndex) and "datetime" in macro.index.names:
        return macro.groupby(level="datetime").first().sort_index()
    if "datetime" in macro.columns:
        macro = macro.copy()
        macro["datetime"] = pd.to_datetime(macro["datetime"], errors="coerce").dt.normalize()
        return macro.dropna(subset=["datetime"]).groupby("datetime").first().sort_index()
    index = pd.to_datetime(macro.index, errors="coerce")
    macro = macro.copy()
    macro.index = index
    return macro[macro.index.notna()].sort_index()


def build_yaml_summary(summary: pd.DataFrame, regime_summary: pd.DataFrame, manifest: dict[str, Any]) -> dict[str, Any]:
    full_name = str(manifest.get("full_experiment", "full_interactions"))
    usable = summary[summary["status"].eq("ok")].copy()
    return {
        "manifest_path": manifest.get("_manifest_path"),
        "variant": manifest.get("variant"),
        "full_experiment": full_name,
        "experiment_count": int(len(summary)),
        "completed_count": int(len(usable)),
        "best_annualized_return": leader(usable, "annualized_return", higher=True),
        "best_rank_ic": leader(usable, "rank_ic_mean", higher=True),
        "best_alpha": leader(usable, "alpha_annualized", higher=True),
        "largest_annualized_drop_vs_full": leader(usable[usable["name"].ne(full_name)], "annualized_return_delta_vs_full", higher=False),
        "largest_rank_ic_drop_vs_full": leader(usable[usable["name"].ne(full_name)], "rank_ic_delta_vs_full", higher=False),
        "best_regimes_vs_baseline": regime_records(regime_summary, ascending=False),
        "worst_regimes_vs_baseline": regime_records(regime_summary, ascending=True),
        "missing_or_failed": summary[~summary["status"].eq("ok")][["name", "status"]].to_dict("records"),
    }


def leader(frame: pd.DataFrame, column: str, *, higher: bool) -> dict[str, Any]:
    if frame.empty or column not in frame:
        return {}
    usable = frame[pd.to_numeric(frame[column], errors="coerce").notna()]
    if usable.empty:
        return {}
    selected = usable.sort_values(column, ascending=not higher).iloc[0]
    columns = [
        "name",
        column,
        "annualized_return",
        "rank_ic_mean",
        "alpha_annualized",
        "beta",
        "annualized_return_delta_vs_full",
    ]
    return {key: normalize(selected.get(key)) for key in columns if key in selected.index}


def regime_records(frame: pd.DataFrame, *, ascending: bool) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    selected = frame.sort_values("annualized_return_diff", ascending=ascending).head(8)
    columns = ["name", "regime_key", "regime_value", "baseline_period_count", "annualized_return_diff", "alpha_annualized_diff", "beta_diff"]
    return [
        {key: normalize(row.get(key)) for key in columns}
        for row in selected[columns].to_dict("records")
    ]


def normalize(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (str, int, bool)):
        return value
    return float(value)


def write_markdown_report(
    path: Path,
    summary: pd.DataFrame,
    regime_summary: pd.DataFrame,
    yaml_summary: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    path.write_text(
        "\n".join(
            [
                f"# {manifest.get('title', 'Macro Interaction Ablation Review')}",
                "",
                f"Generated at: {datetime.now().isoformat(timespec='seconds')}",
                "",
                "## 结论口径",
                "",
                "- 本报告用于学习研究，不是投资建议。",
                "- 所有实验应复用同一股票池、切分、标签、模型参数和回测口径；只改变宏观交互组合。",
                "- 如果收益提高但 IC / Rank IC 没有改善，只能标记为回测收益改善，不能直接认定横截面预测力增强。",
                "",
                "## Manifest",
                "",
                f"- Manifest: `{manifest.get('_manifest_path')}`",
                f"- Variant: `{manifest.get('variant')}`",
                f"- Baseline: `{manifest.get('baseline_experiment')}`",
                f"- Full experiment: `{manifest.get('full_experiment')}`",
                f"- Experiment count: `{len(summary)}`",
                "",
                "## Ablation Summary",
                "",
                markdown_table(
                    summary,
                    [
                        "name",
                        "status",
                        "ic_mean",
                        "rank_ic_mean",
                        "annualized_return",
                        "max_drawdown",
                        "alpha_annualized",
                        "beta",
                        "stress_annualized_return_50bps",
                        "annualized_return_delta_vs_full",
                    ],
                ),
                "",
                "## Leaders",
                "",
                "```yaml",
                yaml.safe_dump(
                    {
                        "best_annualized_return": yaml_summary.get("best_annualized_return", {}),
                        "best_rank_ic": yaml_summary.get("best_rank_ic", {}),
                        "best_alpha": yaml_summary.get("best_alpha", {}),
                        "largest_annualized_drop_vs_full": yaml_summary.get("largest_annualized_drop_vs_full", {}),
                        "largest_rank_ic_drop_vs_full": yaml_summary.get("largest_rank_ic_drop_vs_full", {}),
                        "missing_or_failed": yaml_summary.get("missing_or_failed", []),
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ).strip(),
                "```",
                "",
                "## Regime Summary",
                "",
                markdown_table(
                    regime_summary.head(40),
                    [
                        "name",
                        "regime_key",
                        "regime_value",
                        "annualized_return_diff",
                        "alpha_annualized_diff",
                        "beta_diff",
                        "max_drawdown_diff",
                    ],
                ),
                "",
                "## Output Files",
                "",
                f"- `{manifest.get('output_prefix', 'macro_ablation')}_summary.csv`",
                f"- `{manifest.get('output_prefix', 'macro_ablation')}_regime_summary.csv`",
                f"- `{manifest.get('output_prefix', 'macro_ablation')}_review_summary.yaml`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_No rows._"
    existing = [column for column in columns if column in frame.columns]
    rows = ["| " + " | ".join(existing) + " |", "| " + " | ".join(["---"] * len(existing)) + " |"]
    for _, row in frame[existing].iterrows():
        rows.append("| " + " | ".join(format_markdown_value(row.get(column)) for column in existing) + " |")
    return "\n".join(rows)


def format_markdown_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value).replace("|", "\\|")


def main() -> None:
    args = parse_args()
    result = run_macro_ablation_review(args.manifest)
    print(result.summary.to_string(index=False))
    print(f"Output dir: {resolve_path(load_manifest(args.manifest)['output_dir'])}")


if __name__ == "__main__":
    main()
