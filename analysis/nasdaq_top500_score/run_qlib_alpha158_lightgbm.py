"""Train a Qlib Alpha158 + LightGBM model for Nasdaq top-500 stocks.

The output is a model-scored ranking for the latest available date. This is a
research artifact for learning Qlib, not investment advice.
"""

from __future__ import annotations

import concurrent.futures
import csv
import io
import math
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests

WORKSPACE = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parent
SOURCE_DIR = ROOT / "qlib_source_csv"
QLIB_DIR = ROOT / "qlib_data"
PREDICTION_CSV = ROOT / "nasdaq_qlib_lightgbm_predictions.csv"
REPORT_MD = ROOT / "nasdaq_qlib_lightgbm_top5_report.md"

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
NASDAQ_SCREENER_URL = (
    "https://api.nasdaq.com/api/screener/stocks"
    "?tableonly=true&limit=25&offset=0&download=true&exchange=NASDAQ"
)
NASDAQ_HISTORICAL_URL = "https://api.nasdaq.com/api/quote/{symbol}/historical"
TOP_N = 500

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
}


def parse_float(value: Any) -> float:
    if value is None:
        return math.nan
    text = str(value).replace("$", "").replace(",", "").strip()
    if not text or text in {"--", "N/A"}:
        return math.nan
    try:
        return float(text)
    except ValueError:
        return math.nan


def fetch_json(url: str, *, params: dict[str, str] | None = None, referer: str = "", retries: int = 3) -> dict:
    last_error: Exception | None = None
    headers = {**HEADERS}
    if referer:
        headers["Referer"] = referer
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 - public endpoints are occasionally flaky.
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def fetch_text(url: str, *, retries: int = 3) -> str:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as exc:  # noqa: BLE001 - public endpoints are occasionally flaky.
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def load_top500_universe() -> pd.DataFrame:
    listed_text = fetch_text(NASDAQ_LISTED_URL)
    listed_symbols = set()
    reader = csv.DictReader(io.StringIO(listed_text.replace("\r\n", "\n")), delimiter="|")
    for row in reader:
        symbol = row.get("Symbol", "")
        if not symbol or symbol == "File Creation Time":
            continue
        if row.get("Test Issue") == "N" and row.get("ETF") == "N":
            listed_symbols.add(symbol)

    screener = fetch_json(
        NASDAQ_SCREENER_URL,
        referer="https://www.nasdaq.com/market-activity/stocks/screener",
    )
    frame = pd.DataFrame(screener["data"]["rows"])
    frame = frame[frame["symbol"].isin(listed_symbols)].copy()
    frame["market_cap"] = frame["marketCap"].map(parse_float)
    frame["last_sale"] = frame["lastsale"].map(parse_float)
    frame = frame[frame["market_cap"].notna() & (frame["market_cap"] > 0)]
    frame = frame.sort_values("market_cap", ascending=False).head(TOP_N)
    frame.to_csv(ROOT / "nasdaq_top500_universe.csv", index=False)
    return frame


def download_symbol_history(symbol: str) -> tuple[str, int, str | None]:
    params = {
        "assetclass": "stocks",
        "fromdate": (datetime.now().date() - timedelta(days=900)).isoformat(),
        "todate": datetime.now().date().isoformat(),
        "limit": "9999",
    }
    data = fetch_json(
        NASDAQ_HISTORICAL_URL.format(symbol=symbol),
        params=params,
        referer=f"https://www.nasdaq.com/market-activity/stocks/{symbol.lower()}/historical",
    )
    rows = data.get("data", {}).get("tradesTable", {}).get("rows")
    if not rows:
        return symbol, 0, "no rows"

    parsed = []
    for row in rows:
        date = datetime.strptime(row["date"], "%m/%d/%Y").date().isoformat()
        open_ = parse_float(row.get("open"))
        high = parse_float(row.get("high"))
        low = parse_float(row.get("low"))
        close = parse_float(row.get("close"))
        volume = parse_float(row.get("volume"))
        if any(pd.isna(x) for x in [open_, high, low, close, volume]):
            continue
        parsed.append(
            {
                "date": date,
                "symbol": symbol,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "vwap": (open_ + high + low + close) / 4,
                "volume": volume,
            }
        )
    if len(parsed) < 180:
        return symbol, len(parsed), "history < 180 rows"

    frame = pd.DataFrame(parsed).sort_values("date")
    frame.to_csv(SOURCE_DIR / f"{symbol}.csv", index=False)
    return symbol, len(frame), None


def prepare_source_csv(universe: pd.DataFrame) -> pd.DataFrame:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    failures = []
    symbols = list(universe["symbol"])
    print(f"Downloading Nasdaq historical OHLCV for {len(symbols)} symbols...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_symbol = {executor.submit(download_symbol_history, symbol): symbol for symbol in symbols}
        for index, future in enumerate(concurrent.futures.as_completed(future_to_symbol), start=1):
            symbol, rows, error = future.result()
            if error:
                failures.append({"symbol": symbol, "rows": rows, "error": error})
            if index % 50 == 0 or index == len(symbols):
                print(f"Downloaded {index}/{len(symbols)}; failures/skips: {len(failures)}")

    pd.DataFrame(failures).to_csv(ROOT / "nasdaq_qlib_download_failures.csv", index=False)
    return pd.DataFrame(failures)


def dump_qlib_bin() -> None:
    if QLIB_DIR.exists():
        shutil.rmtree(QLIB_DIR)
    sys.path.insert(0, str(WORKSPACE))
    from scripts.dump_bin import DumpDataAll

    print("Dumping CSV files into Qlib bin format...")
    dumper = DumpDataAll(
        data_path=str(SOURCE_DIR),
        qlib_dir=str(QLIB_DIR),
        freq="day",
        max_workers=8,
        date_field_name="date",
        symbol_field_name="symbol",
        exclude_fields="date,symbol",
        file_suffix=".csv",
    )
    dumper.dump()


def choose_segments() -> dict[str, tuple[str, str]]:
    calendar = pd.read_csv(QLIB_DIR / "calendars/day.txt", header=None)[0]
    dates = pd.to_datetime(calendar).sort_values().reset_index(drop=True)
    if len(dates) < 300:
        raise RuntimeError(f"not enough trading dates for model training: {len(dates)}")

    train_end = dates.iloc[int(len(dates) * 0.62)].strftime("%Y-%m-%d")
    valid_start = dates.iloc[int(len(dates) * 0.62) + 1].strftime("%Y-%m-%d")
    valid_end = dates.iloc[int(len(dates) * 0.80)].strftime("%Y-%m-%d")
    test_start = dates.iloc[int(len(dates) * 0.80) + 1].strftime("%Y-%m-%d")
    return {
        "fit": (dates.iloc[0].strftime("%Y-%m-%d"), train_end),
        "all": (dates.iloc[0].strftime("%Y-%m-%d"), dates.iloc[-1].strftime("%Y-%m-%d")),
        "train": (dates.iloc[60].strftime("%Y-%m-%d"), train_end),
        "valid": (valid_start, valid_end),
        "test": (test_start, dates.iloc[-1].strftime("%Y-%m-%d")),
    }


def train_and_predict(universe: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    sys.path.insert(0, str(WORKSPACE))

    import qlib
    from qlib.constant import REG_US
    from qlib.contrib.data.handler import Alpha158
    from qlib.contrib.model.gbdt import LGBModel
    from qlib.data.dataset import DatasetH
    from qlib.data.dataset.handler import DataHandlerLP

    qlib.init(
        provider_uri=str(QLIB_DIR),
        region=REG_US,
        expression_cache=None,
        dataset_cache=None,
    )
    segments = choose_segments()
    print(f"Segments: {segments}")

    handler = Alpha158(
        instruments="all",
        start_time=segments["all"][0],
        end_time=segments["all"][1],
        fit_start_time=segments["fit"][0],
        fit_end_time=segments["fit"][1],
        freq="day",
    )
    dataset = DatasetH(
        handler=handler,
        segments={
            "train": segments["train"],
            "valid": segments["valid"],
            "test": segments["test"],
        },
    )
    model = LGBModel(
        loss="mse",
        learning_rate=0.05,
        num_leaves=64,
        max_depth=8,
        n_estimators=300,
        subsample=0.85,
        colsample_bytree=0.85,
        lambda_l1=1.0,
        lambda_l2=10.0,
        num_threads=8,
    )
    print("Training Qlib LGBModel on Alpha158 features...")
    model.fit(dataset)
    pred = model.predict(dataset, segment="test")
    pred.name = "score"

    pred_frame = pred.reset_index()
    pred_frame.columns = ["datetime", "instrument", "score"]
    latest_date = pred_frame["datetime"].max()
    latest = pred_frame[pred_frame["datetime"] == latest_date].copy()
    latest["symbol"] = latest["instrument"].astype(str).str.upper()
    merged = latest.merge(universe, on="symbol", how="left")
    merged = merged.sort_values("score", ascending=False)
    merged.to_csv(PREDICTION_CSV, index=False)

    label = dataset.prepare("test", col_set="label", data_key=DataHandlerLP.DK_L)
    label_series = label.iloc[:, 0] if isinstance(label, pd.DataFrame) else label
    aligned = pd.concat([pred.rename("pred"), label_series.rename("label")], axis=1).dropna()
    if aligned.empty:
        ic_mean = math.nan
        rank_ic_mean = math.nan
        ic_count = 0
    else:
        ic = aligned.groupby(level="datetime").apply(lambda x: x["pred"].corr(x["label"]))
        rank_ic = aligned.groupby(level="datetime").apply(lambda x: x["pred"].corr(x["label"], method="spearman"))
        ic_mean = float(ic.mean())
        rank_ic_mean = float(rank_ic.mean())
        ic_count = int(ic.notna().sum())

    meta = {
        "segments": segments,
        "latest_date": str(pd.Timestamp(latest_date).date()),
        "prediction_count": int(len(merged)),
        "ic_mean": ic_mean,
        "rank_ic_mean": rank_ic_mean,
        "ic_count": ic_count,
    }
    return merged, meta


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


def write_report(predictions: pd.DataFrame, meta: dict[str, Any], failures: pd.DataFrame) -> None:
    top5 = predictions.head(5)
    lines = [
        "# Nasdaq Top 500 Qlib Alpha158 LightGBM Report",
        "",
        f"Generated at: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        "## 结论口径",
        "",
        "- 这次结果经过了 Qlib 模型流程：Qlib 数据格式、Alpha158 特征、LightGBM 模型训练、最新日预测分数排序。",
        "- 股票池：Nasdaq-listed、非 ETF、非测试证券，并按 Nasdaq screener 总市值取前 500。",
        "- 标签：Qlib Alpha158 默认标签，即预测未来短期收益 `Ref($close, -2)/Ref($close, -1)-1`。",
        "- 价格数据：Nasdaq historical endpoint 的近 2 年日线 OHLCV；`vwap` 用 OHLC 均值近似。",
        "- 结果是研究模型分数，不是投资建议。",
        "",
        "## 训练区间",
        "",
        f"- Train: {meta['segments']['train'][0]} 到 {meta['segments']['train'][1]}",
        f"- Valid: {meta['segments']['valid'][0]} 到 {meta['segments']['valid'][1]}",
        f"- Test: {meta['segments']['test'][0]} 到 {meta['segments']['test'][1]}",
        f"- 最新预测日：{meta['latest_date']}",
        "",
        "## Top 5",
        "",
        "| Rank | Symbol | Name | Qlib Score | Market Cap | Last Sale | Sector | Industry |",
        "|---:|---|---|---:|---:|---:|---|---|",
    ]
    for rank, row in enumerate(top5.itertuples(index=False), start=1):
        lines.append(
            "| {rank} | {symbol} | {name} | {score:.8f} | {market_cap} | {last_sale:.2f} | {sector} | {industry} |".format(
                rank=rank,
                symbol=row.symbol,
                name=str(row.name).replace("|", "/"),
                score=row.score,
                market_cap=fmt_money(row.market_cap),
                last_sale=row.last_sale if not pd.isna(row.last_sale) else math.nan,
                sector=str(row.sector).replace("|", "/"),
                industry=str(row.industry).replace("|", "/"),
            )
        )

    lines.extend(
        [
            "",
            "## 模型验证",
            "",
            f"- Test 日均 IC：{meta['ic_mean']:.6f}" if not math.isnan(meta["ic_mean"]) else "- Test 日均 IC：N/A",
            f"- Test 日均 Rank IC：{meta['rank_ic_mean']:.6f}" if not math.isnan(meta["rank_ic_mean"]) else "- Test 日均 Rank IC：N/A",
            f"- 参与 IC 计算的交易日：{meta['ic_count']}",
            "",
            "IC 可以粗略理解为：模型预测分数和真实后续收益的相关性。它不是收益率，样本短时尤其容易不稳定。",
            "",
            "## 怎么读",
            "",
            "- 当前排名代表：在这个股票池里，模型认为这些股票的下一期相对收益分数更高。",
            "- 模型只看价格和成交量派生出来的 Alpha158，没有看财报、估值、新闻、宏观和行业基本面。",
            "- 这份结果适合作为学习 Qlib 流程的样例；实盘前还需要更长历史、更干净复权数据、交易成本、回测和风控。",
            "",
            "## 文件",
            "",
            "- `qlib_source_csv/`：每只股票的原始日线 CSV。",
            "- `qlib_data/`：转换后的 Qlib bin 数据。",
            "- `nasdaq_qlib_lightgbm_predictions.csv`：最新日全部模型分数。",
            "- `nasdaq_qlib_lightgbm_top5_report.md`：本报告。",
            "- `nasdaq_qlib_download_failures.csv`：下载失败或历史不足的股票。",
            "",
            "## 数据质量",
            "",
            f"- 最新日可预测股票数：{meta['prediction_count']}。",
            f"- 下载失败或历史不足：{len(failures)}。",
        ]
    )
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    universe = load_top500_universe()
    failures = prepare_source_csv(universe)
    dump_qlib_bin()
    predictions, meta = train_and_predict(universe)
    write_report(predictions, meta, failures)
    print("Qlib model top 5:")
    print(predictions[["symbol", "name", "score", "market_cap", "sector", "industry"]].head(5).to_string(index=False))
    print(f"Report: {REPORT_MD}")


if __name__ == "__main__":
    main()
