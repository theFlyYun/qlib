"""Create a dry-run cleanup manifest for local experiment runs."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


PROTECTED_NAMES = {
    "crsp_daily_raw",
    "crsp_warehouse",
    "crsp_prepared_datasets",
    "crsp_shared_fred_alfred_cache",
    "feature_cache",
    "crsp_alpha158_10d_conservative_2000_2025",
    "crsp_alpha158_10d_conservative_2010_2025",
    "crsp_alpha158_macro_10d_conservative_2000_2025",
    "crsp_alpha158_macro_interactions_10d_conservative_2000_2025",
    "crsp_macro_interaction_ablation_review",
    "crsp_macro_conservative_comparison",
    "crsp_signal_model_comparison",
}


DEFER_UNTIL_2010_VALIDATION = {
    "crsp_alpha158_10d_2000_2025",
    "crsp_alpha158_5d_conservative_2000_2025",
    "crsp_alpha158_20d_conservative_2000_2025",
    "crsp_alpha158_macro_10d_2000_2025",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", default="analysis/nasdaq_top500_score/runs")
    parser.add_argument("--output-dir", default="analysis/nasdaq_top500_score/runs/cleanup_dry_run")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runs_dir = Path(args.runs_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = build_cleanup_rows(runs_dir)
    frame = pd.DataFrame(rows).sort_values(["action", "size_bytes"], ascending=[True, False])
    frame.to_csv(output_dir / "cleanup_candidates.csv", index=False)
    summary = build_summary(frame, runs_dir)
    (output_dir / "cleanup_summary.yaml").write_text(
        yaml.safe_dump(summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (output_dir / "cleanup_report.md").write_text(render_report(frame, summary), encoding="utf-8")
    print(f"Cleanup dry-run report: {output_dir / 'cleanup_report.md'}")


def build_cleanup_rows(runs_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(runs_dir.iterdir()):
        if not path.is_dir():
            continue
        size_bytes = directory_size(path)
        action, reason = classify_run(path.name)
        rows.append(
            {
                "name": path.name,
                "path": str(path),
                "size_bytes": size_bytes,
                "size_gb": round(size_bytes / (1024**3), 3),
                "action": action,
                "reason": reason,
            }
        )
    return rows


def classify_run(name: str) -> tuple[str, str]:
    if name in PROTECTED_NAMES:
        return "keep", "protected_crsp_raw_warehouse_cache_or_current_report"
    if name in DEFER_UNTIL_2010_VALIDATION:
        return "defer", "old_crsp_2000_window_delete_after_2010_baseline_passes"
    if name.startswith("crsp_macro_ablation_"):
        return "delete_candidate", "reproducible_ablation_run_heavy_outputs"
    if name.startswith("nasdaq_"):
        return "delete_candidate", "old_nasdaq_learning_run_superseded_by_crsp"
    if name.startswith("strict_"):
        return "delete_candidate", "strict_vendor_probe_or_placeholder_run"
    if name in {"macro_interaction_ablation_review"}:
        return "delete_candidate", "old_nasdaq_macro_ablation_summary"
    return "review", "unknown_or_recent_run_review_before_delete"


def directory_size(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        if child.is_file() and not child.is_symlink():
            total += child.stat().st_size
    return total


def build_summary(frame: pd.DataFrame, runs_dir: Path) -> dict[str, Any]:
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "runs_dir": str(runs_dir),
        "total_size_gb": round(float(frame["size_bytes"].sum()) / (1024**3), 3) if not frame.empty else 0.0,
        "action_counts": frame["action"].value_counts().to_dict() if not frame.empty else {},
        "delete_candidate_size_gb": round(float(frame.loc[frame["action"].eq("delete_candidate"), "size_bytes"].sum()) / (1024**3), 3)
        if not frame.empty
        else 0.0,
        "deferred_size_gb": round(float(frame.loc[frame["action"].eq("defer"), "size_bytes"].sum()) / (1024**3), 3)
        if not frame.empty
        else 0.0,
        "protected": sorted(PROTECTED_NAMES),
    }


def render_report(frame: pd.DataFrame, summary: dict[str, Any]) -> str:
    lines = [
        "# Cleanup Dry-Run Report",
        "",
        f"Generated at: {summary['generated_at']}",
        "",
        "This is a dry-run only. No directories were deleted.",
        "",
        "## Summary",
        "",
        f"- Total runs size: {summary['total_size_gb']} GB",
        f"- Delete-candidate size: {summary['delete_candidate_size_gb']} GB",
        f"- Deferred size: {summary['deferred_size_gb']} GB",
        "- Action counts:",
        "```yaml",
        yaml.safe_dump(summary["action_counts"], sort_keys=False).strip(),
        "```",
        "",
        "## Candidates",
        "",
        "| Action | Size GB | Name | Reason |",
        "|---|---:|---|---|",
    ]
    for row in frame.sort_values(["action", "size_bytes"], ascending=[True, False]).to_dict("records"):
        lines.append(f"| {row['action']} | {row['size_gb']} | `{row['name']}` | {row['reason']} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
