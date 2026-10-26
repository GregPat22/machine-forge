"""The repair loop: rejected patches go back to the model as the next turn (Phase 1 step 2)."""

from __future__ import annotations

import logging

import pytest

from app.config import load_settings
from app.llm import LLMError
from app.llm.base import Turn
from app.models import Product, Station, Transport
from app.services.designer import Designer, PatchRejected
from app.services.patch import PatchOp, PatchUpdate
from app.storage import Storage


def _first_version() -> PatchUpdate:
    return PatchUpdate(reply="First version.", patches=[
        PatchOp(op="set_param", name="name", text="Test line"),
        PatchOp(op="set_param", name="machine_type", text="test machine"),
        PatchOp(op="set_param", name="summary", text="for the repair loop"),
        PatchOp(op="add_station", station=Station(id="st-a", name="A", function="forms")),
        PatchOp(op="add_station", station=Station(id="st-b", name="B", function="seals")),
        PatchOp(op="connect", transport=Transport(id="tr-a-b", from_station="st-a", to_station="st-b")),
    ])


NEGATIVE_LANES = PatchUpdate(reply="Set -2 lanes.", patches=[PatchOp(op="set_product", product=Product(lanes=-2))])
UNKNOWN_STATION = PatchUpdate(reply="Removed it.", patches=[PatchOp(op="remove_station", station_id="st-x")])
TWO_LANES = PatchUpdate(reply="Two lanes.", patches=[PatchOp(op="set_product", product=Product(lanes=2))])


class ScriptedProvider:
    name = "scripted"
    model = "script"

    def __init__(self, *answers: PatchUpdate) -> None:
        self.answers = list(answers)
        self.calls: list[list[Turn]] = []

    def structured(self, *, system, turns, output, on_progress=None):  # noqa: ANN001
        assert output is PatchUpdate
        self.calls.append(list(turns))
        return self.answers[min(len(self.calls), len(self.answers)) - 1]


def _project(storage: Storage) -> str:
    return Designer(storage, ScriptedProvider(_first_version())).create("A problem statement").id


def test_two_invalid_answers_then_a_valid_one(caplog: pytest.LogCaptureFixture) -> None:
    storage = Storage(":memory:")
    project_id = _project(storage)
    provider = ScriptedProvider(NEGATIVE_LANES, UNKNOWN_STATION, TWO_LANES)

    with caplog.at_level(logging.INFO, logger="app.services.designer"):
        project = Designer(storage, provider, max_attempts=3).refine(project_id, "Use two lanes")

    assert project.latest_revision == 2 and project.design.product.lanes == 2
    assert project.messages[-1].content == "Two lanes."
    attempts = [r for r in caplog.records if r.name == "app.services.designer"]
    assert [r.getMessage().split(":")[0] for r in attempts] == ["attempt 1/3", "attempt 2/3", "attempt 3/3"]

    # Each retry carries the rejected answer and the exact errors, after the original request.
    assert len(provider.calls) == 3
    second, third = provider.calls[1], provider.calls[2]
    assert second[:-2] == provider.calls[0]
    assert second[-2] == {"role": "assistant", "content": NEGATIVE_LANES.model_dump_json()}
    assert "patch 0 (set_product): invalid_value: product lanes is -2; it must be at least 1" in second[-1]["content"]
    assert third[:-2] == second
    assert "patch 0 (remove_station): unknown_station: station 'st-x' does not exist" in third[-1]["content"]


def test_a_provider_that_never_recovers(caplog: pytest.LogCaptureFixture) -> None:
    storage = Storage(":memory:")
    project_id = _project(storage)
    before = storage.get_project(project_id)
    provider = ScriptedProvider(NEGATIVE_LANES)

    with caplog.at_level(logging.INFO, logger="app.services.designer"), pytest.raises(PatchRejected) as raised:
        Designer(storage, provider, max_attempts=2).refine(project_id, "Use minus two lanes")

    assert isinstance(raised.value, LLMError)  # the API shows it to the user like any model error
    assert str(raised.value) == (
        "The AI could not make a valid change in 2 attempts, so the design is unchanged. "
        "Last problems: product lanes is -2; it must be at least 1"
    )
    assert len(provider.calls) == 2
    assert len([r for r in caplog.records if r.name == "app.services.designer"]) == 2
    assert storage.get_project(project_id) == before


def test_the_first_answer_must_name_the_machine() -> None:
    storage = Storage(":memory:")
    unnamed = PatchUpdate(reply="Stations only.", patches=[
        PatchOp(op="add_station", station=Station(id="st-a", name="A", function="forms")),
    ])
    provider = ScriptedProvider(unnamed, _first_version())
    project = Designer(storage, provider).create("A problem statement")
    assert project.design.name == "Test line"
    assert "the first answer must set name, machine_type and summary with set_param" in provider.calls[1][-1]["content"]


def test_max_repair_attempts_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MF_MAX_REPAIR_ATTEMPTS", raising=False)
    assert load_settings().max_repair_attempts == 3
    monkeypatch.setenv("MF_MAX_REPAIR_ATTEMPTS", "5")
    assert load_settings().max_repair_attempts == 5
    monkeypatch.setenv("MF_MAX_REPAIR_ATTEMPTS", "0")
    with pytest.raises(ValueError, match="MF_MAX_REPAIR_ATTEMPTS must be at least 1"):
        load_settings()
