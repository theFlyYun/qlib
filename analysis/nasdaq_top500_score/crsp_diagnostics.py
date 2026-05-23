"""Read-only diagnostics for CRSP labels, prices, features, and early stopping."""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
import yaml

try:  # pragma: no cover - supports direct script execution.
    from data_sources.crsp import (
        build_membership_intervals,
        crsp_label_column,
        crsp_warehouse_paths,
        forward_compound_return,
        membership_mask,
        resolve_config_path,
    )
    from run_qlib_alpha158_lightgbm import build_paths, choose_segments, load_config
except ImportError:  # pragma: no cover - supports importing this module in tests.
    from analysis.nasdaq_top500_score.data_sources.crsp import (
        build_membership_intervals,
        crsp_label_column,
        crsp_warehouse_paths,
        forward_compound_return,
        membership_mask,
        resolve_config_path,
    )
    from analysis.nasdaq_top500_score.run_qlib_alpha158_lightgbm import build_paths, choose_segments, load_config


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = Path("analysis/nasdaq_top500_score/configs/crsp/crsp_alpha158_10d_2000_2025.yaml")
DIAGNOSTIC_FILES = {
    "label": "label_diagnostics.csv",
    "label_distribution": "label_distribution_by_year.csv",
    "label_coverage": "label_coverage_by_segment.csv",
    "price": "price_adjustment_diagnostics.csv",
    "membership": "membership_diagnostics.csv",
    "membership_daily": "membership_daily_counts.csv",
    "feature_ic": "feature_ic_summary.csv",
    "feature_missing": "feature_missing_summary.csv",
    "early_history": "early_stopping_eval_history.csv",
    "early_variants": "early_stopping_variants.csv",
    "horizon": "label_horizon_comparison.csv",
    "summary": "diagnostic_summary.md",
}


@dataclass
class CRSPDiagnosticsResult:
    output_dir: Path
    summary: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help=f"CRSP config. Defaults to {DEFAULT_CONFIG}")
    parser.add_argument(
        "--skip-model-diagnostics",
        action="store_true",
        help="Skip feature IC and early-stopping diagnostics. Label, price, and membership checks still run.",
    )
    return parser.parse_args()


def run_crsp_diagnostics(config_path: Path = DEFAULT_CONFIG, *, skip_model_diagnostics: bool = False) -> CRSPDiagnosticsResult:
    config = load_config(config_path)
    if config["data"]["source"] != "crsp":
        raise ValueError("CRSP diagnostics require data.source=crsp")
    paths = build_paths(config)
    output_dir = paths["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    source_dir = paths["source_dir"]
    if not source_dir.exists():
        raise FileNotFoundError(f"CRSP diagnostics require existing qlib source CSVs: {source_dir}")
    if not paths["qlib_dir"].exists():
        raise FileNotFoundError(f"CRSP diagnostics require existing qlib bin data: {paths['qlib_dir']}")
    warehouse = crsp_warehouse_paths(resolve_config_path(config["crsp"]["warehouse_dir"]))
    membership = read_membership(paths, warehouse)
    selected = sorted(set(membership["instrument"].astype(str).str.upper()))
    label_column = crsp_label_column(int(config["crsp"]["label_horizon_days"]))
    qlib_labels = read_qlib_source_labels(source_dir, label_column)
    daily = read_crsp_daily_for_instruments(
        warehouse.daily_dir,
        selected,
        columns=["date", "instrument", "DlyRet", "DlyRetx", "DlyOpen", "DlyHigh", "DlyLow", "DlyClose", "DlyPrc"],
    )

    label_summary = run_label_diagnostics(config, output_dir, qlib_labels, daily, membership)
    price_summary = run_price_adjustment_diagnostics(output_dir, source_dir, daily, selected)
    membership_summary = run_membership_diagnostics(config, output_dir, qlib_labels, membership, selected)

    model_summary: dict[str, Any] = {"enabled": False}
    if not skip_model_diagnostics:
        model_summary = run_model_diagnostics(config, paths, daily, membership)

    summary = {
        "config": str(resolve_config_path(config_path)),
        "output_dir": str(output_dir),
        "label": label_summary,
        "price_adjustment": price_summary,
        "membership": membership_summary,
        "model": model_summary,
    }
    write_summary(output_dir / DIAGNOSTIC_FILES["summary"], summary)
    return CRSPDiagnosticsResult(output_dir=output_dir, summary=summary)


def read_membership(paths: dict[str, Path], warehouse: Any) -> pd.DataFrame:
    if paths["membership_csv"].exists():
        membership = pd.read_csv(paths["membership_csv"])
    elif warehouse.monthly_membership.exists():
        membership = pd.read_parquet(warehouse.monthly_membership)
    else:
        raise FileNotFoundError("CRSP membership not found in run dir or warehouse")
    membership = membership.copy()
    membership["instrument"] = membership.get("instrument", membership.get("symbol")).astype(str).str.upper()
    membership["symbol"] = membership.get("symbol", membership["instrument"]).astype(str).str.upper()
    for column in ["month_end_date", "effective_start", "effective_end"]:
        membership[column] = pd.to_datetime(membership[column], errors="coerce").dt.normalize()
    return membership


def read_qlib_source_labels(source_dir: Path, label_column: str) -> pd.DataFrame:
    frames = []
    for csv_path in sorted(source_dir.glob("*.csv")):
        frame = pd.read_csv(csv_path, usecols=["date", "symbol", label_column])
        frame["datetime"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
        frame["instrument"] = frame["symbol"].astype(str).str.upper()
        frames.append(frame[["datetime", "instrument", label_column]])
    if not frames:
        raise FileNotFoundError(f"no qlib source CSV files found in {source_dir}")
    return pd.concat(frames, ignore_index=True)


def read_crsp_daily_for_instruments(daily_dir: Path, instruments: list[str], *, columns: list[str]) -> pd.DataFrame:
    selected = {instrument.upper() for instrument in instruments}
    frames = []
    for parquet_path in sorted(daily_dir.rglob("*.parquet")):
        frame = pd.read_parquet(parquet_path, columns=columns)
        frame["instrument"] = frame["instrument"].astype(str).str.upper()
        frame = frame[frame["instrument"].isin(selected)].copy()
        if not frame.empty:
            frames.append(frame)
    if not frames:
        raise FileNotFoundError(f"no CRSP daily rows found for selected instruments in {daily_dir}")
    output = pd.concat(frames, ignore_index=True)
    output["date"] = pd.to_datetime(output["date"], errors="coerce").dt.normalize()
    return output.sort_values(["instrument", "date"]).reset_index(drop=True)


def run_label_diagnostics(
    config: dict[str, Any],
    output_dir: Path,
    qlib_labels: pd.DataFrame,
    daily: pd.DataFrame,
    membership: pd.DataFrame,
) -> dict[str, Any]:
    horizon = int(config["crsp"]["label_horizon_days"])
    label_column = crsp_label_column(horizon)
    recomputed = build_horizon_labels(daily, membership, [horizon])[horizon].rename("recomputed_label").reset_index()
    joined = qlib_labels.merge(
        recomputed,
        left_on=["datetime", "instrument"],
        right_on=["datetime", "instrument"],
        how="left",
    )
    joined["diff"] = joined[label_column] - joined["recomputed_label"]
    joined["abs_diff"] = joined["diff"].abs()
    sample = sample_label_rows(joined, instruments=30, dates_per_instrument=30)
    sample.to_csv(output_dir / DIAGNOSTIC_FILES["label"], index=False)

    distribution = label_distribution_by_year(qlib_labels, config)
    distribution.to_csv(output_dir / DIAGNOSTIC_FILES["label_distribution"], index=False)
    coverage = label_coverage_by_segment(qlib_labels, config)
    coverage.to_csv(output_dir / DIAGNOSTIC_FILES["label_coverage"], index=False)
    max_abs_diff = float(sample["abs_diff"].max()) if not sample.empty else math.nan
    full_max_abs_diff = float(joined["abs_diff"].max(skipna=True))
    return {
        "sample_rows": int(len(sample)),
        "sample_max_abs_diff": max_abs_diff,
        "full_max_abs_diff": full_max_abs_diff,
        "distribution_rows": int(len(distribution)),
        "coverage_rows": int(len(coverage)),
        "label_non_null": int(qlib_labels[label_column].notna().sum()),
    }


def build_horizon_labels(daily: pd.DataFrame, membership: pd.DataFrame, horizons: list[int]) -> dict[int, pd.Series]:
    intervals = build_membership_intervals(membership)
    outputs: dict[int, list[pd.Series]] = {horizon: [] for horizon in horizons}
    for instrument, group in daily.sort_values(["instrument", "date"]).groupby("instrument"):
        group = group.drop_duplicates("date", keep="first").copy()
        member = membership_mask(group["date"], intervals.get(str(instrument).upper(), []))
        index = pd.MultiIndex.from_arrays(
            [pd.to_datetime(group["date"]).dt.normalize(), group["instrument"].astype(str).str.upper()],
            names=["datetime", "instrument"],
        )
        for horizon in horizons:
            labels = forward_compound_return(group["DlyRet"], horizon).where(member, np.nan)
            outputs[horizon].append(pd.Series(labels.to_numpy(), index=index, name=f"label_{horizon}d"))
    return {horizon: pd.concat(parts).sort_index() if parts else pd.Series(dtype=float) for horizon, parts in outputs.items()}


def sample_label_rows(joined: pd.DataFrame, *, instruments: int, dates_per_instrument: int) -> pd.DataFrame:
    label_columns = [column for column in joined.columns if column.startswith("label_") and column.endswith("d_total_return")]
    label_column = label_columns[0] if label_columns else "label_10d_total_return"
    usable = joined[joined[label_column].notna() | joined["recomputed_label"].notna()].copy()
    rows = []
    symbols = sorted(usable["instrument"].dropna().unique().tolist())
    if len(symbols) > instruments:
        positions = np.linspace(0, len(symbols) - 1, instruments).round().astype(int)
        symbols = [symbols[index] for index in positions]
    for symbol in symbols:
        group = usable[usable["instrument"].eq(symbol)].sort_values("datetime")
        group = group[group[label_column].notna()]
        if group.empty:
            continue
        if len(group) > dates_per_instrument:
            positions = np.linspace(0, len(group) - 1, dates_per_instrument).round().astype(int)
            group = group.iloc[positions]
        rows.append(group)
    sample = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=joined.columns)
    sample["match"] = sample["abs_diff"].fillna(np.inf) <= 1e-10
    return sample


def segment_for_date(date_value: pd.Timestamp, config: dict[str, Any]) -> str:
    split = config["split"]
    for segment in ["train", "valid", "test"]:
        start = pd.Timestamp(split[segment]["start"])
        end = pd.Timestamp(split[segment]["end"])
        if start <= date_value <= end:
            return segment
    return "outside"


def label_distribution_by_year(labels: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    label_column = crsp_label_column(int(config.get("crsp", {}).get("label_horizon_days", 10)))
    frame = labels.copy()
    frame["year"] = frame["datetime"].dt.year
    frame["segment"] = frame["datetime"].map(lambda value: segment_for_date(pd.Timestamp(value), config))
    grouped = frame.groupby(["segment", "year"], dropna=False)[label_column]
    return grouped.agg(
        row_count="size",
        non_null_count=lambda x: int(x.notna().sum()),
        nan_rate=lambda x: float(x.isna().mean()),
        mean="mean",
        std="std",
        min="min",
        p01=lambda x: x.quantile(0.01),
        p50="median",
        p99=lambda x: x.quantile(0.99),
        max="max",
    ).reset_index()


def label_coverage_by_segment(labels: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    label_column = crsp_label_column(int(config.get("crsp", {}).get("label_horizon_days", 10)))
    frame = labels.copy()
    frame["segment"] = frame["datetime"].map(lambda value: segment_for_date(pd.Timestamp(value), config))
    grouped = frame.groupby("segment")[label_column]
    return grouped.agg(
        row_count="size",
        non_null_count=lambda x: int(x.notna().sum()),
        nan_rate=lambda x: float(x.isna().mean()),
        mean="mean",
        std="std",
    ).reset_index()


def run_price_adjustment_diagnostics(output_dir: Path, source_dir: Path, daily: pd.DataFrame, selected: list[str]) -> dict[str, Any]:
    raw = daily[["date", "instrument", "DlyRetx"]].copy()
    raw = raw.drop_duplicates(["date", "instrument"], keep="first")
    source = read_qlib_source_prices(source_dir, selected)
    source["adjusted_return"] = source.groupby("instrument")["close"].pct_change()
    joined = source.merge(raw, left_on=["datetime", "instrument"], right_on=["date", "instrument"], how="left")
    joined["retx_diff"] = joined["adjusted_return"] - pd.to_numeric(joined["DlyRetx"], errors="coerce")
    joined["abs_retx_diff"] = joined["retx_diff"].abs()
    joined["ohlc_violation"] = (
        (joined["low"] > joined[["open", "close", "high"]].min(axis=1))
        | (joined["high"] < joined[["open", "close", "low"]].max(axis=1))
    )
    joined["year"] = joined["datetime"].dt.year
    summary = joined.groupby("year").agg(
        row_count=("instrument", "size"),
        retx_compared_count=("abs_retx_diff", lambda x: int(x.notna().sum())),
        mean_abs_retx_diff=("abs_retx_diff", "mean"),
        p99_abs_retx_diff=("abs_retx_diff", lambda x: x.quantile(0.99)),
        max_abs_retx_diff=("abs_retx_diff", "max"),
        ohlc_violation_rate=("ohlc_violation", "mean"),
    ).reset_index()
    summary.to_csv(output_dir / DIAGNOSTIC_FILES["price"], index=False)
    return {
        "rows": int(len(joined)),
        "mean_abs_retx_diff": float(joined["abs_retx_diff"].mean(skipna=True)),
        "max_abs_retx_diff": float(joined["abs_retx_diff"].max(skipna=True)),
        "ohlc_violation_rate": float(joined["ohlc_violation"].mean()),
    }


def read_qlib_source_prices(source_dir: Path, selected: list[str]) -> pd.DataFrame:
    frames = []
    for instrument in selected:
        path = source_dir / f"{instrument}.csv"
        if not path.exists():
            continue
        frame = pd.read_csv(path, usecols=["date", "symbol", "open", "high", "low", "close", "volume"])
        frame["datetime"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
        frame["instrument"] = frame["symbol"].astype(str).str.upper()
        frames.append(frame[["datetime", "instrument", "open", "high", "low", "close", "volume"]])
    if not frames:
        raise FileNotFoundError("no qlib source price CSVs found for selected instruments")
    return pd.concat(frames, ignore_index=True).sort_values(["instrument", "datetime"])


def run_membership_diagnostics(
    config: dict[str, Any],
    output_dir: Path,
    labels: pd.DataFrame,
    membership: pd.DataFrame,
    selected: list[str],
) -> dict[str, Any]:
    rows = []
    monthly = membership.groupby("month_end_date").agg(
        member_count=("instrument", "nunique"),
        max_rank=("rank", "max"),
        min_effective_start=("effective_start", "min"),
    ).reset_index()
    monthly["effective_after_month_end"] = monthly["min_effective_start"] > monthly["month_end_date"]
    rows.append(
        {
            "check": "monthly_member_count",
            "row_count": int(len(monthly)),
            "pass_count": int(monthly["member_count"].eq(int(config["universe"]["top_n_by_market_cap"])).sum()),
            "fail_count": int((~monthly["member_count"].eq(int(config["universe"]["top_n_by_market_cap"]))).sum()),
            "detail": "monthly unique membership count should equal configured top_n",
        }
    )
    rows.append(
        {
            "check": "effective_start_after_month_end",
            "row_count": int(len(monthly)),
            "pass_count": int(monthly["effective_after_month_end"].sum()),
            "fail_count": int((~monthly["effective_after_month_end"]).sum()),
            "detail": "membership should start after the month-end selection date",
        }
    )
    intervals = build_membership_intervals(membership)
    label_columns = [column for column in labels.columns if column.startswith("label_") and column.endswith("d_total_return")]
    label_column = label_columns[0] if label_columns else "label_10d_total_return"
    label_frame = labels.copy()
    member_flags = []
    for instrument, group in label_frame.groupby("instrument"):
        member_flags.append(membership_mask(group["datetime"], intervals.get(str(instrument).upper(), [])))
    label_frame["is_member"] = pd.concat(member_flags).sort_index() if member_flags else False
    outside_non_null = label_frame[~label_frame["is_member"] & label_frame[label_column].notna()]
    rows.append(
        {
            "check": "non_member_label_is_nan",
            "row_count": int((~label_frame["is_member"]).sum()),
            "pass_count": int((~label_frame["is_member"]).sum() - len(outside_non_null)),
            "fail_count": int(len(outside_non_null)),
            "detail": "labels outside effective membership should be NaN",
        }
    )
    diagnostics = pd.DataFrame(rows)
    diagnostics.to_csv(output_dir / DIAGNOSTIC_FILES["membership"], index=False)
    daily = label_frame.groupby("datetime").agg(
        source_row_count=("instrument", "nunique"),
        label_non_null_count=(label_column, lambda x: int(x.notna().sum())),
        member_source_count=("is_member", "sum"),
    ).reset_index()
    daily.to_csv(output_dir / DIAGNOSTIC_FILES["membership_daily"], index=False)
    return {
        "monthly_count_min": int(monthly["member_count"].min()),
        "monthly_count_max": int(monthly["member_count"].max()),
        "effective_start_fail_count": int((~monthly["effective_after_month_end"]).sum()),
        "non_member_label_fail_count": int(len(outside_non_null)),
        "selected_instruments": int(len(selected)),
    }


def run_model_diagnostics(
    config: dict[str, Any],
    paths: dict[str, Path],
    daily: pd.DataFrame,
    membership: pd.DataFrame,
) -> dict[str, Any]:
    dataset, feature_frames = prepare_alpha158_frames(config, paths)
    missing_summary, ic_summary = run_feature_diagnostics(feature_frames)
    missing_summary.to_csv(paths["output_dir"] / DIAGNOSTIC_FILES["feature_missing"], index=False)
    ic_summary.to_csv(paths["output_dir"] / DIAGNOSTIC_FILES["feature_ic"], index=False)
    early_history, early_variants = run_early_stopping_variants(config, feature_frames)
    early_history.to_csv(paths["output_dir"] / DIAGNOSTIC_FILES["early_history"], index=False)
    early_variants.to_csv(paths["output_dir"] / DIAGNOSTIC_FILES["early_variants"], index=False)
    horizons = build_horizon_labels(daily, membership, [5, 10, 20])
    horizon_summary = run_label_horizon_comparison(config, feature_frames, horizons)
    horizon_summary.to_csv(paths["output_dir"] / DIAGNOSTIC_FILES["horizon"], index=False)
    return {
        "enabled": True,
        "feature_count": int(missing_summary["feature"].nunique()),
        "feature_ic_rows": int(len(ic_summary)),
        "early_stopping_variants": early_variants.to_dict("records"),
        "horizon_rows": int(len(horizon_summary)),
    }


def prepare_alpha158_frames(config: dict[str, Any], paths: dict[str, Path]) -> tuple[Any, dict[str, pd.DataFrame]]:
    sys.path.insert(0, str(WORKSPACE))
    import qlib
    from qlib.constant import REG_US
    from qlib.contrib.data.handler import Alpha158
    from qlib.data.dataset import DatasetH
    from qlib.data.dataset.handler import DataHandlerLP

    qlib.init(
        provider_uri=str(paths["qlib_dir"]),
        region=REG_US,
        expression_cache=None,
        dataset_cache=None,
    )
    segments = choose_segments(config, paths)
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
        segments={segment: segments[segment] for segment in ["train", "valid", "test"]},
    )
    frames = {
        segment: dataset.prepare(segment, col_set=["feature", "label"], data_key=DataHandlerLP.DK_L)
        for segment in ["train", "valid", "test"]
    }
    return dataset, frames


def run_feature_diagnostics(feature_frames: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    missing_rows = []
    ic_rows = []
    for segment, frame in feature_frames.items():
        features = frame["feature"]
        label = normalized_label_series(frame)
        for feature in features.columns:
            values = pd.to_numeric(features[feature], errors="coerce")
            finite = np.isfinite(values)
            non_null = values.notna()
            missing_rows.append(
                {
                    "segment": segment,
                    "feature": str(feature),
                    "row_count": int(len(values)),
                    "missing_rate": float(values.isna().mean()),
                    "non_finite_rate": float((~finite & non_null).mean()),
                    "constant": bool(values.dropna().nunique() <= 1),
                    "extreme_abs_gt_1e6_rate": float((values.abs() > 1_000_000).mean()),
                }
            )
        ic = daily_feature_ic(features, label, method="pearson")
        rank_ic = daily_feature_ic(features, label, method="spearman")
        for feature in features.columns:
            ic_rows.append(
                {
                    "segment": segment,
                    "feature": str(feature),
                    "mean_ic": float(ic.get(feature, np.nan)),
                    "mean_rank_ic": float(rank_ic.get(feature, np.nan)),
                }
            )
    return pd.DataFrame(missing_rows), pd.DataFrame(ic_rows)


def normalized_label_series(frame: pd.DataFrame) -> pd.Series:
    label = frame["label"]
    if isinstance(label, pd.DataFrame):
        label = label.iloc[:, 0]
    return pd.to_numeric(label, errors="coerce")


def daily_feature_ic(features: pd.DataFrame, label: pd.Series, *, method: str) -> pd.Series:
    rows = []
    for datetime_value, y in label.groupby(level="datetime"):
        valid_y = y.dropna()
        if len(valid_y) < 3:
            continue
        x = features.loc[valid_y.index]
        if method == "spearman":
            rows.append(x.rank().corrwith(valid_y.rank()))
        else:
            rows.append(x.corrwith(valid_y))
    if not rows:
        return pd.Series(dtype=float)
    return pd.DataFrame(rows).mean(axis=0)


def run_early_stopping_variants(config: dict[str, Any], feature_frames: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    variants = early_stopping_variant_params(config)
    history_rows = []
    summary_rows = []
    train_frame = feature_frames["train"]
    valid_frame = feature_frames["valid"]
    for variant_name, params, rounds in variants:
        result = train_lightgbm_eval(
            train_frame["feature"],
            normalized_label_series(train_frame),
            valid_frame["feature"],
            normalized_label_series(valid_frame),
            params=params,
            num_boost_round=rounds,
        )
        for iteration, train_l2, valid_l2 in result["history"]:
            history_rows.append(
                {
                    "diagnostic": "model_variant",
                    "variant": variant_name,
                    "horizon": int(config["crsp"]["label_horizon_days"]),
                    "iteration": iteration,
                    "train_l2": train_l2,
                    "valid_l2": valid_l2,
                }
            )
        summary_rows.append(
            {
                "diagnostic": "model_variant",
                "variant": variant_name,
                "horizon": int(config["crsp"]["label_horizon_days"]),
                "best_iteration": result["best_iteration"],
                "best_valid_l2": result["best_valid_l2"],
                "final_valid_l2": result["final_valid_l2"],
                "round_count": result["round_count"],
            }
        )
    return pd.DataFrame(history_rows), pd.DataFrame(summary_rows)


def early_stopping_variant_params(config: dict[str, Any]) -> list[tuple[str, dict[str, Any], int]]:
    base = lightgbm_params_from_config(config)
    base_rounds = int(config["model"]["kwargs"].get("n_estimators", 300))
    conservative = {
        **base,
        "learning_rate": 0.03,
        "num_leaves": 16,
        "max_depth": 4,
        "lambda_l1": 5.0,
        "lambda_l2": 50.0,
        "min_data_in_leaf": 500,
        "feature_fraction": 0.75,
        "bagging_fraction": 0.85,
        "bagging_freq": 1,
    }
    tiny = {
        **base,
        "learning_rate": 0.02,
        "num_leaves": 8,
        "max_depth": 3,
        "lambda_l1": 10.0,
        "lambda_l2": 100.0,
        "min_data_in_leaf": 1000,
        "feature_fraction": 0.60,
        "bagging_fraction": 0.75,
        "bagging_freq": 1,
    }
    return [("current", base, base_rounds), ("conservative", conservative, base_rounds), ("tiny", tiny, 120)]


def lightgbm_params_from_config(config: dict[str, Any]) -> dict[str, Any]:
    kwargs = dict(config["model"]["kwargs"])
    loss = kwargs.pop("loss", "mse")
    kwargs.pop("n_estimators", None)
    kwargs.pop("num_boost_round", None)
    kwargs["objective"] = loss
    kwargs.setdefault("verbosity", -1)
    return kwargs


def train_lightgbm_eval(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    x_valid: pd.DataFrame,
    y_valid: pd.Series,
    *,
    params: dict[str, Any],
    num_boost_round: int,
) -> dict[str, Any]:
    train_mask = y_train.notna()
    valid_mask = y_valid.notna()
    train_ds = lgb.Dataset(x_train.loc[train_mask].values, label=y_train.loc[train_mask].to_numpy(), free_raw_data=False)
    valid_ds = lgb.Dataset(x_valid.loc[valid_mask].values, label=y_valid.loc[valid_mask].to_numpy(), free_raw_data=False)
    evals_result: dict[str, dict[str, list[float]]] = {}
    model = lgb.train(
        params,
        train_ds,
        num_boost_round=num_boost_round,
        valid_sets=[train_ds, valid_ds],
        valid_names=["train", "valid"],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.record_evaluation(evals_result), lgb.log_evaluation(period=0)],
    )
    train_l2 = evals_result.get("train", {}).get("l2", [])
    valid_l2 = evals_result.get("valid", {}).get("l2", [])
    history = [(index + 1, train_l2[index], valid_l2[index]) for index in range(min(len(train_l2), len(valid_l2)))]
    return {
        "best_iteration": int(model.best_iteration or len(valid_l2)),
        "best_valid_l2": float(model.best_score.get("valid", {}).get("l2", np.nan)),
        "final_valid_l2": float(valid_l2[-1]) if valid_l2 else math.nan,
        "round_count": int(len(valid_l2)),
        "history": history,
    }


def run_label_horizon_comparison(
    config: dict[str, Any],
    feature_frames: dict[str, pd.DataFrame],
    horizon_labels: dict[int, pd.Series],
) -> pd.DataFrame:
    params = lightgbm_params_from_config(config)
    rounds = int(config["model"]["kwargs"].get("n_estimators", 300))
    rows = []
    for horizon, raw_labels in horizon_labels.items():
        normalized = cross_section_zscore(raw_labels)
        train_y = normalized.reindex(feature_frames["train"].index)
        valid_y = normalized.reindex(feature_frames["valid"].index)
        result = train_lightgbm_eval(
            feature_frames["train"]["feature"],
            train_y,
            feature_frames["valid"]["feature"],
            valid_y,
            params=params,
            num_boost_round=rounds,
        )
        raw_train = raw_labels.reindex(feature_frames["train"].index)
        raw_valid = raw_labels.reindex(feature_frames["valid"].index)
        rows.append(
            {
                "horizon": horizon,
                "train_count": int(raw_train.notna().sum()),
                "valid_count": int(raw_valid.notna().sum()),
                "train_label_mean": float(raw_train.mean(skipna=True)),
                "train_label_std": float(raw_train.std(skipna=True)),
                "valid_label_mean": float(raw_valid.mean(skipna=True)),
                "valid_label_std": float(raw_valid.std(skipna=True)),
                "best_iteration": result["best_iteration"],
                "best_valid_l2": result["best_valid_l2"],
                "final_valid_l2": result["final_valid_l2"],
                "round_count": result["round_count"],
            }
        )
    return pd.DataFrame(rows)


def cross_section_zscore(series: pd.Series) -> pd.Series:
    def zscore(group: pd.Series) -> pd.Series:
        std = group.std(ddof=0)
        if pd.isna(std) or std == 0:
            return pd.Series(np.nan, index=group.index)
        return (group - group.mean()) / std

    return series.groupby(level="datetime", group_keys=False).apply(zscore)


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    model = summary.get("model", {})
    early_rows = model.get("early_stopping_variants", []) if model.get("enabled") else []
    lines = [
        "# CRSP Early Stopping And Negative IC Diagnostics",
        "",
        "## Summary",
        "",
        f"- Config: `{summary['config']}`",
        f"- Output dir: `{summary['output_dir']}`",
        f"- Label sample max absolute diff: `{summary['label']['sample_max_abs_diff']}`",
        f"- Full label max absolute diff: `{summary['label']['full_max_abs_diff']}`",
        f"- Adjusted close vs DlyRetx mean absolute diff: `{summary['price_adjustment']['mean_abs_retx_diff']}`",
        f"- Adjusted close vs DlyRetx max absolute diff: `{summary['price_adjustment']['max_abs_retx_diff']}`",
        f"- OHLC violation rate: `{summary['price_adjustment']['ohlc_violation_rate']}`",
        f"- Non-member non-null label rows: `{summary['membership']['non_member_label_fail_count']}`",
        "",
    ]
    if early_rows:
        lines.extend(["## Early Stopping Variants", ""])
        for row in early_rows:
            lines.append(
                f"- {row['variant']}: best_iteration={row['best_iteration']}, "
                f"best_valid_l2={row['best_valid_l2']:.6f}, final_valid_l2={row['final_valid_l2']:.6f}"
            )
        lines.append("")
    lines.extend(
        [
            "## Output Files",
            "",
            *[f"- `{file_name}`" for file_name in DIAGNOSTIC_FILES.values() if file_name != DIAGNOSTIC_FILES["summary"]],
            "",
            "本诊断只用于定位数据、标签、特征和训练稳定性问题，不作为投资建议。",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    result = run_crsp_diagnostics(args.config, skip_model_diagnostics=args.skip_model_diagnostics)
    print(f"Diagnostic summary: {result.output_dir / DIAGNOSTIC_FILES['summary']}")


if __name__ == "__main__":
    main()
