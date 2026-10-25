"""Writes the v1 fixtures in this folder. Runs only against the v1 code (commit f93f288).

    git worktree add --detach /tmp/mf-v1 f93f288
    backend/.venv/bin/python backend/tests/fixtures/v1/make_fixtures.py /tmp/mf-v1/backend backend/tests/fixtures/v1

Not collected by pytest. The demo problems are synthetic; no third-party data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROBLEMS = {
    "blister": "We need to pack 300 tablets per minute into PVC/Alu blisters of 10 for a pharma customer.",
    "cartoner": "Put 120 cosmetic tubes per minute into folding cartons with a leaflet.",
    "filling": "Fill 60 bottles per minute with 250 ml of liquid soap and cap them.",
    "assembly": "Assemble two plastic housing halves, 20 pieces per minute.",
}


def main(v1_backend: Path, out: Path) -> None:
    sys.path.insert(0, str(v1_backend))
    import app  # noqa: PLC0415

    assert Path(app.__file__).resolve().is_relative_to(v1_backend.resolve()), app.__file__
    from app.llm.mock import _initial_design, _refine  # noqa: PLC0415
    from app.storage import Storage  # noqa: PLC0415

    designs = {name: _initial_design(problem) for name, problem in PROBLEMS.items()}
    designs["blister-vision"] = _refine(_initial_design(PROBLEMS["blister"]), "add vision inspection").design
    designs["blister-u-shape"] = _refine(_initial_design(PROBLEMS["blister"]), "make it u-shaped").design
    (out / "designs").mkdir(parents=True, exist_ok=True)
    for name, design in designs.items():
        (out / "designs" / f"{name}.json").write_text(design.model_dump_json(indent=1) + "\n")

    db = out / "phase0.db"
    db.unlink(missing_ok=True)
    storage = Storage(db)
    pid = storage.create_project(PROBLEMS["blister"], "First design.", designs["blister"])
    storage.add_revision(pid, "add vision inspection", "Added vision.", designs["blister-vision"])
    storage.add_revision(pid, "make it u-shaped", "U-shape.", designs["blister-u-shape"])
    storage.create_project(PROBLEMS["cartoner"], "First design.", designs["cartoner"])
    storage._conn.close()
    (out / "phase0.json").write_text(json.dumps({"blister_project": pid}, indent=1) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
