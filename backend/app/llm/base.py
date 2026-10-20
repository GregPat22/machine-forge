"""Provider-neutral interface for the language model that edits machine designs."""

from __future__ import annotations

from typing import Callable, Literal, Protocol, TypedDict, TypeVar

from pydantic import BaseModel

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

    def structured(
        self, *, system: str, turns: list[Turn], output: type[T], on_progress: ProgressFn | None = None
    ) -> T:
        """Run one model call and return its answer parsed and validated as `output`.

        `on_progress`, when given, is called from the same thread while the answer is generated.
        """
        ...


def progress_from_text(phase: str, text: str, note: str | None = None) -> Progress:
    """Estimate progress from a partial DesignUpdate JSON (every station has "function", every
    component has "category")."""
    return Progress(phase=phase, chars=len(text), stations=text.count('"function"'),  # type: ignore[typeddict-item]
                    components=text.count('"category"'), note=note)
