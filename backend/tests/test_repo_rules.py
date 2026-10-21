"""Repository-wide checks for docs/engineering-rules.md. They read source files, never the network."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO / "frontend" / "src"


def _frontend_sources() -> list[Path]:
    return sorted(p for p in FRONTEND_SRC.rglob("*") if p.suffix in (".ts", ".tsx"))


def test_frontend_does_not_import_the_deleted_render() -> None:
    """Rule 4: the procedural render was removed in Phase 0 and must not come back by import."""
    assert FRONTEND_SRC.is_dir()
    assert not (FRONTEND_SRC / "render").exists(), "frontend/src/render/ was deleted in Phase 0"
    offenders = []
    pattern = re.compile(r"""from\s+["'][^"']*(?:/render/|MachineRender)[^"']*["']""")
    for source in _frontend_sources():
        if pattern.search(source.read_text(encoding="utf-8")):
            offenders.append(str(source.relative_to(REPO)))
    assert offenders == [], f"files import the deleted render: {offenders}"
