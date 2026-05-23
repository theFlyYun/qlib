"""Review rolling-window failures and EDGAR mini-core deltas without retraining."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

try:  # pragma: no cover - supports direct script execution.
    from backtest import summarize_backtest, summarize_benchmark
    from crsp_edgar_mini_core_position_diff import (
        MINI_CORE_COLUMNS,
        attach_fundamentals,
        build_position_diff,
        read_fundamentals,
        read_variant_positions,
    )
    from crsp_rolling_window_validation import (
        DEFAULT_MANIFEST,
        load_manifest,
        manifest_entries,
        run_crsp_rolling_window_validation,
    )
    from run_qlib_alpha158_lightgbm import build_paths, load_config
except ImportError:  # pragma: no cover
    from analysis.nasdaq_top500_score.backtest import summarize_backtest, summarize_benchmark
    from analysis.nasdaq_top500_score.crsp_edgar_mini_core_position_diff import (
        MINI_CORE_COLUMNS,
        attach_fundamentals,
        build_position_diff,
        read_fundamentals,
        read_variant_positions,
    )
    from analysis.nasdaq_top500_score.crsp_rolling_window_validation import (
        DEFAULT_MANIFEST,
        load_manifest,
        manifest_entries,
        run_crsp_rolling_window_validation,
    )
    from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import build_paths, load_config


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = Path("analysis/nasdaq_top500_score/runs/crsp_rolling_windows/failure_review")
DEFAULT_VARIANT = "sector_cap_2_top10"
DEFAULT_COST_BPS = [0, 25, 50]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--variant", default=DEFAULT_VARIANT)
    parser.add_argument("--skip-summary-refresh", action="store_true")
    return parser.parse_args()


def resolve_path(path: str | Path) -> Path:
    value = Path(path).expanduser()
    return value if value.is_absolute() else WORKSPACE / value


def run_crsp_rolling_window_failure_review(
    manifest_path: Path = DEFAULT_MANIFEST,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    variant: str = DEFAULT_VARIANT,
    refresh_rolling_summary: bool = True,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    entries = manifest_entries(manifest)
    output = resolve_path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    run_records = [load_run_record(entry, variant) for entry in entries]
    stress_rows = []
    failure_rows = []
    sector_frames = []
    symbol_frames = []
    drawdown_rows = []
    beta_rows = []

    for record in run_records:
        stress = build_sector_cap_stress(record)
        stress_rows.extend(stress)
        failure_rows.append(build_failure_summary(record, stress))
        drawdown_rows.append(build_drawdown_event(record))
        beta_rows.append(build_beta_exposure(record))
        sector_frames.append(read_contribution_frame(record, "sector"))
        symbol_frames.append(read_contribution_frame(record, "symbol"))

    edgar_delta = build_edgar_delta_by_window(run_records)
    failure = pd.DataFrame(failure_rows)
    sector = concat_frames(sector_frames)
    symbol = concat_frames(symbol_frames)
    drawdown = pd.DataFrame(drawdown_rows)
    beta = pd.DataFrame(beta_rows)
    stress = pd.DataFrame(stress_rows)

    failure.to_csv(output / "rolling_window_failure_summary.csv", index=False)
    sector.to_csv(output / "rolling_window_sector_contribution.csv", index=False)
    symbol.to_csv(output / "rolling_window_position_contribution.csv", index=False)
    drawdown.to_csv(output / "rolling_window_drawdown_events.csv", index=False)
    beta.to_csv(output / "rolling_window_beta_exposure.csv", index=False)
    edgar_delta.to_csv(output / "rolling_edgar_delta_by_window.csv", index=False)
    stress.to_csv(output / "sector_cap_2_stress_matrix.csv", index=False)

    yaml_summary = build_yaml_summary(failure, edgar_delta, stress)
    (output / "rolling_window_failure_review_summary.yaml").write_text(
        yaml.safe_dump(yaml_summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    write_report(output / "rolling_window_failure_review.md", failure, edgar_delta, drawdown, beta, stress, yaml_summary)

    if refresh_rolling_summary:
        run_crsp_rolling_window_validation(manifest_path, only_summary=True)
    return yaml_summary


def load_run_record(entry: dict[str, Any], variant: str) -> dict[str, Any]:
    config = load_config(resolve_path(entry["config"]))
    paths = build_paths(config)
    variant_dir = paths["strategy_comparison_dir"] / variant
    return {
        "window_id": entry["window_id"],
        "window_label": entry["window_label"],
        "feature_set": entry["feature_set"],
        "name": config["experiment"]["name"],
        "config": config,
        "paths": paths,
        "run_dir": paths["output_dir"],
        "variant": variant,
        "variant_dir": variant_dir,
        "nav_path": variant_dir / "backtest_nav.csv",
        "positions_path": variant_dir / "backtest_positions.csv",
        "summary_path": variant_dir / "backtest_summary.yaml",
        "benchmark_path": variant_dir / "benchmark_summary.yaml",
    }


def build_sector_cap_stress(record: dict[str, Any], cost_bps_values: list[int] | None = None) -> list[dict[str, Any]]:
    cost_bps_values = cost_bps_values or DEFAULT_COST_BPS
    nav = pd.read_csv(record["nav_path"])
    positions = pd.read_csv(record["positions_path"])
    config = record["config"]
    rows = []
    for cost_bps in cost_bps_values:
        stressed_nav, summary = stress_nav_for_cost(nav, positions, config, cost_bps)
        benchmark = summary.get("benchmark", {})
        row = {
            "window_id": record["window_id"],
            "window_label": record["window_label"],
            "feature_set": record["feature_set"],
            "variant": record["variant"],
            "entry_lag_days": int(config["backtest"].get("entry_lag_days", 1)),
            "entry_price": str(config["backtest"].get("price", "open")),
            "cost_bps": float(cost_bps),
            "period_count": summary.get("period_count"),
            "cumulative_return": summary.get("cumulative_return"),
            "annualized_return": summary.get("annualized_return"),
            "max_drawdown": summary.get("max_drawdown"),
            "avg_turnover": summary.get("avg_turnover"),
            "total_cost_return": summary.get("total_cost_return"),
            "alpha_annualized": benchmark.get("alpha_annualized"),
            "beta": benchmark.get("beta"),
        }
        rows.append(row)
        if cost_bps == 0:
            stressed_nav.to_csv(record["variant_dir"] / "sector_cap_2_cost0_nav.csv", index=False)

    matrix = pd.DataFrame(rows)
    matrix.to_csv(record["variant_dir"] / "sector_cap_2_stress_matrix.csv", index=False)
    matrix.to_csv(record["variant_dir"] / "backtest_stress_matrix.csv", index=False)
    (record["variant_dir"] / "sector_cap_2_stress_summary.yaml").write_text(
        yaml.safe_dump({"enabled": True, "rows": rows}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return rows


def stress_nav_for_cost(
    nav: pd.DataFrame,
    positions: pd.DataFrame,
    config: dict[str, Any],
    cost_bps: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    stressed = nav.copy()
    cost_rate = float(cost_bps) / 10000.0
    stressed["cost_return"] = pd.to_numeric(stressed["turnover"], errors="coerce").fillna(0.0) * cost_rate
    stressed["net_return"] = pd.to_numeric(stressed["gross_return"], errors="coerce").fillna(0.0) - stressed["cost_return"]
    stressed["nav"] = (1.0 + stressed["net_return"]).cumprod()
    if "benchmark_return" in stressed.columns:
        stressed["benchmark_return"] = pd.to_numeric(stressed["benchmark_return"], errors="coerce")
        stressed["excess_return"] = stressed["net_return"] - stressed["benchmark_return"]
        stressed["benchmark_nav"] = (1.0 + stressed["benchmark_return"].fillna(0.0)).cumprod()
        stressed["relative_nav"] = stressed["nav"] / stressed["benchmark_nav"]
    backtest_config = dict(config["backtest"])
    backtest_config["cost_bps"] = float(cost_bps)
    summary = summarize_backtest(stressed, positions, backtest_config, skipped_periods=0)
    if "benchmark_return" in stressed.columns:
        benchmark_summary = summarize_benchmark(stressed, {**config, "backtest": backtest_config}, config.get("benchmark", {}))
        if benchmark_summary:
            summary["benchmark"] = benchmark_summary
    return stressed, summary


def build_failure_summary(record: dict[str, Any], stress_rows: list[dict[str, Any]]) -> dict[str, Any]:
    backtest = yaml.safe_load(record["summary_path"].read_text(encoding="utf-8")) or {}
    benchmark = yaml.safe_load(record["benchmark_path"].read_text(encoding="utf-8")) or {}
    comparison = read_strategy_row(record)
    stress_50 = next((row for row in stress_rows if row["cost_bps"] == 50.0), {})
    drawdown = build_drawdown_event(record)
    return {
        "window_id": record["window_id"],
        "window_label": record["window_label"],
        "feature_set": record["feature_set"],
        "strategy_state": strategy_state(record["feature_set"], benchmark.get("alpha_annualized")),
        "annualized_return": backtest.get("annualized_return"),
        "alpha_annualized": benchmark.get("alpha_annualized"),
        "beta": benchmark.get("beta"),
        "correlation": benchmark.get("correlation"),
        "max_drawdown": backtest.get("max_drawdown"),
        "stress_50bps_annualized_return": stress_50.get("annualized_return"),
        "stress_50bps_alpha_annualized": stress_50.get("alpha_annualized"),
        "avg_turnover": backtest.get("avg_turnover"),
        "max_avg_sector": comparison.get("max_avg_sector"),
        "max_avg_sector_exposure": comparison.get("max_avg_sector_exposure"),
        "avg_sector_hhi": comparison.get("avg_sector_hhi"),
        "drawdown_peak_date": drawdown.get("peak_date"),
        "drawdown_trough_date": drawdown.get("trough_date"),
        "drawdown_recovery_date": drawdown.get("recovery_date"),
        "drawdown_period_count": drawdown.get("period_count"),
    }


def strategy_state(feature_set: str, alpha: Any) -> str:
    value = to_float(alpha)
    if feature_set == "alpha158_only":
        return "unstable_default_candidate" if pd.isna(value) or value <= 0 else "window_pass"
    return "candidate_branch" if pd.isna(value) or value <= 0 else "window_pass_candidate"


def read_strategy_row(record: dict[str, Any]) -> dict[str, Any]:
    path = record["paths"]["strategy_comparison_csv"]
    if not path.exists():
        return {}
    frame = pd.read_csv(path)
    selected = frame[frame["name"].eq(record["variant"])] if "name" in frame else pd.DataFrame()
    return selected.iloc[0].to_dict() if not selected.empty else {}


def build_drawdown_event(record: dict[str, Any]) -> dict[str, Any]:
    nav = pd.read_csv(record["nav_path"])
    if nav.empty or "nav" not in nav:
        return base_record(record)
    working = nav.copy()
    working["nav"] = pd.to_numeric(working["nav"], errors="coerce")
    working = working.dropna(subset=["nav"]).reset_index(drop=True)
    if working.empty:
        return base_record(record)
    running_max = working["nav"].cummax()
    drawdown = working["nav"] / running_max - 1.0
    trough_idx = int(drawdown.idxmin())
    peak_idx = int(working.loc[:trough_idx, "nav"].idxmax())
    peak_nav = float(working.loc[peak_idx, "nav"])
    recovery_idx = None
    for idx in range(trough_idx + 1, len(working)):
        if float(working.loc[idx, "nav"]) >= peak_nav:
            recovery_idx = idx
            break
    return {
        **base_record(record),
        "peak_date": working.loc[peak_idx, "signal_date"],
        "trough_date": working.loc[trough_idx, "signal_date"],
        "recovery_date": working.loc[recovery_idx, "signal_date"] if recovery_idx is not None else "",
        "max_drawdown": float(drawdown.iloc[trough_idx]),
        "peak_nav": peak_nav,
        "trough_nav": float(working.loc[trough_idx, "nav"]),
        "period_count": int(trough_idx - peak_idx + 1),
    }


def base_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "window_id": record["window_id"],
        "window_label": record["window_label"],
        "feature_set": record["feature_set"],
    }


def build_beta_exposure(record: dict[str, Any]) -> dict[str, Any]:
    benchmark = yaml.safe_load(record["benchmark_path"].read_text(encoding="utf-8")) or {}
    comparison = read_strategy_row(record)
    exposure = read_top_exposure(record)
    return {
        **base_record(record),
        "alpha_annualized": benchmark.get("alpha_annualized"),
        "beta": benchmark.get("beta"),
        "correlation": benchmark.get("correlation"),
        "relative_information_ratio": benchmark.get("relative_information_ratio"),
        "max_avg_sector": comparison.get("max_avg_sector"),
        "max_avg_sector_exposure": comparison.get("max_avg_sector_exposure"),
        "max_sector_weight_any_period": comparison.get("max_sector_weight_any_period"),
        "avg_sector_hhi": comparison.get("avg_sector_hhi"),
        "top_exposure_sector": exposure.get("sector"),
        "top_exposure_avg_weight": exposure.get("avg_weight"),
        "top_exposure_max_weight": exposure.get("max_weight"),
    }


def read_top_exposure(record: dict[str, Any]) -> dict[str, Any]:
    path = record["variant_dir"] / "exposure_by_sector.csv"
    if not path.exists():
        return {}
    frame = pd.read_csv(path)
    if frame.empty or "avg_weight" not in frame:
        return {}
    return frame.sort_values("avg_weight", ascending=False).iloc[0].to_dict()


def read_contribution_frame(record: dict[str, Any], level: str) -> pd.DataFrame:
    path = record["variant_dir"] / f"contribution_by_{level}.csv"
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    frame.insert(0, "feature_set", record["feature_set"])
    frame.insert(0, "window_label", record["window_label"])
    frame.insert(0, "window_id", record["window_id"])
    return frame


def build_edgar_delta_by_window(run_records: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    by_window: dict[str, dict[str, dict[str, Any]]] = {}
    for record in run_records:
        by_window.setdefault(record["window_id"], {})[record["feature_set"]] = record
    for window_id, group in by_window.items():
        alpha = group.get("alpha158_only")
        edgar = group.get("edgar_mini_core")
        if not alpha or not edgar:
            continue
        alpha_positions = read_variant_positions(alpha["run_dir"], alpha["variant"], "alpha158")
        edgar_positions = read_variant_positions(edgar["run_dir"], edgar["variant"], "edgar_mini_core")
        fundamentals = read_fundamentals(edgar["run_dir"] / "fundamental_features_cleaned.parquet")
        diff = attach_fundamentals(build_position_diff(alpha_positions, edgar_positions), fundamentals)
        rows.append(edgar_delta_row(window_id, alpha["window_label"], diff))
    return pd.DataFrame(rows)


def edgar_delta_row(window_id: str, window_label: str, diff: pd.DataFrame) -> dict[str, Any]:
    added = diff[diff["change_type"].eq("added_by_edgar")]
    removed = diff[diff["change_type"].eq("removed_by_edgar")]
    common = diff[diff["change_type"].eq("common")]
    row = {
        "window_id": window_id,
        "window_label": window_label,
        "added_rows": int(len(added)),
        "removed_rows": int(len(removed)),
        "common_rows": int(len(common)),
        "added_unique_symbols": int(added["symbol"].nunique()) if not added.empty else 0,
        "removed_unique_symbols": int(removed["symbol"].nunique()) if not removed.empty else 0,
        "added_edgar_net_contribution_sum": float(pd.to_numeric(added.get("net_contribution_edgar"), errors="coerce").sum(skipna=True)),
        "removed_alpha_net_contribution_sum": float(pd.to_numeric(removed.get("net_contribution_alpha"), errors="coerce").sum(skipna=True)),
        "common_net_contribution_delta_sum": float(pd.to_numeric(common.get("net_contribution_delta"), errors="coerce").sum(skipna=True)),
        "total_net_contribution_delta_sum": float(pd.to_numeric(diff.get("net_contribution_delta"), errors="coerce").sum(skipna=True)),
        "top3_added_positive_share": top_positive_share(added, "symbol"),
        "top_sector_added_positive_share": top_positive_share(added, "sector"),
        "top_period_added_positive_share": top_positive_share(added, "period"),
    }
    for column in MINI_CORE_COLUMNS:
        added_values = pd.to_numeric(added.get(column), errors="coerce")
        removed_values = pd.to_numeric(removed.get(column), errors="coerce")
        row[f"added_{column}_mean"] = safe_mean(added_values)
        row[f"removed_{column}_mean"] = safe_mean(removed_values)
        row[f"added_{column}_missing_rate"] = float(added_values.isna().mean()) if len(added_values) else math.nan
        row[f"removed_{column}_missing_rate"] = float(removed_values.isna().mean()) if len(removed_values) else math.nan
    return row


def top_positive_share(frame: pd.DataFrame, group_col: str) -> float:
    if frame.empty or group_col not in frame:
        return math.nan
    grouped = pd.to_numeric(frame.get("net_contribution_edgar"), errors="coerce").groupby(frame[group_col]).sum().clip(lower=0)
    total = float(grouped.sum())
    if total <= 0:
        return math.nan
    n = 3 if group_col == "symbol" else 1
    return float(grouped.sort_values(ascending=False).head(n).sum() / total)


def build_yaml_summary(failure: pd.DataFrame, edgar_delta: pd.DataFrame, stress: pd.DataFrame) -> dict[str, Any]:
    alpha = failure[failure["feature_set"].eq("alpha158_only")]
    edgar = failure[failure["feature_set"].eq("edgar_mini_core")]
    alpha_positive = int((pd.to_numeric(alpha["alpha_annualized"], errors="coerce") > 0).sum())
    edgar_positive = int((pd.to_numeric(edgar["alpha_annualized"], errors="coerce") > 0).sum())
    stress_50 = stress[pd.to_numeric(stress["cost_bps"], errors="coerce").eq(50)]
    stress_positive = int((pd.to_numeric(stress_50["alpha_annualized"], errors="coerce") > 0).sum())
    weakest = failure.sort_values("alpha_annualized", ascending=True).head(1)
    best_delta = edgar_delta.sort_values("total_net_contribution_delta_sum", ascending=False).head(1)
    return {
        "alpha158_positive_alpha_windows": alpha_positive,
        "edgar_positive_alpha_windows": edgar_positive,
        "sector_cap_2_50bps_positive_alpha_rows": stress_positive,
        "weakest_window": row_to_dict(weakest),
        "best_edgar_delta_window": row_to_dict(best_delta),
        "current_mainline_status": "unstable_default_candidate",
        "edgar_status": "candidate_branch",
        "next_priority": "复盘 2022-2023 的行业暴露、beta、持仓贡献和 drawdown 来源。",
    }


def write_report(
    path: Path,
    failure: pd.DataFrame,
    edgar_delta: pd.DataFrame,
    drawdown: pd.DataFrame,
    beta: pd.DataFrame,
    stress: pd.DataFrame,
    yaml_summary: dict[str, Any],
) -> None:
    lines = [
        "# CRSP Rolling Window Failure Review",
        "",
        "本报告复用 rolling window 的已完成 run，解释 `sector_cap_2_top10` 为什么跨窗口不稳定，并补齐 variant-level 压力测试。",
        "",
        "```yaml",
        yaml.safe_dump(yaml_summary, allow_unicode=True, sort_keys=False).strip(),
        "```",
        "",
        "## Failure Summary",
        "",
        dataframe_to_markdown(
            failure,
            [
                "window_label",
                "feature_set",
                "strategy_state",
                "annualized_return",
                "alpha_annualized",
                "beta",
                "max_drawdown",
                "stress_50bps_annualized_return",
            ],
        ),
        "",
        "## EDGAR Delta By Window",
        "",
        dataframe_to_markdown(
            edgar_delta,
            [
                "window_label",
                "added_rows",
                "removed_rows",
                "total_net_contribution_delta_sum",
                "top3_added_positive_share",
                "top_sector_added_positive_share",
            ],
        ),
        "",
        "## Drawdown Events",
        "",
        dataframe_to_markdown(drawdown, ["window_label", "feature_set", "peak_date", "trough_date", "recovery_date", "max_drawdown", "period_count"]),
        "",
        "## Beta And Exposure",
        "",
        dataframe_to_markdown(beta, ["window_label", "feature_set", "alpha_annualized", "beta", "top_exposure_sector", "top_exposure_avg_weight", "avg_sector_hhi"]),
        "",
        "## Sector Cap 2 Stress",
        "",
        dataframe_to_markdown(stress[stress["cost_bps"].eq(50.0)], ["window_label", "feature_set", "cost_bps", "annualized_return", "alpha_annualized", "max_drawdown"]),
        "",
        "## 结论",
        "",
        "- `Alpha158-only + sector_cap_2` 继续降级为 `unstable_default_candidate`。",
        "- `EDGAR mini-core + sector_cap_2` 保留为 `candidate_branch`，但不能直接替代默认主线。",
        "- `2022-2023` 是首要失效窗口，下一步应聚焦行业暴露、beta、回撤区间和单票贡献。",
        "",
        "结果是学习研究材料，不是投资建议。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def dataframe_to_markdown(frame: pd.DataFrame, columns: list[str], max_rows: int = 20) -> str:
    if frame.empty:
        return "N/A"
    selected = frame[[column for column in columns if column in frame.columns]].head(max_rows)
    if selected.empty:
        return "N/A"
    lines = [
        "| " + " | ".join(selected.columns) + " |",
        "| " + " | ".join(["---"] * len(selected.columns)) + " |",
    ]
    for _, row in selected.iterrows():
        lines.append("| " + " | ".join(format_cell(row[column]) for column in selected.columns) + " |")
    return "\n".join(lines)


def format_cell(value: Any) -> str:
    if pd.isna(value):
        return "N/A"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value).replace("|", "\\|")


def row_to_dict(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {}
    return {key: normalize(value) for key, value in frame.iloc[0].to_dict().items()}


def normalize(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    usable = [frame for frame in frames if not frame.empty]
    return pd.concat(usable, ignore_index=True) if usable else pd.DataFrame()


def safe_mean(values: pd.Series) -> float:
    return float(values.mean(skipna=True)) if len(values) and values.notna().any() else math.nan


def to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def main() -> None:
    args = parse_args()
    summary = run_crsp_rolling_window_failure_review(
        args.manifest,
        args.output_dir,
        variant=args.variant,
        refresh_rolling_summary=not args.skip_summary_refresh,
    )
    print(f"Failure review: {resolve_path(args.output_dir)}")
    print(yaml.safe_dump(summary, allow_unicode=True, sort_keys=False))


if __name__ == "__main__":
    main()
