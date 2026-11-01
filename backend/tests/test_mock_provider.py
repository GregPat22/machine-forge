"""The offline demo engine (Phase 1 spec, section F): an explicit scenario, never the user's text."""

from __future__ import annotations

import math

import pytest

from app.llm import LLMNotConfigured
from app.engines.timing import station_timing
from app.llm.mock import BLISTER_TIMING_ASSUMPTIONS, SCENARIOS, MockProvider, demo_design
from app.llm.prompts import SYSTEM_PROMPT, first_turn, refine_turn
from app.models import MachineDesign
from app.services.patch import PatchUpdate, apply_patches, empty_design


def _first(provider: MockProvider, problem: str) -> PatchUpdate:
    turns = [{"role": "user", "content": first_turn(problem)}]
    return provider.structured(system=SYSTEM_PROMPT, turns=turns, output=PatchUpdate)  # type: ignore[arg-type]


def _refine(provider: MockProvider, design: MachineDesign, request: str) -> PatchUpdate:
    turns = [{"role": "user", "content": refine_turn(design.model_dump_json(indent=1), request)}]
    return provider.structured(system=SYSTEM_PROMPT, turns=turns, output=PatchUpdate)  # type: ignore[arg-type]


def _applied(design: MachineDesign, update: PatchUpdate) -> MachineDesign:
    result = apply_patches(design, update.patches)
    assert result.errors == []
    assert result.design is not None
    return result.design


def test_mock_picks_the_machine_from_the_scenario_id_default_blister(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MF_MOCK_SCENARIO", raising=False)
    assert MockProvider().scenario == "blister"
    blister = _applied(empty_design(), _first(MockProvider(), "Fill 60 bottles per minute and cap them."))
    assert blister == demo_design("blister")
    assert blister.machine_type == "Thermoforming blister packaging machine"

    monkeypatch.setenv("MF_MOCK_SCENARIO", "cartoner")
    assert MockProvider().scenario == "cartoner"
    cartoner = _applied(empty_design(), _first(MockProvider(), "We need to pack 300 tablets into blisters."))
    assert cartoner == demo_design("cartoner")
    assert MockProvider(scenario="filling").scenario == "filling"  # an explicit id wins over the variable


def test_mock_ignores_problem_and_request_text() -> None:
    provider = MockProvider(scenario="blister")
    a = _first(provider, "We need to pack 300 tablets per minute into PVC/Alu blisters of 10.")
    b = _first(provider, "Assemble two plastic housing halves, 20 pieces per minute, cartons, bottles.")
    assert a == b
    design = _applied(empty_design(), a)
    assert _refine(provider, design, "Add vision inspection") == _refine(provider, design, "Make it U-shaped")


def test_unknown_scenario_is_reported_with_the_valid_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MF_MOCK_SCENARIO", "toaster")
    with pytest.raises(LLMNotConfigured, match="MF_MOCK_SCENARIO 'toaster'.*blister, cartoner, filling, assembly"):
        MockProvider()


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_scenario_and_its_scripted_edits_pass_the_validator(scenario: str) -> None:
    provider = MockProvider(scenario=scenario)
    first = _applied(empty_design(), _first(provider, "any text"))
    assert first == demo_design(scenario)

    # First request: a vision station before the outfeed and a U-shaped layout, in one revision.
    second = _applied(first, _refine(provider, first, "any request"))
    vision = next(s for s in second.stations if s.id == "st-vision")
    outfeed = next(s for s in second.stations if s.id == "st-outfeed")
    assert 0 < vision.sequence < outfeed.sequence
    assert (first.layout_style, second.layout_style) == ("inline", "u_shape")

    # Later requests switch the layout back and forth.
    third = _applied(second, _refine(provider, second, "any request"))
    assert third.layout_style == "inline"
    assert third.model_copy(update={"layout_style": "u_shape"}) == second


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_demo_machines_carry_v2_signals_and_mechanisms(scenario: str) -> None:
    design = _applied(demo_design(scenario), _refine(MockProvider(scenario=scenario), demo_design(scenario), "x"))
    components = [c for s in design.stations for c in s.components]
    assert all(c.signals is not None for c in components)
    assert any(c.role is not None for c in components)
    linked = [(s, c) for s in design.stations for c in s.components if c.motion is not None]
    assert linked, "moving axes are mechanisms, linked to the components that drive them"
    for station, component in linked:
        assert component.motion in {m.id for m in station.mechanisms}
    # No invented speeds: unknown until a drive is chosen. The blister's two servo axes take theirs
    # from a public catalog (Phase 2 spec, section H); its cylinders stay without.
    cataloged = {"m-film-index", "m-punch"} if scenario == "blister" else set()
    for station in design.stations:
        for mechanism in station.mechanisms:
            if mechanism.id in cataloged:
                assert mechanism.max_speed is not None and mechanism.acceleration is not None
            else:
                assert mechanism.max_speed is None and mechanism.acceleration is None
    assert any("speed" in q for q in design.open_questions)


def test_blister_process_stations_have_a_computed_cycle_and_limiting_step() -> None:
    """Phase 2 spec, section H: every blister process station gets its cycle from the timing engine."""
    design = demo_design("blister")
    process = [s for s in design.stations if s.kind == "process"]
    assert [s.id for s in process] == ["st-forming", "st-feeding", "st-sealing", "st-cutting"]

    # Hand calculation from the demo's inputs (spec section B formulas):
    # neither servo axis reaches its speed (film index 120 mm < 3000^2/40000 = 225 mm; punch 30 mm <
    # 1200^2/25000 = 57.6 mm), so each move takes 2*sqrt(s/a). Cylinder strokes and process times are
    # fixed steps.
    index = 2 * math.sqrt(120 / 40000)
    punch = 2 * math.sqrt(30 / 25000)
    expected = {
        "st-forming": (index + 0.43 + 0.2 + 0.43, "st-forming-close"),
        "st-feeding": (1.2, "st-feeding-cycle"),
        "st-sealing": (0.35 + 0.4 + 0.35, "st-sealing-seal"),
        "st-cutting": (2 * punch, "st-cutting-down"),
    }
    for station in process:
        timing = station_timing(station)
        assert timing.not_computable == [], station.id
        cycle, limiting = expected[station.id]
        assert timing.cycle_time_s == pytest.approx(cycle, abs=1e-9), station.id
        assert timing.limiting_step_id == limiting
        assert station.cycle_time_s == timing.cycle_time_s
        assert timing.target_cycle_time_s == 1.2

    # A servo axis drives a motion step on a critical path, so editing its stroke changes the cycle
    # with no AI call; the cylinders are fixed steps (ADR 0029), the brush feeder has no mechanism.
    motions = {step.mechanism_id for s in process for step in s.steps if step.kind == "motion"}
    assert motions == {"m-film-index", "m-punch"}
    feeding = next(s for s in process if s.id == "st-feeding")
    assert feeding.mechanisms == []
    assert design.assumptions[1:] == BLISTER_TIMING_ASSUMPTIONS
