"""Load `patient_promotions_dataset.jsonl` and expose eligible rows only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import config


def load_eligible_records() -> list[dict[str, Any]]:
    path = Path(config.DATASET_PATH or "")
    if not path.is_file():
        raise FileNotFoundError(f"Dataset not found: {path}")
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            promo = row.get("promotion") or {}
            if promo.get("patient_is_eligible") is True:
                out.append(row)
    return out


def get_eligible_record(record_id: str) -> dict[str, Any] | None:
    for row in load_eligible_records():
        if row.get("record_id") == record_id:
            return row
    return None
