"""Provider for any OpenAI-compatible chat endpoint.

This is the private-deployment path: Ollama, vLLM, LM Studio, LocalAI or a company
Azure OpenAI deployment all expose `/chat/completions`. Data never leaves the network
when the endpoint is on-premise.
"""

from __future__ import annotations

import httpx

from app.llm.base import LLMError, ProgressFn, T, Turn, answer_with_repair, progress_from_text
from app.schema import strict_schema


class OpenAICompatibleProvider:
    name = "openai_compatible"
    # Strict json_schema is requested; whether the server enforces it depends on the server.
    strict_schema = True
    tools = False
    thinking = False

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
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": output.__name__, "schema": strict_schema(output), "strict": True},
        }
        # Local models follow schemas less reliably than hosted ones: a mismatch goes back with the error.
        return answer_with_repair(lambda t: self._complete(system, t, response_format), turns, output)

    def _complete(self, system: str, turns: list[Turn], response_format: dict) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *turns],
            "response_format": response_format,
        }
        try:
            response = self._http.post("/chat/completions", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"LLM endpoint error {exc.response.status_code}: {exc.response.text[:300]}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Cannot reach the LLM endpoint at {self._http.base_url}: {exc}") from exc

        choice = response.json()["choices"][0]
        if choice.get("finish_reason") == "length":
            raise LLMError("The design got too large for one answer. Ask for a smaller change.")
        return choice["message"].get("content") or ""
