"""Simple non-overlapping TopK backtest for model scores."""

from __future__ import annotations

import math
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import yaml

try:
    from .data_sources.base import parse_float
    from .data_sources.nasdaq_public import NASDAQ_HISTORICAL_URL, fetch_json, nasdaq_history_window
    from .selection import select_bucketed_top
    from .selection.history_buckets import apply_score_calibration, assign_history_bucket, ranking_score_column
    from .selection.liquidity import liquidity_exclusion_reason
except ImportError:  # pragma: no cover - supports running the pipeline as a script.
    from data_sources.base import parse_float
    from data_sources.nasdaq_public import NASDAQ_HISTORICAL_URL, fetch_json, nasdaq_history_window
    from selection import select_bucketed_top
    from selection.history_buckets import apply_score_calibration, assign_history_bucket, ranking_score_column
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
                    "raw_score": row.get("raw_score", row.get("score")),
                    "adjusted_score": row.get("adjusted_score", row.get("score")),
                    "score_bucket_penalty": row.get("score_bucket_penalty"),
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
    nav_frame, benchmark_summary = attach_benchmark(nav_frame, config, paths, price_column)
    if benchmark_summary:
        summary["benchmark"] = benchmark_summary
    positions, attribution_summary = build_attribution(nav_frame, positions, paths, config)
    if attribution_summary:
        summary["attribution"] = attribution_summary
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
    before_calibration_count = len(day)
    day = apply_score_calibration(day, config)
    filter_stats["score_calibration_enabled"] = bool(config.get("score_calibration", {}).get("enabled", False))
    filter_stats["score_calibration_exclusion_count"] = int(before_calibration_count - len(day))
    score_column = ranking_score_column(day)
    day = day.sort_values(score_column, ascending=False).reset_index(drop=True)
    day["global_rank"] = range(1, len(day) + 1)
    if day.empty:
        if "history_bucket" not in day.columns:
            day["history_bucket"] = pd.Series(dtype=object)
        day["bucket_rank"] = pd.Series(dtype=int)
    else:
        day["bucket_rank"] = day.groupby("history_bucket")[score_column].rank(method="first", ascending=False).astype(int)

    ranking_config = config.get("bucket_ranking", {})
    if ranking_config.get("enabled", False):
        industry_constraints, constraint_stats = resolve_industry_constraints_for_signal(
            day,
            signal_ts=signal_date,
            config=config,
            market_data=market_data or {},
        )
        filter_stats.update(constraint_stats)
        return select_bucketed_top(day, ranking_config, top_n, industry_constraints), filter_stats

    selected = day.head(top_n).copy()
    selected["selected_rank"] = range(1, len(selected) + 1)
    return selected, filter_stats


def resolve_industry_constraints_for_signal(
    day: pd.DataFrame,
    signal_ts: pd.Timestamp,
    config: dict[str, Any],
    market_data: dict[str, pd.DataFrame],
) -> tuple[dict[str, Any], dict[str, Any]]:
    constraints = dict(config.get("industry_constraints", {}))
    if not constraints.get("enabled", False):
        return constraints, {
            "sector_momentum_tilt_enabled": False,
            "sector_momentum_tilted_sectors": "",
        }

    tilt = dict(constraints.get("sector_momentum_tilt", {}))
    if not tilt.get("enabled", False):
        return constraints, {
            "sector_momentum_tilt_enabled": False,
            "sector_momentum_tilted_sectors": "",
        }

    lookback_days = int(tilt.get("lookback_days", 60))
    top_sector_count = int(tilt.get("top_sector_count", 3))
    base_max_sector = int(tilt.get("base_max_sector", constraints.get("max_sector", 3)))
    extra_max_sector = int(tilt.get("extra_max_sector", 1))
    max_sector_cap = int(tilt.get("max_sector_cap", base_max_sector + extra_max_sector))
    tilted_max_sector = min(max_sector_cap, base_max_sector + extra_max_sector)
    sector_momentum = compute_sector_momentum(day, market_data, signal_ts, lookback_days)
    tilted_sectors = sector_momentum.head(top_sector_count)["sector"].tolist() if not sector_momentum.empty else []

    constraints["max_sector"] = base_max_sector
    constraints["max_sector_by_value"] = {sector: tilted_max_sector for sector in tilted_sectors}
    return constraints, {
        "sector_momentum_tilt_enabled": True,
        "sector_momentum_tilted_sectors": ",".join(tilted_sectors),
    }


def compute_sector_momentum(
    day: pd.DataFrame,
    market_data: dict[str, pd.DataFrame],
    signal_ts: pd.Timestamp,
    lookback_days: int,
) -> pd.DataFrame:
    if day.empty or "sector" not in day.columns or lookback_days <= 0:
        return pd.DataFrame(columns=["sector", "momentum_return", "symbol_count"])

    rows = []
    for row in day[["symbol", "sector"]].dropna(subset=["symbol"]).to_dict("records"):
        sector = str(row.get("sector") or "").strip()
        if not sector:
            continue
        symbol = str(row["symbol"]).upper()
        frame = market_data.get(symbol)
        if frame is None or frame.empty:
            continue
        usable = frame[frame.index <= signal_ts].dropna(subset=["execution_price"])
        if len(usable) <= lookback_days:
            continue
        start_price = usable["execution_price"].iloc[-lookback_days - 1]
        end_price = usable["execution_price"].iloc[-1]
        if pd.isna(start_price) or pd.isna(end_price) or float(start_price) <= 0:
            continue
        rows.append(
            {
                "sector": sector,
                "momentum_return": float(end_price) / float(start_price) - 1.0,
                "symbol": symbol,
            }
        )

    if not rows:
        return pd.DataFrame(columns=["sector", "momentum_return", "symbol_count"])
    frame = pd.DataFrame(rows)
    return (
        frame.groupby("sector", dropna=False)
        .agg(momentum_return=("momentum_return", "mean"), symbol_count=("symbol", "nunique"))
        .reset_index()
        .sort_values(["momentum_return", "symbol_count", "sector"], ascending=[False, False, True])
        .reset_index(drop=True)
    )


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


def attach_benchmark(
    nav: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
    price_column: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    benchmark_config = config.get("benchmark", {})
    if nav.empty or not benchmark_config.get("enabled", False):
        return nav, {}

    benchmark_prices = load_benchmark_prices(config, paths, price_column)
    if benchmark_prices.empty:
        return nav, {
            "enabled": True,
            "error": "missing_benchmark_prices",
            "config": benchmark_config,
        }

    enriched = nav.copy()
    benchmark_returns = []
    for row in enriched.itertuples(index=False):
        entry_date = pd.Timestamp(row.entry_date).normalize()
        exit_date = pd.Timestamp(row.exit_date).normalize()
        if entry_date not in benchmark_prices.index or exit_date not in benchmark_prices.index:
            benchmark_returns.append(math.nan)
            continue
        entry_price = benchmark_prices.loc[entry_date]
        exit_price = benchmark_prices.loc[exit_date]
        if pd.isna(entry_price) or pd.isna(exit_price) or float(entry_price) <= 0:
            benchmark_returns.append(math.nan)
            continue
        benchmark_returns.append(float(exit_price) / float(entry_price) - 1.0)

    enriched["benchmark_return"] = benchmark_returns
    enriched["excess_return"] = enriched["net_return"] - enriched["benchmark_return"]
    enriched["benchmark_nav"] = (1.0 + enriched["benchmark_return"].fillna(0.0)).cumprod()
    enriched["relative_nav"] = enriched["nav"] / enriched["benchmark_nav"]
    summary = summarize_benchmark(enriched, config, benchmark_config)
    return enriched, summary


def load_benchmark_prices(config: dict[str, Any], paths: dict[str, Path], price_column: str) -> pd.Series:
    benchmark_config = config.get("benchmark", {})
    source = benchmark_config.get("source", "nasdaq_public")
    if source == "csv":
        path = Path(benchmark_config["path"]).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
    elif source == "nasdaq_public":
        path = paths["benchmark_prices_csv"]
        if benchmark_config.get("refresh", False) or not path.exists():
            download_nasdaq_benchmark_prices(config, benchmark_config, path)
    elif source == "fred":
        path = paths["benchmark_prices_csv"]
        if benchmark_config.get("refresh", False) or not path.exists():
            download_fred_benchmark_prices(config, benchmark_config, path)
    else:
        raise ValueError("benchmark.source must be csv, fred, or nasdaq_public")

    if not path.exists():
        return pd.Series(dtype=float)
    frame = pd.read_csv(path)
    if price_column not in frame.columns:
        price_column = "close"
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame[price_column] = pd.to_numeric(frame[price_column], errors="coerce")
    frame = frame.dropna(subset=["date", price_column]).sort_values("date")
    return frame.set_index("date")[price_column]


def download_nasdaq_benchmark_prices(config: dict[str, Any], benchmark_config: dict[str, Any], output_path: Path) -> None:
    symbol = str(benchmark_config.get("symbol", "QQQ")).upper()
    asset_class = str(benchmark_config.get("asset_class", "etf"))
    from_date, to_date = nasdaq_history_window(config["data"])
    data = fetch_json(
        NASDAQ_HISTORICAL_URL.format(symbol=symbol),
        params={
            "assetclass": asset_class,
            "fromdate": from_date,
            "todate": to_date,
            "limit": "9999",
        },
        referer=f"https://www.nasdaq.com/market-activity/{asset_class}/{symbol.lower()}/historical",
    )
    rows = data.get("data", {}).get("tradesTable", {}).get("rows") or []
    parsed = []
    for row in rows:
        date = pd.to_datetime(row.get("date"), format="%m/%d/%Y", errors="coerce")
        open_ = parse_float(row.get("open"))
        high = parse_float(row.get("high"))
        low = parse_float(row.get("low"))
        close = parse_float(row.get("close"))
        volume = parse_float(row.get("volume"))
        if pd.isna(date) or any(pd.isna(value) for value in [open_, high, low, close, volume]):
            continue
        parsed.append(
            {
                "date": date.date().isoformat(),
                "symbol": symbol,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "vwap": (open_ + high + low + close) / 4,
                "volume": volume,
            }
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(parsed).sort_values("date").to_csv(output_path, index=False)


def download_fred_benchmark_prices(config: dict[str, Any], benchmark_config: dict[str, Any], output_path: Path) -> None:
    series_id = str(benchmark_config.get("series_id", benchmark_config.get("symbol", "NASDAQCOM"))).upper()
    from_date, to_date = nasdaq_history_window(config["data"])
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    frame = pd.read_csv(io.StringIO(response.text))
    value_column = series_id if series_id in frame.columns else frame.columns[-1]
    frame = frame.rename(columns={"observation_date": "date", value_column: "close"})
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame["close"] = pd.to_numeric(frame["close"].replace(".", pd.NA), errors="coerce")
    frame = frame.dropna(subset=["date", "close"])
    frame = frame[(frame["date"] >= pd.Timestamp(from_date)) & (frame["date"] <= pd.Timestamp(to_date))].copy()
    frame["symbol"] = series_id
    frame["open"] = frame["close"]
    frame["high"] = frame["close"]
    frame["low"] = frame["close"]
    frame["vwap"] = frame["close"]
    frame["volume"] = pd.NA
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame[["date", "symbol", "open", "high", "low", "close", "vwap", "volume"]].to_csv(output_path, index=False)


def summarize_benchmark(
    nav: pd.DataFrame,
    config: dict[str, Any],
    benchmark_config: dict[str, Any],
) -> dict[str, Any]:
    valid = nav.dropna(subset=["benchmark_return", "excess_return"]).copy()
    if valid.empty:
        return {
            "enabled": True,
            "error": "no_overlapping_benchmark_periods",
            "config": benchmark_config,
        }

    periods_per_year = float(config["backtest"].get("periods_per_year", 252 / int(config["backtest"]["rebalance_days"])))
    benchmark_returns = valid["benchmark_return"].astype(float)
    strategy_returns = valid["net_return"].astype(float)
    excess_returns = valid["excess_return"].astype(float)
    benchmark_cumulative_return = float((1.0 + benchmark_returns).prod() - 1.0)
    strategy_cumulative_return = float((1.0 + strategy_returns).prod() - 1.0)
    excess_cumulative_return = float(valid["relative_nav"].iloc[-1] - 1.0)
    benchmark_volatility = (
        float(benchmark_returns.std(ddof=1) * math.sqrt(periods_per_year)) if len(valid) > 1 else math.nan
    )
    excess_std = float(excess_returns.std(ddof=1)) if len(valid) > 1 else math.nan
    tracking_error = float(excess_std * math.sqrt(periods_per_year)) if len(valid) > 1 else math.nan
    relative_information_ratio = (
        float(excess_returns.mean() / excess_std * math.sqrt(periods_per_year))
        if len(valid) > 1 and not math.isclose(excess_std, 0.0)
        else math.nan
    )
    benchmark_drawdown = valid["benchmark_nav"] / valid["benchmark_nav"].cummax() - 1.0
    relative_drawdown = valid["relative_nav"] / valid["relative_nav"].cummax() - 1.0
    benchmark_variance = float(benchmark_returns.var(ddof=1)) if len(valid) > 1 else math.nan
    beta = (
        float(strategy_returns.cov(benchmark_returns) / benchmark_variance)
        if len(valid) > 1 and not math.isclose(benchmark_variance, 0.0)
        else math.nan
    )
    alpha_per_period = strategy_returns.mean() - beta * benchmark_returns.mean() if not math.isnan(beta) else math.nan
    alpha_annualized = float(alpha_per_period * periods_per_year) if not math.isnan(alpha_per_period) else math.nan
    correlation = float(strategy_returns.corr(benchmark_returns)) if len(valid) > 1 else math.nan
    return {
        "enabled": True,
        "symbol": benchmark_config.get("symbol", "QQQ"),
        "name": benchmark_config.get("name", benchmark_config.get("symbol", "QQQ")),
        "period_count": int(len(valid)),
        "strategy_cumulative_return": strategy_cumulative_return,
        "benchmark_cumulative_return": benchmark_cumulative_return,
        "excess_cumulative_return": excess_cumulative_return,
        "benchmark_annualized_return": float((1.0 + benchmark_cumulative_return) ** (periods_per_year / len(valid)) - 1.0),
        "benchmark_annualized_volatility": benchmark_volatility,
        "benchmark_max_drawdown": float(benchmark_drawdown.min()),
        "tracking_error": tracking_error,
        "relative_information_ratio": relative_information_ratio,
        "beta": beta,
        "alpha_annualized": alpha_annualized,
        "correlation": correlation,
        "relative_max_drawdown": float(relative_drawdown.min()),
        "avg_excess_return": float(excess_returns.mean()),
        "win_rate_vs_benchmark": float((excess_returns > 0).mean()),
        "config": benchmark_config,
    }


def build_attribution(
    nav: pd.DataFrame,
    positions: pd.DataFrame,
    paths: dict[str, Path],
    config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    attribution_config = config.get("attribution", {})
    if nav.empty or positions.empty or not attribution_config.get("enabled", True):
        write_empty_attribution_outputs(paths)
        return positions, {}

    enriched_positions = add_position_contributions(nav, positions)
    symbol_contribution = aggregate_position_contribution(enriched_positions, ["symbol"])
    sector_contribution = aggregate_position_contribution(enriched_positions, ["sector"])
    industry_contribution = aggregate_position_contribution(enriched_positions, ["industry"])
    sector_exposure = aggregate_exposure(enriched_positions, "sector")
    industry_exposure = aggregate_exposure(enriched_positions, "industry")
    top_n = int(attribution_config.get("top_n", 10))
    summary = summarize_attribution(symbol_contribution, sector_contribution, industry_contribution, top_n)

    output_frames = {
        "contribution_by_symbol": symbol_contribution,
        "contribution_by_sector": sector_contribution,
        "contribution_by_industry": industry_contribution,
        "exposure_by_sector": sector_exposure,
        "exposure_by_industry": industry_exposure,
    }
    for key, frame in output_frames.items():
        if key in paths:
            frame.to_csv(paths[key], index=False)
    if "contribution_summary" in paths:
        paths["contribution_summary"].write_text(
            yaml.safe_dump(summary, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    return enriched_positions, summary


def add_position_contributions(nav: pd.DataFrame, positions: pd.DataFrame) -> pd.DataFrame:
    period_costs = nav[["period", "cost_return", "net_return"]].copy()
    if "benchmark_return" in nav:
        period_costs["benchmark_return"] = nav["benchmark_return"]
    derived_columns = [
        "cost_return",
        "net_return",
        "benchmark_return",
        "gross_contribution",
        "cost_contribution",
        "net_contribution",
        "benchmark_contribution",
        "excess_contribution",
    ]
    enriched = positions.drop(columns=[column for column in derived_columns if column in positions], errors="ignore")
    enriched = enriched.merge(period_costs, on="period", how="left")
    enriched["gross_contribution"] = pd.to_numeric(enriched["weight"], errors="coerce") * pd.to_numeric(
        enriched["gross_return"],
        errors="coerce",
    )
    period_counts = enriched.groupby("period")["symbol"].transform("count").replace(0, pd.NA)
    enriched["cost_contribution"] = pd.to_numeric(enriched["cost_return"], errors="coerce").fillna(0.0) / period_counts
    enriched["net_contribution"] = enriched["gross_contribution"] - enriched["cost_contribution"]
    if "benchmark_return" in enriched:
        enriched["benchmark_contribution"] = pd.to_numeric(enriched["weight"], errors="coerce") * pd.to_numeric(
            enriched["benchmark_return"],
            errors="coerce",
        )
        enriched["excess_contribution"] = enriched["net_contribution"] - enriched["benchmark_contribution"]
    return enriched


def aggregate_position_contribution(positions: pd.DataFrame, group_columns: list[str]) -> pd.DataFrame:
    working = positions.copy()
    for column in group_columns:
        working[column] = working[column].fillna("UNKNOWN").replace("", "UNKNOWN")
    grouped = working.groupby(group_columns, dropna=False)
    result = grouped.agg(
        holding_count=("symbol", "size"),
        period_count=("period", "nunique"),
        avg_weight=("weight", "mean"),
        avg_score=("score", "mean"),
        avg_gross_return=("gross_return", "mean"),
        win_rate=("gross_return", lambda series: float((series > 0).mean())),
        gross_contribution_sum=("gross_contribution", "sum"),
        cost_contribution_sum=("cost_contribution", "sum"),
        net_contribution_sum=("net_contribution", "sum"),
        best_single_position_return=("gross_return", "max"),
        worst_single_position_return=("gross_return", "min"),
    ).reset_index()
    if "excess_contribution" in working.columns:
        excess = grouped["excess_contribution"].sum().reset_index(name="excess_contribution_sum")
        result = result.merge(excess, on=group_columns, how="left")
    return result.sort_values("net_contribution_sum", ascending=False).reset_index(drop=True)


def aggregate_exposure(positions: pd.DataFrame, group_column: str) -> pd.DataFrame:
    if group_column not in positions:
        return pd.DataFrame(columns=[group_column, "avg_weight", "max_weight", "period_count"])
    working = positions.copy()
    working[group_column] = working[group_column].fillna("UNKNOWN").replace("", "UNKNOWN")
    period_exposure = working.groupby(["period", group_column], dropna=False)["weight"].sum().reset_index()
    return (
        period_exposure.groupby(group_column, dropna=False)
        .agg(
            avg_weight=("weight", "mean"),
            max_weight=("weight", "max"),
            period_count=("period", "nunique"),
        )
        .reset_index()
        .sort_values("avg_weight", ascending=False)
        .reset_index(drop=True)
    )


def summarize_attribution(
    symbol_contribution: pd.DataFrame,
    sector_contribution: pd.DataFrame,
    industry_contribution: pd.DataFrame,
    top_n: int,
) -> dict[str, Any]:
    total_positive = float(symbol_contribution["net_contribution_sum"].clip(lower=0).sum()) if not symbol_contribution.empty else 0.0
    top_positive = (
        float(symbol_contribution["net_contribution_sum"].clip(lower=0).sort_values(ascending=False).head(5).sum())
        if not symbol_contribution.empty
        else 0.0
    )
    return {
        "enabled": True,
        "top_positive_contribution_share": top_positive / total_positive if total_positive > 0 else math.nan,
        "top_symbols": records_for_yaml(symbol_contribution.head(top_n), "symbol"),
        "bottom_symbols": records_for_yaml(symbol_contribution.sort_values("net_contribution_sum").head(top_n), "symbol"),
        "top_sectors": records_for_yaml(sector_contribution.head(top_n), "sector"),
        "bottom_sectors": records_for_yaml(sector_contribution.sort_values("net_contribution_sum").head(top_n), "sector"),
        "top_industries": records_for_yaml(industry_contribution.head(top_n), "industry"),
        "bottom_industries": records_for_yaml(industry_contribution.sort_values("net_contribution_sum").head(top_n), "industry"),
    }


def records_for_yaml(frame: pd.DataFrame, label_column: str) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    output_columns = [
        label_column,
        "holding_count",
        "period_count",
        "net_contribution_sum",
        "gross_contribution_sum",
        "win_rate",
        "avg_weight",
    ]
    if "excess_contribution_sum" in frame.columns:
        output_columns.append("excess_contribution_sum")
    records = []
    for row in frame[output_columns].to_dict("records"):
        records.append({key: normalize_yaml_scalar(value) for key, value in row.items()})
    return records


def normalize_yaml_scalar(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (int, str, bool)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def write_empty_attribution_outputs(paths: dict[str, Path]) -> None:
    for key in [
        "contribution_by_symbol",
        "contribution_by_sector",
        "contribution_by_industry",
        "exposure_by_sector",
        "exposure_by_industry",
    ]:
        if key in paths:
            pd.DataFrame().to_csv(paths[key], index=False)
    if "contribution_summary" in paths:
        paths["contribution_summary"].write_text(
            yaml.safe_dump({"enabled": False}, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )


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
        "score_calibration_exclusion_count",
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
    if "benchmark_summary" in paths:
        paths["benchmark_summary"].write_text(
            yaml.safe_dump(result.summary.get("benchmark", {}), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
