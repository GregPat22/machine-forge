"""Plausibility bounds: the catalog table and the check against it (Phase 2, section E).

The real table is `backend/app/data/catalog_bounds.yaml`; tests that need a value outside or inside a
bound on purpose build a synthetic table, labelled as a fixture, never as data.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from app.engines.bounds import BoundsRow, BoundsTable, check_bounds
from app.models import ComponentCategory, Component, MachineDesign, Mechanism, Station, Transport, TransportKind
from app.services.bounds import BOUNDS_PATH, load_bounds_table

UNITS = {
    ("stroke", "linear"): "mm", ("stroke", "rotary"): "deg",
    ("max_speed", "linear"): "mm/s", ("max_speed", "rotary"): "deg/s",
    ("acceleration", "linear"): "mm/s2", ("acceleration", "rotary"): "deg/s2",
    ("jerk", "linear"): "mm/s3", ("jerk", "rotary"): "deg/s3",
    ("index_time_s", None): "s", ("speed_mm_s", None): "mm/s",
}


def _row(**kw: Any) -> dict[str, Any]:
    """A synthetic row (test fixture, not catalog data)."""
    row: dict[str, Any] = {
        "id": "fixture-servo-linear-acceleration",
        "applies_to": {"component_category": "servo_motor", "transport_kind": None, "mechanism_kind": "linear"},
        "field": "acceleration",
        "unit": "mm/s2",
        "min": 100.0,
        "max": 1000.0,
        "as_printed": "fixture",
        "source_title": "Fixture table for tests, not catalog data",
        "source_url": "https://example.invalid/fixture",
        "source_page": None,
        "accessed": None,
    }
    row.update(kw)
    return row


def _table(*rows: dict[str, Any]) -> BoundsTable:
    return BoundsTable(version="fixture", rows=list(rows))


def _design(mechanisms: list[Mechanism], components: list[Component],
            transports: list[Transport] | None = None) -> MachineDesign:
    stations = [
        Station(id="st-a", name="Station A", function="f", mechanisms=mechanisms, components=components),
        Station(id="st-b", name="Station B", function="f"),
    ]
    return MachineDesign(name="m", machine_type="t", summary="s", stations=stations, transports=transports or [])


def _servo_axis_design(acceleration: float, name: str = "Servo motor X") -> MachineDesign:
    axis = Mechanism(id="m-x", kind="linear", stroke=300, max_speed=1000, acceleration=acceleration)
    servo = Component(id="servo-x", name=name, category="servo_motor", quantity=1, motion="m-x")
    return _design([axis], [servo])


# --- the table ----------------------------------------------------------------------------------


def test_bounds_file_validates() -> None:
    table = load_bounds_table()
    assert table.version == hashlib.sha256(BOUNDS_PATH.read_bytes()).hexdigest()
    assert table.rows, "the bounds table is empty"
    ids = [row.id for row in table.rows]
    assert len(ids) == len(set(ids)), "row ids must be unique"
    for row in table.rows:
        target = row.applies_to
        assert (target.component_category is None) != (target.transport_kind is None), row.id
        if target.component_category is not None:
            assert target.component_category in get_args(ComponentCategory), row.id
            assert target.mechanism_kind in ("linear", "rotary"), row.id
        else:
            assert target.transport_kind in get_args(TransportKind), row.id
            assert target.mechanism_kind is None, row.id
        assert row.unit == UNITS[(row.field, target.mechanism_kind)], row.id
        if row.min is not None and row.max is not None:
            assert row.min <= row.max, row.id


@pytest.mark.parametrize(
    "change",
    [
        {"applies_to": {"component_category": "spaceship", "transport_kind": None, "mechanism_kind": "linear"}},
        {"applies_to": {"component_category": "servo_motor", "transport_kind": "belt", "mechanism_kind": "linear"}},
        {"applies_to": {"component_category": None, "transport_kind": None, "mechanism_kind": "linear"}},
        {"applies_to": {"component_category": "servo_motor", "transport_kind": None, "mechanism_kind": None}},
        {"applies_to": {"component_category": None, "transport_kind": "indexing", "mechanism_kind": "linear"},
         "field": "index_time_s", "unit": "s"},
        {"applies_to": {"component_category": None, "transport_kind": "indexing", "mechanism_kind": None}},
        {"field": "cycle_time_s"},
        {"unit": "m/s2"},
        {"unit": "deg/s2"},
        {"min": 2000.0, "max": 1000.0},
        {"max": math.inf},
        {"id": "Not A Slug"},
        {"colour": "red"},
    ],
    ids=["unknown-category", "category-and-transport", "neither", "category-without-kind",
         "transport-with-kind", "mechanism-field-on-transport", "unknown-field", "unit-not-the-model-unit",
         "unit-of-the-other-kind", "min-above-max", "infinite-bound", "id-not-a-slug", "unknown-key"],
)
def test_bounds_table_rejects_invalid_rows(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _table(_row(**change))


def test_bounds_table_rejects_duplicate_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        _table(_row(), _row(field="max_speed", unit="mm/s"))


def test_every_active_row_has_a_source() -> None:
    """No number without its source: a row with a bound has a title, a URL, the printed value and a date."""
    for row in load_bounds_table().rows:
        if row.min is None and row.max is None:
            assert not row.active, row.id
            continue
        assert row.source_title, row.id
        assert row.source_url and row.source_url.startswith("https://"), row.id
        assert row.as_printed, row.id
        assert row.accessed is not None, row.id
        assert row.active, row.id


# --- the check ----------------------------------------------------------------------------------


def test_rows_without_a_source_give_no_warning() -> None:
    # Synthetic: a row with bounds but no source, and a row with a source but no bounds.
    no_source = _row(id="no-source", source_url=None, source_title=None)
    no_bound = _row(id="no-bound", min=None, max=None)
    design = _servo_axis_design(acceleration=1e9)
    assert check_bounds(design, _table(no_source, no_bound)).warnings == []
    # Real table: no row still TODO(source) is named by a warning, whatever the value.
    real = load_bounds_table()
    for row in real.rows:
        target = row.applies_to
        if row.active or target.component_category is None:
            continue
        axis = Mechanism(id="m", kind=target.mechanism_kind, **{row.field: 1e12})
        driver = Component(id="c", name="Driver", category=target.component_category, quantity=1, motion="m")
        assert row.id not in {w.row_id for w in check_bounds(_design([axis], [driver]), real).warnings}


def test_out_of_bounds_value_warns_and_is_not_corrected() -> None:
    table = _table(_row())  # fixture: acceleration 100 to 1000 mm/s2
    for value, bound, limit in ((50.0, "min", 100.0), (5000.0, "max", 1000.0)):
        design = _servo_axis_design(acceleration=value)
        before = design.model_dump()
        result = check_bounds(design, table)
        assert design.model_dump() == before, "the check must never change the design"
        assert len(result.warnings) == 1
        warning = result.warnings[0]
        assert warning.code == "out_of_bounds"
        assert (warning.station_id, warning.mechanism_id, warning.transport_id) == ("st-a", "m-x", None)
        assert (warning.field, warning.bound, warning.value, warning.limit) == ("acceleration", bound, value, limit)
        assert warning.row_id == "fixture-servo-linear-acceleration"
        assert warning.source_title == "Fixture table for tests, not catalog data"
        assert warning.source_url == "https://example.invalid/fixture"
    # On the bound and inside it: no warning.
    for value in (100.0, 500.0, 1000.0):
        assert check_bounds(_servo_axis_design(acceleration=value), table).warnings == []


def test_servo_acceleration_of_500_m_s2_warns_with_the_catalog_row() -> None:
    table = load_bounds_table()
    row = next(r for r in table.rows if r.id == "servo-linear-axis-acceleration")
    assert row.active, "the servo linear acceleration row needs its source (section E, row 2)"
    result = check_bounds(_servo_axis_design(acceleration=500_000.0), table)  # 500 m/s2
    warnings = [w for w in result.warnings if w.field == "acceleration"]
    assert len(warnings) == 1
    warning = warnings[0]
    assert (warning.code, warning.bound, warning.value, warning.limit) == ("out_of_bounds", "max", 500_000.0, row.max)
    assert warning.row_id == "servo-linear-axis-acceleration"
    assert warning.source_url == row.source_url and warning.source_title == row.source_title


def test_bounds_ignore_component_names() -> None:
    """Rule 1: only the component's category and the mechanism's kind decide, never a name."""
    table = load_bounds_table()
    named = check_bounds(_servo_axis_design(500_000.0, name="Servo motor X"), table)
    renamed = check_bounds(_servo_axis_design(500_000.0, name="Pneumatic cylinder, rotary table"), table)
    assert named.warnings and named == renamed


def test_rows_match_on_category_and_mechanism_kind() -> None:
    table = _table(_row())  # fixture: servo_motor, linear
    rotary = Mechanism(id="m-r", kind="rotary", stroke=90, max_speed=100, acceleration=1e9)
    servo = Component(id="servo-r", name="Servo", category="servo_motor", quantity=1, motion="m-r")
    assert check_bounds(_design([rotary], [servo]), table).warnings == []
    linear = Mechanism(id="m-x", kind="linear", stroke=300, max_speed=1000, acceleration=1e9)
    motor = Component(id="motor-x", name="Servo", category="motor", quantity=1, motion="m-x")
    assert check_bounds(_design([linear], [motor]), table).warnings == []
    # A component of the right category in another station does not drive this mechanism.
    design = _servo_axis_design(acceleration=1e9)
    design.stations[0].components[0].motion = None
    design.stations[1].components.append(
        Component(id="servo-b", name="Servo", category="servo_motor", quantity=1, motion="m-x"))
    assert check_bounds(design, table).warnings == []


def test_mechanism_no_component_drives_is_not_checked_and_listed() -> None:
    axis = Mechanism(id="m-x", kind="linear", stroke=300, max_speed=1000, acceleration=1e9)
    sensor = Component(id="sensor", name="Sensor", category="sensor", quantity=1)
    result = check_bounds(_design([axis], [sensor]), _table(_row()))
    assert result.warnings == []
    assert [(u.station_id, u.mechanism_id) for u in result.unchecked] == [("st-a", "m-x")]
    assert check_bounds(_servo_axis_design(500.0), _table(_row())).unchecked == []


def test_missing_value_is_not_checked() -> None:
    axis = Mechanism(id="m-x", kind="linear", stroke=300)
    servo = Component(id="servo-x", name="Servo", category="servo_motor", quantity=1, motion="m-x")
    assert check_bounds(_design([axis], [servo]), _table(_row())).warnings == []


def test_transport_index_time_is_checked_against_its_kind() -> None:
    table = load_bounds_table()
    row = next(r for r in table.rows if r.id == "indexing-transport-index-time")
    assert row.active and row.min is not None and row.max is not None
    slow = Transport(id="tr-ab", from_station="st-a", to_station="st-b", kind="indexing", index_time_s=row.max * 2)
    result = check_bounds(_design([], [], [slow]), table)
    warnings = [w for w in result.warnings if w.transport_id == "tr-ab"]
    assert len(warnings) == 1
    warning = warnings[0]
    assert (warning.station_id, warning.mechanism_id) == (None, None)
    assert (warning.field, warning.bound, warning.limit, warning.row_id) == (
        "index_time_s", "max", row.max, "indexing-transport-index-time")
    fine = Transport(id="tr-ab", from_station="st-a", to_station="st-b", kind="indexing",
                     index_time_s=(row.min + row.max) / 2)
    assert check_bounds(_design([], [], [fine]), table).warnings == []
    belt = Transport(id="tr-ab", from_station="st-a", to_station="st-b", kind="belt", index_time_s=row.max * 2)
    assert check_bounds(_design([], [], [belt]), table).warnings == []


def test_bounds_check_is_deterministic() -> None:
    table = load_bounds_table()
    design = _servo_axis_design(500_000.0)
    assert check_bounds(design, table).model_dump_json() == check_bounds(design, table).model_dump_json()


def test_bounds_row_active_needs_source_and_a_bound() -> None:
    assert BoundsRow.model_validate(_row()).active
    assert BoundsRow.model_validate(_row(min=None)).active
    assert not BoundsRow.model_validate(_row(min=None, max=None)).active
    assert not BoundsRow.model_validate(_row(source_url=None)).active
    assert not BoundsRow.model_validate(_row(source_title=None)).active
