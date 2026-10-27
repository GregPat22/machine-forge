"""OpenAI provider (Responses API, `POST /v1/responses`).

Uses strict structured outputs: the answer schema fits OpenAI's documented limits (5000 properties,
10 levels of nesting, no `allOf`). The answer is still validated by our code like any other provider.
"""

from __future__ import annotations

import httpx

from app.llm.base import LLMError, LLMNotConfigured, ProgressFn, T, Turn, answer_with_repair, progress_from_text
from app.schema import strict_schema

OPENAI_URL = "https://api.openai.com/v1"


class OpenAIProvider:
    name = "openai"
    strict_schema = True
    tools = True
    thinking = False  # reasoning is not requested or shown

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = OPENAI_URL,
        timeout_s: float = 600.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model = model
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_s,
            transport=transport,
        )

    def structured(
        self, *, system: str, turns: list[Turn], output: type[T], on_progress: ProgressFn | None = None
    ) -> T:
        if on_progress:
            on_progress(progress_from_text("waiting", ""))  # called without streaming
        text_format = {"type": "json_schema", "name": output.__name__, "schema": strict_schema(output), "strict": True}
        return answer_with_repair(lambda t: self._complete(system, t, text_format), turns, output)

    def _complete(self, system: str, turns: list[Turn], text_format: dict) -> str:
        payload = {
            "model": self.model,
            "input": [{"role": "system", "content": system}, *turns],
            "text": {"format": text_format},
            "store": False,  # designs are company IP: do not keep responses on OpenAI's side
        }
        try:
            response = self._http.post("/responses", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403):
                raise LLMNotConfigured("OpenAI rejected the API key: check OPENAI_API_KEY.") from exc
            if status == 429:
                raise LLMError("OpenAI rate limit reached; retry in a minute.") from exc
            raise LLMError(f"OpenAI API error {status}: {exc.response.text[:300]}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Cannot reach the OpenAI API: {exc}") from exc

        data = response.json()
        if data.get("status") == "incomplete":
            reason = (data.get("incomplete_details") or {}).get("reason")
            if reason == "content_filter":
                raise LLMError("The model declined this request. Rephrase it and try again.")
            raise LLMError("The design got too large for one answer. Ask for a smaller change.")
        parts = [part for item in data.get("output", []) if item.get("type") == "message"
                 for part in item.get("content", [])]
        if any(part.get("type") == "refusal" for part in parts):
            raise LLMError("The model declined this request. Rephrase it and try again.")
        text = "".join(part.get("text", "") for part in parts if part.get("type") == "output_text")
        if not text:
            raise LLMError("The model returned no answer.")
        return text
