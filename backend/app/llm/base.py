"""Provider-neutral interface for the language model that edits machine designs."""

from __future__ import annotations

from typing import Literal, Protocol, TypedDict, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class Turn(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class LLMError(RuntimeError):
    """The model could not produce a usable answer. The message is safe to show to the user."""


class LLMNotConfigured(LLMError):
    pass


class LLMProvider(Protocol):
    name: str
    model: str

    def structured(self, *, system: str, turns: list[Turn], output: type[T]) -> T:
        """Run one model call and return its answer parsed and validated as `output`."""
        ...
