"""Shared paths and serialization helpers for evaluation scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


EVALUATION_ROOT = Path(__file__).resolve().parent
LOG_DIR = EVALUATION_ROOT / "logs"
FIGURE_DIR = EVALUATION_ROOT / "figures"


def ensure_output_dirs() -> tuple[Path, Path]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR, FIGURE_DIR


def write_records(records: Iterable[dict[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(list(records)).to_csv(path, index=False)
    return path


def write_json(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    return path

