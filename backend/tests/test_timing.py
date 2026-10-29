"""Timing engine: a station's cycle from its steps and mechanisms (Phase 2, section C).

Expected values are worked out by hand in each test from the closed forms of Biagiotti &
Melchiorri (2008), sections 3.2 and 3.4 (see `app/engines/motion.py`), never taken from running
the engine. The Hypothesis tests check invariants over random valid stations.
"""

from __future__ import annotations

import copy
import math
from typing import Any, get_args

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.engines.timing import (
    ENGINE_VERSION,
    ReasonCode,
    StationTiming,
    TimingBar,
    TimingError,
    design_timing,
    station_timing,
)
from app.models import MachineDesign, Mechanism, Product, Station, Step

TOL = 1e-9


def _station(steps: list[Step], mechanisms: list[Mechanism] | None = None, target: float | None = None) -> Station:
    return Station(id="st", name="Station", function="f", steps=steps, mechanisms=mechanisms or [],
                   target_cycle_time_s=target)


def _fixed(sid: str, order: int, duration: float | None, group: int | None = None) -> Step:
    return Step(id=sid, order=order, kind="fixed_duration", duration_s=duration, parallel_group=group)


def _move(sid: str, order: int, mechanism_id: str | None, group: int | None = None) -> Step:
    return Step(id=sid, order=order, kind="motion", mechanism_id=mechanism_id, parallel_group=group)


def _axis(mid: str, stroke: float | None = 200.0, max_speed: float | None = 500.0,
          acceleration: float | None = 2000.0, **kw: Any) -> Mechanism:
    return Mechanism(id=mid, kind="linear", stroke=stroke, max_speed=max_speed, acceleration=acceleration, **kw)


def _bars(timing: StationTiming) -> dict[str, TimingBar]:
    return {bar.step_id: bar for row in timing.diagram for bar in row.bars}


# --- rules C.1 to C.7 ----------------------------------------------------------------------------


def test_fixed_steps_in_sequence_add_up() -> None:
    # Listed out of order on purpose: the engine sorts by (order, id).
    timing = station_timing(_station([_fixed("c", 3, 0.3), _fixed("a", 1, 0.5), _fixed("b", 2, 0.7)]))

    assert timing.computable
    assert timing.cycle_time_s == pytest.approx(1.5, abs=TOL)
    assert timing.critical_path == ["a", "b", "c"]
    bars = _bars(timing)
    assert [(bars[s].start_s, bars[s].end_s) for s in "abc"] == [
        pytest.approx((0.0, 0.5)), pytest.approx((0.5, 1.2)), pytest.approx((1.2, 1.5))]
    assert all(bar.source == "fixed" and bar.critical for bar in bars.values())


def test_parallel_group_takes_its_longest_member() -> None:
    steps = [_fixed("load", 1, 0.4), _fixed("seal", 2, 0.9, group=1), _fixed("print", 3, 0.6, group=1),
             _fixed("unload", 4, 0.2)]
    timing = station_timing(_station(steps))

    assert timing.cycle_time_s == pytest.approx(0.4 + 0.9 + 0.2, abs=TOL)  # 1.5, not 2.1 in sequence
    assert timing.critical_path == ["load", "seal", "unload"]
    bars = _bars(timing)
    # Both members start when the block starts and end on their own time; the next block waits for the longer.
    assert bars["seal"].start_s == bars["print"].start_s == pytest.approx(0.4)
    assert bars["print"].end_s == pytest.approx(1.0) and not bars["print"].critical
    assert bars["unload"].start_s == pytest.approx(1.3)


def test_motion_step_is_profile_time_plus_dwell() -> None:
    # Trapezoidal, speed reached (s = 200 >= v²/a = 125): T = s/v + v/a = 0.4 + 0.25 = 0.65 s,
    # plus the 0.1 s dwell at the end of the stroke = 0.75 s.
    lift = _axis("m-lift", dwell_s=0.1)
    # Double-S, v·j = 2e7 >= a² = 4e6 so the acceleration limit is reached: Tj = a/j = 0.05,
    # Ta = Tj + v/a = 0.3; Tv = s/v - Ta = 0.1 >= 0 so the speed is reached: T = 2·Ta + Tv = 0.7 s.
    push = _axis("m-push", profile="s_curve", jerk=40_000.0)
    station = _station([_move("lift", 1, "m-lift"), _move("push", 2, "m-push")], [lift, push])
    timing = station_timing(station)

    bars = _bars(timing)
    assert bars["lift"].duration_s == pytest.approx(0.75, abs=TOL)
    assert bars["lift"].source == "trapezoidal"
    assert bars["push"].duration_s == pytest.approx(0.7, abs=TOL)
    assert bars["push"].source == "s_curve"
    assert timing.cycle_time_s == pytest.approx(1.45, abs=TOL)
    assert station.cycle_time_s == pytest.approx(1.45, abs=TOL)  # the derived value (section D)

    # The same numbers in degrees on a rotary axis give the same time (units pass through).
    turn = Mechanism(id="m-turn", kind="rotary", stroke=200.0, max_speed=500.0, acceleration=2000.0, dwell_s=0.1)
    rotary = station_timing(_station([_move("turn", 1, "m-turn")], [turn]))
    assert rotary.cycle_time_s == pytest.approx(0.75, abs=TOL)


def test_limiting_step_is_the_longest_on_the_critical_path_with_tie_rule() -> None:
    # Equal durations: the lower order wins.
    by_order = station_timing(_station([_fixed("s2", 2, 0.5), _fixed("s1", 1, 0.5)]))
    assert by_order.limiting_step_id == "s1"

    # Equal durations and equal order: the lower id wins.
    by_id = station_timing(_station([_fixed("b", 1, 0.5), _fixed("a", 1, 0.5)]))
    assert by_id.limiting_step_id == "a"

    # The longest member of a parallel block is on the critical path; in a tie, the lower id.
    steps = [_fixed("feed", 1, 0.3), _fixed("y", 2, 0.8, group=4), _fixed("x", 2, 0.8, group=4),
             _fixed("cut", 3, 0.6)]
    timing = station_timing(_station(steps))
    assert timing.critical_path == ["feed", "x", "cut"]
    assert timing.limiting_step_id == "x"

    # A long step is limiting only through the critical path: here the 0.9 s branch.
    branch = station_timing(_station([_fixed("short", 1, 0.2, group=1), _fixed("long", 2, 0.9, group=1),
                                      _fixed("after", 3, 0.6)]))
    assert branch.critical_path == ["long", "after"]
    assert branch.limiting_step_id == "long"


def _axis_station() -> Station:
    # m-lift: trapezoidal, speed reached, 0.65 s per stroke (see the motion step test), down and up.
    # m-pick: s = 50 < v²/a = 125, triangular: T = 2·√(s/a) = 2·√0.025 s, in parallel with the 0.7 s seal.
    # m-spare: no step moves it.
    mechanisms = [_axis("m-lift"), _axis("m-pick", stroke=50.0), _axis("m-spare")]
    steps = [_move("down", 1, "m-lift"), _fixed("seal", 2, 0.7, group=1), _move("pick", 3, "m-pick", group=1),
             _move("up", 4, "m-lift")]
    return _station(steps, mechanisms)


def test_axis_busy_idle_and_utilisation() -> None:
    timing = station_timing(_axis_station())
    assert timing.cycle_time_s == pytest.approx(0.65 + 0.7 + 0.65, abs=TOL)

    axes = {m.mechanism_id: m for m in timing.mechanisms}
    assert list(axes) == ["m-lift", "m-pick"]  # a mechanism no step moves has no timing
    assert axes["m-lift"].busy_s == pytest.approx(1.3, abs=TOL)
    assert axes["m-lift"].idle_s == pytest.approx(0.7, abs=TOL)
    assert axes["m-lift"].utilisation == pytest.approx(0.65, abs=TOL)
    pick = 2 * math.sqrt(50.0 / 2000.0)
    assert axes["m-pick"].busy_s == pytest.approx(pick, abs=TOL)
    assert axes["m-pick"].idle_s == pytest.approx(2.0 - pick, abs=TOL)
    assert axes["m-pick"].utilisation == pytest.approx(pick / 2.0, abs=TOL)


def test_diagram_has_one_row_per_mechanism_and_fixed_step() -> None:
    timing = station_timing(_axis_station())

    # In order of first start; seal and pick start together, so the step order decides.
    assert [(row.kind, row.id) for row in timing.diagram] == [
        ("mechanism", "m-lift"), ("fixed", "seal"), ("mechanism", "m-pick")]
    assert [[bar.step_id for bar in row.bars] for row in timing.diagram] == [["down", "up"], ["seal"], ["pick"]]
    bars = _bars(timing)
    assert (bars["up"].start_s, bars["up"].end_s) == (pytest.approx(1.35), pytest.approx(2.0))
    assert bars["pick"].duration_s == pytest.approx(2 * math.sqrt(0.025), abs=TOL)
    assert {s: b.critical for s, b in bars.items()} == {"down": True, "seal": True, "pick": False, "up": True}
    assert {s: b.source for s, b in bars.items()} == {
        "down": "trapezoidal", "seal": "fixed", "pick": "trapezoidal", "up": "trapezoidal"}


# --- rule C.8: not computable is a result, with reasons --------------------------------------------


def _reasons(timing: StationTiming) -> list[tuple[str, str | None, str | None, int | None]]:
    return [(r.code, r.step_id, r.mechanism_id, r.parallel_group) for r in timing.not_computable]


NOT_COMPUTABLE_CASES: list[tuple[str, Station, list[tuple[str, str | None, str | None, int | None]]]] = [
    ("no_steps", _station([]), [("no_steps", None, None, None)]),
    ("duration_missing", _station([_fixed("seal", 1, None)]), [("duration_missing", "seal", None, None)]),
    ("mechanism_missing", _station([_move("lift", 1, "m-gone"), _move("push", 2, None)]),
     [("mechanism_missing", "lift", "m-gone", None), ("mechanism_missing", "push", None, None)]),
    ("stroke_missing", _station([_move("lift", 1, "m")], [_axis("m", stroke=None)]),
     [("stroke_missing", None, "m", None)]),
    ("max_speed_missing", _station([_move("lift", 1, "m")], [_axis("m", max_speed=None)]),
     [("max_speed_missing", None, "m", None)]),
    ("acceleration_missing", _station([_move("lift", 1, "m")], [_axis("m", acceleration=None)]),
     [("acceleration_missing", None, "m", None)]),
    ("jerk_missing", _station([_move("lift", 1, "m")], [_axis("m", profile="s_curve")]),
     [("jerk_missing", None, "m", None)]),
    ("parallel_group_split", _station([_fixed("a", 1, 0.1, 7), _fixed("b", 2, 0.1), _fixed("c", 3, 0.1, 7)]),
     [("parallel_group_split", None, None, 7)]),
]


def test_missing_values_make_the_station_not_computable_with_reasons() -> None:
    assert {code for code, _, _ in NOT_COMPUTABLE_CASES} == set(get_args(ReasonCode)), "one case per reason code"
    for code, station, expected in NOT_COMPUTABLE_CASES:
        timing = station_timing(station)
        assert not timing.computable, code
        assert _reasons(timing) == expected, code
        assert timing.cycle_time_s is None and station.cycle_time_s is None
        assert timing.limiting_step_id is None and timing.margin_s is None
        assert timing.critical_path == [] and timing.diagram == [] and timing.mechanisms == []

    # Every reason is listed, not only the first; a mechanism is named once however many steps use it.
    steps = [_move("down", 1, "m"), _fixed("seal", 2, None), _move("up", 3, "m")]
    station = _station(steps, [_axis("m", stroke=None, acceleration=None)], target=1.0)
    timing = station_timing(station)
    assert _reasons(timing) == [("stroke_missing", None, "m", None), ("acceleration_missing", None, "m", None),
                                ("duration_missing", "seal", None, None)]
    assert timing.warnings == []  # no target check without a cycle time
    assert timing.target_cycle_time_s == 1.0


def test_split_parallel_group_is_not_computable() -> None:
    split = station_timing(_station([_fixed("a", 1, 0.4, 1), _fixed("b", 2, 0.2), _fixed("c", 3, 0.4, 1)]))
    assert _reasons(split) == [("parallel_group_split", None, None, 1)]

    # Members next to each other in the sorted order are one block, wherever they sit in the list.
    joined = station_timing(_station([_fixed("c", 3, 0.2), _fixed("a", 1, 0.4, 1), _fixed("b", 2, 0.3, 1)]))
    assert joined.cycle_time_s == pytest.approx(0.6, abs=TOL)


def test_target_not_met_names_the_limiting_step() -> None:
    timing = station_timing(_station([_fixed("feed", 1, 0.5), _fixed("seal", 2, 0.9)], target=1.2))
    assert timing.cycle_time_s == pytest.approx(1.4, abs=TOL)
    assert timing.margin_s == pytest.approx(-0.2, abs=TOL)
    (warning,) = timing.warnings
    assert warning.code == "target_not_met"
    assert (warning.station_id, warning.step_id) == ("st", "seal")
    assert warning.value == pytest.approx(1.4, abs=TOL) and warning.limit == 1.2


def test_target_met_gives_no_warning() -> None:
    steps = [_fixed("feed", 1, 0.5), _fixed("seal", 2, 1.0)]
    exact = station_timing(_station(steps, target=1.5))
    assert exact.warnings == [] and exact.margin_s == pytest.approx(0.0, abs=TOL)
    slack = station_timing(_station(steps, target=2.0))
    assert slack.warnings == [] and slack.margin_s == pytest.approx(0.5, abs=TOL)
    no_target = station_timing(_station(steps))
    assert no_target.warnings == [] and no_target.margin_s is None and no_target.target_cycle_time_s is None


def test_values_the_validator_forbids_raise() -> None:
    """C.8: values the patch validator rejects are not warnings; if they reach the engine, it raises."""
    bad = [
        _station([_fixed("s", 1, 0.0)]),
        _station([_fixed("s", 1, -1.0)]),
        _station([_fixed("s", 1, math.nan)]),
        _station([_fixed("s", 1, math.inf)]),
        _station([Step(id="s", order=1, kind="motion", mechanism_id="m", duration_s=0.5)], [_axis("m")]),
        _station([_move("s", 1, "m")], [_axis("m", stroke=0.0)]),
        _station([_move("s", 1, "m")], [_axis("m", max_speed=-1.0)]),
        _station([_move("s", 1, "m")], [_axis("m", profile="s_curve", jerk=0.0)]),
        _station([_move("s", 1, "m")], [_axis("m", dwell_s=-0.1)]),
        _station([_move("s", 1, "m")], [_axis("m"), _axis("m")]),
        _station([_fixed("s", 1, 0.5), _fixed("s", 2, 0.5)]),
        _station([_fixed("s", 1, 0.5)], target=0.0),
    ]
    for station in bad:
        with pytest.raises(TimingError):
            station_timing(station)


def test_design_timing_covers_every_station() -> None:
    a = Station(id="a", name="A", function="f", steps=[_fixed("s", 1, 0.5)])
    frame = Station(id="frame", name="Frame", kind="frame", function="f")
    design = MachineDesign(name="t", machine_type="t", summary="t", product=Product(), stations=[a, frame])
    result = design_timing(design)
    assert result.engine_version == ENGINE_VERSION
    assert result.bounds_version is None  # filled in with the bounds table (section E)
    assert [(s.station_id, s.cycle_time_s) for s in result.stations] == [("a", 0.5), ("frame", None)]
    assert _reasons(result.stations[1]) == [("no_steps", None, None, None)]


# --- invariants over random valid stations --------------------------------------------------------

_POSITIVE = {"allow_nan": False, "allow_infinity": False}


@st.composite
def _stations(draw: st.DrawFn) -> Station:
    mechanisms = []
    for i in range(draw(st.integers(0, 3))):
        profile = draw(st.sampled_from(["trapezoidal", "s_curve"]))
        mechanisms.append(Mechanism(
            id=f"m{i}",
            kind=draw(st.sampled_from(["linear", "rotary"])),
            stroke=draw(st.floats(0.1, 1000.0, **_POSITIVE)),
            max_speed=draw(st.floats(1.0, 5000.0, **_POSITIVE)),
            acceleration=draw(st.floats(1.0, 1e5, **_POSITIVE)),
            profile=profile,
            jerk=draw(st.floats(1.0, 1e7, **_POSITIVE)) if profile == "s_curve" else None,
            dwell_s=draw(st.none() | st.floats(0.0, 1.0, **_POSITIVE)),
        ))
    steps: list[Step] = []
    for block in range(draw(st.integers(1, 5))):
        size = draw(st.integers(1, 3))
        group = block + 1 if size > 1 or draw(st.booleans()) else None  # a group of one is allowed
        for _ in range(size):
            order = len(steps) + 1
            if mechanisms and draw(st.booleans()):
                steps.append(_move(f"s{order}", order, draw(st.sampled_from(mechanisms)).id, group))
            else:
                steps.append(_fixed(f"s{order}", order, draw(st.floats(0.001, 10.0, **_POSITIVE)), group))
    return _station(list(draw(st.permutations(steps))), mechanisms)


def _alone(station: Station, step: Step) -> float:
    """A step's duration measured on its own: a station with that one step."""
    single = station.model_copy(update={"steps": [step.model_copy(update={"parallel_group": None})]})
    cycle = station_timing(single).cycle_time_s
    assert cycle is not None
    return cycle


def _cycle(station: Station) -> float:
    cycle = station_timing(station).cycle_time_s
    assert cycle is not None, "a random valid station is computable"
    return cycle


def _close_or_below(a: float, b: float) -> bool:
    return a <= b + 1e-9 * max(1.0, abs(b))


_HYPOTHESIS = settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@_HYPOTHESIS
@given(_stations())
def test_cycle_time_is_at_least_the_longest_step(station: Station) -> None:
    assert _close_or_below(max(_alone(station, s) for s in station.steps), _cycle(station))


@_HYPOTHESIS
@given(_stations())
def test_parallel_steps_never_shorten_below_the_longest_branch(station: Station) -> None:
    blocks: dict[object, list[float]] = {}
    for step in station.steps:
        blocks.setdefault(step.parallel_group if step.parallel_group is not None else step.id, []).append(
            _alone(station, step))
    longest_branches = math.fsum(max(durations) for durations in blocks.values())
    in_sequence = math.fsum(d for durations in blocks.values() for d in durations)
    cycle = _cycle(station)
    assert _close_or_below(longest_branches, cycle)
    assert _close_or_below(cycle, in_sequence)


@_HYPOTHESIS
@given(_stations(), st.data())
def test_removing_a_step_never_increases_cycle_time(station: Station, data: st.DataObject) -> None:
    if len(station.steps) < 2:
        return
    index = data.draw(st.integers(0, len(station.steps) - 1))
    fewer = station.model_copy(update={"steps": station.steps[:index] + station.steps[index + 1:]})
    assert _close_or_below(_cycle(fewer), _cycle(station))


def _durations_of(station: Station, mechanism_id: str) -> list[float]:
    timing = station_timing(station)
    return [bar.duration_s for row in timing.diagram if row.id == mechanism_id and row.kind == "mechanism"
            for bar in row.bars]


def _changed(station: Station, mechanism_id: str, **update: float) -> Station:
    mechanisms = [m.model_copy(update=update) if m.id == mechanism_id else m for m in station.mechanisms]
    return station.model_copy(update={"mechanisms": mechanisms})


def _moved_mechanism(station: Station, data: st.DataObject) -> str | None:
    moved = sorted({s.mechanism_id for s in station.steps if s.kind == "motion" and s.mechanism_id})
    return data.draw(st.sampled_from(moved)) if moved else None


@_HYPOTHESIS
@given(_stations(), st.data(), st.floats(1.0, 10.0, **_POSITIVE))
def test_longer_stroke_never_shortens_a_motion_step(station: Station, data: st.DataObject, factor: float) -> None:
    mid = _moved_mechanism(station, data)
    if mid is None:
        return
    mechanism = next(m for m in station.mechanisms if m.id == mid)
    assert mechanism.stroke is not None
    before = _durations_of(station, mid)
    after = _durations_of(_changed(station, mid, stroke=mechanism.stroke * factor), mid)
    assert all(_close_or_below(b, a) for b, a in zip(before, after, strict=True))


@_HYPOTHESIS
@given(_stations(), st.data(), st.sampled_from(["max_speed", "acceleration"]), st.floats(1.0, 10.0, **_POSITIVE))
def test_more_speed_or_acceleration_never_lengthens_a_motion_step(
    station: Station, data: st.DataObject, field: str, factor: float
) -> None:
    mid = _moved_mechanism(station, data)
    if mid is None:
        return
    mechanism = next(m for m in station.mechanisms if m.id == mid)
    before = _durations_of(station, mid)
    after = _durations_of(_changed(station, mid, **{field: getattr(mechanism, field) * factor}), mid)
    assert all(_close_or_below(a, b) for b, a in zip(before, after, strict=True))


@_HYPOTHESIS
@given(_stations())
def test_timing_is_deterministic(station: Station) -> None:
    first = station_timing(station)
    assert station_timing(station) == first
    assert station_timing(copy.deepcopy(station)).model_dump_json() == first.model_dump_json()
