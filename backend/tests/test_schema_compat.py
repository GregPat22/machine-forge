"""The AI's answer schema (PatchUpdate) works with strict structured outputs (Phase 1 step 2).

The answer fixture is written in the strict-output shape (every key present, unused ones null).
It is synthetic: tests run without network or keys, so it was not recorded from a live API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anthropic
import httpx
import httpx2

from app.llm.anthropic_provider import AnthropicProvider
from app.llm.openai_compatible import OpenAICompatibleProvider
from app.schema import _UNSUPPORTED_KEYS, strict_schema
from app.services.patch import PatchUpdate, apply_patches, empty_design
from tests.test_llm_providers import _sse

ANSWER = (Path(__file__).parent / "fixtures" / "patches" / "first_turn.json").read_text(encoding="utf-8")
OPS = {
    "add_station", "remove_station", "set_param", "add_component", "remove_component", "replace_component",
    "add_mechanism", "set_mechanism", "add_step", "remove_step", "connect", "disconnect", "set_product",
    "set_utility", "add_assumption", "add_open_question",
}


def _nodes(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _nodes(value)
    elif isinstance(node, list):
        for item in node:
            yield from _nodes(item)


def _refs(node: Any) -> set[str]:
    return {n["$ref"].rsplit("/", 1)[-1] for n in _nodes(node) if "$ref" in n}


def test_patch_update_schema_is_strict_friendly() -> None:
    schema = strict_schema(PatchUpdate)
    for node in _nodes(schema):
        assert not set(node) & _UNSUPPORTED_KEYS, node  # no numeric or string bounds, no defaults
        if node.get("type") == "object":
            # Closed objects only: a free-form dict has no properties or open additionalProperties.
            assert node.get("properties"), node
            assert node["additionalProperties"] is False
            assert node["required"] == list(node["properties"])

    # No recursion: the definitions reference each other without a cycle.
    defs = schema.get("$defs", {})
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(name: str) -> None:
        assert name not in visiting, f"recursive schema through {name}"
        if name in done:
            return
        visiting.add(name)
        for ref in _refs(defs[name]):
            visit(ref)
        visiting.discard(name)
        done.add(name)

    for name in defs:
        visit(name)

    op = defs["PatchOp"]["properties"]["op"]
    assert set(op["enum"]) == OPS

    text = json.dumps(schema)
    for computed in ("sequence", "cycle_time_s", "placement", "schema_version", "x_mm"):
        assert f'"{computed}"' not in text


def test_answer_fixture_is_in_the_strict_shape_and_applies() -> None:
    raw = json.loads(ANSWER)
    fields = set(strict_schema(PatchUpdate)["$defs"]["PatchOp"]["properties"])
    assert all(set(patch) == fields for patch in raw["patches"])  # every key present, as strict mode returns
    update = PatchUpdate.model_validate(raw)
    result = apply_patches(empty_design(), update.patches)
    assert result.ok, result.errors


def test_anthropic_sends_the_strict_schema_and_parses_the_answer() -> None:
    seen: dict = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, text=_sse(ANSWER), headers={"content-type": "text/event-stream"})

    client = anthropic.Anthropic(api_key="test-key", max_retries=0,
                                 http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)))
    update = AnthropicProvider(model="claude-opus-5-5", client=client).structured(
        system="s", turns=[{"role": "user", "content": "x"}], output=PatchUpdate)
    assert seen["body"]["output_config"]["format"] == {"type": "json_schema", "schema": strict_schema(PatchUpdate)}
    assert update == PatchUpdate.model_validate_json(ANSWER)


def test_openai_compatible_sends_the_strict_schema_and_parses_the_answer() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [
            {"message": {"role": "assistant", "content": ANSWER}, "finish_reason": "stop"}]})

    provider = OpenAICompatibleProvider("http://llm.local/v1", "llama3.1", transport=httpx.MockTransport(handler))
    update = provider.structured(system="s", turns=[{"role": "user", "content": "x"}], output=PatchUpdate)
    assert seen["body"]["response_format"]["json_schema"] == {
        "name": "PatchUpdate", "schema": strict_schema(PatchUpdate), "strict": True,
    }
    assert update == PatchUpdate.model_validate_json(ANSWER)
