"""Timing results per revision (Phase 2, section G; ADR 0028).

The timing of a revision is computed the first time it is read, then stored with its provenance:
the engine version and the bounds table version. A stored row whose versions match is returned
as it is; a row from an older engine or table is recomputed and replaced. Old revisions are
handled the same way the first time they are read; nothing is filled in bulk. The revision's
design is never changed (ADR 0003).
"""

from __future__ import annotations

from functools import cache

from app.engines.bounds import BoundsTable, check_bounds
from app.engines.timing import ENGINE_VERSION, TimingResult, design_timing
from app.models import MachineDesign
from app.services.bounds import load_bounds_table
from app.services.designer import ProjectNotFound
from app.storage import Storage

ENGINE = "timing"


@cache
def bounds_table() -> BoundsTable:
    """The plausibility bounds table, read once per process."""
    return load_bounds_table()


def compute_timing(design: MachineDesign, table: BoundsTable) -> TimingResult:
    """The timing engine and the bounds check over one design, in one result.

    A mechanism's `out_of_bounds` warnings follow its station's own warnings; a transport's go to
    the result's `warnings`, since no station owns a transport.
    """
    result = design_timing(design)
    check = check_bounds(design, table)
    stations = [
        station.model_copy(update={"warnings": [
            *station.warnings, *(w for w in check.warnings if w.station_id == station.station_id)]})
        for station in result.stations
    ]
    return result.model_copy(update={
        "bounds_version": table.version,
        "stations": stations,
        "warnings": [w for w in check.warnings if w.station_id is None],
        "unchecked": check.unchecked,
    })


def timing_for(storage: Storage, project_id: str, revision: int, table: BoundsTable | None = None) -> TimingResult:
    """The stored timing of a revision when it is current, else computed, stored and returned."""
    table = table or bounds_table()
    stored = storage.get_result(project_id, revision, ENGINE)
    if stored is not None and stored.engine_version == ENGINE_VERSION and stored.inputs_version == table.version:
        return TimingResult.model_validate_json(stored.result)
    rev = storage.get_revision(project_id, revision)
    if rev is None:
        raise ProjectNotFound(f"Revision {revision} of project {project_id} not found")
    result = compute_timing(rev.design, table)
    storage.put_result(project_id, revision, ENGINE, ENGINE_VERSION, table.version, result.model_dump_json())
    return result
