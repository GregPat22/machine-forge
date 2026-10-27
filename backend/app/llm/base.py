"""Provider-neutral interface for the language model that edits machine designs."""

from __future__ import annotations

import json
from typing import Callable, Literal, Protocol, TypedDict, TypeVar

from pydantic import BaseModel, ValidationError

from app.schema import strict_schema

T = TypeVar("T", bound=BaseModel)


class Turn(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class Progress(TypedDict):
    phase: Literal["waiting", "thinking", "writing"]
    chars: int       # characters of the answer written so far
    stations: int    # stations written so far (estimated from the partial JSON)
    components: int  # components written so far (estimated)
    note: str | None  # e.g. the latest line of the model's thinking summary


ProgressFn = Callable[[Progress], None]


class LLMError(RuntimeError):
    """The model could not produce a usable answer. The message is safe to show to the user."""


class LLMNotConfigured(LLMError):
    pass


class LLMProvider(Protocol):
    name: str
    model: str
    # The API constrains the answer to the JSON schema. When false, the schema is sent as text and only
    # our validation checks the answer; correctness never depends on this flag (decision D6).
    strict_schema: bool
    # The API supports tool calls (not used yet).
    tools: bool
    # The provider asks for the model's reasoning and reports it as progress.
    thinking: bool

    def structured(
        self, *, system: str, turns: list[Turn], output: type[T], on_progress: ProgressFn | None = None
    ) -> T:
        """Run one model call and return its answer parsed and validated as `output`.

        `on_progress`, when given, is called from the same thread while the answer is generated.
        """
        ...


def progress_from_text(phase: str, text: str, note: str | None = None) -> Progress:
    """Estimate progress from a partial answer JSON (every station has "function", every
    component has "category")."""
    return Progress(phase=phase, chars=len(text), stations=text.count('"function"'),  # type: ignore[typeddict-item]
                    components=text.count('"category"'), note=note)


# Answers per call when the JSON does not match the schema (the first one included). This only checks
# the shape; the meaning of the patches is checked by the designer's repair loop.
SCHEMA_ATTEMPTS = 2


def schema_instructions(output: type[BaseModel]) -> str:
    """The schema as text, for providers that do not enforce it (appended to the system prompt)."""
    return (
        "Answer with one JSON object and nothing else. It must match this JSON schema; "
        "give every property, null where a value is unknown:\n" + json.dumps(strict_schema(output))
    )


def answer_with_repair(
    complete: Callable[[list[Turn]], str], turns: list[Turn], output: type[T], attempts: int = SCHEMA_ATTEMPTS
) -> T:
    """Call `complete` and validate its text as `output`; on a mismatch, send the error back and retry."""
    last_error = ""
    for _attempt in range(attempts):
        text = complete(turns)
        try:
            # extra="forbid": a key outside the schema is an error, as in strict mode, not silently dropped.
            return output.model_validate(json.loads(_unfenced(text)), extra="forbid")
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = str(exc)
            turns = [
                *turns,
                {"role": "assistant", "content": text},
                {"role": "user", "content": "That answer is not valid against the JSON schema:\n"
                                            f"{last_error}\nReturn the corrected JSON only."},
            ]
    raise LLMError(f"The model's answer did not match the design schema: {last_error}")


def _unfenced(text: str) -> str:
    """The answer without a Markdown code fence around it, which models without strict mode sometimes add."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text
