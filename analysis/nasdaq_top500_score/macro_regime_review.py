"""Macro regime review for baseline vs macro experiments."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


REGIME_DAILY_COLUMNS = [
    "experiment",
    "period",
    "signal_date",
    "entry_date",
    "exit_date",
    "net_return",
    "benchmark_return",
    "excess_return",
]
REGIME_KEYS = [
    "vix_level",
    "vix_trend",
    "rate_level",
    "rate_trend",
    "curve_inversion",
    "credit_stress",
    "dollar_trend",
    "oil_trend",
]


@dataclass
class MacroRegimeReviewResult:
    daily_metrics: pd.DataFrame
    summary: pd.DataFrame
    strategy_comparison: pd.DataFrame
    sector_exposure: pd.DataFrame
    contribution_summary: pd.DataFrame
    yaml_summary: dict[str, Any]

    @classmethod
    def empty(cls, paths: dict[str, Path]) -> "MacroRegimeReviewResult":
        daily = pd.DataFrame(columns=REGIME_DAILY_COLUMNS)
        summary = pd.DataFrame()
        comparison = pd.DataFrame()
        exposure = pd.DataFrame()
        contribution = pd.DataFrame()
        yaml_summary = {"enabled": False}
        write_outputs(paths, daily, summary, comparison, exposure, contribution, yaml_summary)
        return cls(daily, summary, comparison, exposure, contribution, yaml_summary)


def run_macro_regime_review(config: dict[str, Any], paths: dict[str, Path]) -> MacroRegimeReviewResult:
    review_config = config.get("macro_regime_review", {})
    if not review_config.get("enabled", False):
        return MacroRegimeReviewResult.empty(paths)

    macro_features_path = resolve_path(review_config.get("macro_features_path"), paths["macro_features"])
    if not macro_features_path.exists():
        return empty_with_error(paths, f"missing macro_features_path: {macro_features_path}")

    experiments = review_config.get("experiments", default_experiments(paths))
    variant = str(review_config.get("variant", "sector_cap_2_top10"))
    macro_features = pd.read_parquet(macro_features_path)
    macro_daily = macro_features.groupby(level="datetime").first().sort_index()

    experiment_frames = []
    position_frames = []
    missing = []
    for experiment in experiments:
        name = str(experiment["name"])
        run_dir = resolve_path(experiment["run_dir"], paths["output_dir"])
        nav_path, positions_path = backtest_output_paths(run_dir, variant)
        if not nav_path.exists() or not positions_path.exists():
            missing.append(f"{name}: missing {variant} backtest outputs")
            continue
        nav = pd.read_csv(nav_path)
        nav["experiment"] = name
        positions = pd.read_csv(positions_path)
        positions["experiment"] = name
        experiment_frames.append(nav)
        position_frames.append(positions)

    if not experiment_frames:
        return empty_with_error(paths, "; ".join(missing) or "no experiment outputs")

    nav_all = pd.concat(experiment_frames, ignore_index=True)
    nav_all["signal_date"] = pd.to_datetime(nav_all["signal_date"], errors="coerce").dt.normalize()
    threshold_history = macro_daily[macro_daily.index < nav_all["signal_date"].min()]
    thresholds = build_thresholds(threshold_history)
    regimes = classify_regimes(macro_daily, thresholds)
    daily = nav_all.merge(regimes.reset_index().rename(columns={"datetime": "signal_date"}), on="signal_date", how="left")
    summary = summarize_by_regime(daily, config)
    comparison = compare_experiments(summary, review_config)
    positions_all = pd.concat(position_frames, ignore_index=True)
    positions_all["signal_date"] = pd.to_datetime(positions_all["signal_date"], errors="coerce").dt.normalize()
    positions_with_regimes = positions_all.merge(
        regimes.reset_index().rename(columns={"datetime": "signal_date"}), on="signal_date", how="left"
    )
    sector_exposure = summarize_sector_exposure(positions_with_regimes)
    contribution = summarize_contribution(positions_with_regimes)
    yaml_summary = build_yaml_summary(comparison, thresholds, missing, review_config)
    write_outputs(paths, daily, summary, comparison, sector_exposure, contribution, yaml_summary)
    return MacroRegimeReviewResult(daily, summary, comparison, sector_exposure, contribution, yaml_summary)


def default_experiments(paths: dict[str, Path]) -> list[dict[str, str]]:
    return [{"name": "current", "run_dir": str(paths["output_dir"])}]


def backtest_output_paths(run_dir: Path, variant: str) -> tuple[Path, Path]:
    if variant == "main_backtest":
        return run_dir / "backtest_nav.csv", run_dir / "backtest_positions.csv"
    variant_dir = run_dir / "strategy_comparison" / variant
    return variant_dir / "backtest_nav.csv", variant_dir / "backtest_positions.csv"


def resolve_path(value: Any, default: Path) -> Path:
    if value is None:
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else Path.cwd() / path


def build_thresholds(history: pd.DataFrame) -> dict[str, dict[str, float]]:
    thresholds = {}
    for key, column in {
        "vix_level": "macro_vix",
        "rate_level": "macro_dgs10",
        "credit_stress": "macro_baa10y_credit_spread",
    }.items():
        if column not in history.columns or history[column].dropna().empty:
            thresholds[key] = {"low": math.nan, "high": math.nan}
            continue
        thresholds[key] = {
            "low": float(history[column].quantile(0.30)),
            "high": float(history[column].quantile(0.70)),
        }
    return thresholds


def classify_regimes(macro_daily: pd.DataFrame, thresholds: dict[str, dict[str, float]]) -> pd.DataFrame:
    regimes = pd.DataFrame(index=macro_daily.index)
    regimes.index.name = "datetime"
    regimes["vix_level"] = ternary_level(macro_daily.get("macro_vix"), thresholds.get("vix_level", {}), "low_vix", "mid_vix", "high_vix")
    regimes["vix_trend"] = trend_label(macro_daily.get("macro_vix_change_20d"), "vix_rising", "vix_flat_or_falling")
    regimes["rate_level"] = ternary_level(
        macro_daily.get("macro_dgs10"), thresholds.get("rate_level", {}), "low_rate", "mid_rate", "high_rate"
    )
    regimes["rate_trend"] = trend_label(macro_daily.get("macro_dgs10_change_20d"), "rates_rising", "rates_flat_or_falling")
    regimes["curve_inversion"] = bool_label(
        macro_daily.get("macro_yield_curve_10y_2y_inverted"), "curve_inverted", "curve_not_inverted"
    )
    regimes["credit_stress"] = ternary_level(
        macro_daily.get("macro_baa10y_credit_spread"),
        thresholds.get("credit_stress", {}),
        "low_credit_stress",
        "mid_credit_stress",
        "high_credit_stress",
    )
    regimes["dollar_trend"] = trend_label(
        macro_daily.get("macro_broad_dollar_index_pct_change_20d"), "dollar_stronger", "dollar_flat_or_weaker"
    )
    regimes["oil_trend"] = trend_label(macro_daily.get("macro_wti_oil_pct_change_20d"), "oil_up", "oil_flat_or_down")
    return regimes


def ternary_level(series: pd.Series | None, thresholds: dict[str, float], low_label: str, mid_label: str, high_label: str) -> pd.Series:
    if series is None:
        return pd.Series("unknown", index=pd.Index([]))
    low = thresholds.get("low")
    high = thresholds.get("high")
    output = pd.Series(mid_label, index=series.index)
    if pd.notna(low):
        output[series <= low] = low_label
    if pd.notna(high):
        output[series >= high] = high_label
    output[series.isna()] = "unknown"
    return output


def trend_label(series: pd.Series | None, up_label: str, down_label: str) -> pd.Series:
    if series is None:
        return pd.Series("unknown", index=pd.Index([]))
    output = pd.Series(down_label, index=series.index)
    output[series > 0] = up_label
    output[series.isna()] = "unknown"
    return output


def bool_label(series: pd.Series | None, true_label: str, false_label: str) -> pd.Series:
    if series is None:
        return pd.Series("unknown", index=pd.Index([]))
    output = pd.Series(false_label, index=series.index)
    output[pd.to_numeric(series, errors="coerce") > 0] = true_label
    output[series.isna()] = "unknown"
    return output


def summarize_by_regime(daily: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for key in REGIME_KEYS:
        if key not in daily.columns:
            continue
        for (experiment, value), group in daily.groupby(["experiment", key], dropna=False):
            rows.append(summary_record(experiment, key, value, group, config))
    return pd.DataFrame(rows)


def summary_record(experiment: str, regime_key: str, regime_value: str, group: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    net = pd.to_numeric(group["net_return"], errors="coerce").dropna()
    benchmark = pd.to_numeric(group["benchmark_return"], errors="coerce") if "benchmark_return" in group else pd.Series(index=group.index, dtype=float)
    excess = pd.to_numeric(group["excess_return"], errors="coerce") if "excess_return" in group else pd.Series(index=group.index, dtype=float)
    periods_per_year = float(config.get("backtest", {}).get("periods_per_year", 252 / int(config.get("backtest", {}).get("rebalance_days", 5))))
    cumulative = float((1.0 + net).prod() - 1.0) if not net.empty else math.nan
    nav = (1.0 + net).cumprod() if not net.empty else pd.Series(dtype=float)
    drawdown = nav / nav.cummax() - 1.0 if not nav.empty else pd.Series(dtype=float)
    benchmark_valid = pd.concat([net.rename("strategy"), benchmark.rename("benchmark")], axis=1).dropna()
    beta = math.nan
    alpha = math.nan
    if len(benchmark_valid) > 1:
        variance = float(benchmark_valid["benchmark"].var(ddof=1))
        if not math.isclose(variance, 0.0):
            beta = float(benchmark_valid["strategy"].cov(benchmark_valid["benchmark"]) / variance)
            alpha = float((benchmark_valid["strategy"].mean() - beta * benchmark_valid["benchmark"].mean()) * periods_per_year)
    return {
        "experiment": experiment,
        "regime_key": regime_key,
        "regime_value": regime_value,
        "period_count": int(len(group)),
        "cumulative_return": cumulative,
        "annualized_return": float((1.0 + cumulative) ** (periods_per_year / len(net)) - 1.0) if len(net) else math.nan,
        "max_drawdown": float(drawdown.min()) if not drawdown.empty else math.nan,
        "avg_net_return": float(net.mean()) if len(net) else math.nan,
        "win_rate": float((net > 0).mean()) if len(net) else math.nan,
        "avg_excess_return": float(excess.mean()) if len(excess.dropna()) else math.nan,
        "cumulative_excess_return": float((1.0 + excess.dropna()).prod() - 1.0) if len(excess.dropna()) else math.nan,
        "beta": beta,
        "alpha_annualized": alpha,
    }


def compare_experiments(summary: pd.DataFrame, review_config: dict[str, Any]) -> pd.DataFrame:
    baseline_name = str(review_config.get("baseline_experiment", "baseline"))
    rows = []
    for (regime_key, regime_value), group in summary.groupby(["regime_key", "regime_value"], dropna=False):
        by_experiment = group.set_index("experiment")
        if baseline_name not in by_experiment.index:
            continue
        baseline = by_experiment.loc[baseline_name]
        for experiment_name, experiment in by_experiment.iterrows():
            if experiment_name == baseline_name:
                continue
            rows.append(
                {
                    "regime_key": regime_key,
                    "regime_value": regime_value,
                    "comparison_experiment": experiment_name,
                    "baseline_period_count": baseline["period_count"],
                    "comparison_period_count": experiment["period_count"],
                    "baseline_cumulative_return": baseline["cumulative_return"],
                    "comparison_cumulative_return": experiment["cumulative_return"],
                    "cumulative_return_diff": experiment["cumulative_return"] - baseline["cumulative_return"],
                    "baseline_annualized_return": baseline["annualized_return"],
                    "comparison_annualized_return": experiment["annualized_return"],
                    "annualized_return_diff": experiment["annualized_return"] - baseline["annualized_return"],
                    "baseline_max_drawdown": baseline["max_drawdown"],
                    "comparison_max_drawdown": experiment["max_drawdown"],
                    "max_drawdown_diff": experiment["max_drawdown"] - baseline["max_drawdown"],
                    "baseline_beta": baseline["beta"],
                    "comparison_beta": experiment["beta"],
                    "beta_diff": experiment["beta"] - baseline["beta"],
                    "baseline_alpha_annualized": baseline["alpha_annualized"],
                    "comparison_alpha_annualized": experiment["alpha_annualized"],
                    "alpha_annualized_diff": experiment["alpha_annualized"] - baseline["alpha_annualized"],
                }
            )
    return (
        pd.DataFrame(rows).sort_values(["comparison_experiment", "regime_key", "regime_value"]).reset_index(drop=True)
        if rows
        else pd.DataFrame()
    )


def summarize_sector_exposure(positions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key in REGIME_KEYS:
        if key not in positions.columns:
            continue
        group_cols = ["experiment", key, "sector"]
        grouped = positions.assign(sector=positions["sector"].fillna("UNKNOWN")).groupby(group_cols, dropna=False)
        frame = grouped.agg(
            position_count=("symbol", "count"),
            avg_weight=("weight", "mean"),
            gross_contribution_sum=("gross_contribution", "sum"),
            net_contribution_sum=("net_contribution", "sum"),
        ).reset_index()
        frame = frame.rename(columns={key: "regime_value"})
        frame["regime_key"] = key
        rows.append(frame)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def summarize_contribution(positions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key in REGIME_KEYS:
        if key not in positions.columns:
            continue
        grouped = positions.groupby(["experiment", key], dropna=False)
        frame = grouped.agg(
            position_count=("symbol", "count"),
            gross_contribution_sum=("gross_contribution", "sum"),
            net_contribution_sum=("net_contribution", "sum"),
            excess_contribution_sum=("excess_contribution", "sum"),
        ).reset_index()
        frame = frame.rename(columns={key: "regime_value"})
        frame["regime_key"] = key
        rows.append(frame)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def build_yaml_summary(
    comparison: pd.DataFrame,
    thresholds: dict[str, Any],
    missing: list[str],
    review_config: dict[str, Any],
) -> dict[str, Any]:
    if comparison.empty:
        return {"enabled": True, "thresholds": thresholds, "missing": missing, "insights": {}}
    min_periods = int(review_config.get("min_periods", 5))
    usable = comparison[
        (pd.to_numeric(comparison["baseline_period_count"], errors="coerce") >= min_periods)
        & (pd.to_numeric(comparison["comparison_period_count"], errors="coerce") >= min_periods)
    ]
    best = usable.sort_values("annualized_return_diff", ascending=False).head(5)
    worst = usable.sort_values("annualized_return_diff", ascending=True).head(5)
    beta = usable.sort_values("beta_diff", ascending=True).head(5)
    return {
        "enabled": True,
        "thresholds": thresholds,
        "missing": missing,
        "min_periods_for_insights": min_periods,
        "low_sample_comparison_rows": int(len(comparison) - len(usable)),
        "insights": {
            "best_regimes_vs_baseline": records(
                best,
                ["comparison_experiment", "regime_key", "regime_value", "annualized_return_diff", "alpha_annualized_diff"],
            ),
            "worst_regimes_vs_baseline": records(
                worst,
                ["comparison_experiment", "regime_key", "regime_value", "annualized_return_diff", "alpha_annualized_diff"],
            ),
            "largest_beta_reductions_vs_baseline": records(
                beta,
                ["comparison_experiment", "regime_key", "regime_value", "beta_diff", "max_drawdown_diff"],
            ),
        },
    }


def records(frame: pd.DataFrame, columns: list[str]) -> list[dict[str, Any]]:
    output = []
    for row in frame[columns].to_dict("records"):
        output.append({key: normalize(value) for key, value in row.items()})
    return output


def normalize(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (str, int, bool)):
        return value
    return float(value)


def write_outputs(
    paths: dict[str, Path],
    daily: pd.DataFrame,
    summary: pd.DataFrame,
    comparison: pd.DataFrame,
    exposure: pd.DataFrame,
    contribution: pd.DataFrame,
    yaml_summary: dict[str, Any],
) -> None:
    daily.to_csv(paths["macro_regime_daily_metrics"], index=False)
    summary.to_csv(paths["macro_regime_summary"], index=False)
    comparison.to_csv(paths["macro_regime_strategy_comparison"], index=False)
    exposure.to_csv(paths["macro_regime_sector_exposure"], index=False)
    contribution.to_csv(paths["macro_regime_contribution_summary"], index=False)
    paths["macro_regime_review_summary"].write_text(
        yaml.safe_dump(yaml_summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def empty_with_error(paths: dict[str, Path], error: str) -> MacroRegimeReviewResult:
    result = MacroRegimeReviewResult.empty(paths)
    result.yaml_summary.update({"enabled": True, "error": error})
    paths["macro_regime_review_summary"].write_text(
        yaml.safe_dump(result.yaml_summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return result
