"""Lightweight runtime profiling for experiment stages."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import pandas as pd
import yaml


@dataclass
class RuntimeProfiler:
    """Collect wall-clock durations without coupling stages to logging."""

    rows: list[dict[str, Any]] = field(default_factory=list)

    @contextmanager
    def stage(self, name: str, **metadata: Any) -> Iterator[None]:
        started = time.perf_counter()
        status = "ok"
        error = ""
        try:
            yield
        except Exception as exc:
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            elapsed = time.perf_counter() - started
            self.rows.append(
                {
                    "stage": name,
                    "seconds": elapsed,
                    "status": status,
                    "error": error,
                    **metadata,
                }
            )

    def write(self, csv_path: Path, yaml_path: Path) -> None:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        frame = pd.DataFrame(self.rows)
        frame.to_csv(csv_path, index=False)
        summary = {
            "stage_count": int(len(self.rows)),
            "total_seconds": float(frame["seconds"].sum()) if "seconds" in frame else 0.0,
            "slowest_stages": frame.sort_values("seconds", ascending=False).head(10).to_dict("records")
            if "seconds" in frame
            else [],
        }
        yaml_path.write_text(
            yaml.safe_dump(summary, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
