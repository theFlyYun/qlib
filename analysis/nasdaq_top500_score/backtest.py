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
    from .selection.history_buckets import assign_history_bucket
    from .selection.liquidity import liquidity_exclusion_reason
except ImportError:  # pragma: no cover - supports running the pipeline as a script.
    from selection import select_bucketed_top
    from selection.history_buckets import assign_history_bucket
    from selection.liquidity import liquidity_exclusion_reason


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

    price_column = str(backtest_config.get("price", "close"))
    market_data = load_market_data(paths["source_dir"], price_column)
    close = price_matrix_from_market_data(market_data)
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
        selected, filter_stats = select_for_signal_date(enriched, signal_ts, config, top_n, market_data)
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
                **filter_stats,
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
                    "history_rows_asof": row.get("history_rows_asof"),
                    "latest_close_asof": row.get("latest_close_asof"),
                    "avg_dollar_volume_20d_asof": row.get("avg_dollar_volume_20d_asof"),
                    "median_dollar_volume_60d_asof": row.get("median_dollar_volume_60d_asof"),
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
    market_data: dict[str, pd.DataFrame] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    day = enriched[enriched["datetime"] == signal_date].copy()
    day = day.sort_values("score", ascending=False).reset_index(drop=True)
    day, filter_stats = apply_point_in_time_filters(day, signal_date, config, market_data or {})
    day["global_rank"] = range(1, len(day) + 1)
    if day.empty:
        if "history_bucket" not in day.columns:
            day["history_bucket"] = pd.Series(dtype=object)
        day["bucket_rank"] = pd.Series(dtype=int)
    else:
        day["bucket_rank"] = day.groupby("history_bucket")["score"].rank(method="first", ascending=False).astype(int)

    ranking_config = config.get("bucket_ranking", {})
    if ranking_config.get("enabled", False):
        return select_bucketed_top(day, ranking_config, top_n, config.get("industry_constraints", {})), filter_stats

    selected = day.head(top_n).copy()
    selected["selected_rank"] = range(1, len(selected) + 1)
    return selected, filter_stats


def apply_point_in_time_filters(
    day: pd.DataFrame,
    signal_date: pd.Timestamp,
    config: dict[str, Any],
    market_data: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    pit_config = config.get("backtest", {}).get("point_in_time_filters", {})
    if not pit_config.get("enabled", False):
        return day, {
            "candidate_count_before_pit": int(len(day)),
            "candidate_count_after_pit": int(len(day)),
            "pit_history_pass_count": int(len(day)),
            "pit_liquidity_pass_count": int(len(day)),
        }

    rows = []
    min_history_rows = int(pit_config.get("min_history_rows", config["universe"].get("min_history_rows", 1)))
    history_asof = bool(pit_config.get("history_bucket_asof", True))
    liquidity_asof = bool(pit_config.get("liquidity_asof", True))
    liquidity_config = pit_config.get("liquidity", config.get("liquidity_filter", {}))

    for row in day.to_dict("records"):
        symbol = str(row["symbol"]).upper()
        profile = build_asof_market_profile(symbol, market_data, signal_date)
        history_rows_asof = int(profile["rows"])
        if history_asof:
            row["history_bucket"] = assign_history_bucket(history_rows_asof, config.get("history_buckets", {}))
        row["history_rows_asof"] = history_rows_asof
        row["latest_close_asof"] = profile["latest_close"]
        row["avg_dollar_volume_20d_asof"] = profile["avg_dollar_volume_20d"]
        row["median_dollar_volume_60d_asof"] = profile["median_dollar_volume_60d"]
        row["zero_volume_ratio_60d_asof"] = profile["zero_volume_ratio_60d"]
        row["recent_trading_days_60d_asof"] = profile["recent_trading_days_60d"]

        history_reason = None if history_rows_asof >= min_history_rows else f"history_rows_asof < {min_history_rows}"
        liquidity_reason = liquidity_exclusion_reason(profile, liquidity_config) if liquidity_asof else None
        row["pit_history_pass"] = history_reason is None
        row["pit_liquidity_pass"] = liquidity_reason is None
        row["pit_exclusion_reason"] = history_reason or liquidity_reason
        rows.append(row)

    filtered = pd.DataFrame(rows)
    if filtered.empty:
        return filtered, {
            "candidate_count_before_pit": int(len(day)),
            "candidate_count_after_pit": 0,
            "pit_history_pass_count": 0,
            "pit_liquidity_pass_count": 0,
        }

    history_pass = filtered["pit_history_pass"]
    liquidity_pass = filtered["pit_liquidity_pass"]
    filtered = filtered[history_pass & liquidity_pass].copy()
    return filtered, {
        "candidate_count_before_pit": int(len(day)),
        "candidate_count_after_pit": int(len(filtered)),
        "pit_history_pass_count": int(history_pass.sum()),
        "pit_liquidity_pass_count": int(liquidity_pass.sum()),
    }


def build_asof_market_profile(
    symbol: str,
    market_data: dict[str, pd.DataFrame],
    signal_date: pd.Timestamp,
) -> dict[str, Any]:
    frame = market_data.get(symbol)
    if frame is None or frame.empty:
        return empty_asof_market_profile(symbol, "missing market data")

    working = frame[frame.index <= signal_date].copy()
    if working.empty:
        return empty_asof_market_profile(symbol, "no data as of signal date")

    working = working.dropna(subset=["close", "volume", "execution_price"])
    if working.empty:
        return empty_asof_market_profile(symbol, "no usable rows as of signal date")

    working["dollar_volume"] = working["execution_price"] * working["volume"]
    recent_20 = working.tail(20)
    recent_60 = working.tail(60)
    recent_60_count = int(len(recent_60))
    zero_volume_days = int((recent_60["volume"] <= 0).sum())
    return {
        "symbol": symbol,
        "rows": int(len(working)),
        "latest_close": float(working["close"].iloc[-1]),
        "avg_dollar_volume_20d": float(recent_20["dollar_volume"].mean()),
        "median_dollar_volume_60d": float(recent_60["dollar_volume"].median()),
        "zero_volume_ratio_60d": zero_volume_days / recent_60_count if recent_60_count else 1.0,
        "recent_trading_days_60d": recent_60_count,
        "exclusion_reason": None,
    }


def empty_asof_market_profile(symbol: str, reason: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "rows": 0,
        "latest_close": pd.NA,
        "avg_dollar_volume_20d": pd.NA,
        "median_dollar_volume_60d": pd.NA,
        "zero_volume_ratio_60d": pd.NA,
        "recent_trading_days_60d": 0,
        "exclusion_reason": reason,
    }


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
    return price_matrix_from_market_data(load_market_data(source_dir, price_column))


def load_market_data(source_dir: Path, price_column: str) -> dict[str, pd.DataFrame]:
    series = {}
    for csv_path in sorted(source_dir.glob("*.csv")):
        symbol = csv_path.stem.upper()
        usecols = ["date", "close", "volume"]
        if price_column not in usecols:
            usecols.append(price_column)
        frame = pd.read_csv(csv_path, usecols=usecols)
        frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
        frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
        frame["execution_price"] = pd.to_numeric(frame[price_column], errors="coerce")
        frame = frame.set_index("date").sort_index()
        series[symbol] = frame[["close", "volume", "execution_price"]]
    return series


def price_matrix_from_market_data(market_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    if not market_data:
        return pd.DataFrame()
    return pd.DataFrame({symbol: frame["execution_price"] for symbol, frame in market_data.items()}).sort_index()


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
    pit_columns = [
        "candidate_count_before_pit",
        "candidate_count_after_pit",
        "pit_history_pass_count",
        "pit_liquidity_pass_count",
    ]
    pit_stats = {
        f"avg_{column}": float(nav[column].mean())
        for column in pit_columns
        if column in nav.columns
    }
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
        "point_in_time_filters": config.get("point_in_time_filters", {}),
        **pit_stats,
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
