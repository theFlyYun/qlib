"""Review position differences between Alpha158 and EDGAR mini-core sector-capped portfolios."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_ALPHA_RUN = Path(
    "analysis/nasdaq_top500_score/runs/crsp_alpha158_industry_strategy_comparison_10d_conservative_2010_2025"
)
DEFAULT_EDGAR_RUN = Path(
    "analysis/nasdaq_top500_score/runs/crsp_alpha158_edgar_mini_core_10d_conservative_2010_2025"
)
DEFAULT_OUTPUT_DIR = Path("analysis/nasdaq_top500_score/runs/crsp_edgar_mini_core_position_diff_review")
DEFAULT_VARIANT = "sector_cap_2_top10"
MINI_CORE_COLUMNS = [
    "edgar_operating_margin",
    "edgar_free_cash_flow_ttm",
    "edgar_net_margin",
    "edgar_fcf_margin",
    "edgar_operating_cash_flow_ttm",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alpha-run", type=Path, default=DEFAULT_ALPHA_RUN)
    parser.add_argument("--edgar-run", type=Path, default=DEFAULT_EDGAR_RUN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--variant", default=DEFAULT_VARIANT)
    return parser.parse_args()


def resolve_path(path: str | Path) -> Path:
    value = Path(path).expanduser()
    return value if value.is_absolute() else WORKSPACE / value


def run_crsp_edgar_mini_core_position_diff(
    alpha_run: Path = DEFAULT_ALPHA_RUN,
    edgar_run: Path = DEFAULT_EDGAR_RUN,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    variant: str = DEFAULT_VARIANT,
) -> dict[str, Any]:
    alpha_dir = resolve_path(alpha_run)
    edgar_dir = resolve_path(edgar_run)
    output = resolve_path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    alpha_positions = read_variant_positions(alpha_dir, variant, "alpha158")
    edgar_positions = read_variant_positions(edgar_dir, variant, "edgar_mini_core")
    fundamentals = read_fundamentals(edgar_dir / "fundamental_features_cleaned.parquet")

    position_diff = build_position_diff(alpha_positions, edgar_positions)
    position_diff = attach_fundamentals(position_diff, fundamentals)
    added_removed = summarize_added_removed(position_diff)
    contribution = summarize_contribution_diff(position_diff)
    fundamental_diff = summarize_fundamental_diff(position_diff)
    yaml_summary = build_summary(position_diff, added_removed, contribution, fundamental_diff, alpha_dir, edgar_dir, variant)

    position_diff.to_csv(output / "edgar_mini_core_position_diff.csv", index=False)
    added_removed.to_csv(output / "edgar_mini_core_added_removed_summary.csv", index=False)
    contribution.to_csv(output / "edgar_mini_core_contribution_diff.csv", index=False)
    fundamental_diff.to_csv(output / "edgar_mini_core_fundamental_diff.csv", index=False)
    (output / "edgar_mini_core_position_diff_summary.yaml").write_text(
        yaml.safe_dump(yaml_summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    write_report(output / "report.md", yaml_summary, added_removed, contribution, fundamental_diff)
    return yaml_summary


def read_variant_positions(run_dir: Path, variant: str, source: str) -> pd.DataFrame:
    candidates = [
        run_dir / "strategy_comparison" / variant / "backtest_positions.csv",
        run_dir / "backtest_positions.csv",
    ]
    for path in candidates:
        if path.exists():
            frame = pd.read_csv(path)
            frame["source"] = source
            frame["signal_date"] = pd.to_datetime(frame["signal_date"], errors="coerce").dt.normalize()
            return frame
    raise FileNotFoundError(f"Missing backtest_positions.csv for {source}: {run_dir}")


def read_fundamentals(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["signal_date", "symbol", *MINI_CORE_COLUMNS])
    frame = pd.read_parquet(path, columns=[column for column in MINI_CORE_COLUMNS])
    frame = frame.reset_index().rename(columns={"datetime": "signal_date", "instrument": "symbol"})
    frame["signal_date"] = pd.to_datetime(frame["signal_date"], errors="coerce").dt.normalize()
    return frame


def build_position_diff(alpha_positions: pd.DataFrame, edgar_positions: pd.DataFrame) -> pd.DataFrame:
    alpha_keys = position_key_frame(alpha_positions, "alpha")
    edgar_keys = position_key_frame(edgar_positions, "edgar")
    merged = alpha_keys.merge(edgar_keys, on=["period", "signal_date", "symbol"], how="outer", suffixes=("_alpha", "_edgar"))
    merged["change_type"] = merged.apply(classify_change, axis=1)
    merged["sector"] = merged["sector_edgar"].combine_first(merged["sector_alpha"])
    merged["industry"] = merged["industry_edgar"].combine_first(merged["industry_alpha"])
    merged["history_bucket"] = merged["history_bucket_edgar"].combine_first(merged["history_bucket_alpha"])
    for column in ["net_contribution", "gross_contribution", "excess_contribution", "gross_return", "score"]:
        merged[f"{column}_delta"] = numeric(merged.get(f"{column}_edgar")).fillna(0.0) - numeric(
            merged.get(f"{column}_alpha")
        ).fillna(0.0)
    return merged.sort_values(["period", "change_type", "symbol"]).reset_index(drop=True)


def position_key_frame(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    columns = [
        "period",
        "signal_date",
        "symbol",
        "selected_rank",
        "sector",
        "industry",
        "history_bucket",
        "score",
        "weight",
        "gross_return",
        "net_return",
        "gross_contribution",
        "net_contribution",
        "excess_contribution",
    ]
    available = [column for column in columns if column in frame.columns]
    output = frame[available].copy()
    return output.rename(columns={column: f"{column}_{label}" for column in available if column not in {"period", "signal_date", "symbol"}})


def classify_change(row: pd.Series) -> str:
    in_alpha = not pd.isna(row.get("selected_rank_alpha"))
    in_edgar = not pd.isna(row.get("selected_rank_edgar"))
    if in_alpha and in_edgar:
        return "common"
    if in_edgar:
        return "added_by_edgar"
    return "removed_by_edgar"


def attach_fundamentals(position_diff: pd.DataFrame, fundamentals: pd.DataFrame) -> pd.DataFrame:
    if fundamentals.empty:
        for column in MINI_CORE_COLUMNS:
            position_diff[column] = math.nan
        return position_diff
    return position_diff.merge(
        fundamentals,
        on=["signal_date", "symbol"],
        how="left",
    )


def summarize_added_removed(position_diff: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for change_type, group in position_diff.groupby("change_type", dropna=False):
        rows.append(summary_row(group, "change_type", change_type))
    for keys, group in position_diff.groupby(["change_type", "sector"], dropna=False):
        rows.append(summary_row(group, "change_type_sector", "|".join(map(str, keys))))
    for keys, group in position_diff.groupby(["change_type", "history_bucket"], dropna=False):
        rows.append(summary_row(group, "change_type_history_bucket", "|".join(map(str, keys))))
    return pd.DataFrame(rows).sort_values(["group_level", "net_contribution_delta_sum"], ascending=[True, False])


def summary_row(group: pd.DataFrame, level: str, name: str) -> dict[str, Any]:
    edgar_contribution = numeric(group.get("net_contribution_edgar")).sum(skipna=True)
    alpha_contribution = numeric(group.get("net_contribution_alpha")).sum(skipna=True)
    delta = numeric(group.get("net_contribution_delta")).sum(skipna=True)
    return {
        "group_level": level,
        "group": name,
        "row_count": int(len(group)),
        "unique_symbols": int(group["symbol"].nunique()),
        "edgar_net_contribution_sum": float(edgar_contribution),
        "alpha_net_contribution_sum": float(alpha_contribution),
        "net_contribution_delta_sum": float(delta),
        "edgar_avg_gross_return": numeric(group.get("gross_return_edgar")).mean(skipna=True),
        "alpha_avg_gross_return": numeric(group.get("gross_return_alpha")).mean(skipna=True),
        "win_rate_edgar": win_rate(group.get("gross_return_edgar")),
        "win_rate_alpha": win_rate(group.get("gross_return_alpha")),
    }


def summarize_contribution_diff(position_diff: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for group_cols in [["symbol"], ["sector"], ["industry"]]:
        working = position_diff.copy()
        for column in group_cols:
            working[column] = working[column].fillna("UNKNOWN")
        grouped = working.groupby(group_cols, dropna=False)
        frame = grouped.agg(
            row_count=("symbol", "size"),
            edgar_holding_count=("selected_rank_edgar", lambda value: int(value.notna().sum())),
            alpha_holding_count=("selected_rank_alpha", lambda value: int(value.notna().sum())),
            edgar_net_contribution_sum=("net_contribution_edgar", "sum"),
            alpha_net_contribution_sum=("net_contribution_alpha", "sum"),
            net_contribution_delta_sum=("net_contribution_delta", "sum"),
        ).reset_index()
        frame.insert(0, "group_level", "_".join(group_cols))
        frame["group"] = frame[group_cols].astype(str).agg("|".join, axis=1)
        frames.append(frame.drop(columns=group_cols))
    return pd.concat(frames, ignore_index=True).sort_values("net_contribution_delta_sum", ascending=False)


def summarize_fundamental_diff(position_diff: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for change_type, group in position_diff.groupby("change_type", dropna=False):
        for column in MINI_CORE_COLUMNS:
            values = numeric(group.get(column))
            rows.append(
                {
                    "change_type": change_type,
                    "feature": column,
                    "count": int(values.notna().sum()),
                    "missing_rate": float(values.isna().mean()) if len(values) else math.nan,
                    "mean": float(values.mean(skipna=True)) if values.notna().any() else math.nan,
                    "median": float(values.median(skipna=True)) if values.notna().any() else math.nan,
                }
            )
    return pd.DataFrame(rows)


def build_summary(
    position_diff: pd.DataFrame,
    added_removed: pd.DataFrame,
    contribution: pd.DataFrame,
    fundamental_diff: pd.DataFrame,
    alpha_dir: Path,
    edgar_dir: Path,
    variant: str,
) -> dict[str, Any]:
    added = position_diff[position_diff["change_type"].eq("added_by_edgar")]
    removed = position_diff[position_diff["change_type"].eq("removed_by_edgar")]
    total_added_positive = float(numeric(added["net_contribution_edgar"]).clip(lower=0).sum())
    top3_added_positive = float(
        added.groupby("symbol")["net_contribution_edgar"].sum().clip(lower=0).sort_values(ascending=False).head(3).sum()
    )
    sector_positive = added.groupby("sector")["net_contribution_edgar"].sum().clip(lower=0).sort_values(ascending=False)
    top_sector_positive = float(sector_positive.iloc[0]) if len(sector_positive) else 0.0
    flags = risk_flags(position_diff, total_added_positive, top3_added_positive, top_sector_positive, fundamental_diff)
    return {
        "variant": variant,
        "alpha_run": str(alpha_dir),
        "edgar_run": str(edgar_dir),
        "period_count": int(position_diff["period"].nunique()),
        "changed_position_rows": int(len(added) + len(removed)),
        "common_position_rows": int(position_diff["change_type"].eq("common").sum()),
        "added_unique_symbols": int(added["symbol"].nunique()),
        "removed_unique_symbols": int(removed["symbol"].nunique()),
        "added_edgar_net_contribution_sum": float(numeric(added["net_contribution_edgar"]).sum(skipna=True)),
        "removed_alpha_net_contribution_sum": float(numeric(removed["net_contribution_alpha"]).sum(skipna=True)),
        "common_net_contribution_delta_sum": float(
            numeric(position_diff.loc[position_diff["change_type"].eq("common"), "net_contribution_delta"]).sum(skipna=True)
        ),
        "top3_added_positive_share": top3_added_positive / total_added_positive if total_added_positive > 0 else math.nan,
        "top_added_sector_positive_share": top_sector_positive / total_added_positive if total_added_positive > 0 else math.nan,
        "risk_flags": flags,
        "conclusion": conclusion(flags),
    }


def risk_flags(
    position_diff: pd.DataFrame,
    total_added_positive: float,
    top3_added_positive: float,
    top_sector_positive: float,
    fundamental_diff: pd.DataFrame,
) -> list[str]:
    flags = []
    if total_added_positive > 0 and top3_added_positive / total_added_positive > 0.5:
        flags.append("concentrated_contribution")
    if total_added_positive > 0 and top_sector_positive / total_added_positive > 0.5:
        flags.append("sector_concentrated")
    added_missing = fundamental_diff[fundamental_diff["change_type"].eq("added_by_edgar")]["missing_rate"]
    if not added_missing.empty and float(added_missing.mean()) > 0.5:
        flags.append("weak_fundamental_explanation")
    period_contribution = (
        position_diff[position_diff["change_type"].eq("added_by_edgar")]
        .groupby("period")["net_contribution_edgar"]
        .sum()
        .clip(lower=0)
        .sort_values(ascending=False)
    )
    if period_contribution.sum() > 0 and period_contribution.head(2).sum() / period_contribution.sum() > 0.5:
        flags.append("period_concentrated")
    return flags


def conclusion(flags: list[str]) -> str:
    if not flags:
        return "EDGAR mini-core 的持仓替换相对分散，可继续作为研究分支。"
    return "EDGAR mini-core 的改善存在集中或解释不足风险，暂不进入默认主线。"


def write_report(
    path: Path,
    summary: dict[str, Any],
    added_removed: pd.DataFrame,
    contribution: pd.DataFrame,
    fundamental_diff: pd.DataFrame,
) -> None:
    top_contribution = contribution[contribution["group_level"].eq("symbol")].head(10)
    lines = [
        "# CRSP EDGAR Mini-Core Position Difference Review",
        "",
        "本报告比较 Alpha158-only 与 EDGAR mini-core 在 `sector_cap_2_top10` 下的持仓差异。",
        "",
        "```yaml",
        yaml.safe_dump(summary, allow_unicode=True, sort_keys=False).strip(),
        "```",
        "",
        "## 关键贡献差异",
        "",
        dataframe_to_markdown(top_contribution),
        "",
        "## 新增 / 移除汇总",
        "",
        dataframe_to_markdown(added_removed[added_removed["group_level"].eq("change_type")]),
        "",
        "## Mini-Core 财报字段差异",
        "",
        dataframe_to_markdown(fundamental_diff),
        "",
        "## 结论",
        "",
        summary["conclusion"],
        "",
        "结果是学习研究材料，不是投资建议。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    if pd.isna(value):
        return "N/A"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value).replace("|", "\\|")


def numeric(values: Any) -> pd.Series:
    if values is None:
        return pd.Series(dtype="float64")
    return pd.to_numeric(values, errors="coerce")


def win_rate(values: Any) -> float:
    series = numeric(values)
    valid = series.dropna()
    return float((valid > 0).mean()) if len(valid) else math.nan


def main() -> None:
    args = parse_args()
    summary = run_crsp_edgar_mini_core_position_diff(
        args.alpha_run,
        args.edgar_run,
        args.output_dir,
        variant=args.variant,
    )
    print(f"Position diff review: {resolve_path(args.output_dir)}")
    print(yaml.safe_dump({"conclusion": summary["conclusion"], "risk_flags": summary["risk_flags"]}, allow_unicode=True))


if __name__ == "__main__":
    main()
