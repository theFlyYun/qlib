"""Run a config-driven Qlib Alpha158 + LightGBM Nasdaq experiment.

The output is a model-scored ranking for the latest available date. This is a
research artifact for learning Qlib, not investment advice.
"""

from __future__ import annotations

import argparse
import math
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

try:
    from data_sources import DataSourceUnavailable, create_data_source
except ImportError:  # pragma: no cover - supports importing this script as a module in tests.
    from analysis.nasdaq_top500_score.data_sources import DataSourceUnavailable, create_data_source

WORKSPACE = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "configs" / "nasdaq_alpha158_lgbm_1d.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"YAML experiment config. Defaults to {DEFAULT_CONFIG}",
    )
    return parser.parse_args()


def resolve_path(path_text: str | Path) -> Path:
    path = Path(path_text).expanduser()
    if path.is_absolute():
        return path
    return WORKSPACE / path


def load_config(config_path: Path) -> dict[str, Any]:
    resolved_path = resolve_path(config_path)
    with resolved_path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    required_sections = [
        "experiment",
        "universe",
        "data",
        "label",
        "features",
        "split",
        "model",
        "report",
    ]
    missing = [section for section in required_sections if section not in config]
    if missing:
        raise ValueError(f"missing config section(s): {', '.join(missing)}")

    config["_config_path"] = str(resolved_path)
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    source = config["data"]["source"]
    if source not in {"nasdaq_public", "norgate"}:
        raise ValueError("supported data.source values: nasdaq_public, norgate")
    if source == "nasdaq_public" and config["universe"]["exchange"] != "NASDAQ":
        raise ValueError("nasdaq_public currently supports universe.exchange: NASDAQ")
    if source == "norgate":
        required_universe_keys = ["index_name", "index_symbol", "candidate_databases", "min_history_rows"]
        required_data_keys = ["start_date", "price_adjustment", "padding", "vwap_method"]
        missing = [key for key in required_universe_keys if key not in config["universe"]]
        missing.extend(key for key in required_data_keys if key not in config["data"])
        if missing:
            raise ValueError(f"norgate config missing key(s): {', '.join(missing)}")
    if config["data"]["freq"] != "day":
        raise ValueError("currently supports data.freq: day")
    if config["data"]["vwap_method"] != "ohlc_mean":
        raise ValueError("currently supports data.vwap_method: ohlc_mean")
    if config["features"]["handler"] != "Alpha158":
        raise ValueError("currently supports features.handler: Alpha158")
    if config["model"]["class"] != "LGBModel":
        raise ValueError("currently supports model.class: LGBModel")
    if config["split"]["method"] != "ratio":
        raise ValueError("currently supports split.method: ratio")

    train_ratio = float(config["split"]["train_ratio"])
    valid_ratio = float(config["split"]["valid_ratio"])
    test_ratio = float(config["split"]["test_ratio"])
    if not math.isclose(train_ratio + valid_ratio + test_ratio, 1.0, rel_tol=0, abs_tol=1e-6):
        raise ValueError("split train_ratio + valid_ratio + test_ratio must equal 1.0")


def build_paths(config: dict[str, Any]) -> dict[str, Path]:
    output_dir = resolve_path(config["experiment"]["output_dir"])
    return {
        "output_dir": output_dir,
        "source_dir": output_dir / "qlib_source_csv",
        "qlib_dir": output_dir / "qlib_data",
        "universe_csv": output_dir / "universe.csv",
        "failures_csv": output_dir / "download_failures.csv",
        "membership_csv": output_dir / "membership.csv",
        "predictions_csv": output_dir / "predictions.csv",
        "report_md": output_dir / "report.md",
        "resolved_config": output_dir / "resolved_config.yaml",
    }


def write_resolved_config(config: dict[str, Any], paths: dict[str, Path]) -> None:
    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    resolved = {key: value for key, value in config.items() if not key.startswith("_")}
    resolved["_metadata"] = {
        "config_path": config["_config_path"],
        "output_dir_absolute": str(paths["output_dir"]),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    paths["resolved_config"].write_text(
        yaml.safe_dump(resolved, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def dump_qlib_bin(config: dict[str, Any], paths: dict[str, Path]) -> None:
    qlib_dir = paths["qlib_dir"]
    if qlib_dir.exists():
        shutil.rmtree(qlib_dir)
    sys.path.insert(0, str(WORKSPACE))
    from scripts.dump_bin import DumpDataAll

    print("Dumping CSV files into Qlib bin format...")
    dumper = DumpDataAll(
        data_path=str(paths["source_dir"]),
        qlib_dir=str(qlib_dir),
        freq=config["data"]["freq"],
        max_workers=8,
        date_field_name="date",
        symbol_field_name="symbol",
        exclude_fields="date,symbol",
        file_suffix=".csv",
    )
    dumper.dump()


def choose_segments(config: dict[str, Any], paths: dict[str, Path]) -> dict[str, tuple[str, str]]:
    calendar = pd.read_csv(paths["qlib_dir"] / "calendars/day.txt", header=None)[0]
    dates = pd.to_datetime(calendar).sort_values().reset_index(drop=True)
    warmup_days = int(config["split"]["warmup_days"])
    if len(dates) < max(300, warmup_days + 30):
        raise RuntimeError(f"not enough trading dates for model training: {len(dates)}")

    train_ratio = float(config["split"]["train_ratio"])
    valid_ratio = float(config["split"]["valid_ratio"])
    train_end_idx = int(len(dates) * train_ratio)
    valid_end_idx = int(len(dates) * (train_ratio + valid_ratio))
    if train_end_idx <= warmup_days or valid_end_idx <= train_end_idx + 1 or valid_end_idx >= len(dates) - 1:
        raise RuntimeError("split ratios leave an invalid train/valid/test segment")

    train_end = dates.iloc[train_end_idx].strftime("%Y-%m-%d")
    valid_start = dates.iloc[train_end_idx + 1].strftime("%Y-%m-%d")
    valid_end = dates.iloc[valid_end_idx].strftime("%Y-%m-%d")
    test_start = dates.iloc[valid_end_idx + 1].strftime("%Y-%m-%d")
    return {
        "fit": (dates.iloc[0].strftime("%Y-%m-%d"), train_end),
        "all": (dates.iloc[0].strftime("%Y-%m-%d"), dates.iloc[-1].strftime("%Y-%m-%d")),
        "train": (dates.iloc[warmup_days].strftime("%Y-%m-%d"), train_end),
        "valid": (valid_start, valid_end),
        "test": (test_start, dates.iloc[-1].strftime("%Y-%m-%d")),
    }


def train_and_predict(
    universe: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    sys.path.insert(0, str(WORKSPACE))

    import qlib
    from qlib.constant import REG_US
    from qlib.contrib.data.handler import Alpha158
    from qlib.contrib.model.gbdt import LGBModel
    from qlib.data.dataset import DatasetH
    from qlib.data.dataset.handler import DataHandlerLP

    qlib.init(
        provider_uri=str(paths["qlib_dir"]),
        region=REG_US,
        expression_cache=None,
        dataset_cache=None,
    )
    segments = choose_segments(config, paths)
    print(f"Segments: {segments}")

    handler = Alpha158(
        instruments=config["features"]["instruments"],
        start_time=segments["all"][0],
        end_time=segments["all"][1],
        fit_start_time=segments["fit"][0],
        fit_end_time=segments["fit"][1],
        freq=config["data"]["freq"],
        label=([config["label"]["expression"]], [config["label"]["name"]]),
    )
    dataset = DatasetH(
        handler=handler,
        segments={
            "train": segments["train"],
            "valid": segments["valid"],
            "test": segments["test"],
        },
    )
    model = LGBModel(**config["model"]["kwargs"])
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
    merged.to_csv(paths["predictions_csv"], index=False)

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


def fmt_optional_money(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/A"
    return fmt_money(numeric)


def format_yaml_block(value: Any) -> list[str]:
    dumped = yaml.safe_dump(value, allow_unicode=True, sort_keys=False).strip()
    return ["```yaml", dumped, "```"]


def write_report(
    predictions: pd.DataFrame,
    meta: dict[str, Any],
    failures: pd.DataFrame,
    config: dict[str, Any],
    paths: dict[str, Path],
) -> None:
    top_n = int(config["report"]["top_n"])
    top_predictions = predictions.head(top_n)
    model_kwargs = config["model"]["kwargs"]
    lines = [
        f"# {config['experiment']['name']} Report",
        "",
        f"Generated at: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        "## 结论口径",
        "",
        "- 这次结果经过了 Qlib 模型流程：Qlib 数据格式、Alpha158 特征、LightGBM 模型训练、最新日预测分数排序。",
        "- 结果是学习研究材料，不是投资建议。",
        "",
        "## 实验名",
        "",
        f"- `{config['experiment']['name']}`",
        "",
        "## 股票池规则",
        "",
        *format_yaml_block(config["universe"]),
        "",
        "## 数据口径",
        "",
        *format_yaml_block(config["data"]),
        "",
        "## 标签与特征",
        "",
        f"- 标签名：`{config['label']['name']}`",
        f"- 标签表达式：`{config['label']['expression']}`",
        f"- 特征处理器：`{config['features']['handler']}`",
        f"- 特征股票范围：`{config['features']['instruments']}`",
        "",
        "## 模型参数",
        "",
        *format_yaml_block(model_kwargs),
        "",
        "## 训练/验证/测试区间",
        "",
        f"- Fit: {meta['segments']['fit'][0]} 到 {meta['segments']['fit'][1]}",
        f"- Train: {meta['segments']['train'][0]} 到 {meta['segments']['train'][1]}",
        f"- Valid: {meta['segments']['valid'][0]} 到 {meta['segments']['valid'][1]}",
        f"- Test: {meta['segments']['test'][0]} 到 {meta['segments']['test'][1]}",
        f"- 最新预测日：{meta['latest_date']}",
        "",
        f"## Top {top_n} 预测结果",
        "",
        "| Rank | Symbol | Name | Qlib Score | Market Cap | Sector | Industry |",
        "|---:|---|---|---:|---:|---|---|",
    ]
    for rank, (_, row) in enumerate(top_predictions.iterrows(), start=1):
        lines.append(
            "| {rank} | {symbol} | {name} | {score:.8f} | {market_cap} | {sector} | {industry} |".format(
                rank=rank,
                symbol=row.get("symbol", row.get("instrument", "N/A")),
                name=str(row.get("name", "")).replace("|", "/"),
                score=float(row["score"]),
                market_cap=fmt_optional_money(row.get("market_cap")),
                sector=str(row.get("sector", "")).replace("|", "/"),
                industry=str(row.get("industry", "")).replace("|", "/"),
            )
        )

    lines.extend(
        [
            "",
            "## 模型验证",
            "",
            f"- Test 日均 IC：{meta['ic_mean']:.6f}" if not math.isnan(meta["ic_mean"]) else "- Test 日均 IC：N/A",
            f"- Test 日均 Rank IC：{meta['rank_ic_mean']:.6f}"
            if not math.isnan(meta["rank_ic_mean"])
            else "- Test 日均 Rank IC：N/A",
            f"- 参与 IC 计算的交易日：{meta['ic_count']}",
            "",
            "IC 可以粗略理解为：每个交易日横截面上，模型预测分数和真实后续收益的相关性。",
            "",
            "## 数据失败数量",
            "",
            f"- 最新日可预测股票数：{meta['prediction_count']}",
            f"- 下载失败或历史不足：{len(failures)}",
            "",
            "## 输出文件",
            "",
            "- `universe.csv`：本次实验股票池。",
            "- `membership.csv`：历史指数成分日级标记；仅 Norgate 等成分感知数据源生成有效内容。",
            "- `download_failures.csv`：下载失败或历史不足的股票。",
            "- `predictions.csv`：最新日全部模型分数。",
            "- `report.md`：本报告。",
            "- `resolved_config.yaml`：本次实际使用配置，复盘时优先看它。",
            "- `qlib_source_csv/`：逐股票原始日线 CSV。",
            "- `qlib_data/`：转换后的 Qlib bin 数据。",
        ]
    )
    paths["report_md"].write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    paths = build_paths(config)
    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    write_resolved_config(config, paths)

    print(f"Experiment: {config['experiment']['name']}")
    print(f"Output dir: {paths['output_dir']}")
    try:
        prepared = create_data_source(config, paths).prepare()
    except DataSourceUnavailable as exc:
        raise SystemExit(f"Data source unavailable: {exc}") from None
    universe = prepared.universe
    failures = prepared.failures
    dump_qlib_bin(config, paths)
    predictions, meta = train_and_predict(universe, config, paths)
    write_report(predictions, meta, failures, config, paths)
    print(f"Qlib model top {config['report']['top_n']}:")
    preview_columns = [column for column in ["symbol", "name", "score", "market_cap", "sector", "industry"] if column in predictions]
    print(predictions[preview_columns].head(int(config["report"]["top_n"])).to_string(index=False))
    print(f"Report: {paths['report_md']}")


if __name__ == "__main__":
    main()
