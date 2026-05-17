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

import numpy as np
import pandas as pd
import yaml

try:
    from data_sources import DataSourceUnavailable, create_data_source
    from fundamentals import build_fundamental_features
    from industry import build_industry_feature_frame
    from selection import apply_bucket_ranking, apply_liquidity_filter, build_history_buckets
except ImportError:  # pragma: no cover - supports importing this script as a module in tests.
    from analysis.nasdaq_top500_score.data_sources import DataSourceUnavailable, create_data_source
    from analysis.nasdaq_top500_score.fundamentals import build_fundamental_features
    from analysis.nasdaq_top500_score.industry import build_industry_feature_frame
    from analysis.nasdaq_top500_score.selection import apply_bucket_ranking, apply_liquidity_filter, build_history_buckets

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
    if source == "nasdaq_public":
        fixed_window = bool(config["data"].get("start_date") or config["data"].get("end_date"))
        if fixed_window:
            missing = [key for key in ["start_date", "end_date"] if key not in config["data"]]
            if missing:
                raise ValueError(f"nasdaq_public fixed window missing data key(s): {', '.join(missing)}")
            validate_date_order(config["data"]["start_date"], config["data"]["end_date"], "data")
        elif "lookback_days" not in config["data"]:
            raise ValueError("nasdaq_public requires either data.lookback_days or data.start_date/data.end_date")
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
    if config["split"]["method"] not in {"ratio", "date"}:
        raise ValueError("currently supports split.method: ratio, date")
    fundamentals = config.get("fundamentals", {})
    if fundamentals:
        if fundamentals.get("source") != "sec_edgar":
            raise ValueError("currently supports fundamentals.source: sec_edgar")
        if fundamentals.get("enabled") and not fundamentals.get("cache_dir"):
            raise ValueError("enabled fundamentals require fundamentals.cache_dir")
    industry = config.get("industry", {})
    if industry:
        if industry.get("source") != "universe":
            raise ValueError("currently supports industry.source: universe")
        if industry.get("enabled") and not fundamentals.get("enabled", False):
            raise ValueError("enabled industry features require fundamentals.enabled: true")
        if industry.get("enabled") and not industry.get("rank_features"):
            raise ValueError("enabled industry features require industry.rank_features")

    if config["split"]["method"] == "ratio":
        train_ratio = float(config["split"]["train_ratio"])
        valid_ratio = float(config["split"]["valid_ratio"])
        test_ratio = float(config["split"]["test_ratio"])
        if not math.isclose(train_ratio + valid_ratio + test_ratio, 1.0, rel_tol=0, abs_tol=1e-6):
            raise ValueError("split train_ratio + valid_ratio + test_ratio must equal 1.0")
    else:
        validate_date_split(config["split"])
    validate_bucket_ranking(config)
    validate_industry_constraints(config)
    validate_liquidity_filter(config)


def validate_bucket_ranking(config: dict[str, Any]) -> None:
    ranking = config.get("bucket_ranking", {})
    if not ranking or not ranking.get("enabled", False):
        return
    if not config.get("history_buckets", {}).get("enabled", False):
        raise ValueError("enabled bucket_ranking requires history_buckets.enabled: true")
    quotas = ranking.get("quotas", {})
    missing = [bucket for bucket in ["full_10y", "5_10y", "2_5y", "lt_2y"] if bucket not in quotas]
    if missing:
        raise ValueError(f"bucket_ranking.quotas missing bucket(s): {', '.join(missing)}")
    top_n = int(config["report"]["top_n"])
    quota_total = sum(int(value) for value in quotas.values())
    if quota_total != top_n:
        raise ValueError("bucket_ranking quota total must equal report.top_n")


def validate_industry_constraints(config: dict[str, Any]) -> None:
    constraints = config.get("industry_constraints", {})
    if not constraints or not constraints.get("enabled", False):
        return
    if not config.get("bucket_ranking", {}).get("enabled", False):
        raise ValueError("enabled industry_constraints requires bucket_ranking.enabled: true")
    for key in ["max_sector", "max_industry"]:
        if key not in constraints:
            raise ValueError(f"enabled industry_constraints requires {key}")
        if int(constraints[key]) <= 0:
            raise ValueError(f"industry_constraints.{key} must be positive")


def validate_liquidity_filter(config: dict[str, Any]) -> None:
    liquidity = config.get("liquidity_filter", {})
    if not liquidity or not liquidity.get("enabled", False):
        return
    positive_keys = [
        "min_latest_close",
        "min_avg_dollar_volume_20d",
        "min_median_dollar_volume_60d",
        "min_recent_trading_days_60d",
    ]
    for key in positive_keys:
        if key in liquidity and float(liquidity[key]) < 0:
            raise ValueError(f"liquidity_filter.{key} must be non-negative")
    if "max_zero_volume_ratio_60d" in liquidity:
        value = float(liquidity["max_zero_volume_ratio_60d"])
        if value < 0 or value > 1:
            raise ValueError("liquidity_filter.max_zero_volume_ratio_60d must be between 0 and 1")


def date_value(value: Any) -> pd.Timestamp:
    if isinstance(value, str) and value == "latest":
        return pd.Timestamp.today().normalize()
    return pd.Timestamp(value).normalize()


def validate_date_order(start: Any, end: Any, label: str) -> None:
    if date_value(start) > date_value(end):
        raise ValueError(f"{label} start date must be before or equal to end date")


def validate_date_split(split: dict[str, Any]) -> None:
    missing_segments = [segment for segment in ["train", "valid", "test"] if segment not in split]
    if missing_segments:
        raise ValueError(f"date split missing segment(s): {', '.join(missing_segments)}")
    for segment in ["train", "valid", "test"]:
        missing = [key for key in ["start", "end"] if key not in split[segment]]
        if missing:
            raise ValueError(f"date split {segment} missing key(s): {', '.join(missing)}")
        validate_date_order(split[segment]["start"], split[segment]["end"], f"split.{segment}")
    if date_value(split["train"]["end"]) >= date_value(split["valid"]["start"]):
        raise ValueError("date split train.end must be before valid.start")
    if date_value(split["valid"]["end"]) >= date_value(split["test"]["start"]):
        raise ValueError("date split valid.end must be before test.start")


def build_paths(config: dict[str, Any]) -> dict[str, Path]:
    output_dir = resolve_path(config["experiment"]["output_dir"])
    paths = {
        "output_dir": output_dir,
        "source_dir": output_dir / "qlib_source_csv",
        "qlib_dir": output_dir / "qlib_data",
        "universe_csv": output_dir / "universe.csv",
        "universe_exclusions_csv": output_dir / "universe_exclusions.csv",
        "failures_csv": output_dir / "download_failures.csv",
        "membership_csv": output_dir / "membership.csv",
        "history_buckets_csv": output_dir / "history_buckets.csv",
        "liquidity_profile_csv": output_dir / "liquidity_profile.csv",
        "liquidity_exclusions_csv": output_dir / "liquidity_exclusions.csv",
        "fundamental_features": output_dir / "fundamental_features.parquet",
        "fundamental_failures": output_dir / "fundamental_failures.csv",
        "edgar_cik_map": output_dir / "edgar_cik_map.csv",
        "industry_features": output_dir / "industry_features.parquet",
        "industry_failures": output_dir / "industry_failures.csv",
        "predictions_csv": output_dir / "predictions.csv",
        "bucketed_predictions_csv": output_dir / "bucketed_predictions.csv",
        "selected_top10_csv": output_dir / "selected_top10.csv",
        "report_md": output_dir / "report.md",
        "resolved_config": output_dir / "resolved_config.yaml",
    }
    fundamentals = config.get("fundamentals", {})
    cache_dir = fundamentals.get("cache_dir") if fundamentals else None
    paths["edgar_cache_dir"] = resolve_path(cache_dir) if cache_dir else output_dir / "edgar_cache"
    return paths


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

    if config["split"]["method"] == "date":
        return choose_date_segments(config, dates, warmup_days)

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


def choose_date_segments(
    config: dict[str, Any],
    dates: pd.Series,
    warmup_days: int,
) -> dict[str, tuple[str, str]]:
    split = config["split"]
    train = calendar_segment(dates, split["train"]["start"], split["train"]["end"], "train")
    valid = calendar_segment(dates, split["valid"]["start"], split["valid"]["end"], "valid")
    test = calendar_segment(dates, split["test"]["start"], split["test"]["end"], "test")
    warmup_start = dates.iloc[warmup_days]
    train_start = max(pd.Timestamp(train[0]), warmup_start).strftime("%Y-%m-%d")
    if pd.Timestamp(train_start) > pd.Timestamp(train[1]):
        raise RuntimeError("warmup_days leave no dates in the configured train segment")
    return {
        "fit": (dates.iloc[0].strftime("%Y-%m-%d"), train[1]),
        "all": (dates.iloc[0].strftime("%Y-%m-%d"), dates.iloc[-1].strftime("%Y-%m-%d")),
        "train": (train_start, train[1]),
        "valid": valid,
        "test": test,
    }


def calendar_segment(dates: pd.Series, start: Any, end: Any, label: str) -> tuple[str, str]:
    start_ts = date_value(start)
    end_ts = date_value(end)
    selected = dates[(dates >= start_ts) & (dates <= end_ts)]
    if selected.empty:
        raise RuntimeError(f"no trading dates available for configured {label} segment")
    return selected.iloc[0].strftime("%Y-%m-%d"), selected.iloc[-1].strftime("%Y-%m-%d")


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
    from qlib.data.dataset.loader import StaticDataLoader

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
    fundamental_result = None
    industry_result = None
    extra_feature_frames: list[pd.DataFrame] = []
    if config.get("fundamentals", {}).get("enabled", False):
        print("Building SEC EDGAR point-in-time fundamental features...")
        fundamental_result = build_fundamental_features(universe, config, paths)
        extra_feature_frames.append(fundamental_result.features)
    if config.get("industry", {}).get("enabled", False):
        print("Building industry-relative fundamental features...")
        if fundamental_result is None:
            raise RuntimeError("industry features require fundamental features to be built first")
        industry_result = build_industry_feature_frame(universe, config, paths, fundamental_result.features)
        extra_feature_frames.append(industry_result.features)
    if extra_feature_frames:
        raw = handler.fetch(
            selector=slice(segments["all"][0], segments["all"][1]),
            col_set=["feature", "label"],
            data_key=DataHandlerLP.DK_R,
        )
        combined = combine_alpha_and_feature_frames_raw(raw, extra_feature_frames)
        handler = DataHandlerLP(
            data_loader=StaticDataLoader(combined),
            learn_processors=[
                {"class": "DropnaLabel"},
                {"class": "CSZScoreNorm", "kwargs": {"fields_group": "label"}},
            ],
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
    top_predictions, bucket_meta = apply_bucket_ranking(merged, config, paths)

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
        "fundamentals_enabled": bool(config.get("fundamentals", {}).get("enabled", False)),
        "fundamental_feature_count": 0 if fundamental_result is None else int(fundamental_result.features.shape[1]),
        "fundamental_failure_count": 0 if fundamental_result is None else int(len(fundamental_result.failures)),
        "cik_mapped_count": 0 if fundamental_result is None else int(len(fundamental_result.cik_map)),
        "industry_enabled": bool(config.get("industry", {}).get("enabled", False)),
        "industry_feature_count": 0 if industry_result is None else int(industry_result.features.shape[1]),
        "industry_failure_count": 0 if industry_result is None else int(len(industry_result.failures)),
        "industry_coverage": {} if industry_result is None else industry_result.coverage,
        "bucket_ranking_enabled": bool(bucket_meta["bucket_ranking_enabled"]),
        "history_bucket_counts": bucket_meta["bucket_counts"],
        "bucket_quotas": bucket_meta["bucket_quotas"],
        "selected_bucket_counts": bucket_meta["selected_bucket_counts"],
        "industry_constraints_enabled": bool(bucket_meta.get("industry_constraints_enabled", False)),
        "industry_constraints": bucket_meta.get("industry_constraints", {}),
        "selected_sector_counts": bucket_meta.get("selected_sector_counts", {}),
        "selected_industry_counts": bucket_meta.get("selected_industry_counts", {}),
        "top_sector_counts": top_predictions["sector"].fillna("UNKNOWN").value_counts().to_dict()
        if "sector" in top_predictions
        else {},
        "top_industry_counts": top_predictions["industry"].fillna("UNKNOWN").value_counts().to_dict()
        if "industry" in top_predictions
        else {},
    }
    return top_predictions, meta


def combine_alpha_and_feature_frames_raw(
    alpha_raw: pd.DataFrame,
    extra_feature_frames: list[pd.DataFrame],
) -> pd.DataFrame:
    alpha_features = alpha_raw["feature"]
    labels = alpha_raw["label"]
    aligned_features = [frame.reindex(alpha_features.index) for frame in extra_feature_frames if not frame.empty]
    combined_features = pd.concat([alpha_features, *aligned_features], axis=1)
    combined_features = combined_features.mask(combined_features.isna(), np.nan).apply(pd.to_numeric, errors="coerce")
    labels = labels.mask(labels.isna(), np.nan).apply(pd.to_numeric, errors="coerce")
    return pd.concat({"feature": combined_features, "label": labels}, axis=1).sort_index()


def combine_alpha_and_fundamental_raw(alpha_raw: pd.DataFrame, fundamental_features: pd.DataFrame) -> pd.DataFrame:
    return combine_alpha_and_feature_frames_raw(alpha_raw, [fundamental_features])


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
    universe_exclusions = read_optional_csv(paths["universe_exclusions_csv"])
    liquidity_exclusions = read_optional_csv(paths["liquidity_exclusions_csv"])
    exclusion_reason_counts = (
        universe_exclusions["exclusion_reason"].value_counts().to_dict()
        if "exclusion_reason" in universe_exclusions and not universe_exclusions.empty
        else {}
    )
    liquidity_exclusion_reason_counts = (
        liquidity_exclusions["exclusion_reason"].value_counts().to_dict()
        if "exclusion_reason" in liquidity_exclusions and not liquidity_exclusions.empty
        else {}
    )
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
        "## 财报与估值特征",
        "",
        *(
            format_yaml_block(config.get("fundamentals", {}))
            if config.get("fundamentals", {}).get("enabled", False)
            else ["- 未启用。"]
        ),
        "",
        "## 行业相对特征",
        "",
        *(
            format_yaml_block(config.get("industry", {}))
            if config.get("industry", {}).get("enabled", False)
            else ["- 未启用。"]
        ),
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
    ]
    if meta.get("bucket_ranking_enabled", False):
        lines.extend(
            [
                "| Rank | Symbol | Bucket | Bucket Rank | Global Rank | Name | Qlib Score | Market Cap | Sector | Industry |",
                "|---:|---|---|---:|---:|---|---:|---:|---|---|",
            ]
        )
    else:
        lines.extend(
            [
                "| Rank | Symbol | Name | Qlib Score | Market Cap | Sector | Industry |",
                "|---:|---|---|---:|---:|---|---|",
            ]
        )
    for rank, (_, row) in enumerate(top_predictions.iterrows(), start=1):
        if meta.get("bucket_ranking_enabled", False):
            lines.append(
                "| {rank} | {symbol} | {bucket} | {bucket_rank} | {global_rank} | {name} | {score:.8f} | {market_cap} | {sector} | {industry} |".format(
                    rank=rank,
                    symbol=row.get("symbol", row.get("instrument", "N/A")),
                    bucket=row.get("history_bucket", "N/A"),
                    bucket_rank=row.get("bucket_rank", "N/A"),
                    global_rank=row.get("global_rank", "N/A"),
                    name=str(row.get("name", "")).replace("|", "/"),
                    score=float(row["score"]),
                    market_cap=fmt_optional_money(row.get("market_cap")),
                    sector=str(row.get("sector", "")).replace("|", "/"),
                    industry=str(row.get("industry", "")).replace("|", "/"),
                )
            )
        else:
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
            f"- EDGAR 特征数量：{meta.get('fundamental_feature_count', 0)}",
            f"- EDGAR CIK 映射数量：{meta.get('cik_mapped_count', 0)}",
            f"- EDGAR 失败或跳过数量：{meta.get('fundamental_failure_count', 0)}",
            f"- 行业相对特征数量：{meta.get('industry_feature_count', 0)}",
            f"- 行业分类失败或跳过数量：{meta.get('industry_failure_count', 0)}",
            "",
            "IC 可以粗略理解为：每个交易日横截面上，模型预测分数和真实后续收益的相关性。",
            "",
            "## 流动性过滤",
            "",
            *(
                [
                    "- 流动性过滤：已启用。",
                    "- 过滤规则：",
                    *format_yaml_block(meta.get("liquidity_filter", {})),
                    f"- 生成流动性画像股票数：{meta.get('liquidity_profile_count', 0)}",
                    f"- 流动性剔除数量：{meta.get('liquidity_exclusion_count', 0)}",
                    "- 流动性剔除原因：",
                    *format_yaml_block(liquidity_exclusion_reason_counts),
                ]
                if meta.get("liquidity_filter_enabled", False)
                else ["- 未启用。"]
            ),
            "",
            "## 股票池清洗与历史分桶",
            "",
            *(
                [
                    "- 桶内 TopN 排名：已启用。",
                    f"- 股票池清洗剔除数量：{len(universe_exclusions)}",
                    "- 清洗剔除原因：",
                    *format_yaml_block(exclusion_reason_counts),
                    "- 桶名额：",
                    *format_yaml_block(meta.get("bucket_quotas", {})),
                    "- 最新日可预测股票分桶：",
                    *format_yaml_block(meta.get("history_bucket_counts", {})),
                    "- 最终 TopN 分桶：",
                    *format_yaml_block(meta.get("selected_bucket_counts", {})),
                    "- 行业名额约束：",
                    *(
                        format_yaml_block(meta.get("industry_constraints", {}))
                        if meta.get("industry_constraints_enabled", False)
                        else ["未启用。"]
                    ),
                    "- 最终 TopN sector 分布：",
                    *format_yaml_block(meta.get("selected_sector_counts", {})),
                    "- 最终 TopN industry 分布：",
                    *format_yaml_block(meta.get("selected_industry_counts", {})),
                ]
                if meta.get("bucket_ranking_enabled", False)
                else ["- 未启用。"]
            ),
            "",
            "## 行业覆盖",
            "",
            f"- 股票池 sector 缺失数量：{meta.get('industry_coverage', {}).get('sector_missing_count', 0)}",
            f"- 股票池 industry 缺失数量：{meta.get('industry_coverage', {}).get('industry_missing_count', 0)}",
            "- TopN sector 分布：",
            *format_yaml_block(meta.get("top_sector_counts", {})),
            "- TopN industry 分布：",
            *format_yaml_block(meta.get("top_industry_counts", {})),
            "",
            "第一版行业分类来自当前 Nasdaq public snapshot，不是历史 PIT 行业分类。它适合学习行业内比较，但不能替代严谨回测里的历史行业口径。",
            "",
            "## 数据失败数量",
            "",
            f"- 最新日可预测股票数：{meta['prediction_count']}",
            f"- 下载失败或历史不足：{len(failures)}",
            "",
            "## 输出文件",
            "",
            "- `universe.csv`：本次实验股票池。",
            "- `universe_exclusions.csv`：股票池清洗剔除记录；仅启用清洗时生成有效内容。",
            "- `membership.csv`：历史指数成分日级标记；仅 Norgate 等成分感知数据源生成有效内容。",
            "- `download_failures.csv`：下载失败或历史不足的股票。",
            "- `liquidity_profile.csv`：每只已下载股票的成交额、价格和零成交画像。",
            "- `liquidity_exclusions.csv`：流动性过滤剔除记录。",
            "- `history_buckets.csv`：每只进入 Qlib source CSV 股票的历史长度分桶。",
            "- `fundamental_features.parquet`：日频 PIT 财报与估值特征；仅启用 EDGAR 时生成有效内容。",
            "- `fundamental_failures.csv`：EDGAR 映射、字段或行情缺失记录。",
            "- `edgar_cik_map.csv`：本次股票池 ticker 到 SEC CIK 的映射。",
            "- `industry_features.parquet`：行业内 rank / percentile 特征；仅启用行业特征时生成有效内容。",
            "- `industry_failures.csv`：sector / industry 缺失或 rank 字段缺失记录。",
            "- `predictions.csv`：最新日全部模型分数。",
            "- `bucketed_predictions.csv`：追加历史分桶、桶内排名和全局排名后的全部模型分数。",
            "- `selected_top10.csv`：按历史长度桶名额选择后的最终 Top10。",
            "- `report.md`：本报告。",
            "- `resolved_config.yaml`：本次实际使用配置，复盘时优先看它。",
            "- `qlib_source_csv/`：逐股票原始日线 CSV。",
            "- `qlib_data/`：转换后的 Qlib bin 数据。",
        ]
    )
    paths["report_md"].write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_optional_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


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
    universe, liquidity_meta = apply_liquidity_filter(universe, paths["source_dir"], config, paths)
    build_history_buckets(paths["source_dir"], paths["history_buckets_csv"], config)
    dump_qlib_bin(config, paths)
    try:
        predictions, meta = train_and_predict(universe, config, paths)
        meta.update(liquidity_meta)
    except DataSourceUnavailable as exc:
        raise SystemExit(f"Fundamental data unavailable: {exc}") from None
    write_report(predictions, meta, failures, config, paths)
    print(f"Qlib model top {config['report']['top_n']}:")
    preview_columns = [
        column
        for column in ["symbol", "history_bucket", "bucket_rank", "global_rank", "name", "score", "market_cap", "sector", "industry"]
        if column in predictions
    ]
    print(predictions[preview_columns].head(int(config["report"]["top_n"])).to_string(index=False))
    print(f"Report: {paths['report_md']}")


if __name__ == "__main__":
    main()
