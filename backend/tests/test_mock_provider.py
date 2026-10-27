"""The offline demo engine (Phase 1 spec, section F): an explicit scenario, never the user's text."""

from __future__ import annotations

import pytest

from app.llm import LLMNotConfigured
from app.llm.mock import SCENARIOS, MockProvider, demo_design
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
    for station in design.stations:
        for mechanism in station.mechanisms:  # no invented speeds: unknown until a drive is chosen
            assert mechanism.max_speed is None and mechanism.acceleration is None
    assert any("speed" in q for q in design.open_questions)
