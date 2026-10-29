"""Model v1 -> v2 (Phase 1 spec, section B). Fixtures in tests/fixtures/v1 were written by the v1 code."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import get_args

import pytest

from app.llm.mock import _refine, demo_design
from app.migrations.design_v1 import CATEGORY_ROLES, ComponentCategoryV1, MachineDesignV1, migrate_design, to_v1
from app.models import MachineDesign, Step
from app.services.patch import PatchOp, apply_patches
from app.storage import DESIGN_SCHEMA_VERSION, Storage
from tests.fixtures.v1.make_fixtures import PROBLEMS
from tests.test_migration import _write_v03_database

FIXTURES = Path(__file__).parent / "fixtures" / "v1"
DESIGNS = sorted((FIXTURES / "designs").glob("*.json"))


def _raw(name: str) -> dict:
    return json.loads((FIXTURES / "designs" / f"{name}.json").read_text())


def test_fixtures_exist() -> None:
    assert [p.stem for p in DESIGNS] == [
        "assembly", "blister-u-shape", "blister-vision", "blister", "cartoner", "filling",
    ]


@pytest.mark.parametrize("path", DESIGNS, ids=lambda p: p.stem)
def test_v1_fixture_revisions_migrate_to_v2(path: Path, tmp_path: Path) -> None:
    design = migrate_design(json.loads(path.read_text()), from_version=1)
    assert isinstance(design, MachineDesign) and design.schema_version == 3
    MachineDesign.model_validate_json(design.model_dump_json())  # valid as stored v2

    db = tmp_path / "v03.db"
    expected = _write_v03_database(db)
    project = Storage(db).get_project("abc123")
    assert project is not None and project.design == expected and project.design.schema_version == 3


@pytest.mark.parametrize("path", DESIGNS, ids=lambda p: p.stem)
def test_v1_to_v2_round_trip_keeps_all_v1_fields(path: Path) -> None:
    raw = json.loads(path.read_text())
    v2 = MachineDesign.model_validate_json(migrate_design(raw, from_version=1).model_dump_json())
    assert to_v1(v2).model_dump() == MachineDesignV1.model_validate(raw).model_dump()


def test_sequence_becomes_linear_transport_chain() -> None:
    raw = _raw("blister-vision")
    design = migrate_design(raw, from_version=1)
    flow = ["st-forming", "st-feeding", "st-sealing", "st-cutting", "st-vision", "st-outfeed"]
    assert [(t.from_station, t.to_station) for t in design.transports] == list(zip(flow, flow[1:]))
    assert {t.kind for t in design.transports} == {"belt"}
    for t in design.transports:  # nothing guessed: lengths, speeds and buffers stay unknown
        assert t.id == f"tr-{t.from_station}-{t.to_station}"
        assert (t.length_mm, t.speed_mm_s, t.index_time_s, t.buffer_capacity, t.products_per_move,
                t.reject_to, t.reject_rate) == (None,) * 7
    infrastructure = {s["id"] for s in raw["stations"] if s["sequence"] == 0}
    assert infrastructure == {"st-frame", "st-control", "st-safety", "st-pneumatics"}
    in_graph = {t.from_station for t in design.transports} | {t.to_station for t in design.transports}
    assert not infrastructure & in_graph
    assert {s.id: s.sequence for s in design.stations} == {s["id"]: s["sequence"] for s in raw["stations"]}


def test_cycle_time_becomes_fixed_step() -> None:
    design = migrate_design(_raw("blister"), from_version=1)
    forming = next(s for s in design.stations if s.id == "st-forming")
    assert forming.steps == [Step(id="st-forming-cycle", order=1, kind="fixed_duration", duration_s=1.2)]
    assert forming.target_cycle_time_s == 1.2 and forming.cycle_time_s == 1.2
    outfeed = next(s for s in design.stations if s.id == "st-outfeed")
    assert outfeed.steps == [] and outfeed.target_cycle_time_s is None and outfeed.cycle_time_s is None


def test_product_and_throughput_text_move_to_the_display_fields() -> None:
    raw = _raw("blister")
    design = migrate_design(raw, from_version=1)
    assert design.product.description == raw["product"] == "blisters"
    assert design.target_rate_text == raw["throughput"] == "300 tablets/min"
    p = design.product  # nothing guessed
    assert (p.name, p.length_mm, p.width_mm, p.height_mm, p.mass_g, p.lanes, p.pitch_mm) == (None,) * 7
    assert p.orientation == "unspecified"


def test_category_maps_to_role() -> None:
    design = migrate_design(_raw("blister"), from_version=1)
    roles = {c.id: c.role for s in design.stations for c in s.components}
    assert roles["forming-servo"] == "actuator"
    assert roles["sealing-tc"] == "sensor"
    assert roles["plc-cpu"] == "controller"
    assert roles["servo-drives"] == "drive"
    assert roles["punch-tool"] == "tooling"
    assert roles["frame-base"] == "structure"
    assert roles["forming-die"] is None  # custom_part: no role can be read from the category
    assert all(c.signals is None and c.motion is None for s in design.stations for c in s.components)
    assert set(CATEGORY_ROLES) == set(get_args(ComponentCategoryV1))  # every v1 category is decided


def test_irregular_v1_sequences_still_load() -> None:
    """Gaps, duplicate sequences and duplicate ids (all seen in AI output) never make a design unreadable."""
    def st(sid: str, seq: int, kind: str = "process") -> dict:
        return {"id": sid, "name": sid, "kind": kind, "sequence": seq, "function": "f"}
    raw = {"name": "t", "machine_type": "t", "summary": "t", "product": "p", "stations": [
        st("loose", 0), st("a", 10), st("b", 20), st("b", 25), st("c", 20), st("cab", 0, "control"),
    ]}
    design = migrate_design(raw, from_version=1)
    assert [(t.from_station, t.to_station) for t in design.transports] == [("a", "b"), ("b", "c")]
    assert [(s.id, s.sequence) for s in design.stations] == [
        ("loose", 4), ("a", 1), ("b", 2), ("b", 2), ("c", 3), ("cab", 0),
    ]


def test_unknown_schema_version_is_rejected() -> None:
    with pytest.raises(ValueError, match="schema version 7"):
        migrate_design(_raw("blister"), from_version=7)


def test_old_database_opens_after_phase_1(tmp_path: Path) -> None:
    db = tmp_path / "phase0.db"
    shutil.copy(FIXTURES / "phase0.db", db)
    blister_id = json.loads((FIXTURES / "phase0.json").read_text())["blister_project"]
    before = sqlite3.connect(db).execute("SELECT rowid, design FROM revisions ORDER BY rowid").fetchall()

    storage = Storage(db)
    assert len(storage.list_projects()) == 2
    revisions = storage.list_revisions(blister_id)
    assert [r.number for r in revisions] == [1, 2, 3]
    assert [r.schema_version for r in revisions] == [1, 1, 1]  # kept until a new revision is saved
    for revision, name in zip(revisions, ("blister", "blister-vision", "blister-u-shape")):
        assert revision.design == migrate_design(_raw(name), from_version=1)
    project = storage.get_project(blister_id)
    assert project is not None and project.design.layout_style == "u_shape"

    number = storage.add_revision(blister_id, "restore 1", "ok", revisions[0].design)
    new = storage.get_revision(blister_id, number)
    assert new is not None and new.schema_version == DESIGN_SCHEMA_VERSION == 3
    assert new.design == revisions[0].design
    conn = sqlite3.connect(db)
    after = conn.execute("SELECT rowid, design FROM revisions ORDER BY rowid").fetchall()
    assert after[: len(before)] == before  # old rows are migrated on read, never rewritten


# Two v1 fields of the demo machines differ from the v1 mock on purpose (Phase 1 step 4): the
# summary no longer quotes the problem text, and one open question asks for the axis speeds.
DEMO_TEXT_FIELDS = ("summary", "open_questions")


def _without_demo_text(data: dict) -> dict:
    return {k: v for k, v in data.items() if k not in DEMO_TEXT_FIELDS}


@pytest.mark.parametrize("name", sorted(PROBLEMS))
def test_mock_output_matches_its_v1_fixture(name: str) -> None:
    """The mock builds the same machines as the v1 mock did, picked by scenario id instead of text."""
    exported = to_v1(demo_design(name)).model_dump()
    expected = MachineDesignV1.model_validate(_raw(name)).model_dump()
    assert PROBLEMS[name] in expected["summary"] and PROBLEMS[name] not in exported["summary"]
    assert expected["open_questions"] == [] and len(exported["open_questions"]) == 1
    assert _without_demo_text(exported) == _without_demo_text(expected)


def test_mock_refinements_match_their_v1_fixtures() -> None:
    """The first demo edit is the v1 'add vision inspection' in a U-shaped layout; the next one
    switches back to inline, which is the v1 fixture again. The v1 'make it u-shaped' fixture is
    the demo machine with only its layout patched."""
    initial = demo_design("blister")
    u_shaped = apply_patches(initial, [PatchOp(op="set_param", name="layout_style", text="u_shape")]).design
    assert u_shaped is not None
    assert to_v1(u_shaped).model_dump() == {
        **MachineDesignV1.model_validate(_raw("blister-u-shape")).model_dump(),
        **{field: getattr(initial, field) for field in DEMO_TEXT_FIELDS},
    }

    expected = _without_demo_text(MachineDesignV1.model_validate(_raw("blister-vision")).model_dump())
    design = initial
    for layout in ("u_shape", "inline"):
        refined = apply_patches(design, _refine(design).patches).design
        assert refined is not None
        assert (refined.summary, refined.open_questions) == (initial.summary, initial.open_questions)
        design = refined
        exported = to_v1(design)
        # A patch appends a new station; the v1 mock sorted the list by sequence. In v2 the list
        # order carries no meaning (sequence is derived), so put it in the v1 mock's order.
        exported.stations.sort(key=lambda s: (s.sequence == 0, s.sequence))
        assert _without_demo_text(exported.model_dump()) == {**expected, "layout_style": layout}
