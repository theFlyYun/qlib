"""Deep-dive review for the 2022-2023 CRSP rolling-window failure."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

try:  # pragma: no cover - supports direct script execution.
    from crsp_edgar_mini_core_position_diff import (
        MINI_CORE_COLUMNS,
        attach_fundamentals,
        build_position_diff,
        read_fundamentals,
        read_variant_positions,
    )
except ImportError:  # pragma: no cover
    from analysis.nasdaq_top500_score.crsp_edgar_mini_core_position_diff import (
        MINI_CORE_COLUMNS,
        attach_fundamentals,
        build_position_diff,
        read_fundamentals,
        read_variant_positions,
    )


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_ALPHA_RUN = Path("analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023/alpha158_only")
DEFAULT_EDGAR_RUN = Path("analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023/edgar_mini_core")
DEFAULT_OUTPUT_DIR = Path("analysis/nasdaq_top500_score/runs/crsp_rolling_windows/2022_2023_failure_deep_dive")
DEFAULT_VARIANT = "sector_cap_2_top10"
DEFAULT_LABEL_COLUMN = "label_10d_total_return"
ROLLING_BETA_WINDOW = 6


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alpha-run", type=Path, default=DEFAULT_ALPHA_RUN)
    parser.add_argument("--edgar-run", type=Path, default=DEFAULT_EDGAR_RUN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--variant", default=DEFAULT_VARIANT)
    parser.add_argument("--label-column", default=DEFAULT_LABEL_COLUMN)
    return parser.parse_args()


def resolve_path(path: str | Path) -> Path:
    value = Path(path).expanduser()
    return value if value.is_absolute() else WORKSPACE / value


def run_crsp_2022_2023_failure_deep_dive(
    alpha_run: Path = DEFAULT_ALPHA_RUN,
    edgar_run: Path = DEFAULT_EDGAR_RUN,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    variant: str = DEFAULT_VARIANT,
    label_column: str = DEFAULT_LABEL_COLUMN,
) -> dict[str, Any]:
    output = resolve_path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    records = [
        build_run_record(resolve_path(alpha_run), "alpha158_only", variant),
        build_run_record(resolve_path(edgar_run), "edgar_mini_core", variant),
    ]

    divergence_frames = []
    beta_frames = []
    drawdown_period_frames = []
    drawdown_summary_rows = []
    sector_frames = []
    industry_frames = []
    symbol_frames = []
    worst_examples = []

    for record in records:
        predictions = read_predictions(record["run_dir"] / "test_predictions.csv")
        labels = read_labels_for_predictions(record["run_dir"], predictions, label_column)
        positions = read_positions(record)
        nav = read_nav(record)

        divergence = build_ic_topk_divergence(predictions, labels, nav, positions, record["feature_set"])
        divergence_frames.append(divergence)

        beta = build_beta_by_period(nav, record["feature_set"])
        beta_frames.append(beta)

        event = identify_drawdown(nav, record["feature_set"])
        drawdown_summary_rows.append(event)
        drawdown_period_frames.append(build_drawdown_period_attribution(nav, positions, event, record["feature_set"]))

        for scope_name, scoped_positions in scoped_position_frames(positions, event):
            sector_frames.append(aggregate_position_contribution(scoped_positions, "sector", record["feature_set"], scope_name))
            industry_frames.append(aggregate_position_contribution(scoped_positions, "industry", record["feature_set"], scope_name))
            symbol_frames.append(aggregate_position_contribution(scoped_positions, "symbol", record["feature_set"], scope_name))
        worst_examples.append(build_worst_position_examples(positions, event, record["feature_set"]))

    edgar_delta, edgar_delta_by_sector = build_edgar_delta(records[0], records[1])

    divergence = concat_frames(divergence_frames)
    beta = concat_frames(beta_frames)
    drawdown_periods = concat_frames(drawdown_period_frames)
    drawdown_summary = pd.DataFrame(drawdown_summary_rows)
    sectors = concat_frames(sector_frames)
    industries = concat_frames(industry_frames)
    symbols = concat_frames(symbol_frames)
    worst = concat_frames(worst_examples)

    divergence_summary = build_divergence_summary(divergence)
    deep_dive_summary = build_deep_dive_summary(divergence_summary, drawdown_summary, sectors, symbols, edgar_delta)

    divergence.to_csv(output / "ic_topk_divergence_by_period.csv", index=False)
    (output / "ic_topk_divergence_summary.yaml").write_text(
        yaml.safe_dump(divergence_summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    beta.to_csv(output / "beta_by_period.csv", index=False)
    drawdown_periods.to_csv(output / "drawdown_period_attribution.csv", index=False)
    (output / "drawdown_summary.yaml").write_text(
        yaml.safe_dump(records_to_native(drawdown_summary), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    sectors.to_csv(output / "sector_failure_contribution.csv", index=False)
    industries.to_csv(output / "industry_failure_contribution.csv", index=False)
    symbols.to_csv(output / "symbol_failure_contribution.csv", index=False)
    worst.to_csv(output / "worst_position_examples.csv", index=False)
    edgar_delta.to_csv(output / "edgar_vs_alpha_2022_2023_delta.csv", index=False)
    edgar_delta_by_sector.to_csv(output / "edgar_delta_by_sector.csv", index=False)
    (output / "2022_2023_failure_deep_dive_summary.yaml").write_text(
        yaml.safe_dump(deep_dive_summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    write_report(
        output / "2022_2023_failure_deep_dive_report.md",
        deep_dive_summary,
        divergence,
        beta,
        drawdown_summary,
        sectors,
        symbols,
        edgar_delta_by_sector,
    )
    return deep_dive_summary


def build_run_record(run_dir: Path, feature_set: str, variant: str) -> dict[str, Any]:
    variant_dir = run_dir / "strategy_comparison" / variant
    return {
        "run_dir": run_dir,
        "feature_set": feature_set,
        "variant": variant,
        "variant_dir": variant_dir,
        "nav_path": variant_dir / "backtest_nav.csv",
        "positions_path": variant_dir / "backtest_positions.csv",
    }


def read_predictions(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    require_columns(frame, ["datetime", "instrument", "score"], path)
    frame = frame[["datetime", "instrument", "score"]].copy()
    frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce").dt.normalize()
    frame["instrument"] = frame["instrument"].astype(str).str.upper()
    frame["score"] = pd.to_numeric(frame["score"], errors="coerce")
    return frame.dropna(subset=["datetime", "instrument", "score"])


def read_labels_for_predictions(run_dir: Path, predictions: pd.DataFrame, label_column: str) -> pd.DataFrame:
    source_dir = find_source_dir(run_dir)
    dates = set(pd.to_datetime(predictions["datetime"]).dt.normalize())
    rows = []
    for instrument in sorted(predictions["instrument"].dropna().astype(str).str.upper().unique()):
        path = source_dir / f"{instrument}.csv"
        if not path.exists():
            continue
        try:
            frame = pd.read_csv(path, usecols=["date", "symbol", label_column])
        except ValueError:
            continue
        frame = frame.rename(columns={"date": "datetime", "symbol": "instrument", label_column: "label"})
        frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce").dt.normalize()
        frame = frame[frame["datetime"].isin(dates)]
        frame["instrument"] = frame["instrument"].astype(str).str.upper()
        frame["label"] = pd.to_numeric(frame["label"], errors="coerce")
        rows.append(frame[["datetime", "instrument", "label"]])
    if not rows:
        return pd.DataFrame(columns=["datetime", "instrument", "label"])
    return pd.concat(rows, ignore_index=True).dropna(subset=["datetime", "instrument", "label"])


def find_source_dir(run_dir: Path) -> Path:
    direct = run_dir / "qlib_source_csv"
    if direct.exists():
        return direct
    qlib_dir = run_dir / "qlib_data"
    if qlib_dir.exists():
        candidate = qlib_dir.resolve().parent / "qlib_source_csv"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Cannot locate qlib_source_csv for {run_dir}")


def read_positions(record: dict[str, Any]) -> pd.DataFrame:
    frame = pd.read_csv(record["positions_path"])
    require_columns(frame, ["period", "signal_date", "symbol", "sector", "industry", "score", "gross_return"], record["positions_path"])
    for column in ["signal_date", "entry_date", "exit_date"]:
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce").dt.normalize()
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    numeric_columns = [
        "period",
        "score",
        "weight",
        "gross_return",
        "net_return",
        "gross_contribution",
        "net_contribution",
        "benchmark_contribution",
        "excess_contribution",
    ]
    for column in numeric_columns:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def read_nav(record: dict[str, Any]) -> pd.DataFrame:
    frame = pd.read_csv(record["nav_path"])
    require_columns(frame, ["period", "signal_date", "gross_return", "net_return", "benchmark_return", "nav"], record["nav_path"])
    for column in ["signal_date", "entry_date", "exit_date"]:
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce").dt.normalize()
    for column in ["period", "gross_return", "net_return", "benchmark_return", "nav", "excess_return"]:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def build_ic_topk_divergence(
    predictions: pd.DataFrame,
    labels: pd.DataFrame,
    nav: pd.DataFrame,
    positions: pd.DataFrame,
    feature_set: str,
) -> pd.DataFrame:
    aligned = predictions.merge(labels, on=["datetime", "instrument"], how="inner").dropna(subset=["score", "label"])
    daily_rows = []
    for date, group in aligned.groupby("datetime"):
        daily_rows.append(
            {
                "signal_date": pd.Timestamp(date).normalize(),
                "candidate_count": int(len(group)),
                "ic": correlation(group["score"], group["label"], method="pearson"),
                "rank_ic": correlation(group["score"], group["label"], method="spearman"),
                "candidate_mean_label": safe_mean(group["label"]),
                "candidate_median_label": safe_median(group["label"]),
                "candidate_top_decile_label": top_quantile_mean(group, "score", "label", 0.1),
                "candidate_bottom_decile_label": bottom_quantile_mean(group, "score", "label", 0.1),
            }
        )
    daily = pd.DataFrame(daily_rows)
    period = nav[["period", "signal_date", "gross_return", "net_return", "benchmark_return", "excess_return"]].copy()
    period = period.rename(columns={"gross_return": "topk_gross_return", "net_return": "topk_net_return"})
    topk = positions.groupby("period", dropna=False).agg(
        topk_position_count=("symbol", "count"),
        topk_avg_position_return=("gross_return", "mean"),
        topk_win_rate=("gross_return", lambda value: float((pd.to_numeric(value, errors="coerce") > 0).mean())),
        topk_worst_position_return=("gross_return", "min"),
        topk_best_position_return=("gross_return", "max"),
    ).reset_index()
    merged = period.merge(daily, on="signal_date", how="left").merge(topk, on="period", how="left")
    merged["topk_minus_candidate_mean"] = merged["topk_gross_return"] - merged["candidate_mean_label"]
    merged["top_decile_minus_topk"] = merged["candidate_top_decile_label"] - merged["topk_gross_return"]
    merged["feature_set"] = feature_set
    merged["divergence_flag"] = merged.apply(classify_divergence, axis=1)
    ordered_columns = ["feature_set"] + [column for column in merged.columns if column != "feature_set"]
    return merged[ordered_columns]


def classify_divergence(row: pd.Series) -> str:
    ic = row.get("ic")
    rank_ic = row.get("rank_ic")
    topk = row.get("topk_gross_return")
    candidate = row.get("candidate_mean_label")
    if pd.notna(ic) and pd.notna(rank_ic) and ic > 0 and rank_ic > 0 and topk < 0:
        return "positive_ic_rank_ic_negative_topk"
    if pd.notna(ic) and ic > 0 and topk < 0:
        return "positive_ic_negative_topk"
    if pd.notna(rank_ic) and rank_ic > 0 and topk < 0:
        return "positive_rank_ic_negative_topk"
    if pd.notna(ic) and pd.notna(rank_ic) and ic < 0 and rank_ic < 0 and topk < 0:
        return "negative_ic_negative_topk"
    if pd.notna(candidate) and pd.notna(topk) and topk < candidate:
        return "topk_underperformed_candidate_mean"
    return "aligned_or_mixed"


def build_beta_by_period(nav: pd.DataFrame, feature_set: str, window: int = ROLLING_BETA_WINDOW) -> pd.DataFrame:
    frame = nav[["period", "signal_date", "gross_return", "net_return", "benchmark_return", "nav"]].copy()
    frame.insert(0, "feature_set", feature_set)
    strategy = frame["net_return"]
    benchmark = frame["benchmark_return"]
    frame["rolling_beta_6p"] = rolling_beta(strategy, benchmark, window)
    frame["rolling_corr_6p"] = strategy.rolling(window, min_periods=3).corr(benchmark)
    frame["benchmark_direction"] = frame["benchmark_return"].apply(lambda value: "up" if value > 0 else "down" if value < 0 else "flat")
    frame["up_capture_to_date"] = capture_ratio(frame, up=True)
    frame["down_capture_to_date"] = capture_ratio(frame, up=False)
    return frame


def rolling_beta(strategy: pd.Series, benchmark: pd.Series, window: int) -> pd.Series:
    values = []
    for index in range(len(strategy)):
        left = max(0, index - window + 1)
        s = strategy.iloc[left : index + 1]
        b = benchmark.iloc[left : index + 1]
        if len(s.dropna()) < 3 or float(b.var()) == 0.0:
            values.append(math.nan)
        else:
            values.append(float(s.cov(b) / b.var()))
    return pd.Series(values, index=strategy.index)


def capture_ratio(frame: pd.DataFrame, *, up: bool) -> pd.Series:
    values = []
    for index in range(len(frame)):
        history = frame.iloc[: index + 1]
        selected = history[history["benchmark_return"] > 0] if up else history[history["benchmark_return"] < 0]
        benchmark_sum = selected["benchmark_return"].sum()
        values.append(float(selected["net_return"].sum() / benchmark_sum) if len(selected) and benchmark_sum != 0 else math.nan)
    return pd.Series(values, index=frame.index)


def identify_drawdown(nav: pd.DataFrame, feature_set: str) -> dict[str, Any]:
    working = nav.dropna(subset=["nav"]).reset_index(drop=True).copy()
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
        "feature_set": feature_set,
        "peak_period": int(working.loc[peak_idx, "period"]),
        "trough_period": int(working.loc[trough_idx, "period"]),
        "peak_date": date_string(working.loc[peak_idx, "signal_date"]),
        "trough_date": date_string(working.loc[trough_idx, "signal_date"]),
        "recovery_date": date_string(working.loc[recovery_idx, "signal_date"]) if recovery_idx is not None else "",
        "max_drawdown": float(drawdown.iloc[trough_idx]),
        "peak_nav": peak_nav,
        "trough_nav": float(working.loc[trough_idx, "nav"]),
        "drawdown_period_count": int(trough_idx - peak_idx + 1),
    }


def build_drawdown_period_attribution(nav: pd.DataFrame, positions: pd.DataFrame, event: dict[str, Any], feature_set: str) -> pd.DataFrame:
    peak = int(event["peak_period"])
    trough = int(event["trough_period"])
    selected_nav = nav[(nav["period"] >= peak) & (nav["period"] <= trough)].copy()
    rows = []
    for _, period_row in selected_nav.iterrows():
        period = period_row["period"]
        period_positions = positions[positions["period"].eq(period)]
        worst = period_positions.sort_values("gross_return").head(1)
        sector_loss = (
            period_positions.groupby("sector", dropna=False)["net_contribution"]
            .sum()
            .sort_values()
            .head(1)
        )
        rows.append(
            {
                "feature_set": feature_set,
                "period": int(period),
                "signal_date": date_string(period_row["signal_date"]),
                "net_return": period_row.get("net_return"),
                "benchmark_return": period_row.get("benchmark_return"),
                "excess_return": period_row.get("excess_return"),
                "nav": period_row.get("nav"),
                "negative_position_count": int((period_positions["gross_return"] < 0).sum()),
                "position_count": int(len(period_positions)),
                "worst_symbol": worst.iloc[0]["symbol"] if not worst.empty else "",
                "worst_position_return": worst.iloc[0]["gross_return"] if not worst.empty else math.nan,
                "worst_sector": sector_loss.index[0] if len(sector_loss) else "",
                "worst_sector_net_contribution": float(sector_loss.iloc[0]) if len(sector_loss) else math.nan,
            }
        )
    return pd.DataFrame(rows)


def scoped_position_frames(positions: pd.DataFrame, event: dict[str, Any]) -> list[tuple[str, pd.DataFrame]]:
    peak = int(event["peak_period"])
    trough = int(event["trough_period"])
    drawdown = positions[(positions["period"] >= peak) & (positions["period"] <= trough)].copy()
    return [("full_window", positions.copy()), ("max_drawdown", drawdown)]


def aggregate_position_contribution(frame: pd.DataFrame, group_col: str, feature_set: str, scope: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    working = frame.copy()
    working[group_col] = working[group_col].fillna("UNKNOWN").astype(str)
    grouped = working.groupby(group_col, dropna=False)
    result = grouped.agg(
        holding_count=("symbol", "count"),
        period_count=("period", "nunique"),
        avg_weight=("weight", "mean"),
        avg_score=("score", "mean"),
        avg_gross_return=("gross_return", "mean"),
        win_rate=("gross_return", lambda value: float((pd.to_numeric(value, errors="coerce") > 0).mean())),
        gross_contribution_sum=("gross_contribution", "sum"),
        net_contribution_sum=("net_contribution", "sum"),
        benchmark_contribution_sum=("benchmark_contribution", "sum"),
        excess_contribution_sum=("excess_contribution", "sum"),
        worst_single_position_return=("gross_return", "min"),
        best_single_position_return=("gross_return", "max"),
    ).reset_index().rename(columns={group_col: "group"})
    result.insert(0, "group_level", group_col)
    result.insert(0, "scope", scope)
    result.insert(0, "feature_set", feature_set)
    return result.sort_values("net_contribution_sum").reset_index(drop=True)


def build_worst_position_examples(positions: pd.DataFrame, event: dict[str, Any], feature_set: str, limit: int = 50) -> pd.DataFrame:
    peak = int(event["peak_period"])
    trough = int(event["trough_period"])
    frame = positions.copy()
    frame["feature_set"] = feature_set
    frame["in_max_drawdown"] = frame["period"].between(peak, trough)
    columns = [
        "feature_set",
        "in_max_drawdown",
        "period",
        "signal_date",
        "entry_date",
        "exit_date",
        "symbol",
        "selected_rank",
        "sector",
        "industry",
        "history_bucket",
        "score",
        "gross_return",
        "net_contribution",
        "excess_contribution",
    ]
    available = [column for column in columns if column in frame]
    return frame.sort_values("gross_return").head(limit)[available].reset_index(drop=True)


def build_edgar_delta(alpha_record: dict[str, Any], edgar_record: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    alpha_positions = read_variant_positions(alpha_record["run_dir"], alpha_record["variant"], "alpha158")
    edgar_positions = read_variant_positions(edgar_record["run_dir"], edgar_record["variant"], "edgar_mini_core")
    fundamentals = read_fundamentals(edgar_record["run_dir"] / "fundamental_features_cleaned.parquet")
    diff = attach_fundamentals(build_position_diff(alpha_positions, edgar_positions), fundamentals)
    sector = aggregate_edgar_delta(diff, "sector")
    return diff, sector


def aggregate_edgar_delta(diff: pd.DataFrame, group_col: str) -> pd.DataFrame:
    working = diff.copy()
    working[group_col] = working[group_col].fillna("UNKNOWN").astype(str)
    grouped = working.groupby(group_col, dropna=False)
    frame = grouped.agg(
        row_count=("symbol", "size"),
        added_rows=("change_type", lambda value: int(value.eq("added_by_edgar").sum())),
        removed_rows=("change_type", lambda value: int(value.eq("removed_by_edgar").sum())),
        common_rows=("change_type", lambda value: int(value.eq("common").sum())),
        edgar_net_contribution_sum=("net_contribution_edgar", "sum"),
        alpha_net_contribution_sum=("net_contribution_alpha", "sum"),
        net_contribution_delta_sum=("net_contribution_delta", "sum"),
        avg_gross_return_delta=("gross_return_delta", "mean"),
    ).reset_index().rename(columns={group_col: "group"})
    frame.insert(0, "group_level", group_col)
    return frame.sort_values("net_contribution_delta_sum").reset_index(drop=True)


def build_divergence_summary(divergence: pd.DataFrame) -> dict[str, Any]:
    rows = {}
    for feature_set, group in divergence.groupby("feature_set"):
        flags = group["divergence_flag"].value_counts(dropna=False).to_dict()
        rows[str(feature_set)] = {
            "period_count": int(len(group)),
            "ic_mean": safe_mean(group["ic"]),
            "rank_ic_mean": safe_mean(group["rank_ic"]),
            "topk_gross_return_mean": safe_mean(group["topk_gross_return"]),
            "candidate_mean_label_mean": safe_mean(group["candidate_mean_label"]),
            "topk_minus_candidate_mean": safe_mean(group["topk_minus_candidate_mean"]),
            "positive_ic_negative_topk_periods": int(
                group["divergence_flag"].isin(["positive_ic_rank_ic_negative_topk", "positive_ic_negative_topk"]).sum()
            ),
            "topk_underperformed_candidate_periods": int((group["topk_minus_candidate_mean"] < 0).sum()),
            "flags": {str(key): int(value) for key, value in flags.items()},
        }
    return rows


def build_deep_dive_summary(
    divergence_summary: dict[str, Any],
    drawdown_summary: pd.DataFrame,
    sectors: pd.DataFrame,
    symbols: pd.DataFrame,
    edgar_delta: pd.DataFrame,
) -> dict[str, Any]:
    alpha_drawdown = select_record(drawdown_summary, "alpha158_only")
    edgar_drawdown = select_record(drawdown_summary, "edgar_mini_core")
    alpha_worst_sector = worst_group(sectors, "alpha158_only", "max_drawdown")
    edgar_worst_sector = worst_group(sectors, "edgar_mini_core", "max_drawdown")
    alpha_worst_symbol = worst_group(symbols, "alpha158_only", "max_drawdown")
    edgar_worst_symbol = worst_group(symbols, "edgar_mini_core", "max_drawdown")
    added = edgar_delta[edgar_delta["change_type"].eq("added_by_edgar")]
    removed = edgar_delta[edgar_delta["change_type"].eq("removed_by_edgar")]
    edgar_delta_sum = float(pd.to_numeric(edgar_delta.get("net_contribution_delta"), errors="coerce").sum(skipna=True))
    return {
        "window": "2022-2023",
        "main_question": "弱正 IC 为什么没有转化为 sector_cap_2 Top10 收益",
        "divergence": divergence_summary,
        "drawdown": {
            "alpha158_only": alpha_drawdown,
            "edgar_mini_core": edgar_drawdown,
        },
        "worst_groups_in_drawdown": {
            "alpha158_sector": alpha_worst_sector,
            "edgar_sector": edgar_worst_sector,
            "alpha158_symbol": alpha_worst_symbol,
            "edgar_symbol": edgar_worst_symbol,
        },
        "edgar_delta": {
            "added_rows": int(len(added)),
            "removed_rows": int(len(removed)),
            "total_net_contribution_delta_sum": edgar_delta_sum,
            "added_edgar_net_contribution_sum": float(pd.to_numeric(added.get("net_contribution_edgar"), errors="coerce").sum(skipna=True)),
            "removed_alpha_net_contribution_sum": float(pd.to_numeric(removed.get("net_contribution_alpha"), errors="coerce").sum(skipna=True)),
        },
        "decision": {
            "model_signal_status": "weak_positive_ic",
            "topk_status": "failed_conversion",
            "next_priority": "先改组合构建和风险过滤，再考虑新增特征。",
        },
    }


def select_record(frame: pd.DataFrame, feature_set: str) -> dict[str, Any]:
    selected = frame[frame["feature_set"].eq(feature_set)]
    return row_to_native(selected.iloc[0].to_dict()) if not selected.empty else {}


def worst_group(frame: pd.DataFrame, feature_set: str, scope: str) -> dict[str, Any]:
    selected = frame[frame["feature_set"].eq(feature_set) & frame["scope"].eq(scope)]
    if selected.empty:
        return {}
    return row_to_native(selected.sort_values("net_contribution_sum").iloc[0].to_dict())


def write_report(
    path: Path,
    summary: dict[str, Any],
    divergence: pd.DataFrame,
    beta: pd.DataFrame,
    drawdown_summary: pd.DataFrame,
    sectors: pd.DataFrame,
    symbols: pd.DataFrame,
    edgar_delta_by_sector: pd.DataFrame,
) -> None:
    lines = [
        "# CRSP 2022-2023 Failure Deep Dive",
        "",
        "本报告只复用已完成 rolling run，不重新训练模型。目标是解释 2022-2023 为什么出现弱正 IC 但 sector_cap_2 Top10 亏损。",
        "",
        "```yaml",
        yaml.safe_dump(summary, allow_unicode=True, sort_keys=False).strip(),
        "```",
        "",
        "## IC / TopK 背离",
        "",
        dataframe_to_markdown(
            divergence[
                [
                    "feature_set",
                    "period",
                    "signal_date",
                    "ic",
                    "rank_ic",
                    "topk_gross_return",
                    "candidate_mean_label",
                    "topk_minus_candidate_mean",
                    "divergence_flag",
                ]
            ].head(20)
        ),
        "",
        "## Drawdown Summary",
        "",
        dataframe_to_markdown(drawdown_summary),
        "",
        "## Beta By Period",
        "",
        dataframe_to_markdown(beta.tail(20)),
        "",
        "## Worst Sectors In Drawdown",
        "",
        dataframe_to_markdown(
            sectors[sectors["scope"].eq("max_drawdown")].sort_values("net_contribution_sum").head(20)
        ),
        "",
        "## Worst Symbols In Drawdown",
        "",
        dataframe_to_markdown(
            symbols[symbols["scope"].eq("max_drawdown")].sort_values("net_contribution_sum").head(20)
        ),
        "",
        "## EDGAR Delta By Sector",
        "",
        dataframe_to_markdown(edgar_delta_by_sector.head(20)),
        "",
        "## 结论",
        "",
        "- 2022-2023 不是模型完全无信号，而是弱正 IC 没有稳定转化成 Top10 组合收益。",
        "- 下一步优先检查组合构建、风险过滤、beta 控制和持仓集中，而不是继续堆新特征。",
        "- 结果是学习研究材料，不是投资建议。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def require_columns(frame: pd.DataFrame, columns: list[str], path: Path) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{path} missing column(s): {', '.join(missing)}")


def correlation(left: pd.Series, right: pd.Series, *, method: str) -> float:
    values = pd.concat([pd.to_numeric(left, errors="coerce"), pd.to_numeric(right, errors="coerce")], axis=1).dropna()
    if len(values) < 2 or values.iloc[:, 0].nunique() < 2 or values.iloc[:, 1].nunique() < 2:
        return math.nan
    return float(values.iloc[:, 0].corr(values.iloc[:, 1], method=method))


def top_quantile_mean(frame: pd.DataFrame, sort_col: str, value_col: str, fraction: float) -> float:
    if frame.empty:
        return math.nan
    n = max(1, int(math.ceil(len(frame) * fraction)))
    return safe_mean(frame.sort_values(sort_col, ascending=False).head(n)[value_col])


def bottom_quantile_mean(frame: pd.DataFrame, sort_col: str, value_col: str, fraction: float) -> float:
    if frame.empty:
        return math.nan
    n = max(1, int(math.ceil(len(frame) * fraction)))
    return safe_mean(frame.sort_values(sort_col, ascending=False).tail(n)[value_col])


def safe_mean(values: Any) -> float:
    series = pd.to_numeric(values, errors="coerce")
    return float(series.mean(skipna=True)) if series.notna().any() else math.nan


def safe_median(values: Any) -> float:
    series = pd.to_numeric(values, errors="coerce")
    return float(series.median(skipna=True)) if series.notna().any() else math.nan


def date_string(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return pd.Timestamp(value).date().isoformat()


def concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    usable = [frame for frame in frames if not frame.empty]
    return pd.concat(usable, ignore_index=True) if usable else pd.DataFrame()


def dataframe_to_markdown(frame: pd.DataFrame, max_rows: int = 20) -> str:
    if frame.empty:
        return "N/A"
    clipped = frame.head(max_rows).copy()
    columns = [str(column) for column in clipped.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in clipped.iterrows():
        values = [format_cell(row[column]) for column in clipped.columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def format_cell(value: Any) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value).replace("|", "\\|")


def records_to_native(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [row_to_native(record) for record in frame.to_dict("records")]


def row_to_native(record: dict[str, Any]) -> dict[str, Any]:
    output = {}
    for key, value in record.items():
        if isinstance(value, pd.Timestamp):
            output[key] = date_string(value)
        elif isinstance(value, float) and math.isnan(value):
            output[key] = None
        elif hasattr(value, "item"):
            output[key] = value.item()
        else:
            output[key] = value
    return output


def main() -> None:
    args = parse_args()
    summary = run_crsp_2022_2023_failure_deep_dive(
        args.alpha_run,
        args.edgar_run,
        args.output_dir,
        variant=args.variant,
        label_column=args.label_column,
    )
    print(f"2022-2023 failure deep dive: {resolve_path(args.output_dir)}")
    print(yaml.safe_dump(summary["decision"], allow_unicode=True, sort_keys=False))


if __name__ == "__main__":
    main()
