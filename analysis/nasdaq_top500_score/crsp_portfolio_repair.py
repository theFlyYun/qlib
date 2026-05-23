"""Portfolio construction and risk-filter repair review for CRSP rolling runs."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

try:  # pragma: no cover - supports direct script execution.
    from backtest import (
        add_position_contributions,
        aggregate_exposure,
        aggregate_position_contribution,
        apply_point_in_time_filters,
        attach_benchmark,
        compute_turnover,
        enrich_predictions,
        filter_day_by_membership,
        load_benchmark_prices,
        load_market_data,
        read_calendar,
        read_history_buckets,
        read_membership,
        summarize_backtest,
        summarize_benchmark,
    )
    from crsp_rolling_window_validation import DEFAULT_MANIFEST, load_manifest, manifest_entries
    from run_qlib_alpha158_lightgbm import build_paths, load_config
except ImportError:  # pragma: no cover
    from analysis.nasdaq_top500_score.backtest import (
        add_position_contributions,
        aggregate_exposure,
        aggregate_position_contribution,
        apply_point_in_time_filters,
        attach_benchmark,
        compute_turnover,
        enrich_predictions,
        filter_day_by_membership,
        load_benchmark_prices,
        load_market_data,
        read_calendar,
        read_history_buckets,
        read_membership,
        summarize_backtest,
        summarize_benchmark,
    )
    from analysis.nasdaq_top500_score.crsp_rolling_window_validation import DEFAULT_MANIFEST, load_manifest, manifest_entries
    from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import build_paths, load_config


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = Path("analysis/nasdaq_top500_score/runs/crsp_rolling_windows/portfolio_repair")
DEFAULT_LABEL_COLUMN = "label_10d_total_return"
TOPK_WIDTHS = [10, 20, 30, 50]
SECTOR_CAP_BY_TOPK = {10: 2, 20: 4, 30: 6, 50: 10}
WEIGHT_CAP_BY_TOPK = {10: 0.15, 20: 0.08, 30: 0.06, 50: 0.04}
STRESS_COST_BPS = [0, 25, 50]


@dataclass(frozen=True)
class RepairVariant:
    group: str
    name: str
    top_n: int
    weight_method: str = "equal_weight"
    risk_filter: str = "none"
    beta_control: str = "none"
    score_penalty: str = "none"

    @property
    def max_sector(self) -> int:
        return SECTOR_CAP_BY_TOPK[self.top_n]

    @property
    def max_industry(self) -> int:
        return SECTOR_CAP_BY_TOPK[self.top_n]

    @property
    def max_weight(self) -> float:
        return WEIGHT_CAP_BY_TOPK[self.top_n]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--label-column", default=DEFAULT_LABEL_COLUMN)
    return parser.parse_args()


def resolve_path(path: str | Path) -> Path:
    value = Path(path).expanduser()
    return value if value.is_absolute() else WORKSPACE / value


def run_crsp_portfolio_repair(
    manifest_path: Path = DEFAULT_MANIFEST,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    label_column: str = DEFAULT_LABEL_COLUMN,
) -> dict[str, Any]:
    output = resolve_path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(manifest_path)
    records = [load_repair_record(entry) for entry in manifest_entries(manifest)]

    baseline = build_baseline_summary(records, label_column)
    baseline.to_csv(output / "crsp_portfolio_repair_baseline_summary.csv", index=False)

    variants = build_repair_variants()
    all_rows: list[dict[str, Any]] = []
    removed_rows: list[dict[str, Any]] = []
    beta_period_rows: list[dict[str, Any]] = []
    drawdown_rows: list[dict[str, Any]] = []

    market_cache: dict[tuple[str, str], dict[str, pd.DataFrame]] = {}
    for record in records:
        print(f"Running portfolio repair for {record['window_id']} / {record['feature_set']}...", flush=True)
        market_data = cached_market_data(record, market_cache)
        price_matrix = pd.DataFrame({symbol: frame["execution_price"] for symbol, frame in market_data.items()}).sort_index()
        contexts = build_signal_contexts(record, market_data)
        for variant in variants:
            result = run_variant_backtest(record, contexts, price_matrix, variant)
            all_rows.append(result["summary_row"])
            removed_rows.extend(result["removed_rows"])
            beta_period_rows.extend(result["beta_period_rows"])
            drawdown_rows.append(result["drawdown_row"])

    all_results = pd.DataFrame(all_rows)
    removed = pd.DataFrame(removed_rows)
    beta_periods = pd.DataFrame(beta_period_rows)
    drawdowns = pd.DataFrame(drawdown_rows)

    all_results.to_csv(output / "crsp_portfolio_repair_all_results.csv", index=False)
    write_group_outputs(output, all_results, removed, beta_periods, drawdowns)
    decision = build_decision_summary(all_results, baseline)
    (output / "crsp_portfolio_repair_decision.yaml").write_text(
        yaml.safe_dump(decision, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    write_report(output / "crsp_portfolio_repair_report.md", decision, baseline, all_results)
    return decision


def load_repair_record(entry: dict[str, Any]) -> dict[str, Any]:
    config = load_config(resolve_path(entry["config"]))
    paths = build_paths(config)
    return {
        "window_id": entry["window_id"],
        "window_label": entry["window_label"],
        "feature_set": entry["feature_set"],
        "config": config,
        "paths": paths,
        "run_dir": paths["output_dir"],
    }


def build_baseline_summary(records: list[dict[str, Any]], label_column: str) -> pd.DataFrame:
    rows = []
    label_cache: dict[tuple[str, str], pd.DataFrame] = {}
    rolling_path = resolve_path("analysis/nasdaq_top500_score/runs/crsp_rolling_windows/crsp_rolling_window_summary.csv")
    rolling = pd.read_csv(rolling_path) if rolling_path.exists() else pd.DataFrame()
    for record in records:
        key = (record["window_id"], record["feature_set"])
        roll_row = rolling[
            rolling["window_id"].eq(key[0]) & rolling["feature_set"].eq(key[1])
        ].head(1)
        run_dir = record["run_dir"]
        variant_dir = run_dir / "strategy_comparison" / "sector_cap_2_top10"
        nav = read_csv_if_exists(variant_dir / "backtest_nav.csv")
        positions = read_csv_if_exists(variant_dir / "backtest_positions.csv")
        topk_mean = float(pd.to_numeric(nav.get("gross_return"), errors="coerce").mean()) if not nav.empty else math.nan
        topk_vs_candidate = compute_topk_candidate_stats(run_dir, nav, positions, label_column, label_cache)
        row = {
            "window_id": record["window_id"],
            "window_label": record["window_label"],
            "feature_set": record["feature_set"],
            "variant": "sector_cap_2_top10",
            "topk_avg_gross_return": topk_mean,
            **topk_vs_candidate,
        }
        if not roll_row.empty:
            selected = roll_row.iloc[0]
            row.update(
                {
                    "ic_mean": selected.get("ic_mean"),
                    "rank_ic_mean": selected.get("rank_ic_mean"),
                    "annualized_return": selected.get("sector_cap_2_annualized_return"),
                    "alpha_annualized": selected.get("sector_cap_2_alpha_annualized"),
                    "beta": selected.get("sector_cap_2_beta"),
                    "max_drawdown": selected.get("sector_cap_2_max_drawdown"),
                    "stress_50bps_annualized_return": selected.get("sector_cap_2_stress_annualized_return_50bps"),
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)


def compute_topk_candidate_stats(
    run_dir: Path,
    nav: pd.DataFrame,
    positions: pd.DataFrame,
    label_column: str,
    label_cache: dict[tuple[str, str], pd.DataFrame],
) -> dict[str, Any]:
    if nav.empty or positions.empty:
        return {
            "candidate_mean_label_mean": math.nan,
            "topk_minus_candidate_mean": math.nan,
            "topk_beat_candidate_rate": math.nan,
        }
    predictions_path = run_dir / "test_predictions.csv"
    if not predictions_path.exists():
        return {
            "candidate_mean_label_mean": math.nan,
            "topk_minus_candidate_mean": math.nan,
            "topk_beat_candidate_rate": math.nan,
        }
    predictions = pd.read_csv(predictions_path, usecols=["datetime", "instrument", "score"])
    predictions["datetime"] = pd.to_datetime(predictions["datetime"], errors="coerce").dt.normalize()
    predictions["instrument"] = predictions["instrument"].astype(str).str.upper()
    labels = read_cached_labels(run_dir, label_column, label_cache)
    dates = set(pd.to_datetime(predictions["datetime"]).dt.normalize())
    instruments = set(predictions["instrument"].dropna().astype(str).str.upper())
    labels = labels[labels["datetime"].isin(dates) & labels["instrument"].isin(instruments)].copy()
    aligned = predictions.merge(labels, on=["datetime", "instrument"], how="inner")
    if aligned.empty:
        return {
            "candidate_mean_label_mean": math.nan,
            "topk_minus_candidate_mean": math.nan,
            "topk_beat_candidate_rate": math.nan,
        }
    candidate_mean = aligned.groupby("datetime")["label"].mean().rename("candidate_mean_label")
    working = nav.copy()
    working["signal_date"] = pd.to_datetime(working["signal_date"], errors="coerce").dt.normalize()
    working = working.merge(candidate_mean, left_on="signal_date", right_index=True, how="left")
    working["topk_minus_candidate"] = pd.to_numeric(working["gross_return"], errors="coerce") - pd.to_numeric(
        working["candidate_mean_label"],
        errors="coerce",
    )
    return {
        "candidate_mean_label_mean": float(working["candidate_mean_label"].mean(skipna=True)),
        "topk_minus_candidate_mean": float(working["topk_minus_candidate"].mean(skipna=True)),
        "topk_beat_candidate_rate": float((working["topk_minus_candidate"] > 0).mean()),
    }


def read_cached_labels(
    run_dir: Path,
    label_column: str,
    label_cache: dict[tuple[str, str], pd.DataFrame],
) -> pd.DataFrame:
    source_dir = (run_dir / "qlib_source_csv").resolve()
    key = (str(source_dir), label_column)
    if key not in label_cache:
        rows = []
        for path in sorted(source_dir.glob("*.csv")):
            try:
                frame = pd.read_csv(path, usecols=["date", "symbol", label_column])
            except ValueError:
                continue
            frame = frame.rename(columns={"date": "datetime", "symbol": "instrument", label_column: "label"})
            frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce").dt.normalize()
            frame["instrument"] = frame["instrument"].astype(str).str.upper()
            frame["label"] = pd.to_numeric(frame["label"], errors="coerce")
            rows.append(frame[["datetime", "instrument", "label"]])
        label_cache[key] = pd.concat(rows, ignore_index=True).dropna(subset=["datetime", "instrument", "label"]) if rows else pd.DataFrame(columns=["datetime", "instrument", "label"])
    return label_cache[key]


def build_repair_variants() -> list[RepairVariant]:
    variants: list[RepairVariant] = []
    for top_n in TOPK_WIDTHS:
        variants.append(RepairVariant("topk_width", f"top{top_n}_equal_weight_sector_cap", top_n))
        for method in ["equal_weight", "score_weight", "inverse_vol_weight", "beta_adjusted_weight"]:
            variants.append(RepairVariant("weighting", f"top{top_n}_{method}", top_n, weight_method=method))
        variants.extend(
            [
                RepairVariant("risk_filter", f"top{top_n}_risk_filter_soft", top_n, risk_filter="soft"),
                RepairVariant("risk_filter", f"top{top_n}_risk_filter_hard", top_n, risk_filter="hard"),
                RepairVariant("beta_control", f"top{top_n}_beta_cap_1_5", top_n, beta_control="cap_1_5"),
                RepairVariant("beta_control", f"top{top_n}_beta_cap_1_2", top_n, beta_control="cap_1_2"),
                RepairVariant("beta_control", f"top{top_n}_beta_neutral_weight", top_n, weight_method="beta_neutral_weight", beta_control="neutral_weight"),
                RepairVariant("beta_control", f"top{top_n}_beta_penalty_score", top_n, score_penalty="beta_penalty"),
            ]
        )
    return variants


def cached_market_data(record: dict[str, Any], cache: dict[tuple[str, str], dict[str, pd.DataFrame]]) -> dict[str, pd.DataFrame]:
    paths = record["paths"]
    price_column = str(record["config"].get("backtest", {}).get("price", "open"))
    key = (str(paths["source_dir"].resolve()), price_column)
    if key not in cache:
        cache[key] = load_market_data(paths["source_dir"], price_column)
    return cache[key]


def build_signal_contexts(record: dict[str, Any], market_data: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    paths = record["paths"]
    config = record["config"]
    predictions = pd.read_csv(paths["test_predictions_csv"])
    universe = pd.read_csv(paths["universe_csv"])
    history = read_history_buckets(paths["history_buckets_csv"])
    membership = read_membership(paths.get("membership_csv"))
    enriched = enrich_predictions(predictions, universe, history)
    calendar = read_calendar(paths["qlib_dir"])
    calendar_index = {date: index for index, date in enumerate(calendar)}
    benchmark_prices = load_benchmark_prices(config, paths, str(config.get("backtest", {}).get("price", "open")))
    benchmark_returns = benchmark_prices.pct_change().dropna() if not benchmark_prices.empty else pd.Series(dtype=float)
    rebalance_days = int(config["backtest"]["rebalance_days"])
    entry_lag_days = int(config["backtest"].get("entry_lag_days", 1))
    holding_days = int(config["backtest"]["holding_days"])
    signal_dates = sorted(pd.to_datetime(enriched["datetime"]).dt.normalize().dropna().unique())
    profile_cache: dict[tuple[str, pd.Timestamp], dict[str, Any]] = {}
    contexts = []
    for signal_date in signal_dates[::rebalance_days]:
        signal_ts = pd.Timestamp(signal_date).normalize()
        if signal_ts not in calendar_index:
            continue
        entry_index = calendar_index[signal_ts] + entry_lag_days
        exit_index = entry_index + holding_days
        if entry_index >= len(calendar) or exit_index >= len(calendar):
            continue
        day = build_candidate_day(enriched, signal_ts, config, market_data, membership, profile_cache)
        if day.empty:
            continue
        day = add_risk_metrics(day, market_data, benchmark_returns, signal_ts)
        contexts.append(
            {
                "signal_date": signal_ts,
                "entry_date": calendar[entry_index],
                "exit_date": calendar[exit_index],
                "day": day,
            }
        )
    return contexts


def build_candidate_day(
    enriched: pd.DataFrame,
    signal_ts: pd.Timestamp,
    config: dict[str, Any],
    market_data: dict[str, pd.DataFrame],
    membership: pd.DataFrame,
    profile_cache: dict[tuple[str, pd.Timestamp], dict[str, Any]],
) -> pd.DataFrame:
    day = enriched[enriched["datetime"] == signal_ts].copy().sort_values("score", ascending=False).reset_index(drop=True)
    day = filter_day_by_membership(day, signal_ts, membership)
    day, _ = apply_point_in_time_filters(day, signal_ts, config, market_data, profile_cache)
    if day.empty:
        return day
    day["score"] = pd.to_numeric(day["score"], errors="coerce")
    day = day.dropna(subset=["score"]).sort_values("score", ascending=False).reset_index(drop=True)
    day["global_rank"] = range(1, len(day) + 1)
    return day


def add_risk_metrics(
    day: pd.DataFrame,
    market_data: dict[str, pd.DataFrame],
    benchmark_returns: pd.Series,
    signal_ts: pd.Timestamp,
) -> pd.DataFrame:
    rows = []
    for row in day.to_dict("records"):
        symbol = str(row["symbol"]).upper()
        metrics = compute_symbol_risk_metrics(market_data.get(symbol), benchmark_returns, signal_ts)
        rows.append({**row, **metrics})
    frame = pd.DataFrame(rows)
    frame["risk_flag_count"] = (
        frame["vol_60d"].gt(0.80).fillna(False).astype(int)
        + frame["max_drawdown_60d"].lt(-0.25).fillna(False).astype(int)
        + frame["beta_120d"].gt(1.50).fillna(False).astype(int)
    )
    return frame


def compute_symbol_risk_metrics(
    frame: pd.DataFrame | None,
    benchmark_returns: pd.Series,
    signal_ts: pd.Timestamp,
) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {"vol_60d": math.nan, "max_drawdown_60d": math.nan, "beta_120d": math.nan}
    usable = frame[frame.index <= signal_ts].copy()
    if len(usable) < 3:
        return {"vol_60d": math.nan, "max_drawdown_60d": math.nan, "beta_120d": math.nan}
    close = pd.to_numeric(usable["close"], errors="coerce").dropna()
    returns = close.pct_change().dropna()
    vol = float(returns.tail(60).std(ddof=1) * math.sqrt(252)) if len(returns.tail(60)) > 1 else math.nan
    prices_60 = close.tail(60)
    drawdown = prices_60 / prices_60.cummax() - 1.0
    max_drawdown = float(drawdown.min()) if len(drawdown) else math.nan
    beta = compute_beta(returns.tail(120), benchmark_returns[benchmark_returns.index <= signal_ts].tail(120))
    return {"vol_60d": vol, "max_drawdown_60d": max_drawdown, "beta_120d": beta}


def compute_beta(stock_returns: pd.Series, benchmark_returns: pd.Series) -> float:
    aligned = pd.concat([stock_returns.rename("stock"), benchmark_returns.rename("benchmark")], axis=1).dropna()
    if len(aligned) < 20:
        return math.nan
    variance = float(aligned["benchmark"].var(ddof=1))
    if math.isclose(variance, 0.0):
        return math.nan
    return float(aligned["stock"].cov(aligned["benchmark"]) / variance)


def run_variant_backtest(
    record: dict[str, Any],
    contexts: list[dict[str, Any]],
    price_matrix: pd.DataFrame,
    variant: RepairVariant,
) -> dict[str, Any]:
    config = record["config"]
    nav_value = 1.0
    previous_weights: dict[str, float] = {}
    nav_rows = []
    position_rows = []
    removed_rows = []
    beta_period_rows = []
    for context in contexts:
        selected, removed = select_variant_positions(context["day"], variant)
        removed_rows.extend(add_removed_context(removed, record, variant, context["signal_date"]))
        tradable = build_variant_position_returns(selected, price_matrix, context["entry_date"], context["exit_date"])
        if tradable.empty:
            continue
        weights = compute_variant_weights(tradable, variant)
        tradable["weight"] = weights
        new_weights = dict(zip(tradable["symbol"], tradable["weight"], strict=False))
        turnover = compute_turnover(previous_weights, new_weights)
        gross_return = float((tradable["gross_return"] * tradable["weight"]).sum())
        cost_return = 0.0
        net_return = gross_return
        nav_value *= 1.0 + net_return
        period = len(nav_rows) + 1
        nav_rows.append(
            {
                "period": period,
                "signal_date": context["signal_date"].date().isoformat(),
                "entry_date": context["entry_date"].date().isoformat(),
                "exit_date": context["exit_date"].date().isoformat(),
                "position_count": int(len(tradable)),
                "gross_return": gross_return,
                "turnover": turnover,
                "cost_return": cost_return,
                "net_return": net_return,
                "nav": nav_value,
            }
        )
        for row in tradable.to_dict("records"):
            position_rows.append(
                {
                    "period": period,
                    "signal_date": context["signal_date"].date().isoformat(),
                    "entry_date": context["entry_date"].date().isoformat(),
                    "exit_date": context["exit_date"].date().isoformat(),
                    "symbol": row["symbol"],
                    "selected_rank": row["selected_rank"],
                    "sector": row.get("sector"),
                    "industry": row.get("industry"),
                    "score": row.get("score"),
                    "selection_score": row.get("selection_score"),
                    "weight": row.get("weight"),
                    "vol_60d": row.get("vol_60d"),
                    "max_drawdown_60d": row.get("max_drawdown_60d"),
                    "beta_120d": row.get("beta_120d"),
                    "risk_flag_count": row.get("risk_flag_count"),
                    "entry_price": row["entry_price"],
                    "exit_price": row["exit_price"],
                    "gross_return": row["gross_return"],
                }
            )
        beta_period_rows.append(
            {
                "window_id": record["window_id"],
                "window_label": record["window_label"],
                "feature_set": record["feature_set"],
                "variant": variant.name,
                "signal_date": context["signal_date"].date().isoformat(),
                "portfolio_beta_120d": float((tradable["beta_120d"] * tradable["weight"]).sum(skipna=True)),
                "portfolio_vol_60d": float((tradable["vol_60d"] * tradable["weight"]).sum(skipna=True)),
                "avg_risk_flag_count": float(tradable["risk_flag_count"].mean(skipna=True)),
            }
        )
        previous_weights = new_weights
    nav = pd.DataFrame(nav_rows)
    positions = pd.DataFrame(position_rows)
    backtest_config = dict(config["backtest"])
    backtest_config["top_n"] = variant.top_n
    backtest_config["cost_bps"] = 0
    summary = summarize_backtest(nav, positions, backtest_config, skipped_periods=max(0, len(contexts) - len(nav)))
    nav, benchmark = attach_benchmark(nav, {**config, "backtest": backtest_config}, record["paths"], str(config["backtest"].get("price", "open")))
    if benchmark:
        summary["benchmark"] = benchmark
    positions = add_position_contributions(nav, positions) if not nav.empty and not positions.empty else positions
    stress = build_stress_rows(nav, positions, config, variant)
    row = build_summary_row(record, variant, summary, benchmark, stress, positions)
    return {
        "summary_row": row,
        "removed_rows": removed_rows,
        "beta_period_rows": beta_period_rows,
        "drawdown_row": build_drawdown_row(record, variant, nav),
    }


def select_variant_positions(day: pd.DataFrame, variant: RepairVariant) -> tuple[pd.DataFrame, pd.DataFrame]:
    working = day.copy()
    working["selection_score"] = build_selection_score(working, variant)
    removed_frames = []
    if variant.risk_filter == "hard":
        removed = working[working["risk_flag_count"].fillna(0).gt(0)].copy()
        removed["removed_reason"] = "risk_filter_hard"
        removed_frames.append(removed)
        working = working[working["risk_flag_count"].fillna(0).le(0)].copy()
    if variant.beta_control == "cap_1_5":
        removed = working[working["beta_120d"].gt(1.5)].copy()
        removed["removed_reason"] = "beta_cap_1_5"
        removed_frames.append(removed)
        working = working[~working["beta_120d"].gt(1.5)].copy()
    if variant.beta_control == "cap_1_2":
        removed = working[working["beta_120d"].gt(1.2)].copy()
        removed["removed_reason"] = "beta_cap_1_2"
        removed_frames.append(removed)
        working = working[~working["beta_120d"].gt(1.2)].copy()
    selected_rows = []
    sector_counts: dict[str, int] = {}
    industry_counts: dict[str, int] = {}
    for row in working.sort_values("selection_score", ascending=False).to_dict("records"):
        sector = normalize_group(row.get("sector"))
        industry = normalize_group(row.get("industry"))
        if sector_counts.get(sector, 0) >= variant.max_sector:
            continue
        if industry_counts.get(industry, 0) >= variant.max_industry:
            continue
        selected_rows.append(row)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
        industry_counts[industry] = industry_counts.get(industry, 0) + 1
        if len(selected_rows) >= variant.top_n:
            break
    selected = pd.DataFrame(selected_rows)
    if not selected.empty:
        selected = selected.reset_index(drop=True)
        selected["selected_rank"] = range(1, len(selected) + 1)
    removed = pd.concat(removed_frames, ignore_index=True) if removed_frames else pd.DataFrame()
    return selected, removed


def build_selection_score(day: pd.DataFrame, variant: RepairVariant) -> pd.Series:
    score = pd.to_numeric(day["score"], errors="coerce")
    if variant.score_penalty == "beta_penalty":
        score_rank = score.rank(pct=True, method="first")
        beta = pd.to_numeric(day["beta_120d"], errors="coerce").fillna(1.0)
        beta_penalty = beta.clip(lower=1.0).rank(pct=True, method="first")
        return score_rank - 0.25 * beta_penalty
    if variant.risk_filter == "soft":
        score_rank = score.rank(pct=True, method="first")
        risk_penalty = pd.to_numeric(day["risk_flag_count"], errors="coerce").fillna(0.0) * 0.10
        return score_rank - risk_penalty
    return score


def normalize_group(value: Any) -> str:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return "UNKNOWN"
    return str(value)


def build_variant_position_returns(
    selected: pd.DataFrame,
    prices: pd.DataFrame,
    entry_date: pd.Timestamp,
    exit_date: pd.Timestamp,
) -> pd.DataFrame:
    if selected.empty or entry_date not in prices.index or exit_date not in prices.index:
        return pd.DataFrame()
    rows = []
    for row in selected.to_dict("records"):
        symbol = str(row["symbol"]).upper()
        if symbol not in prices.columns:
            continue
        entry_price = prices.at[entry_date, symbol]
        exit_price = prices.at[exit_date, symbol]
        if pd.isna(entry_price) or pd.isna(exit_price) or float(entry_price) <= 0:
            continue
        rows.append({**row, "entry_price": float(entry_price), "exit_price": float(exit_price), "gross_return": float(exit_price) / float(entry_price) - 1.0})
    return pd.DataFrame(rows)


def compute_variant_weights(selected: pd.DataFrame, variant: RepairVariant) -> pd.Series:
    if selected.empty:
        return pd.Series(dtype=float)
    if variant.weight_method == "score_weight":
        values = positive_shift(pd.to_numeric(selected["selection_score"], errors="coerce"))
    elif variant.weight_method == "inverse_vol_weight":
        values = 1.0 / (pd.to_numeric(selected["vol_60d"], errors="coerce").clip(lower=0.05).fillna(0.50))
    elif variant.weight_method == "beta_adjusted_weight":
        values = 1.0 / (pd.to_numeric(selected["beta_120d"], errors="coerce").clip(lower=0.30).fillna(1.0))
    elif variant.weight_method == "beta_neutral_weight":
        values = 1.0 / (pd.to_numeric(selected["beta_120d"], errors="coerce").clip(lower=0.30).fillna(1.0) ** 2)
    else:
        values = pd.Series(1.0, index=selected.index)
    if variant.risk_filter == "soft":
        values = values * (0.5 ** pd.to_numeric(selected["risk_flag_count"], errors="coerce").fillna(0.0))
    weights = normalize_weights(values)
    return cap_and_renormalize(weights, variant.max_weight)


def positive_shift(values: pd.Series) -> pd.Series:
    cleaned = values.fillna(values.median()).astype(float)
    shifted = cleaned - cleaned.min() + 1e-6
    if math.isclose(float(shifted.sum()), 0.0):
        return pd.Series(1.0, index=values.index)
    return shifted


def normalize_weights(values: pd.Series) -> pd.Series:
    cleaned = values.replace([math.inf, -math.inf], math.nan).fillna(0.0).clip(lower=0.0)
    total = float(cleaned.sum())
    if total <= 0:
        return pd.Series(1.0 / len(cleaned), index=cleaned.index)
    return cleaned / total


def cap_and_renormalize(weights: pd.Series, cap: float) -> pd.Series:
    result = weights.copy().astype(float)
    for _ in range(20):
        over = result > cap
        if not over.any():
            break
        excess = float((result[over] - cap).sum())
        result[over] = cap
        under = ~over
        under_sum = float(result[under].sum())
        if under_sum <= 0 or excess <= 0:
            break
        result[under] += result[under] / under_sum * excess
    total = float(result.sum())
    return result / total if total > 0 else pd.Series(1.0 / len(result), index=result.index)


def build_stress_rows(nav: pd.DataFrame, positions: pd.DataFrame, config: dict[str, Any], variant: RepairVariant) -> list[dict[str, Any]]:
    rows = []
    for cost_bps in STRESS_COST_BPS:
        stressed = nav.copy()
        cost_rate = float(cost_bps) / 10000.0
        stressed["cost_return"] = pd.to_numeric(stressed["turnover"], errors="coerce").fillna(0.0) * cost_rate
        stressed["net_return"] = pd.to_numeric(stressed["gross_return"], errors="coerce").fillna(0.0) - stressed["cost_return"]
        stressed["nav"] = (1.0 + stressed["net_return"]).cumprod()
        if "benchmark_return" in stressed:
            stressed["excess_return"] = stressed["net_return"] - stressed["benchmark_return"]
            stressed["benchmark_nav"] = (1.0 + stressed["benchmark_return"].fillna(0.0)).cumprod()
            stressed["relative_nav"] = stressed["nav"] / stressed["benchmark_nav"]
        backtest_config = dict(config["backtest"])
        backtest_config["cost_bps"] = cost_bps
        backtest_config["top_n"] = variant.top_n
        summary = summarize_backtest(stressed, positions, backtest_config, skipped_periods=0)
        benchmark = {}
        if "benchmark_return" in stressed:
            try:
                benchmark = summarize_benchmark(stressed, {**config, "backtest": backtest_config}, config.get("benchmark", {}))
            except Exception:
                benchmark = {}
        rows.append(
            {
                "cost_bps": cost_bps,
                "annualized_return": summary.get("annualized_return"),
                "max_drawdown": summary.get("max_drawdown"),
                "alpha_annualized": benchmark.get("alpha_annualized"),
            }
        )
    return rows


def build_summary_row(
    record: dict[str, Any],
    variant: RepairVariant,
    summary: dict[str, Any],
    benchmark: dict[str, Any],
    stress: list[dict[str, Any]],
    positions: pd.DataFrame,
) -> dict[str, Any]:
    stress_25 = next((row for row in stress if row["cost_bps"] == 25), {})
    stress_50 = next((row for row in stress if row["cost_bps"] == 50), {})
    exposure = aggregate_exposure(positions, "sector") if not positions.empty else pd.DataFrame()
    max_exposure = float(exposure["max_weight"].max()) if not exposure.empty and "max_weight" in exposure else math.nan
    return {
        "window_id": record["window_id"],
        "window_label": record["window_label"],
        "feature_set": record["feature_set"],
        "group": variant.group,
        "variant": variant.name,
        "top_n": variant.top_n,
        "weight_method": variant.weight_method,
        "risk_filter": variant.risk_filter,
        "beta_control": variant.beta_control,
        "score_penalty": variant.score_penalty,
        "max_sector": variant.max_sector,
        "max_industry": variant.max_industry,
        "max_weight": variant.max_weight,
        "period_count": summary.get("period_count"),
        "annualized_return": summary.get("annualized_return"),
        "alpha_annualized": benchmark.get("alpha_annualized"),
        "beta": benchmark.get("beta"),
        "correlation": benchmark.get("correlation"),
        "max_drawdown": summary.get("max_drawdown"),
        "avg_turnover": summary.get("avg_turnover"),
        "avg_position_count": summary.get("avg_position_count"),
        "max_sector_weight_any_period": max_exposure,
        "stress_25bps_annualized_return": stress_25.get("annualized_return"),
        "stress_25bps_alpha_annualized": stress_25.get("alpha_annualized"),
        "stress_50bps_annualized_return": stress_50.get("annualized_return"),
        "stress_50bps_alpha_annualized": stress_50.get("alpha_annualized"),
    }


def add_removed_context(
    removed: pd.DataFrame,
    record: dict[str, Any],
    variant: RepairVariant,
    signal_date: pd.Timestamp,
) -> list[dict[str, Any]]:
    if removed.empty:
        return []
    rows = []
    for row in removed.head(200).to_dict("records"):
        rows.append(
            {
                "window_id": record["window_id"],
                "window_label": record["window_label"],
                "feature_set": record["feature_set"],
                "variant": variant.name,
                "signal_date": signal_date.date().isoformat(),
                "symbol": row.get("symbol"),
                "sector": row.get("sector"),
                "industry": row.get("industry"),
                "score": row.get("score"),
                "vol_60d": row.get("vol_60d"),
                "max_drawdown_60d": row.get("max_drawdown_60d"),
                "beta_120d": row.get("beta_120d"),
                "risk_flag_count": row.get("risk_flag_count"),
                "removed_reason": row.get("removed_reason"),
            }
        )
    return rows


def build_drawdown_row(record: dict[str, Any], variant: RepairVariant, nav: pd.DataFrame) -> dict[str, Any]:
    base = {
        "window_id": record["window_id"],
        "window_label": record["window_label"],
        "feature_set": record["feature_set"],
        "variant": variant.name,
        "group": variant.group,
    }
    if nav.empty or "nav" not in nav:
        return {**base, "max_drawdown": math.nan}
    working = nav.copy()
    working["nav"] = pd.to_numeric(working["nav"], errors="coerce")
    drawdown = working["nav"] / working["nav"].cummax() - 1.0
    trough_idx = int(drawdown.idxmin())
    peak_idx = int(working.loc[:trough_idx, "nav"].idxmax())
    return {
        **base,
        "peak_date": working.loc[peak_idx, "signal_date"],
        "trough_date": working.loc[trough_idx, "signal_date"],
        "max_drawdown": float(drawdown.iloc[trough_idx]),
        "drawdown_period_count": int(trough_idx - peak_idx + 1),
    }


def write_group_outputs(
    output: Path,
    all_results: pd.DataFrame,
    removed: pd.DataFrame,
    beta_periods: pd.DataFrame,
    drawdowns: pd.DataFrame,
) -> None:
    topk = all_results[all_results["group"].eq("topk_width")].copy()
    weighting = all_results[all_results["group"].eq("weighting")].copy()
    risk = all_results[all_results["group"].eq("risk_filter")].copy()
    beta = all_results[all_results["group"].eq("beta_control")].copy()
    summarize_variants(topk).to_csv(output / "topk_width_comparison.csv", index=False)
    topk.to_csv(output / "topk_width_by_window.csv", index=False)
    drawdowns[drawdowns["group"].eq("topk_width")].to_csv(output / "topk_width_drawdown_summary.csv", index=False)
    summarize_variants(weighting).to_csv(output / "portfolio_weighting_comparison.csv", index=False)
    weighting.to_csv(output / "portfolio_weighting_by_window.csv", index=False)
    summarize_variants(risk).to_csv(output / "single_name_risk_filter_comparison.csv", index=False)
    removed.to_csv(output / "risk_filter_removed_positions.csv", index=False)
    drawdowns[drawdowns["group"].eq("risk_filter")].to_csv(output / "risk_filter_drawdown_impact.csv", index=False)
    summarize_variants(beta).to_csv(output / "beta_control_comparison.csv", index=False)
    beta_periods.to_csv(output / "beta_exposure_by_period.csv", index=False)
    drawdowns[drawdowns["group"].eq("beta_control")].to_csv(output / "beta_drawdown_attribution.csv", index=False)


def summarize_variants(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    grouped = frame.groupby(["feature_set", "group", "variant", "top_n"], dropna=False)
    return (
        grouped.agg(
            windows=("window_id", "nunique"),
            mean_annualized_return=("annualized_return", "mean"),
            mean_alpha=("alpha_annualized", "mean"),
            positive_alpha_windows=("alpha_annualized", lambda s: int((pd.to_numeric(s, errors="coerce") > 0).sum())),
            mean_beta=("beta", "mean"),
            mean_max_drawdown=("max_drawdown", "mean"),
            worst_max_drawdown=("max_drawdown", "min"),
            mean_turnover=("avg_turnover", "mean"),
            mean_stress_50bps_return=("stress_50bps_annualized_return", "mean"),
            positive_50bps_alpha_windows=("stress_50bps_alpha_annualized", lambda s: int((pd.to_numeric(s, errors="coerce") > 0).sum())),
        )
        .reset_index()
        .sort_values(["mean_alpha", "mean_max_drawdown"], ascending=[False, False])
        .reset_index(drop=True)
    )


def build_decision_summary(all_results: pd.DataFrame, baseline: pd.DataFrame) -> dict[str, Any]:
    summary = summarize_variants(all_results)
    baseline_mean_beta = float(pd.to_numeric(baseline["beta"], errors="coerce").mean())
    candidates = summary[
        (summary["positive_alpha_windows"] >= 3)
        & (summary["mean_beta"] < baseline_mean_beta)
        & (summary["positive_50bps_alpha_windows"] >= 2)
    ].copy()
    if candidates.empty:
        return {
            "stage": "CRSP-19",
            "status": "no_portfolio_rule_passed",
            "recommended_next_stage": "CRSP-20 标签重设计",
            "reason": "没有组合规则同时满足跨窗口 alpha、beta 和 50bps 压力条件。",
            "best_observation": row_to_dict(summary.head(1)),
            "baseline_mean_beta": baseline_mean_beta,
        }
    best = candidates.sort_values(["positive_alpha_windows", "mean_alpha", "worst_max_drawdown"], ascending=[False, False, False]).head(1)
    return {
        "stage": "CRSP-19",
        "status": "candidate_portfolio_rule_found",
        "recommended_next_stage": "CRSP-20 候选组合规则滚动复验",
        "candidate": row_to_dict(best),
        "baseline_mean_beta": baseline_mean_beta,
    }


def write_report(path: Path, decision: dict[str, Any], baseline: pd.DataFrame, all_results: pd.DataFrame) -> None:
    lines = [
        "# CRSP Portfolio Construction And Risk Filter Repair",
        "",
        "本报告复用 rolling run 的预测分数，不重训 LightGBM，检查 TopK 宽度、权重、单票风险过滤和 beta 控制能否修复 IC/TopK 背离。",
        "",
        "```yaml",
        yaml.safe_dump(decision, allow_unicode=True, sort_keys=False).strip(),
        "```",
        "",
        "## Baseline",
        "",
        dataframe_to_markdown(
            baseline,
            ["window_label", "feature_set", "ic_mean", "rank_ic_mean", "annualized_return", "alpha_annualized", "beta", "max_drawdown", "topk_minus_candidate_mean"],
        ),
        "",
        "## TopK Width",
        "",
        dataframe_to_markdown(summarize_variants(all_results[all_results["group"].eq("topk_width")]).head(12), ["feature_set", "variant", "mean_alpha", "positive_alpha_windows", "mean_beta", "worst_max_drawdown", "mean_stress_50bps_return"]),
        "",
        "## Weighting",
        "",
        dataframe_to_markdown(summarize_variants(all_results[all_results["group"].eq("weighting")]).head(12), ["feature_set", "variant", "mean_alpha", "positive_alpha_windows", "mean_beta", "worst_max_drawdown", "mean_stress_50bps_return"]),
        "",
        "## Risk Filter",
        "",
        dataframe_to_markdown(summarize_variants(all_results[all_results["group"].eq("risk_filter")]).head(12), ["feature_set", "variant", "mean_alpha", "positive_alpha_windows", "mean_beta", "worst_max_drawdown", "mean_stress_50bps_return"]),
        "",
        "## Beta Control",
        "",
        dataframe_to_markdown(summarize_variants(all_results[all_results["group"].eq("beta_control")]).head(12), ["feature_set", "variant", "mean_alpha", "positive_alpha_windows", "mean_beta", "worst_max_drawdown", "mean_stress_50bps_return"]),
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
    if value is None or pd.isna(value):
        return "N/A"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value).replace("|", "\\|")


def row_to_dict(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {}
    row = frame.iloc[0].to_dict()
    return {key: native(value) for key, value in row.items()}


def native(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def main() -> None:
    args = parse_args()
    decision = run_crsp_portfolio_repair(args.manifest, args.output_dir, label_column=args.label_column)
    print(f"Portfolio repair: {resolve_path(args.output_dir)}")
    print(yaml.safe_dump(decision, allow_unicode=True, sort_keys=False))


if __name__ == "__main__":
    main()
