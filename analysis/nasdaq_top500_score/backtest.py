"""Simple non-overlapping TopK backtest for model scores."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

try:
    from .selection import select_bucketed_top
except ImportError:  # pragma: no cover - supports running the pipeline as a script.
    from selection import select_bucketed_top


@dataclass
class BacktestResult:
    nav: pd.DataFrame
    positions: pd.DataFrame
    summary: dict[str, Any]


def run_topk_backtest(
    predictions: pd.DataFrame,
    universe: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
) -> BacktestResult:
    backtest_config = config.get("backtest", {})
    if not backtest_config.get("enabled", False):
        result = BacktestResult(
            nav=pd.DataFrame(),
            positions=pd.DataFrame(),
            summary={"enabled": False},
        )
        write_backtest_outputs(result, paths)
        return result

    close = load_price_matrix(paths["source_dir"], str(backtest_config.get("price", "close")))
    history = read_history_buckets(paths["history_buckets_csv"])
    enriched = enrich_predictions(predictions, universe, history)
    calendar = read_calendar(paths["qlib_dir"])
    calendar_index = {date: index for index, date in enumerate(calendar)}
    signal_dates = sorted(pd.to_datetime(enriched["datetime"]).dt.normalize().dropna().unique())

    rebalance_days = int(backtest_config["rebalance_days"])
    holding_days = int(backtest_config["holding_days"])
    entry_lag_days = int(backtest_config.get("entry_lag_days", 1))
    cost_rate = float(backtest_config.get("cost_bps", 0.0)) / 10000.0
    min_positions = int(backtest_config.get("min_positions", 1))
    top_n = int(backtest_config.get("top_n", config["report"]["top_n"]))

    nav = 1.0
    previous_weights: dict[str, float] = {}
    period_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []
    skipped_periods = 0

    for signal_date in signal_dates[::rebalance_days]:
        signal_ts = pd.Timestamp(signal_date).normalize()
        if signal_ts not in calendar_index:
            skipped_periods += 1
            continue
        signal_index = calendar_index[signal_ts]
        entry_index = signal_index + entry_lag_days
        exit_index = entry_index + holding_days
        if entry_index >= len(calendar) or exit_index >= len(calendar):
            skipped_periods += 1
            continue

        entry_date = calendar[entry_index]
        exit_date = calendar[exit_index]
        selected = select_for_signal_date(enriched, signal_ts, config, top_n)
        tradable_positions = build_position_returns(selected, close, entry_date, exit_date)
        if len(tradable_positions) < min_positions:
            skipped_periods += 1
            continue

        weight = 1.0 / len(tradable_positions)
        new_weights = {row["symbol"]: weight for row in tradable_positions}
        turnover = compute_turnover(previous_weights, new_weights)
        cost_return = turnover * cost_rate
        gross_return = sum(row["gross_return"] * weight for row in tradable_positions)
        net_return = gross_return - cost_return
        nav *= 1.0 + net_return

        period_rows.append(
            {
                "period": len(period_rows) + 1,
                "signal_date": signal_ts.date().isoformat(),
                "entry_date": entry_date.date().isoformat(),
                "exit_date": exit_date.date().isoformat(),
                "position_count": len(tradable_positions),
                "gross_return": gross_return,
                "turnover": turnover,
                "cost_return": cost_return,
                "net_return": net_return,
                "nav": nav,
            }
        )
        for row in tradable_positions:
            position_rows.append(
                {
                    "period": len(period_rows),
                    "signal_date": signal_ts.date().isoformat(),
                    "entry_date": entry_date.date().isoformat(),
                    "exit_date": exit_date.date().isoformat(),
                    "symbol": row["symbol"],
                    "selected_rank": row.get("selected_rank"),
                    "history_bucket": row.get("history_bucket"),
                    "sector": row.get("sector"),
                    "industry": row.get("industry"),
                    "score": row.get("score"),
                    "weight": weight,
                    "entry_price": row["entry_price"],
                    "exit_price": row["exit_price"],
                    "gross_return": row["gross_return"],
                }
            )
        previous_weights = new_weights

    nav_frame = pd.DataFrame(period_rows)
    positions = pd.DataFrame(position_rows)
    summary = summarize_backtest(nav_frame, positions, backtest_config, skipped_periods)
    result = BacktestResult(nav=nav_frame, positions=positions, summary=summary)
    write_backtest_outputs(result, paths)
    return result


def enrich_predictions(predictions: pd.DataFrame, universe: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    frame = predictions.copy()
    frame["datetime"] = pd.to_datetime(frame["datetime"]).dt.normalize()
    frame["symbol"] = frame["instrument"].astype(str).str.upper()
    frame = frame.merge(universe, on="symbol", how="left")
    if not history.empty:
        frame = frame.merge(history, on="symbol", how="left")
    frame["history_bucket"] = frame["history_bucket"].fillna("missing_history")
    return frame.sort_values(["datetime", "score"], ascending=[True, False]).reset_index(drop=True)


def select_for_signal_date(
    enriched: pd.DataFrame,
    signal_date: pd.Timestamp,
    config: dict[str, Any],
    top_n: int,
) -> pd.DataFrame:
    day = enriched[enriched["datetime"] == signal_date].copy()
    day = day.sort_values("score", ascending=False).reset_index(drop=True)
    day["global_rank"] = range(1, len(day) + 1)
    day["bucket_rank"] = day.groupby("history_bucket")["score"].rank(method="first", ascending=False).astype(int)

    ranking_config = config.get("bucket_ranking", {})
    if ranking_config.get("enabled", False):
        return select_bucketed_top(day, ranking_config, top_n, config.get("industry_constraints", {}))

    selected = day.head(top_n).copy()
    selected["selected_rank"] = range(1, len(selected) + 1)
    return selected


def build_position_returns(
    selected: pd.DataFrame,
    close: pd.DataFrame,
    entry_date: pd.Timestamp,
    exit_date: pd.Timestamp,
) -> list[dict[str, Any]]:
    rows = []
    if entry_date not in close.index or exit_date not in close.index:
        return rows
    for row in selected.to_dict("records"):
        symbol = str(row["symbol"]).upper()
        if symbol not in close.columns:
            continue
        entry_price = close.at[entry_date, symbol]
        exit_price = close.at[exit_date, symbol]
        if pd.isna(entry_price) or pd.isna(exit_price) or float(entry_price) <= 0:
            continue
        rows.append(
            {
                **row,
                "entry_price": float(entry_price),
                "exit_price": float(exit_price),
                "gross_return": float(exit_price) / float(entry_price) - 1.0,
            }
        )
    return rows


def load_price_matrix(source_dir: Path, price_column: str) -> pd.DataFrame:
    series = {}
    for csv_path in sorted(source_dir.glob("*.csv")):
        symbol = csv_path.stem.upper()
        frame = pd.read_csv(csv_path, usecols=["date", price_column])
        frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
        prices = pd.to_numeric(frame[price_column], errors="coerce")
        prices.index = frame["date"]
        series[symbol] = prices
    if not series:
        return pd.DataFrame()
    return pd.DataFrame(series).sort_index()


def read_history_buckets(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["symbol", "history_bucket"])
    return pd.read_csv(path)


def read_calendar(qlib_dir: Path) -> list[pd.Timestamp]:
    calendar = pd.read_csv(qlib_dir / "calendars/day.txt", header=None)[0]
    return list(pd.to_datetime(calendar).dt.normalize())


def compute_turnover(previous_weights: dict[str, float], new_weights: dict[str, float]) -> float:
    symbols = set(previous_weights) | set(new_weights)
    return float(sum(abs(new_weights.get(symbol, 0.0) - previous_weights.get(symbol, 0.0)) for symbol in symbols))


def summarize_backtest(
    nav: pd.DataFrame,
    positions: pd.DataFrame,
    config: dict[str, Any],
    skipped_periods: int,
) -> dict[str, Any]:
    if nav.empty:
        return {
            "enabled": True,
            "period_count": 0,
            "skipped_periods": skipped_periods,
        }

    periods_per_year = float(config.get("periods_per_year", 252 / int(config["rebalance_days"])))
    net_returns = nav["net_return"].astype(float)
    gross_returns = nav["gross_return"].astype(float)
    cumulative_return = float(nav["nav"].iloc[-1] - 1.0)
    annualized_return = float((1.0 + cumulative_return) ** (periods_per_year / len(nav)) - 1.0)
    annualized_volatility = float(net_returns.std(ddof=1) * math.sqrt(periods_per_year)) if len(nav) > 1 else math.nan
    information_ratio = (
        float(net_returns.mean() / net_returns.std(ddof=1) * math.sqrt(periods_per_year))
        if len(nav) > 1 and not math.isclose(float(net_returns.std(ddof=1)), 0.0)
        else math.nan
    )
    drawdown = nav["nav"] / nav["nav"].cummax() - 1.0
    top_symbols = positions["symbol"].value_counts().head(10).to_dict() if not positions.empty else {}
    return {
        "enabled": True,
        "period_count": int(len(nav)),
        "skipped_periods": int(skipped_periods),
        "start_entry_date": str(nav["entry_date"].iloc[0]),
        "end_exit_date": str(nav["exit_date"].iloc[-1]),
        "cumulative_return": cumulative_return,
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_volatility,
        "information_ratio": information_ratio,
        "max_drawdown": float(drawdown.min()),
        "avg_gross_return": float(gross_returns.mean()),
        "avg_net_return": float(net_returns.mean()),
        "win_rate": float((net_returns > 0).mean()),
        "avg_turnover": float(nav["turnover"].mean()),
        "total_cost_return": float(nav["cost_return"].sum()),
        "avg_position_count": float(nav["position_count"].mean()),
        "top_symbols_by_holding_count": top_symbols,
        "config": config,
    }


def write_backtest_outputs(result: BacktestResult, paths: dict[str, Path]) -> None:
    paths["backtest_nav_csv"].parent.mkdir(parents=True, exist_ok=True)
    result.nav.to_csv(paths["backtest_nav_csv"], index=False)
    result.positions.to_csv(paths["backtest_positions_csv"], index=False)
    paths["backtest_summary"].write_text(
        yaml.safe_dump(result.summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
