"""Claude (Anthropic API) provider."""

from __future__ import annotations

import time

import anthropic

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

FALLBACK_BETA = "server-side-fallback-2026-07-01"
PROGRESS_INTERVAL_S = 0.4


class AnthropicProvider:
    name = "anthropic"
    # Strict mode allows 16 nullable fields per request and the answer schema has more, so the schema goes
    # in the system prompt and our code validates the answer (ADR 0014).
    strict_schema = False
    tools = True
    thinking = True

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

    def structured(
        self, *, system: str, turns: list[Turn], output: type[T], on_progress: ProgressFn | None = None
    ) -> T:
        system = f"{system}\n\n{schema_instructions(output)}"
        return answer_with_repair(lambda t: self._complete(system, t, on_progress), turns, output)

    def _complete(self, system: str, turns: list[Turn], on_progress: ProgressFn | None) -> str:
        """One streamed call; returns the answer text."""
        text, thought = "", ""
        last_report = 0.0

        def report(phase: str, force: bool = False) -> None:
            nonlocal last_report
            if on_progress is None or (not force and time.monotonic() - last_report < PROGRESS_INTERVAL_S):
                return
            last_report = time.monotonic()
            lines = [ln.strip() for ln in thought.splitlines() if ln.strip()]
            on_progress(progress_from_text(phase, text, lines[-1][-160:] if lines else None))

        try:
            # Streaming keeps long design generations clear of HTTP timeouts and lets us report progress.
            with self._client.beta.messages.stream(
                model=self.model,
                max_tokens=64000,
                system=system,
                messages=list(turns),
                # Summarized thinking gives the user something to read while the model reasons.
                thinking={"type": "adaptive", "display": "summarized"},
                output_config={"effort": self.effort},
                # The system prompt (with the schema) is identical on every call, so cache it.
                cache_control={"type": "ephemeral"},
                # If a safety classifier declines, let the API retry on its recommended fallback model.
                betas=[FALLBACK_BETA],
                fallbacks="default",
            ) as stream:
                report("waiting", force=True)
                for event in stream:
                    if event.type != "content_block_delta":
                        continue
                    delta = event.delta
                    if delta.type == "thinking_delta":
                        thought += delta.thinking
                        report("thinking")
                    elif delta.type == "text_delta":
                        text += delta.text
                        report("writing")
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

        answer = next((block.text for block in message.content if block.type == "text"), None)
        if answer is None:
            raise LLMError("The model returned no answer.")
        return answer
