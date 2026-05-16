"""Build a Nasdaq-listed top-500 market-cap momentum score report.

This is a research/learning helper, not investment advice. It uses public web
endpoints and a transparent technical scoring formula so the result can be
reproduced and challenged.
"""

from __future__ import annotations

import concurrent.futures
import csv
import io
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parent
NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
NASDAQ_SCREENER_URL = (
    "https://api.nasdaq.com/api/screener/stocks"
    "?tableonly=true&limit=25&offset=0&download=true&exchange=NASDAQ"
)
NASDAQ_HISTORICAL_URL = "https://api.nasdaq.com/api/quote/{symbol}/historical"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


@dataclass(frozen=True)
class PriceFeatures:
    symbol: str
    latest_date: str
    latest_close: float
    history_days: int
    ret_12m: float
    ret_12m_ex_1m: float
    ret_6m: float
    ret_3m: float
    ret_1m: float
    ma200_gap: float
    vol_3m: float
    max_drawdown_1y: float
    risk_adjusted_6m: float


def parse_market_cap(value: Any) -> float:
    if value is None:
        return math.nan
    text = str(value).replace("$", "").replace(",", "").strip()
    if not text or text in {"--", "N/A"}:
        return math.nan
    try:
        return float(text)
    except ValueError:
        return math.nan


def parse_last_sale(value: Any) -> float:
    if value is None:
        return math.nan
    text = str(value).replace("$", "").replace(",", "").strip()
    if not text or text in {"--", "N/A"}:
        return math.nan
    try:
        return float(text)
    except ValueError:
        return math.nan


def fetch_text(url: str, *, retries: int = 3) -> str:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as exc:  # noqa: BLE001 - report public data failures.
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def fetch_json(url: str, *, retries: int = 3) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 - report public data failures.
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def load_nasdaq_listed_symbols() -> pd.DataFrame:
    text = fetch_text(NASDAQ_LISTED_URL)
    rows = []
    reader = csv.DictReader(io.StringIO(text.replace("\r\n", "\n")), delimiter="|")
    for row in reader:
        symbol = row.get("Symbol", "")
        if not symbol or symbol == "File Creation Time":
            continue
        if row.get("Test Issue") != "N":
            continue
        if row.get("ETF") != "N":
            continue
        rows.append(row)
    return pd.DataFrame(rows)


def load_nasdaq_screener() -> pd.DataFrame:
    data = fetch_json(NASDAQ_SCREENER_URL)
    rows = data["data"]["rows"]
    frame = pd.DataFrame(rows)
    frame["market_cap"] = frame["marketCap"].map(parse_market_cap)
    frame["last_sale"] = frame["lastsale"].map(parse_last_sale)
    frame["volume_num"] = pd.to_numeric(frame["volume"], errors="coerce")
    return frame


def compute_features(symbol: str) -> PriceFeatures | None:
    params = {
        "assetclass": "stocks",
        "fromdate": (datetime.now().date() - timedelta(days=800)).isoformat(),
        "todate": datetime.now().date().isoformat(),
        "limit": "9999",
    }
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.get(
                NASDAQ_HISTORICAL_URL.format(symbol=symbol),
                params=params,
                headers={
                    **HEADERS,
                    "Origin": "https://www.nasdaq.com",
                    "Referer": f"https://www.nasdaq.com/market-activity/stocks/{symbol.lower()}/historical",
                },
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            rows = (
                payload.get("data", {})
                .get("tradesTable", {})
                .get("rows")
            )
            if not rows:
                return None

            price_rows = []
            for row in rows:
                close = parse_last_sale(row.get("close"))
                if pd.isna(close):
                    continue
                price_rows.append(
                    {
                        "date": datetime.strptime(row["date"], "%m/%d/%Y").date(),
                        "close": close,
                    }
                )
            if len(price_rows) < 180:
                return None
            prices = pd.DataFrame(price_rows).drop_duplicates("date").sort_values("date")
            closes = prices["close"].astype(float)
            daily_returns = closes.pct_change().dropna()
            latest_close = float(closes.iloc[-1])

            def period_return(days: int) -> float:
                if len(closes) <= days:
                    return latest_close / float(closes.iloc[0]) - 1
                return latest_close / float(closes.iloc[-days]) - 1

            one_year = closes.tail(min(252, len(closes)))
            running_max = one_year.cummax()
            drawdowns = one_year / running_max - 1
            vol_window = daily_returns.tail(min(63, len(daily_returns)))
            vol_3m = float(vol_window.std() * math.sqrt(252)) if len(vol_window) > 5 else math.nan
            ret_6m = period_return(126)
            ma200 = float(closes.tail(min(200, len(closes))).mean())
            risk_adjusted = ret_6m / vol_3m if vol_3m and not math.isnan(vol_3m) else math.nan
            ret_1m = period_return(21)

            return PriceFeatures(
                symbol=symbol,
                latest_date=str(prices["date"].iloc[-1]),
                latest_close=latest_close,
                history_days=len(closes),
                ret_12m=period_return(252),
                ret_12m_ex_1m=period_return(252) - ret_1m,
                ret_6m=ret_6m,
                ret_3m=period_return(63),
                ret_1m=ret_1m,
                ma200_gap=latest_close / ma200 - 1,
                vol_3m=vol_3m,
                max_drawdown_1y=float(drawdowns.min()),
                risk_adjusted_6m=risk_adjusted,
            )
        except Exception as exc:  # noqa: BLE001 - public endpoint can be flaky.
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    print(f"price fetch failed for {symbol}: {last_error}")
    return None


def percentile_rank(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    ranked = series.rank(pct=True, ascending=higher_is_better)
    return (ranked * 100).fillna(0)


def add_score(frame: pd.DataFrame) -> pd.DataFrame:
    scored = frame.copy()
    scored["score"] = (
        percentile_rank(scored["ret_12m_ex_1m"]) * 0.30
        + percentile_rank(scored["ret_6m"]) * 0.20
        + percentile_rank(scored["ret_3m"]) * 0.15
        + percentile_rank(scored["ma200_gap"]) * 0.15
        + percentile_rank(scored["risk_adjusted_6m"]) * 0.10
        + percentile_rank(scored["max_drawdown_1y"]) * 0.10
    )
    return scored.sort_values("score", ascending=False)


def fmt_pct(value: float) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{value * 100:.2f}%"


def fmt_money(value: float) -> str:
    if pd.isna(value):
        return "N/A"
    if value >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value:,.0f}"


def write_report(scored: pd.DataFrame, universe: pd.DataFrame, failures: list[str]) -> None:
    top5 = scored.head(5)
    lines = [
        "# Nasdaq Top 500 Market-Cap Score Report",
        "",
        f"Generated at: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        "## 口径",
        "",
        "- 这是一份学习用量化研究榜单，不是投资建议。",
        "- 股票池：NasdaqTrader 当前 Nasdaq-listed、非 ETF、非测试证券。",
        "- 初筛：用 Nasdaq screener 的 marketCap 字段取总市值最高 500 只。",
        "- 历史价格：Nasdaq historical endpoint 的近 2 年日线收盘价。",
        "- 只保留至少 180 个交易日历史价格的股票。",
        "- 双重股权类别按独立交易代码保留，例如 GOOG 与 GOOGL。",
        "",
        "## 打分公式",
        "",
        "总分采用横截面百分位排名，满分 100：",
        "",
        "- 12 个月动量扣除近 1 个月：30%",
        "- 6 个月收益：20%",
        "- 3 个月收益：15%",
        "- 当前价格相对 200 日均线：15%",
        "- 6 个月收益 / 3 个月年化波动：10%",
        "- 近 1 年最大回撤控制：10%",
        "",
        "这个公式偏向趋势和风险调整后的强势股，不是价值投资评分，也没有使用财报、估值、新闻或分析师预测。",
        "",
        "## Top 5",
        "",
        "| Rank | Symbol | Name | Score | Market Cap | Close | 12M | 6M | 3M | 1M | 3M Vol | Max DD 1Y | Sector |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for idx, row in enumerate(top5.itertuples(index=False), start=1):
        lines.append(
            "| {rank} | {symbol} | {name} | {score:.2f} | {market_cap} | "
            "{close:.2f} | {ret12} | {ret6} | {ret3} | {ret1} | {vol} | {dd} | {sector} |".format(
                rank=idx,
                symbol=row.symbol,
                name=str(row.name).replace("|", "/"),
                score=row.score,
                market_cap=fmt_money(row.market_cap),
                close=row.latest_close,
                ret12=fmt_pct(row.ret_12m),
                ret6=fmt_pct(row.ret_6m),
                ret3=fmt_pct(row.ret_3m),
                ret1=fmt_pct(row.ret_1m),
                vol=fmt_pct(row.vol_3m),
                dd=fmt_pct(row.max_drawdown_1y),
                sector=str(row.sector).replace("|", "/"),
            )
        )

    lines.extend(
        [
            "",
            "## 怎么读这个结果",
            "",
            "- 排名靠前代表：在当前 Nasdaq 大市值股票池里，最近中期趋势强、站在长期均线上方，并且风险调整后表现较好。",
            "- 它不代表：公司一定被低估、未来一定上涨、适合你的账户买入。",
            "- 下一步应补充：估值、盈利质量、行业景气、财报事件、仓位上限、止损规则，以及与 QQQ/SPY 的相对强弱比较。",
            "",
            "## 文件",
            "",
            "- `nasdaq_top500_universe.csv`：总市值前 500 股票池。",
            "- `nasdaq_top500_scored.csv`：完成历史价格计算后的打分表。",
            "- `nasdaq_top5_report.md`：本报告。",
            "",
            "## 数据质量提示",
            "",
            f"- 初筛股票数：{len(universe)}。",
            f"- 可评分股票数：{len(scored)}。",
            f"- 历史价格抓取失败或历史不足：{len(failures)}。",
            "- 免费公开接口可能存在延迟、字段缺失、复权口径差异；正式交易前应使用付费且可审计的数据源复核。",
        ]
    )
    if failures:
        lines.extend(["", "失败/跳过样例：", ", ".join(failures[:30])])

    (ROOT / "nasdaq_top5_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    listed = load_nasdaq_listed_symbols()
    screener = load_nasdaq_screener()

    listed_symbols = set(listed["Symbol"])
    merged = screener[screener["symbol"].isin(listed_symbols)].copy()
    merged = merged[merged["market_cap"].notna() & (merged["market_cap"] > 0)]
    merged = merged.sort_values("market_cap", ascending=False).head(500)
    merged.to_csv(ROOT / "nasdaq_top500_universe.csv", index=False)

    print(f"Nasdaq-listed symbols: {len(listed_symbols)}")
    print(f"Screener rows after Nasdaq-listed filter: {len(merged)}")
    print("Fetching 2y daily prices for top 500...")

    features: list[PriceFeatures] = []
    failures: list[str] = []
    symbols = list(merged["symbol"])
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        future_to_symbol = {executor.submit(compute_features, symbol): symbol for symbol in symbols}
        for i, future in enumerate(concurrent.futures.as_completed(future_to_symbol), start=1):
            symbol = future_to_symbol[future]
            result = future.result()
            if result is None:
                failures.append(symbol)
            else:
                features.append(result)
            if i % 50 == 0 or i == len(symbols):
                print(f"Fetched {i}/{len(symbols)}; scored candidates so far: {len(features)}")

    feature_frame = pd.DataFrame([feature.__dict__ for feature in features])
    full = merged.merge(feature_frame, on="symbol", how="inner")
    scored = add_score(full)
    scored.to_csv(ROOT / "nasdaq_top500_scored.csv", index=False)
    write_report(scored, merged, failures)
    print("Top 5:")
    print(
        scored[
            [
                "symbol",
                "name",
                "score",
                "market_cap",
                "latest_close",
                "ret_12m",
                "ret_6m",
                "ret_3m",
                "vol_3m",
                "max_drawdown_1y",
            ]
        ]
        .head(5)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
