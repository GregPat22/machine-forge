"""Timing engine: one station's cycle laid out in time (Phase 2, section C; ADR 0027).

A pure function over the model: no I/O, deterministic. The steps of a station are sorted by
`(order, id)` and grouped into blocks: a step with no `parallel_group` is a block of its own,
steps that share a group form one block. Blocks run one after another; a block lasts as long as
its longest member. This is the longest (critical) path of a series-parallel plan:
J. E. Kelley Jr., M. R. Walker, "Critical-path planning and scheduling", Papers presented at the
December 1-3, 1959, Eastern Joint IRE-AIEE-ACM Computer Conference, pp. 160-173,
doi:10.1145/1460299.1460318 (pages from the publisher's Crossref record, read 2026-10-29).
TODO(source): the section and page of the forward pass inside the paper were not checked against
the text.

A fixed-duration step lasts its `duration_s`. A motion step moves its mechanism through one full
stroke, rest to rest, with the mechanism's profile (`app.engines.motion`, Biagiotti & Melchiorri
2008, sections 3.2 and 3.4), then pauses for the mechanism's `dwell_s` when set.

An incomplete station is a normal result with its reasons (`not_computable`). A value the patch
validator forbids (a zero or negative number, a motion step with a duration, a duplicate id) that
still reaches the engine raises `TimingError`; nothing is clamped or approximated.

The result models live here, not in `MachineDesign` (ADR 0003): they are computed, never stored
in the design.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Literal

from pydantic import BaseModel

from app.engines.motion import MotionError, MoveProfile, s_curve, trapezoidal
from app.models import MachineDesign, Mechanism, Station, Step

# Bumped whenever a formula or a rule of this engine changes, so stored results are recomputed.
# A stored timing result also holds the bounds check (`app.engines.bounds`) and its merge
# (`app.services.timing.compute_timing`): a change to either bumps this too.
ENGINE_VERSION = 3

ReasonCode = Literal[
    "no_steps",
    "duration_missing",
    "mechanism_missing",
    "stroke_missing",
    "max_speed_missing",
    "acceleration_missing",
    "jerk_missing",
    "parallel_group_split",
    "mechanism_overlap",
]
WarningCode = Literal["target_not_met", "out_of_bounds"]
BarSource = Literal["trapezoidal", "s_curve", "fixed"]
# Fields the plausibility bounds can check (`app.engines.bounds`): a mechanism's or a transport's.
BoundsField = Literal["stroke", "max_speed", "acceleration", "jerk", "index_time_s", "speed_mm_s"]


class TimingError(ValueError):
    """A value the patch validator forbids reached the timing engine."""


class NotComputableReason(BaseModel):
    """Why a station has no cycle time. Names the step, the mechanism or the group concerned."""

    code: ReasonCode
    step_id: str | None = None
    mechanism_id: str | None = None
    parallel_group: int | None = None


class TimingWarning(BaseModel):
    """A finding. Never a correction: the design is not changed.

    `target_not_met`: on a computable station, `value` is the cycle, `limit` the target.
    `out_of_bounds`: `value` is the mechanism's (station and mechanism ids) or the transport's
    `field`, `limit` the catalog bound (`min` or `max`) it passes, from the bounds row `row_id`
    with its source title and URL.
    """

    code: WarningCode
    station_id: str | None = None
    step_id: str | None = None
    value: float
    limit: float
    mechanism_id: str | None = None
    transport_id: str | None = None
    field: BoundsField | None = None
    bound: Literal["min", "max"] | None = None
    row_id: str | None = None
    source_title: str | None = None
    source_url: str | None = None


class TimingBar(BaseModel):
    """One step in the timing diagram, in seconds from the start of the cycle."""

    step_id: str
    start_s: float
    end_s: float
    duration_s: float
    critical: bool
    source: BarSource


class TimingRow(BaseModel):
    """A diagram row: a mechanism (a bar per motion step) or a fixed-duration step (one bar)."""

    kind: Literal["mechanism", "fixed"]
    id: str
    bars: list[TimingBar]


class MechanismTiming(BaseModel):
    """Busy time (its motion steps, dwell included), idle time (cycle - busy), utilisation (busy / cycle)."""

    mechanism_id: str
    busy_s: float
    idle_s: float
    utilisation: float


class StationTiming(BaseModel):
    station_id: str
    cycle_time_s: float | None = None
    target_cycle_time_s: float | None = None
    margin_s: float | None = None
    limiting_step_id: str | None = None
    critical_path: list[str] = []
    mechanisms: list[MechanismTiming] = []
    diagram: list[TimingRow] = []
    warnings: list[TimingWarning] = []
    not_computable: list[NotComputableReason] = []

    @property
    def computable(self) -> bool:
        return self.cycle_time_s is not None


class UncheckedMechanism(BaseModel):
    """A mechanism that no component drives, so no plausibility bound can apply to it."""

    station_id: str
    mechanism_id: str


class TimingResult(BaseModel):
    engine_version: int = ENGINE_VERSION
    # SHA-256 of the plausibility bounds table (section E); set by the service that reads it.
    bounds_version: str | None = None
    stations: list[StationTiming]
    # Set by the service from the bounds check: a mechanism's warnings go to its station's
    # `warnings`; a transport's warnings, which no station owns, go here.
    warnings: list[TimingWarning] = []
    unchecked: list[UncheckedMechanism] = []


def design_timing(design: MachineDesign) -> TimingResult:
    """The timing of every station of the design, in the order of `design.stations`."""
    return TimingResult(stations=[station_timing(s) for s in design.stations])


def station_timing(station: Station) -> StationTiming:
    """Cycle time, critical path, limiting step, axis use, diagram and target check of one station."""
    steps = sorted(station.steps, key=lambda s: (s.order, s.id))
    _unique(station.id, "step", [s.id for s in steps])
    _unique(station.id, "mechanism", [m.id for m in station.mechanisms])
    mechanisms = {m.id: m for m in station.mechanisms}
    target = station.target_cycle_time_s
    if target is not None:
        _positive(f"station '{station.id}' target_cycle_time_s", target)

    reasons: list[NotComputableReason] = []
    if not steps:
        reasons.append(NotComputableReason(code="no_steps"))
    durations: dict[str, float] = {}
    sources: dict[str, BarSource] = {}
    for step in steps:
        if step.kind == "fixed_duration":
            if step.duration_s is None:
                reasons.append(NotComputableReason(code="duration_missing", step_id=step.id))
                continue
            durations[step.id] = _positive(f"step '{step.id}' duration_s", step.duration_s)
            sources[step.id] = "fixed"
            continue
        if step.duration_s is not None:
            raise TimingError(f"step '{step.id}' is a motion step: its duration is computed, not set")
        mechanism = mechanisms.get(step.mechanism_id) if step.mechanism_id is not None else None
        if mechanism is None:
            reasons.append(NotComputableReason(code="mechanism_missing", step_id=step.id,
                                               mechanism_id=step.mechanism_id))
            continue
        missing = _missing_values(mechanism)
        for code in missing:
            reason = NotComputableReason(code=code, mechanism_id=mechanism.id)
            if reason not in reasons:
                reasons.append(reason)
        if not missing:
            durations[step.id] = _stroke_time(mechanism)
            sources[step.id] = mechanism.profile

    blocks, split_groups = _blocks(steps)
    reasons.extend(NotComputableReason(code="parallel_group_split", parallel_group=g) for g in split_groups)
    for block in blocks:
        moves = Counter(s.mechanism_id for s in block if s.kind == "motion" and s.mechanism_id in mechanisms)
        reasons.extend(NotComputableReason(code="mechanism_overlap", mechanism_id=mid,
                                           parallel_group=block[0].parallel_group)
                       for mid, count in moves.items() if count > 1)
    if reasons:
        return StationTiming(station_id=station.id, target_cycle_time_s=target, not_computable=reasons)

    # Each block starts when the previous one ends. Its first longest member is on the critical
    # path: members are in (order, id) order, so ties go to the lower order, then the lower id.
    starts: dict[str, float] = {}
    critical: list[Step] = []
    block_durations: list[float] = []
    for block in blocks:
        start = math.fsum(block_durations)
        longest = max(durations[s.id] for s in block)
        critical.append(next(s for s in block if durations[s.id] == longest))
        block_durations.append(longest)
        for step in block:
            starts[step.id] = start
    cycle = math.fsum(block_durations)
    longest_critical = max(durations[s.id] for s in critical)
    limiting = next(s for s in critical if durations[s.id] == longest_critical)
    on_path = {s.id for s in critical}

    # One row per mechanism and per fixed step, in order of first start (steps are in start order).
    rows: dict[tuple[str, str], TimingRow] = {}
    for step in steps:
        key = ("mechanism", step.mechanism_id) if step.kind == "motion" and step.mechanism_id else ("fixed", step.id)
        row = rows.setdefault(key, TimingRow(kind=key[0], id=key[1], bars=[]))  # type: ignore[arg-type]
        start, duration = starts[step.id], durations[step.id]
        row.bars.append(TimingBar(step_id=step.id, start_s=start, end_s=start + duration, duration_s=duration,
                                  critical=step.id in on_path, source=sources[step.id]))
    axes = []
    for row in rows.values():
        if row.kind == "mechanism":
            busy = math.fsum(bar.duration_s for bar in row.bars)
            axes.append(MechanismTiming(mechanism_id=row.id, busy_s=busy, idle_s=cycle - busy, utilisation=busy / cycle))
    moved = {axis.mechanism_id for axis in axes}
    axes.extend(MechanismTiming(mechanism_id=m.id, busy_s=0.0, idle_s=cycle, utilisation=0.0)
                for m in station.mechanisms if m.id not in moved)

    warnings = []
    if target is not None and cycle > target:
        warnings.append(TimingWarning(code="target_not_met", station_id=station.id, step_id=limiting.id,
                                      value=cycle, limit=target))
    return StationTiming(
        station_id=station.id,
        cycle_time_s=cycle,
        target_cycle_time_s=target,
        margin_s=target - cycle if target is not None else None,
        limiting_step_id=limiting.id,
        critical_path=[s.id for s in critical],
        mechanisms=axes,
        diagram=list(rows.values()),
        warnings=warnings,
    )


def _blocks(steps: list[Step]) -> tuple[list[list[Step]], list[int]]:
    """Steps (already sorted) grouped into blocks, and the groups whose members are not next to each other."""
    blocks: list[list[Step]] = []
    seen: set[int] = set()
    split: list[int] = []
    for step in steps:
        group = step.parallel_group
        if group is not None and blocks and blocks[-1][0].parallel_group == group:
            blocks[-1].append(step)
            continue
        if group is not None:
            if group in seen and group not in split:
                split.append(group)
            seen.add(group)
        blocks.append([step])
    return blocks, split


def _missing_values(mechanism: Mechanism) -> list[ReasonCode]:
    missing: list[ReasonCode] = []
    if mechanism.stroke is None:
        missing.append("stroke_missing")
    if mechanism.max_speed is None:
        missing.append("max_speed_missing")
    if mechanism.acceleration is None:
        missing.append("acceleration_missing")
    if mechanism.profile == "s_curve" and mechanism.jerk is None:
        missing.append("jerk_missing")
    return missing


def _stroke_time(mechanism: Mechanism) -> float:
    """One full rest-to-rest stroke with the mechanism's profile, plus its dwell when set."""
    assert mechanism.stroke is not None and mechanism.max_speed is not None and mechanism.acceleration is not None
    try:
        move: MoveProfile
        if mechanism.profile == "s_curve":
            assert mechanism.jerk is not None
            move = s_curve(mechanism.stroke, mechanism.max_speed, mechanism.acceleration, mechanism.jerk)
        else:
            move = trapezoidal(mechanism.stroke, mechanism.max_speed, mechanism.acceleration)
    except MotionError as exc:
        raise TimingError(f"mechanism '{mechanism.id}': {exc}") from exc
    dwell = mechanism.dwell_s
    if dwell is None:
        return move.duration_s
    if isinstance(dwell, bool) or not math.isfinite(dwell) or dwell < 0:
        raise TimingError(f"mechanism '{mechanism.id}' dwell_s must be finite and >= 0, got {dwell!r}")
    return move.duration_s + dwell


def _positive(where: str, value: float) -> float:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise TimingError(f"{where} must be finite and > 0, got {value!r}")
    return float(value)


def _unique(station_id: str, kind: str, ids: list[str]) -> None:
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise TimingError(f"station '{station_id}' has duplicate {kind} ids: {', '.join(duplicates)}")
