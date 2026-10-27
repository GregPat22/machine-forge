"""Google Gemini provider (`models.generateContent`).

JSON mode without a response schema. Google documents that complex schemas can be rejected with
`400 INVALID_ARGUMENT` and the answer schema has 51 nullable (`anyOf`) fields; whether Gemini accepts
it is untested. Until a live test shows it does, the schema goes in the system instruction and our
code validates the answer, as for Claude (ADR 0014).
"""

from __future__ import annotations

import httpx

from app.llm.base import (
    LLMError,
    LLMNotConfigured,
    ProgressFn,
    T,
    Turn,
    answer_with_repair,
    progress_from_text,
    schema_instructions,
)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
# finishReason values that mean the model stopped for a policy reason, not because it was done.
DECLINED = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}


class GeminiProvider:
    name = "gemini"
    strict_schema = False
    tools = True
    thinking = False  # thoughts are not requested or shown

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = GEMINI_URL,
        timeout_s: float = 600.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model = model
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"), headers={"x-goog-api-key": api_key}, timeout=timeout_s, transport=transport
        )

    def structured(
        self, *, system: str, turns: list[Turn], output: type[T], on_progress: ProgressFn | None = None
    ) -> T:
        if on_progress:
            on_progress(progress_from_text("waiting", ""))  # called without streaming
        system = f"{system}\n\n{schema_instructions(output)}"
        return answer_with_repair(lambda t: self._complete(system, t), turns, output)

    def _complete(self, system: str, turns: list[Turn]) -> str:
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [
                {"role": "model" if t["role"] == "assistant" else "user", "parts": [{"text": t["content"]}]}
                for t in turns
            ],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        try:
            response = self._http.post(f"/models/{self.model}:generateContent", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403):
                raise LLMNotConfigured("Gemini rejected the API key: check GEMINI_API_KEY.") from exc
            if status == 429:
                raise LLMError("Gemini rate limit reached; retry in a minute.") from exc
            raise LLMError(f"Gemini API error {status}: {exc.response.text[:300]}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Cannot reach the Gemini API: {exc}") from exc

        data = response.json()
        if (data.get("promptFeedback") or {}).get("blockReason"):
            raise LLMError("The model declined this request. Rephrase it and try again.")
        candidates = data.get("candidates") or []
        if not candidates:
            raise LLMError("The model returned no answer.")
        candidate = candidates[0]
        finish = candidate.get("finishReason")
        if finish in DECLINED:
            raise LLMError("The model declined this request. Rephrase it and try again.")
        if finish == "MAX_TOKENS":
            raise LLMError("The design got too large for one answer. Ask for a smaller change.")
        if finish not in (None, "STOP"):
            raise LLMError(f"Gemini stopped before finishing the answer ({finish}). Try again.")
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
        if not text:
            raise LLMError("The model returned no answer.")
        return text
