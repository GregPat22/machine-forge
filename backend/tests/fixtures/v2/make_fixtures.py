"""Writes the v2 fixtures in this folder. Runs only against the v2 code (commit 180f707).

    git worktree add --detach /tmp/mf-v2 180f707
    backend/.venv/bin/python backend/tests/fixtures/v2/make_fixtures.py /tmp/mf-v2/backend backend/tests/fixtures/v2

Not collected by pytest. The demo machines are synthetic; no third-party data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(v2_backend: Path, out: Path) -> None:
    sys.path.insert(0, str(v2_backend))
    import app  # noqa: PLC0415

    assert Path(app.__file__).resolve().is_relative_to(v2_backend.resolve()), app.__file__
    from app.llm.mock import SCENARIOS, _refine, demo_design  # noqa: PLC0415
    from app.models import MachineDesign  # noqa: PLC0415
    from app.services.patch import apply_patches  # noqa: PLC0415
    from app.services.project_json import export_project  # noqa: PLC0415
    from app.storage import Storage  # noqa: PLC0415
    from tests.fixtures.v1.make_fixtures import PROBLEMS  # noqa: PLC0415

    assert MachineDesign.model_fields["schema_version"].default == 2

    def refined(design: MachineDesign) -> tuple[str, MachineDesign]:
        update = _refine(design)
        result = apply_patches(design, update.patches)
        assert result.design is not None, result.errors
        return update.reply, result.design

    db = out / "phase1.db"
    db.unlink(missing_ok=True)
    storage = Storage(db)
    ids: dict[str, str] = {}
    for scenario in SCENARIOS:
        design = demo_design(scenario)
        ids[scenario] = storage.create_project(PROBLEMS[scenario], "First design.", design)
    # The blister project also holds the two demo edits: add vision (U-shaped), then back to inline.
    design = demo_design("blister")
    for prompt in ("add vision inspection", "make it inline again"):
        reply, design = refined(design)
        storage.add_revision(ids["blister"], prompt, reply, design)
    # The blister project as the Phase 1 export wrote it (designs and revisions at version 2).
    project = storage.get_project(ids["blister"])
    assert project is not None
    exported = export_project(project, storage.list_revisions(ids["blister"]))
    (out / "blister-export.json").write_text(json.dumps(exported, indent=1) + "\n")
    storage._conn.close()
    (out / "phase1.json").write_text(json.dumps({"projects": ids}, indent=1) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
