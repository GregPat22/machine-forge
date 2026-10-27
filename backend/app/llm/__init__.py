from __future__ import annotations

from app.config import Settings
from app.llm.base import LLMError, LLMNotConfigured, LLMProvider, Turn

__all__ = ["LLMError", "LLMNotConfigured", "LLMProvider", "Turn", "make_provider"]


def make_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "anthropic":
        from app.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(model=settings.anthropic_model, effort=settings.anthropic_effort)
    if settings.llm_provider == "openai":
        from app.llm.openai_provider import OpenAIProvider

        _require(settings.openai_native_api_key, "OpenAI", "OPENAI_API_KEY")
        _require(settings.openai_native_model, "OpenAI", "MF_OPENAI_NATIVE_MODEL")
        return OpenAIProvider(model=settings.openai_native_model, api_key=settings.openai_native_api_key)
    if settings.llm_provider == "gemini":
        from app.llm.gemini_provider import GeminiProvider

        _require(settings.gemini_api_key, "Gemini", "GEMINI_API_KEY")
        _require(settings.gemini_model, "Gemini", "MF_GEMINI_MODEL")
        return GeminiProvider(model=settings.gemini_model, api_key=settings.gemini_api_key)
    if settings.llm_provider == "openai_compatible":
        from app.llm.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(
            base_url=settings.openai_base_url, model=settings.openai_model, api_key=settings.openai_api_key
        )
    if settings.llm_provider == "mock":
        from app.llm.mock import MockProvider

        return MockProvider()
    raise LLMNotConfigured(
        f"Unknown MF_LLM_PROVIDER '{settings.llm_provider}'. "
        "Use anthropic, openai, gemini, openai_compatible or mock."
    )


def _require(value: str, provider: str, variable: str) -> None:
    if not value.strip():
        raise LLMNotConfigured(f"{provider} is not configured: set {variable} in backend/.env.")
