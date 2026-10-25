"""SQLite persistence. One file, no server; swap for Postgres when several users share it."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.migrations.design_v1 import CURRENT_VERSION, migrate_design
from app.models import (
    ChatMessage,
    MachineDesign,
    Offer,
    PriceListEntry,
    Project,
    SupplierInfo,
    SupplierRating,
    ProjectSummary,
    Revision,
)

# Every table carries a workspace_id (one default workspace until users exist, see ADR 0008).
# Stored designs carry the schema version of MachineDesign they were written with (1 = v0.3 and
# Phase 0, 2 = model v2). Older designs are migrated on read; their rows are never rewritten.
DEFAULT_WORKSPACE = "default"
DESIGN_SCHEMA_VERSION = CURRENT_VERSION

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL DEFAULT 'default',
    name TEXT NOT NULL,
    problem TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS revisions (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    workspace_id TEXT NOT NULL DEFAULT 'default',
    number INTEGER NOT NULL,
    prompt TEXT NOT NULL,
    reply TEXT NOT NULL,
    design TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    PRIMARY KEY (project_id, number)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    workspace_id TEXT NOT NULL DEFAULT 'default',
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    revision INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_list (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL DEFAULT 'default',
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
    workspace_id TEXT NOT NULL DEFAULT 'default',
    quality INTEGER,
    delivery INTEGER,
    preferred INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS offer_cache (
    connector TEXT NOT NULL,
    query TEXT NOT NULL,
    workspace_id TEXT NOT NULL DEFAULT 'default',
    offers TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (connector, query)
);
"""

# Columns added after v0.3, applied to databases created before them: (table, column, DDL type).
MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("projects", "workspace_id", "TEXT NOT NULL DEFAULT 'default'"),
    ("revisions", "workspace_id", "TEXT NOT NULL DEFAULT 'default'"),
    ("revisions", "schema_version", "INTEGER NOT NULL DEFAULT 1"),
    ("messages", "workspace_id", "TEXT NOT NULL DEFAULT 'default'"),
    ("price_list", "workspace_id", "TEXT NOT NULL DEFAULT 'default'"),
    ("supplier_ratings", "workspace_id", "TEXT NOT NULL DEFAULT 'default'"),
    ("offer_cache", "workspace_id", "TEXT NOT NULL DEFAULT 'default'"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Storage:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._lock = threading.Lock()

    def _migrate(self) -> None:
        """Add columns that newer versions expect; safe to run on every start."""
        with self._conn:
            for table, column, ddl in MIGRATIONS:
                existing = {row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})")}
                if column not in existing:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    # --- projects -------------------------------------------------------------------------

    def create_project(self, problem: str, reply: str, design: MachineDesign) -> str:
        project_id = uuid.uuid4().hex[:12]
        now = _now().isoformat()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO projects (id, name, problem, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (project_id, design.name, problem, now, now),
            )
            self._insert_revision(project_id, 1, problem, reply, design, now)
        return project_id

    def add_revision(self, project_id: str, prompt: str, reply: str, design: MachineDesign) -> int:
        now = _now().isoformat()
        with self._lock, self._conn:
            (latest,) = self._conn.execute(
                "SELECT MAX(number) FROM revisions WHERE project_id = ?", (project_id,)
            ).fetchone()
            number = (latest or 0) + 1
            self._insert_revision(project_id, number, prompt, reply, design, now)
            self._conn.execute(
                "UPDATE projects SET name = ?, updated_at = ? WHERE id = ?", (design.name, now, project_id)
            )
        return number

    def _insert_revision(
        self, project_id: str, number: int, prompt: str, reply: str, design: MachineDesign, now: str
    ) -> None:
        self._conn.execute(
            """INSERT INTO revisions (project_id, number, prompt, reply, design, schema_version, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (project_id, number, prompt, reply, design.model_dump_json(), DESIGN_SCHEMA_VERSION, now),
        )
        self._conn.executemany(
            "INSERT INTO messages (project_id, role, content, revision, created_at) VALUES (?, ?, ?, ?, ?)",
            [(project_id, "user", prompt, None, now), (project_id, "assistant", reply, number, now)],
        )

    def add_message(self, project_id: str, role: str, content: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO messages (project_id, role, content, revision, created_at) VALUES (?, ?, ?, NULL, ?)",
                (project_id, role, content, _now().isoformat()),
            )

    def list_projects(self) -> list[ProjectSummary]:
        rows = self._conn.execute(
            """SELECT p.*, (SELECT MAX(number) FROM revisions r WHERE r.project_id = p.id) AS latest
               FROM projects p ORDER BY p.updated_at DESC"""
        ).fetchall()
        return [self._summary(row) for row in rows]

    def get_project(self, project_id: str) -> Project | None:
        row = self._conn.execute(
            """SELECT p.*, (SELECT MAX(number) FROM revisions r WHERE r.project_id = p.id) AS latest
               FROM projects p WHERE p.id = ?""",
            (project_id,),
        ).fetchone()
        if row is None:
            return None
        revision = self.get_revision(project_id, row["latest"])
        assert revision is not None
        messages = [
            ChatMessage(role=m["role"], content=m["content"], revision=m["revision"], created_at=m["created_at"])
            for m in self._conn.execute(
                "SELECT * FROM messages WHERE project_id = ? ORDER BY id", (project_id,)
            ).fetchall()
        ]
        return Project(**self._summary(row).model_dump(), messages=messages, design=revision.design)

    def get_revision(self, project_id: str, number: int) -> Revision | None:
        row = self._conn.execute(
            "SELECT * FROM revisions WHERE project_id = ? AND number = ?", (project_id, number)
        ).fetchone()
        if row is None:
            return None
        return Revision(
            number=row["number"],
            prompt=row["prompt"],
            reply=row["reply"],
            design=migrate_design(json.loads(row["design"]), from_version=row["schema_version"]),
            schema_version=row["schema_version"],
            created_at=row["created_at"],
        )

    def list_revisions(self, project_id: str) -> list[Revision]:
        rows = self._conn.execute(
            "SELECT number FROM revisions WHERE project_id = ? ORDER BY number", (project_id,)
        ).fetchall()
        return [r for row in rows if (r := self.get_revision(project_id, row["number"])) is not None]

    def delete_project(self, project_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return cur.rowcount > 0

    @staticmethod
    def _summary(row: sqlite3.Row) -> ProjectSummary:
        return ProjectSummary(
            id=row["id"],
            name=row["name"],
            problem=row["problem"],
            latest_revision=row["latest"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # --- price list -----------------------------------------------------------------------

    def replace_price_list(self, entries: list[PriceListEntry], append: bool = False) -> int:
        with self._lock, self._conn:
            if not append:
                self._conn.execute("DELETE FROM price_list")
            self._conn.executemany(
                """INSERT INTO price_list (supplier, manufacturer, part_number, description, unit_price,
                   currency, lead_time_days, moq, source_file) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (e.supplier, e.manufacturer, e.part_number, e.description, e.unit_price, e.currency,
                     e.lead_time_days, e.moq, e.source_file)
                    for e in entries
                ],
            )
        return len(entries)

    def price_list(self) -> list[PriceListEntry]:
        rows = self._conn.execute("SELECT * FROM price_list ORDER BY supplier, part_number").fetchall()
        return [PriceListEntry(**dict(row)) for row in rows]

    # --- supplier ratings -----------------------------------------------------------------

    def set_rating(self, rating: SupplierRating) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO supplier_ratings (name, quality, delivery, preferred, notes) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET quality = excluded.quality, delivery = excluded.delivery,
                   preferred = excluded.preferred, notes = excluded.notes""",
                (rating.name.strip(), rating.quality, rating.delivery, int(rating.preferred), rating.notes),
            )

    def ratings(self) -> dict[str, SupplierRating]:
        """Ratings keyed by lower-case supplier name."""
        rows = self._conn.execute("SELECT * FROM supplier_ratings").fetchall()
        return {
            row["name"].lower(): SupplierRating(name=row["name"], quality=row["quality"], delivery=row["delivery"],
                                                preferred=bool(row["preferred"]), notes=row["notes"])
            for row in rows
        }

    def suppliers(self) -> list[SupplierInfo]:
        """Every supplier in the price list or the ratings, with its rating and item count."""
        counts = {
            row["supplier"].lower(): (row["supplier"], row["n"])
            for row in self._conn.execute("SELECT supplier, COUNT(*) AS n FROM price_list GROUP BY supplier COLLATE NOCASE")
        }
        ratings = self.ratings()
        names = {key: counts[key][0] if key in counts else ratings[key].name for key in {*counts, *ratings}}
        out = []
        for key, name in names.items():
            rating = ratings.get(key) or SupplierRating(name=name)
            out.append(SupplierInfo(**{**rating.model_dump(), "name": name},
                                    price_list_items=counts.get(key, (name, 0))[1]))
        return sorted(out, key=lambda s: s.name.lower())

    # --- external offer cache -------------------------------------------------------------

    def cached_offers(self, connector: str, query: str, max_age_hours: int) -> list[Offer] | None:
        row = self._conn.execute(
            "SELECT offers, fetched_at FROM offer_cache WHERE connector = ? AND query = ?", (connector, query)
        ).fetchone()
        if row is None or datetime.fromisoformat(row["fetched_at"]) < _now() - timedelta(hours=max_age_hours):
            return None
        return [Offer.model_validate(o) for o in json.loads(row["offers"])]

    def cache_offers(self, connector: str, query: str, offers: list[Offer]) -> None:
        payload = json.dumps([o.model_dump() for o in offers])
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO offer_cache (connector, query, offers, fetched_at) VALUES (?, ?, ?, ?)",
                (connector, query, payload, _now().isoformat()),
            )
