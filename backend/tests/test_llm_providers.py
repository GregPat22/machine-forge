"""LLM providers against simulated HTTP endpoints (no network, no keys)."""

from __future__ import annotations

import json

import anthropic
import httpx
import httpx2
import pytest

from app.llm.anthropic_provider import FALLBACK_BETA, AnthropicProvider
from app.llm.base import LLMError, LLMNotConfigured
from app.llm.mock import _design_patches, _initial_design
from app.llm.openai_compatible import OpenAICompatibleProvider
from app.services.patch import PatchUpdate, apply_patches, empty_design
from tests.conftest import BLISTER_PROBLEM

ANSWER = PatchUpdate(reply="First version.", patches=_design_patches(_initial_design(BLISTER_PROBLEM))).model_dump_json()


def _design(update: PatchUpdate):
    result = apply_patches(empty_design(), update.patches)
    assert result.design is not None, result.errors
    return result.design


def _sse(text: str, stop_reason: str = "end_turn", thinking: list[str] | None = None, chunks: int = 1) -> str:
    events = [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": [],
            "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 1}}}),
    ]
    index = 0
    if thinking:
        events.append(("content_block_start", {"type": "content_block_start", "index": 0,
                                               "content_block": {"type": "thinking", "thinking": "", "signature": ""}}))
        events += [("content_block_delta", {"type": "content_block_delta", "index": 0,
                                            "delta": {"type": "thinking_delta", "thinking": t}}) for t in thinking]
        events += [("content_block_delta", {"type": "content_block_delta", "index": 0,
                                            "delta": {"type": "signature_delta", "signature": "sig"}}),
                   ("content_block_stop", {"type": "content_block_stop", "index": 0})]
        index = 1
    size = max(1, -(-len(text) // chunks))
    events.append(("content_block_start", {"type": "content_block_start", "index": index,
                                           "content_block": {"type": "text", "text": ""}}))
    events += [("content_block_delta", {"type": "content_block_delta", "index": index,
                                        "delta": {"type": "text_delta", "text": text[i:i + size]}})
               for i in range(0, max(len(text), 1), size)]
    events += [
        ("content_block_stop", {"type": "content_block_stop", "index": index}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                           "usage": {"output_tokens": 100}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)


def _anthropic(handler) -> AnthropicProvider:
    client = anthropic.Anthropic(
        api_key="test-key",
        max_retries=0,
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return AnthropicProvider(model="claude-opus-5-5", client=client)


def test_anthropic_request_shape_and_parsing() -> None:
    seen: dict = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        seen["beta"] = request.headers.get("anthropic-beta")
        return httpx2.Response(200, text=_sse(ANSWER), headers={"content-type": "text/event-stream"})

    result = _anthropic(handler).structured(
        system="sys", turns=[{"role": "user", "content": "hi"}], output=PatchUpdate
    )
    assert result.reply == "First version."
    assert _design(result).target_rate_text == "300 tablets/min"

    body = seen["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["stream"] is True
    assert body["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["fallbacks"] == "default"
    assert FALLBACK_BETA in seen["beta"]


def test_anthropic_reports_progress_while_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.llm.anthropic_provider as module

    monkeypatch.setattr(module, "PROGRESS_INTERVAL_S", 0.0)  # report every delta

    def handler(request: httpx2.Request) -> httpx2.Response:
        sse = _sse(ANSWER, thinking=["Sizing the forming station.\n", "Checking cycle time."], chunks=8)
        return httpx2.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    seen: list[dict] = []
    result = _anthropic(handler).structured(
        system="s", turns=[{"role": "user", "content": "x"}], output=PatchUpdate, on_progress=seen.append
    )
    assert result.reply == "First version."
    phases = [p["phase"] for p in seen]
    assert phases[0] == "waiting" and "thinking" in phases and phases[-1] == "writing"
    assert next(p for p in seen if p["phase"] == "thinking" and p["note"])["note"] == "Sizing the forming station."
    design = _design(result)
    assert seen[-1]["stations"] == len(design.stations)
    assert seen[-1]["components"] == sum(len(s.components) for s in design.stations)


def test_anthropic_refusal_is_reported() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, text=_sse("", stop_reason="refusal"), headers={"content-type": "text/event-stream"})

    with pytest.raises(LLMError, match="declined"):
        _anthropic(handler).structured(system="s", turns=[{"role": "user", "content": "x"}], output=PatchUpdate)


def test_anthropic_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    client = anthropic.Anthropic()
    if client.credentials:  # a local `ant auth login` profile exists: nothing to assert
        pytest.skip("credentials available from a local profile")
    with pytest.raises(LLMNotConfigured):
        AnthropicProvider(model="claude-opus-5-5", client=client)


def test_openai_compatible_retries_after_invalid_json() -> None:
    answers = iter(["not json", ANSWER])
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [
            {"message": {"role": "assistant", "content": next(answers)}, "finish_reason": "stop"}]})

    provider = OpenAICompatibleProvider("http://llm.local/v1", "llama3.1", transport=httpx.MockTransport(handler))
    result = provider.structured(system="sys", turns=[{"role": "user", "content": "hi"}], output=PatchUpdate)
    assert result.reply == "First version."
    assert len(bodies) == 2
    assert bodies[0]["response_format"]["json_schema"]["strict"] is True
    assert bodies[1]["messages"][-1]["content"].startswith("That answer is not valid")
