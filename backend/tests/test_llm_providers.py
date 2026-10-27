"""LLM providers against simulated HTTP endpoints (no network, no keys)."""

from __future__ import annotations

import json

import anthropic
import httpx
import httpx2
import pytest

from app.config import Settings
from app.llm import make_provider
from app.llm.anthropic_provider import FALLBACK_BETA, AnthropicProvider
from app.llm.base import LLMError, LLMNotConfigured
from app.llm.gemini_provider import GeminiProvider
from app.llm.mock import MockProvider, _design_patches, _initial_design
from app.llm.openai_compatible import OpenAICompatibleProvider
from app.llm.openai_provider import OpenAIProvider
from app.schema import strict_schema
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
    # Not strict mode: the answer schema is too large for it (ADR 0014). The schema is in the system prompt.
    assert "format" not in body["output_config"]
    assert json.dumps(strict_schema(PatchUpdate)) in body["system"]
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


def _sse_response(text: str) -> httpx2.Response:
    return httpx2.Response(200, text=_sse(text), headers={"content-type": "text/event-stream"})


def test_capability_flags_are_reported() -> None:
    flags = lambda p: (p.strict_schema, p.tools, p.thinking)  # noqa: E731
    assert flags(_anthropic(lambda r: _sse_response(ANSWER))) == (False, True, True)
    assert flags(OpenAIProvider(model="gpt-test", api_key="k")) == (True, True, False)
    assert flags(GeminiProvider(model="gemini-test", api_key="k")) == (False, True, False)
    assert flags(OpenAICompatibleProvider("http://llm.local/v1", "llama3.1")) == (True, False, False)
    assert flags(MockProvider()) == (True, False, False)


def test_anthropic_repairs_an_answer_that_does_not_match_the_schema() -> None:
    answers = iter(['{"reply": "no patches key"}', ANSWER])
    bodies: list[dict] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        bodies.append(json.loads(request.content))
        return _sse_response(next(answers))

    result = _anthropic(handler).structured(system="s", turns=[{"role": "user", "content": "x"}], output=PatchUpdate)
    assert result.reply == "First version."
    assert len(bodies) == 2
    assert bodies[1]["messages"][-2] == {"role": "assistant", "content": '{"reply": "no patches key"}'}
    assert bodies[1]["messages"][-1]["content"].startswith("That answer is not valid against the JSON schema")
    assert "patches" in bodies[1]["messages"][-1]["content"]


def test_an_unknown_key_is_sent_back_not_dropped() -> None:
    # Strict mode used to reject keys outside the schema; our check must too, or a misspelled field
    # would silently become null.
    misspelled = json.loads(ANSWER)
    misspelled["patches"][0]["nmae"] = misspelled["patches"][0].pop("name")
    answers = iter([json.dumps(misspelled), ANSWER])
    bodies: list[dict] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        bodies.append(json.loads(request.content))
        return _sse_response(next(answers))

    result = _anthropic(handler).structured(system="s", turns=[{"role": "user", "content": "x"}], output=PatchUpdate)
    assert result.reply == "First version."
    assert len(bodies) == 2
    error = bodies[1]["messages"][-1]["content"]
    assert "patches.0.nmae" in error and "Extra inputs are not permitted" in error


def test_anthropic_gives_up_after_the_schema_attempts() -> None:
    calls: list[int] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(1)
        return _sse_response("not json")

    with pytest.raises(LLMError, match="did not match the design schema"):
        _anthropic(handler).structured(system="s", turns=[{"role": "user", "content": "x"}], output=PatchUpdate)
    assert len(calls) == 2


def test_anthropic_reads_an_answer_wrapped_in_a_code_fence() -> None:
    fenced = f"```json\n{ANSWER}\n```"
    result = _anthropic(lambda r: _sse_response(fenced)).structured(
        system="s", turns=[{"role": "user", "content": "x"}], output=PatchUpdate)
    assert result.reply == "First version."


# OpenAI Responses API. The payloads follow the documented shape; they are synthetic, not recorded live
# (tests run without network or keys).

def _openai_response(text: str | None = None, *, refusal: str | None = None, status: str = "completed",
                     reason: str | None = None) -> dict:
    part = {"type": "refusal", "refusal": refusal} if refusal else {"type": "output_text", "text": text, "annotations": []}
    return {
        "id": "resp_1", "object": "response", "status": status, "model": "gpt-test",
        "incomplete_details": {"reason": reason} if reason else None,
        "output": [
            {"type": "reasoning", "id": "rs_1", "summary": []},
            {"type": "message", "id": "msg_1", "role": "assistant", "status": status, "content": [part]},
        ],
    }


def _openai(handler) -> OpenAIProvider:
    return OpenAIProvider(model="gpt-test", api_key="sk-test", transport=httpx.MockTransport(handler))


def test_openai_request_shape_and_parsing() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_openai_response(ANSWER))

    turns = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}, {"role": "user", "content": "c"}]
    result = _openai(handler).structured(system="sys", turns=turns, output=PatchUpdate)
    assert result.reply == "First version."
    assert _design(result).target_rate_text == "300 tablets/min"

    assert seen["url"] == "https://api.openai.com/v1/responses"
    assert seen["auth"] == "Bearer sk-test"
    body = seen["body"]
    assert body["model"] == "gpt-test"
    assert body["input"] == [{"role": "system", "content": "sys"}, *turns]
    assert body["text"]["format"] == {
        "type": "json_schema", "name": "PatchUpdate", "schema": strict_schema(PatchUpdate), "strict": True,
    }
    assert body["store"] is False  # designs are company IP: do not keep responses on OpenAI's side


def test_openai_refusal_and_truncation_are_reported() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_response(refusal="I can't help with that."))

    def truncate(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_response('{"reply": "Fir', status="incomplete",
                                                         reason="max_output_tokens"))

    turns = [{"role": "user", "content": "x"}]
    with pytest.raises(LLMError, match="declined"):
        _openai(refuse).structured(system="s", turns=turns, output=PatchUpdate)
    with pytest.raises(LLMError, match="too large"):
        _openai(truncate).structured(system="s", turns=turns, output=PatchUpdate)


def test_openai_rejected_key_is_reported_as_not_configured() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Incorrect API key provided"}})

    with pytest.raises(LLMNotConfigured, match="OPENAI_API_KEY"):
        _openai(handler).structured(system="s", turns=[{"role": "user", "content": "x"}], output=PatchUpdate)


# Google Gemini generateContent. Same note: synthetic payloads in the documented shape.

def _gemini_response(text: str, finish: str = "STOP", thought: str | None = None) -> dict:
    parts = ([{"text": thought, "thought": True}] if thought else []) + [{"text": text}]
    return {"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": finish, "index": 0}],
            "modelVersion": "gemini-test"}


def _gemini(handler) -> GeminiProvider:
    return GeminiProvider(model="gemini-test", api_key="g-test", transport=httpx.MockTransport(handler))


def test_gemini_request_shape_and_parsing() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_gemini_response(ANSWER, thought="Planning the stations."))

    turns = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}, {"role": "user", "content": "c"}]
    result = _gemini(handler).structured(system="sys", turns=turns, output=PatchUpdate)
    assert result.reply == "First version."  # the thought part is not part of the answer

    assert seen["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent"
    assert seen["key"] == "g-test"
    body = seen["body"]
    system = body["systemInstruction"]["parts"][0]["text"]
    assert system.startswith("sys") and json.dumps(strict_schema(PatchUpdate)) in system
    assert body["contents"] == [
        {"role": "user", "parts": [{"text": "a"}]},
        {"role": "model", "parts": [{"text": "b"}]},
        {"role": "user", "parts": [{"text": "c"}]},
    ]
    assert body["generationConfig"] == {"responseMimeType": "application/json"}  # JSON mode, no schema


def test_gemini_goes_through_the_repair_path() -> None:
    answers = iter(["not json", ANSWER])
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=_gemini_response(next(answers)))

    result = _gemini(handler).structured(system="s", turns=[{"role": "user", "content": "x"}], output=PatchUpdate)
    assert result.reply == "First version."
    assert len(bodies) == 2
    assert bodies[1]["contents"][-2] == {"role": "model", "parts": [{"text": "not json"}]}
    assert bodies[1]["contents"][-1]["parts"][0]["text"].startswith("That answer is not valid")


def test_gemini_block_and_truncation_are_reported() -> None:
    def blocked(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})

    def safety_stop(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_gemini_response("", finish="SAFETY"))

    def truncate(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_gemini_response('{"reply": "Fir', finish="MAX_TOKENS"))

    turns = [{"role": "user", "content": "x"}]
    for handler in (blocked, safety_stop):
        with pytest.raises(LLMError, match="declined"):
            _gemini(handler).structured(system="s", turns=turns, output=PatchUpdate)
    with pytest.raises(LLMError, match="too large"):
        _gemini(truncate).structured(system="s", turns=turns, output=PatchUpdate)


def test_gemini_any_other_early_stop_is_reported_with_its_reason() -> None:
    def malformed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_gemini_response('{"reply": "Fir', finish="MALFORMED_RESPONSE"))

    with pytest.raises(LLMError, match="MALFORMED_RESPONSE"):
        _gemini(malformed).structured(system="s", turns=[{"role": "user", "content": "x"}], output=PatchUpdate)


def test_make_provider_builds_the_native_providers_and_reports_missing_settings() -> None:
    openai = make_provider(Settings(llm_provider="openai", openai_native_api_key="k", openai_native_model="gpt-test"))
    gemini = make_provider(Settings(llm_provider="gemini", gemini_api_key="k", gemini_model="gemini-test"))
    assert (openai.name, openai.model) == ("openai", "gpt-test")
    assert (gemini.name, gemini.model) == ("gemini", "gemini-test")

    with pytest.raises(LLMNotConfigured, match="OPENAI_API_KEY"):
        make_provider(Settings(llm_provider="openai", openai_native_model="gpt-test"))
    with pytest.raises(LLMNotConfigured, match="MF_OPENAI_NATIVE_MODEL"):
        make_provider(Settings(llm_provider="openai", openai_native_api_key="k"))
    with pytest.raises(LLMNotConfigured, match="GEMINI_API_KEY"):
        make_provider(Settings(llm_provider="gemini", gemini_model="gemini-test"))
    with pytest.raises(LLMNotConfigured, match="MF_GEMINI_MODEL"):
        make_provider(Settings(llm_provider="gemini", gemini_api_key="k"))
