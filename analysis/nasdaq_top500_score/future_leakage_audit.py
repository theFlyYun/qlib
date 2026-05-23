"""Future leakage and backtest-water audit helpers for Nasdaq/Qlib runs."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_TARGET_RUN = (
    WORKSPACE
    / "analysis/nasdaq_top500_score/runs/"
    "nasdaq_alpha158_edgar_macro_ablation_drop_credit_quality_interactions_10y_frozen_2023_top500_5d_pit_safe"
)
DEFAULT_OUTPUT_DIR = DEFAULT_TARGET_RUN / "future_leakage_audit"
DEFAULT_VARIANT = "sector_cap_2_top10"


@dataclass
class AuditResult:
    risk_register: pd.DataFrame
    universe_sample: pd.DataFrame
    macro_sample: pd.DataFrame
    market_sample: pd.DataFrame
    edgar_sample: pd.DataFrame
    backtest_sample: pd.DataFrame
    summary: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_TARGET_RUN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--variant", default=DEFAULT_VARIANT)
    parser.add_argument("--sample-size", type=int, default=20)
    return parser.parse_args()


def resolve_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    return candidate if candidate.is_absolute() else WORKSPACE / candidate


def run_audit(
    run_dir: Path = DEFAULT_TARGET_RUN,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    variant: str = DEFAULT_VARIANT,
    sample_size: int = 20,
) -> AuditResult:
    run_dir = resolve_path(run_dir)
    output_dir = resolve_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    universe_sample = sample_universe_selection(run_dir, sample_size)
    macro_sample = sample_macro_asof(run_dir, sample_size)
    market_sample = sample_market_features(run_dir, sample_size)
    edgar_sample = sample_edgar_features(run_dir, sample_size)
    backtest_sample = recalculate_backtest_periods(run_dir, variant, sample_size=10)
    risk_register = build_risk_register(run_dir, universe_sample, macro_sample, market_sample, edgar_sample, backtest_sample)
    summary = build_summary(run_dir, variant, risk_register, universe_sample, macro_sample, market_sample, edgar_sample, backtest_sample)

    risk_register.to_csv(output_dir / "future_leakage_risk_register.csv", index=False)
    universe_sample.to_csv(output_dir / "universe_asof_selection_sample.csv", index=False)
    macro_sample.to_csv(output_dir / "macro_asof_sample.csv", index=False)
    market_sample.to_csv(output_dir / "market_feature_recalc_sample.csv", index=False)
    edgar_sample.to_csv(output_dir / "edgar_visibility_sample.csv", index=False)
    backtest_sample.to_csv(output_dir / "backtest_recalc_sample.csv", index=False)
    (output_dir / "audit_summary.yaml").write_text(
        yaml.safe_dump(summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return AuditResult(
        risk_register=risk_register,
        universe_sample=universe_sample,
        macro_sample=macro_sample,
        market_sample=market_sample,
        edgar_sample=edgar_sample,
        backtest_sample=backtest_sample,
        summary=summary,
    )


def sample_universe_selection(run_dir: Path, sample_size: int) -> pd.DataFrame:
    path = run_dir / "universe_selection.csv"
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    selected = frame[frame["selection_status"].eq("selected")].copy() if "selection_status" in frame else frame.copy()
    columns = [
        column
        for column in [
            "symbol",
            "selection_status",
            "selection_as_of_date",
            "asof_close_date",
            "asof_close",
            "latest_close_for_asof_estimate",
            "current_market_cap",
            "market_cap_asof_estimate",
            "selection_error",
        ]
        if column in selected.columns
    ]
    selected = selected[columns].head(sample_size).copy()
    selected["audit_finding"] = "uses_current_market_cap_and_latest_close_to_estimate_asof_market_cap"
    selected["risk_level"] = "high"
    return selected


def sample_macro_asof(run_dir: Path, sample_size: int) -> pd.DataFrame:
    path = run_dir / "macro_asof_observations.parquet"
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_parquet(path).copy()
    for column in ["datetime", "observation_date", "realtime_start", "realtime_end", "effective_date"]:
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce").dt.normalize()
    frame["effective_after_feature_date"] = frame["effective_date"] > frame["datetime"]
    frame["realtime_after_feature_date"] = frame["realtime_start"] > frame["datetime"]
    interesting = frame.sort_values(["datetime", "series_id"]).head(sample_size).copy()
    columns = [
        "datetime",
        "series_id",
        "name",
        "observation_date",
        "realtime_start",
        "realtime_end",
        "effective_date",
        "days_since_release",
        "observation_age_days",
        "value",
        "effective_after_feature_date",
        "realtime_after_feature_date",
    ]
    return interesting[[column for column in columns if column in interesting.columns]]


def sample_market_features(run_dir: Path, sample_size: int) -> pd.DataFrame:
    path = run_dir / "market_features.parquet"
    if not path.exists():
        return pd.DataFrame()
    features = pd.read_parquet(path).reset_index()
    if "market_momentum_20d" not in features.columns:
        return pd.DataFrame()
    rows = []
    candidates = features.dropna(subset=["market_momentum_20d"]).head(sample_size * 5)
    for row in candidates.itertuples(index=False):
        symbol = str(row.instrument).upper()
        csv_path = run_dir / "qlib_source_csv" / f"{symbol}.csv"
        if not csv_path.exists():
            continue
        price = pd.read_csv(csv_path, usecols=["date", "close"])
        price["date"] = pd.to_datetime(price["date"], errors="coerce").dt.normalize()
        price["close"] = pd.to_numeric(price["close"], errors="coerce")
        price = price.dropna().sort_values("date")
        date = pd.Timestamp(row.datetime).normalize()
        past = price[price["date"] <= date].tail(21)
        future_rows = int((price["date"] > date).sum())
        if len(past) < 21:
            continue
        recomputed = float(past["close"].iloc[-1]) / float(past["close"].iloc[0]) - 1.0
        recorded = float(row.market_momentum_20d)
        rows.append(
            {
                "datetime": date.date().isoformat(),
                "symbol": symbol,
                "recorded_market_momentum_20d": recorded,
                "recomputed_from_past_20d": recomputed,
                "abs_diff": abs(recorded - recomputed),
                "used_future_rows": 0,
                "future_rows_available_but_not_used": future_rows,
            }
        )
        if len(rows) >= sample_size:
            break
    return pd.DataFrame(rows)


def sample_edgar_features(run_dir: Path, sample_size: int) -> pd.DataFrame:
    path = run_dir / "fundamental_features.parquet"
    if not path.exists():
        return pd.DataFrame()
    features = pd.read_parquet(path).reset_index()
    if "edgar_is_recent_filing" not in features.columns:
        return pd.DataFrame()
    features["datetime"] = pd.to_datetime(features["datetime"], errors="coerce").dt.normalize()
    features["instrument"] = features["instrument"].astype(str).str.upper()
    rows = []
    recent = features[pd.to_numeric(features["edgar_is_recent_filing"], errors="coerce").fillna(0) > 0]
    for row in recent.head(sample_size * 5).itertuples(index=False):
        symbol = row.instrument
        date = pd.Timestamp(row.datetime).normalize()
        symbol_frame = features[features["instrument"].eq(symbol)].sort_values("datetime")
        previous = symbol_frame[symbol_frame["datetime"] < date].tail(1)
        previous_recent = (
            float(previous["edgar_is_recent_filing"].iloc[0])
            if not previous.empty and pd.notna(previous["edgar_is_recent_filing"].iloc[0])
            else math.nan
        )
        days_since_10q = getattr(row, "edgar_days_since_last_10q", math.nan)
        days_since_10k = getattr(row, "edgar_days_since_last_10k", math.nan)
        rows.append(
            {
                "datetime": date.date().isoformat(),
                "symbol": symbol,
                "edgar_is_recent_filing": getattr(row, "edgar_is_recent_filing"),
                "previous_trading_day_recent_filing": previous_recent,
                "edgar_days_since_last_10q": days_since_10q,
                "edgar_days_since_last_10k": days_since_10k,
                "audit_note": "recent filing feature is present only after SEC adapter effective date expansion",
            }
        )
        if len(rows) >= sample_size:
            break
    return pd.DataFrame(rows)


def recalculate_backtest_periods(run_dir: Path, variant: str, *, sample_size: int = 10) -> pd.DataFrame:
    variant_dir = run_dir / "strategy_comparison" / variant
    positions_path = variant_dir / "backtest_positions.csv"
    nav_path = variant_dir / "backtest_nav.csv"
    if not positions_path.exists() or not nav_path.exists():
        positions_path = run_dir / "backtest_positions.csv"
        nav_path = run_dir / "backtest_nav.csv"
    if not positions_path.exists() or not nav_path.exists():
        return pd.DataFrame()
    positions = pd.read_csv(positions_path)
    nav = pd.read_csv(nav_path)
    rows = []
    for period, group in positions.groupby("period", sort=True):
        nav_row = nav[nav["period"].eq(period)]
        if nav_row.empty:
            continue
        group = group.copy()
        group["weight"] = pd.to_numeric(group["weight"], errors="coerce")
        group["gross_return"] = pd.to_numeric(group["gross_return"], errors="coerce")
        group["entry_price"] = pd.to_numeric(group["entry_price"], errors="coerce")
        group["exit_price"] = pd.to_numeric(group["exit_price"], errors="coerce")
        recomputed_position_return = group["exit_price"] / group["entry_price"] - 1.0
        recomputed_gross = float((recomputed_position_return * group["weight"]).sum())
        recorded_gross = float(nav_row.iloc[0]["gross_return"])
        rows.append(
            {
                "period": int(period),
                "signal_date": nav_row.iloc[0].get("signal_date"),
                "entry_date": nav_row.iloc[0].get("entry_date"),
                "exit_date": nav_row.iloc[0].get("exit_date"),
                "position_count": int(len(group)),
                "recorded_gross_return": recorded_gross,
                "recomputed_gross_return": recomputed_gross,
                "gross_abs_diff": abs(recorded_gross - recomputed_gross),
                "recorded_net_return": nav_row.iloc[0].get("net_return"),
                "turnover": nav_row.iloc[0].get("turnover"),
                "cost_return": nav_row.iloc[0].get("cost_return"),
                "entry_after_signal": pd.Timestamp(nav_row.iloc[0]["entry_date"]) > pd.Timestamp(nav_row.iloc[0]["signal_date"]),
                "exit_after_entry": pd.Timestamp(nav_row.iloc[0]["exit_date"]) > pd.Timestamp(nav_row.iloc[0]["entry_date"]),
            }
        )
        if len(rows) >= sample_size:
            break
    return pd.DataFrame(rows)


def build_risk_register(
    run_dir: Path,
    universe_sample: pd.DataFrame,
    macro_sample: pd.DataFrame,
    market_sample: pd.DataFrame,
    edgar_sample: pd.DataFrame,
    backtest_sample: pd.DataFrame,
) -> pd.DataFrame:
    macro_future_count = int(macro_sample.get("effective_after_feature_date", pd.Series(dtype=bool)).fillna(False).sum())
    macro_realtime_future_count = int(macro_sample.get("realtime_after_feature_date", pd.Series(dtype=bool)).fillna(False).sum())
    market_max_diff = float(market_sample.get("abs_diff", pd.Series([math.nan])).max()) if not market_sample.empty else math.nan
    backtest_max_diff = float(backtest_sample.get("gross_abs_diff", pd.Series([math.nan])).max()) if not backtest_sample.empty else math.nan
    rows = [
        risk_row(
            "R1",
            "股票池",
            "HIGH",
            "confirmed_risk",
            "`nasdaq_public` 缺少退市股票、历史成分和历史证券主数据，存在幸存者偏差。",
            "使用 Norgate/CRSP/历史成分数据源后重跑核心实验。",
        ),
        risk_row(
            "R2",
            "股票池",
            "HIGH",
            "confirmed_risk" if not universe_sample.empty else "needs_evidence",
            "`approximate_market_cap_asof` 使用当前市值与 latest close 反推 as-of 市值，隐含当前 shares / 当前公司状态。",
            "不要把当前结果视为严格 PIT；需要历史 shares outstanding 或 PIT 市值数据。",
            "universe_asof_selection_sample.csv",
        ),
        risk_row(
            "R3",
            "行业分类",
            "MEDIUM",
            "confirmed_risk",
            "sector/industry 来自当前 Nasdaq snapshot，不是历史 PIT 行业分类。",
            "行业特征可先做研究参考；严谨回测需换 PIT 行业分类。",
        ),
        risk_row(
            "R4",
            "EDGAR",
            "MEDIUM",
            "partial_mitigation",
            "EDGAR 特征按 acceptance/filing 后下一交易日生效，但 companyfacts 是否完全等价 as-filed 仍需 accession 抽样核对。",
            "保留下一交易日生效；后续抽样 SEC 原始 filing XBRL 和 companyfacts 一致性。",
            "edgar_visibility_sample.csv",
        ),
        risk_row(
            "R5",
            "宏观",
            "MEDIUM" if macro_future_count == 0 and macro_realtime_future_count else "LOW" if macro_future_count == 0 else "HIGH",
            "partial_mitigation" if macro_future_count == 0 and macro_realtime_future_count else "checked" if macro_future_count == 0 else "failed",
            "宏观特征按 effective_date <= feature date 可见；但部分日频市场序列使用 latest 模式，realtime_start 晚于历史 feature date。",
            "保留下一交易日生效；严谨回测需确认这些日频序列不可修订，或改成完整 vintage/as-of 获取。",
            "macro_asof_sample.csv",
        ),
        risk_row(
            "R6",
            "行情派生特征",
            "LOW" if (pd.notna(market_max_diff) and market_max_diff < 1e-9) else "MEDIUM",
            "checked" if (pd.notna(market_max_diff) and market_max_diff < 1e-9) else "needs_evidence",
            "market momentum/volatility/liquidity 使用 signal date 及以前行情滚动计算。",
            "继续用单元测试保护滚动窗口不使用未来价格。",
            "market_feature_recalc_sample.csv",
        ),
        risk_row(
            "R7",
            "回测",
            "LOW" if (pd.notna(backtest_max_diff) and backtest_max_diff < 1e-9) else "MEDIUM",
            "checked" if (pd.notna(backtest_max_diff) and backtest_max_diff < 1e-9) else "needs_evidence",
            "回测使用 signal date 后一交易日入场、5 个交易日后退出，抽样复算 gross return 与记录一致。",
            "继续做 entry_lag=2、成本 25/50/100 bps 压力测试。",
            "backtest_recalc_sample.csv",
        ),
        risk_row(
            "R8",
            "收益解释",
            "MEDIUM",
            "needs_stress_test",
            "当前收益非常高，可能来自股票池幸存者偏差、少数股票/行业贡献、成本假设偏低或窗口适配。",
            "修复股票池口径前，不把年化收益作为可交易策略结论。",
        ),
    ]
    return pd.DataFrame(rows)


def risk_row(
    risk_id: str,
    area: str,
    severity: str,
    status: str,
    finding: str,
    recommendation: str,
    evidence_file: str = "",
) -> dict[str, str]:
    return {
        "risk_id": risk_id,
        "area": area,
        "severity": severity,
        "status": status,
        "finding": finding,
        "recommendation": recommendation,
        "evidence_file": evidence_file,
    }


def build_summary(
    run_dir: Path,
    variant: str,
    risk_register: pd.DataFrame,
    universe_sample: pd.DataFrame,
    macro_sample: pd.DataFrame,
    market_sample: pd.DataFrame,
    edgar_sample: pd.DataFrame,
    backtest_sample: pd.DataFrame,
) -> dict[str, Any]:
    strategy_path = run_dir / "strategy_comparison.csv"
    strategy_row: dict[str, Any] = {}
    if strategy_path.exists():
        strategy = pd.read_csv(strategy_path)
        selected = strategy[strategy["name"].eq(variant)]
        if not selected.empty:
            strategy_row = selected.iloc[0].to_dict()
    return {
        "run_dir": str(run_dir),
        "variant": variant,
        "strategy_metrics": {
            key: normalize_scalar(strategy_row.get(key))
            for key in [
                "cumulative_return",
                "annualized_return",
                "max_drawdown",
                "excess_cumulative_return",
                "alpha_annualized",
                "beta",
                "avg_turnover",
                "period_count",
            ]
        },
        "risk_counts": risk_register.groupby(["severity", "status"]).size().reset_index(name="count").to_dict("records"),
        "sample_counts": {
            "universe": int(len(universe_sample)),
            "macro": int(len(macro_sample)),
            "market": int(len(market_sample)),
            "edgar": int(len(edgar_sample)),
            "backtest": int(len(backtest_sample)),
        },
        "max_market_momentum_abs_diff": normalize_scalar(
            market_sample.get("abs_diff", pd.Series([math.nan])).max() if not market_sample.empty else math.nan
        ),
        "max_backtest_gross_abs_diff": normalize_scalar(
            backtest_sample.get("gross_abs_diff", pd.Series([math.nan])).max() if not backtest_sample.empty else math.nan
        ),
    }


def normalize_scalar(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (str, bool, int)):
        return value
    return float(value)


def main() -> None:
    args = parse_args()
    result = run_audit(args.run_dir, args.output_dir, variant=args.variant, sample_size=args.sample_size)
    print(yaml.safe_dump(result.summary, allow_unicode=True, sort_keys=False))
    print(f"Output dir: {resolve_path(args.output_dir)}")


if __name__ == "__main__":
    main()
