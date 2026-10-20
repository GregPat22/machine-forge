"""Provider for any OpenAI-compatible chat endpoint.

This is the private-deployment path: Ollama, vLLM, LM Studio, LocalAI or a company
Azure OpenAI deployment all expose `/chat/completions`. Data never leaves the network
when the endpoint is on-premise.
"""

from __future__ import annotations

import json

import httpx
from pydantic import ValidationError

from app.llm.base import LLMError, ProgressFn, T, Turn, progress_from_text
from app.schema import strict_schema


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_s: float = 600.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout_s, transport=transport
        )

    def structured(
        self, *, system: str, turns: list[Turn], output: type[T], on_progress: ProgressFn | None = None
    ) -> T:
        if on_progress:
            on_progress(progress_from_text("waiting", ""))  # this endpoint is called without streaming
        schema = strict_schema(output)
        messages = [{"role": "system", "content": system}, *turns]
        last_error = ""
        # Local models follow schemas less reliably than hosted ones: retry once with the error.
        for _attempt in range(2):
            payload = {
                "model": self.model,
                "messages": messages,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": output.__name__, "schema": schema, "strict": True},
                },
            }
            try:
                response = self._http.post("/chat/completions", json=payload)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise LLMError(f"LLM endpoint error {exc.response.status_code}: {exc.response.text[:300]}") from exc
            except httpx.HTTPError as exc:
                raise LLMError(f"Cannot reach the LLM endpoint at {self._http.base_url}: {exc}") from exc

            choice = response.json()["choices"][0]
            text = choice["message"].get("content") or ""
            if choice.get("finish_reason") == "length":
                raise LLMError("The design got too large for one answer. Ask for a smaller change.")
            try:
                return output.model_validate(json.loads(text))
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = str(exc)
                messages = [
                    *messages,
                    {"role": "assistant", "content": text},
                    {
                        "role": "user",
                        "content": "That answer is not valid against the JSON schema:\n"
                        f"{last_error}\nReturn the corrected JSON only.",
                    },
                ]
        raise LLMError(f"The model's answer did not match the design schema: {last_error}")
