"""Claude (Anthropic API) provider."""

from __future__ import annotations

import json

import anthropic
from pydantic import ValidationError

from app.llm.base import LLMError, LLMNotConfigured, T, Turn
from app.schema import strict_schema

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str, effort: str = "high", client: anthropic.Anthropic | None = None):
        self.model = model
        self.effort = effort
        # Credentials come from ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN or an `ant auth login` profile.
        self._client = client or anthropic.Anthropic()
        if not (self._client.api_key or self._client.auth_token or self._client.credentials):
            raise LLMNotConfigured(
                "Claude is not configured: set ANTHROPIC_API_KEY in backend/.env "
                "(or choose another MF_LLM_PROVIDER)."
            )

    def structured(self, *, system: str, turns: list[Turn], output: type[T]) -> T:
        try:
            # Streaming keeps long design generations clear of HTTP timeouts.
            with self._client.beta.messages.stream(
                model=self.model,
                max_tokens=64000,
                system=system,
                messages=list(turns),
                thinking={"type": "adaptive"},
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": strict_schema(output)},
                },
                # The system prompt is identical on every call, so cache it.
                cache_control={"type": "ephemeral"},
                # If a safety classifier declines, let the API retry on its recommended fallback model.
                betas=[FALLBACK_BETA],
                fallbacks="default",
            ) as stream:
                message = stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise LLMNotConfigured("Claude rejected the API key: check ANTHROPIC_API_KEY.") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Claude rate limit reached; retry in a minute.") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Claude API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Cannot reach the Claude API (network or proxy problem).") from exc

        if message.stop_reason == "refusal":
            raise LLMError("The model declined this request. Rephrase it and try again.")
        if message.stop_reason == "max_tokens":
            raise LLMError("The design got too large for one answer. Ask for a smaller change.")

        text = next((block.text for block in message.content if block.type == "text"), None)
        if text is None:
            raise LLMError("The model returned no answer.")
        try:
            return output.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise LLMError(f"The model's answer did not match the design schema: {exc}") from exc
