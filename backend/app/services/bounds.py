"""Loads the plausibility bounds table (Phase 2, section E).

The only reader of `backend/data/catalog_bounds.yaml`: the check itself is the pure function
`app.engines.bounds.check_bounds`. The table's version is the SHA-256 of the file, so results
computed with an older table are recomputed when it changes.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from app.engines.bounds import BoundsTable

BOUNDS_PATH = Path(__file__).resolve().parents[2] / "data" / "catalog_bounds.yaml"


def load_bounds_table(path: Path = BOUNDS_PATH) -> BoundsTable:
    """Reads, parses (`yaml.safe_load`) and validates the table. Raises if a row is invalid."""
    raw = path.read_bytes()
    return BoundsTable(version=hashlib.sha256(raw).hexdigest(), rows=yaml.safe_load(raw))
