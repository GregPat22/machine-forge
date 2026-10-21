"""Databases written by v0.3 must open with the current Storage (engineering rule 7)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.models import MachineDesign
from app.llm.mock import _initial_design
from app.storage import DEFAULT_WORKSPACE, DESIGN_SCHEMA_VERSION, MIGRATIONS, Storage
from tests.conftest import BLISTER_PROBLEM

# The schema exactly as v0.3 (commit 776efa2) created it. Do not edit: it is the fixture.
V03_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    problem TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS revisions (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    number INTEGER NOT NULL,
    prompt TEXT NOT NULL,
    reply TEXT NOT NULL,
    design TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (project_id, number)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    revision INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_list (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier TEXT NOT NULL,
    manufacturer TEXT,
    part_number TEXT,
    description TEXT,
    unit_price REAL,
    currency TEXT NOT NULL,
    lead_time_days INTEGER,
    moq INTEGER,
    source_file TEXT
);
CREATE TABLE IF NOT EXISTS supplier_ratings (
    name TEXT PRIMARY KEY COLLATE NOCASE,
    quality INTEGER,
    delivery INTEGER,
    preferred INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS offer_cache (
    connector TEXT NOT NULL,
    query TEXT NOT NULL,
    offers TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (connector, query)
);
"""
NOW = "2026-10-20T08:00:00+00:00"


def _write_v03_database(path: Path) -> MachineDesign:
    design = _initial_design(BLISTER_PROBLEM)
    conn = sqlite3.connect(path)
    with conn:
        conn.executescript(V03_SCHEMA)
        conn.execute("INSERT INTO projects VALUES (?, ?, ?, ?, ?)", ("abc123", design.name, BLISTER_PROBLEM, NOW, NOW))
        conn.execute(
            "INSERT INTO revisions VALUES (?, ?, ?, ?, ?, ?)",
            ("abc123", 1, BLISTER_PROBLEM, "First design.", design.model_dump_json(), NOW),
        )
        conn.executemany(
            "INSERT INTO messages (project_id, role, content, revision, created_at) VALUES (?, ?, ?, ?, ?)",
            [("abc123", "user", BLISTER_PROBLEM, None, NOW), ("abc123", "assistant", "First design.", 1, NOW)],
        )
        conn.execute(
            "INSERT INTO price_list (supplier, manufacturer, part_number, currency) VALUES (?, ?, ?, ?)",
            ("ACME", "Festo", "DSBC-80-50", "EUR"),
        )
        conn.execute("INSERT INTO supplier_ratings (name, quality, delivery) VALUES (?, ?, ?)", ("ACME", 4, 5))
        conn.execute(
            "INSERT INTO offer_cache VALUES (?, ?, ?, ?)", ("mouser", "DSBC-80-50", json.dumps([]), NOW)
        )
    conn.close()
    return design


def _columns(path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def test_v03_database_opens_and_reads_projects(tmp_path: Path) -> None:
    path = tmp_path / "v03.db"
    design = _write_v03_database(path)

    storage = Storage(path)
    [summary] = storage.list_projects()
    assert summary.id == "abc123" and summary.latest_revision == 1
    project = storage.get_project("abc123")
    assert project is not None
    assert project.design == design
    assert [m.role for m in project.messages] == ["user", "assistant"]
    revision = storage.get_revision("abc123", 1)
    assert revision is not None and revision.schema_version == DESIGN_SCHEMA_VERSION
    assert storage.price_list()[0].part_number == "DSBC-80-50"
    assert storage.ratings()["acme"].quality == 4
    assert storage.cached_offers("mouser", "DSBC-80-50", max_age_hours=10**6) == []

    conn = sqlite3.connect(path)
    try:
        for table, column, _ in MIGRATIONS:
            assert column in _columns(path, table), f"{table}.{column} missing after migration"
            if column == "workspace_id":
                values = {row[0] for row in conn.execute(f"SELECT DISTINCT workspace_id FROM {table}")}
                assert values == {DEFAULT_WORKSPACE}
        assert {row[0] for row in conn.execute("SELECT DISTINCT schema_version FROM revisions")} == {1}
    finally:
        conn.close()


def test_migration_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "v03.db"
    _write_v03_database(path)
    Storage(path)
    Storage(path)  # second open: columns exist, nothing to add, no error
    for table, column, _ in MIGRATIONS:
        assert sum(1 for c in _columns(path, table) if c == column) == 1


def test_new_revisions_record_the_schema_version(storage: Storage) -> None:
    design = _initial_design(BLISTER_PROBLEM)
    project_id = storage.create_project(BLISTER_PROBLEM, "ok", design)
    revision = storage.get_revision(project_id, 1)
    assert revision is not None and revision.schema_version == DESIGN_SCHEMA_VERSION
