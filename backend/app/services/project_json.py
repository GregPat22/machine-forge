"""Project JSON export and import (Phase 1 spec, section E). Own format only.

The file holds the project, every revision (designs at the current schema version) and the chat
messages. Import validates size and versions, migrates designs written with an older
`schema_version`, and always creates a new project; it never overwrites one.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.migrations.design_v1 import CURRENT_VERSION, migrate_design
from app.models import ChatMessage, Project, Revision
from app.storage import Storage

FORMAT = "machine-forge-project"
FORMAT_VERSION = 1
DEFAULT_MAX_IMPORT_BYTES = 20 * 1024 * 1024


class ProjectImportError(ValueError):
    """The file cannot be imported. `status` is the HTTP status the API answers with."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class ExportedProject(BaseModel):
    name: str
    problem: str
    created_at: datetime
    updated_at: datetime


class ExportedRevision(BaseModel):
    number: int
    prompt: str
    reply: str
    schema_version: int
    created_at: datetime
    design: dict[str, Any]


class ProjectFile(BaseModel):
    format: str
    format_version: int
    project: ExportedProject
    revisions: list[ExportedRevision] = Field(min_length=1)
    messages: list[ChatMessage] = Field(default_factory=list)


def export_project(project: Project, revisions: list[Revision]) -> dict[str, Any]:
    """The project as a JSON-ready dict; each design is stored as it is read (current version)."""
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "project": {
            "name": project.name,
            "problem": project.problem,
            "created_at": project.created_at.isoformat(),
            "updated_at": project.updated_at.isoformat(),
        },
        "revisions": [
            {
                "number": r.number,
                "prompt": r.prompt,
                "reply": r.reply,
                "schema_version": CURRENT_VERSION,
                "created_at": r.created_at.isoformat(),
                "design": r.design.model_dump(mode="json"),
            }
            for r in revisions
        ],
        "messages": [m.model_dump(mode="json") for m in project.messages],
    }


def import_project(storage: Storage, data: bytes, max_bytes: int = DEFAULT_MAX_IMPORT_BYTES) -> str:
    """Validate `data`, migrate its designs and store them as a new project. Returns its id."""
    if len(data) > max_bytes:
        raise ProjectImportError(
            f"File is {len(data)} bytes; the import limit is {max_bytes} bytes.", status=413
        )
    try:
        raw = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectImportError(f"Not a valid JSON file: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("format") != FORMAT:
        raise ProjectImportError(f'Not a Machine Forge project file (expected format "{FORMAT}").')
    version = raw.get("format_version")
    if version != FORMAT_VERSION:
        raise ProjectImportError(
            f"Unsupported format_version {version!r}; this version reads format_version {FORMAT_VERSION}."
        )
    try:
        file = ProjectFile.model_validate(raw)
    except ValidationError as exc:
        raise ProjectImportError(f"Project file is malformed: {_first_error(exc)}") from exc

    numbers = [r.number for r in file.revisions]
    if len(set(numbers)) != len(numbers) or min(numbers) < 1:
        raise ProjectImportError("Revision numbers must be unique and start at 1 or higher.")
    for message in file.messages:
        if message.revision is not None and message.revision not in numbers:
            raise ProjectImportError(f"A message refers to revision {message.revision}, which is not in the file.")

    revisions: list[Revision] = []
    for rev in sorted(file.revisions, key=lambda r: r.number):
        if rev.schema_version > CURRENT_VERSION:
            raise ProjectImportError(
                f"Revision {rev.number} uses design schema {rev.schema_version}; "
                f"this version reads up to {CURRENT_VERSION}."
            )
        try:
            design = migrate_design(rev.design, from_version=rev.schema_version)
        except (ValidationError, ValueError) as exc:
            detail = _first_error(exc) if isinstance(exc, ValidationError) else str(exc)
            raise ProjectImportError(f"Revision {rev.number} has an invalid design: {detail}") from exc
        revisions.append(
            Revision(number=rev.number, prompt=rev.prompt, reply=rev.reply, design=design,
                     schema_version=CURRENT_VERSION, created_at=rev.created_at)
        )
    return storage.import_project(file.project.model_dump(), revisions, file.messages)


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    where = ".".join(str(p) for p in err["loc"]) or "(root)"
    return f"{where}: {err['msg']}"
