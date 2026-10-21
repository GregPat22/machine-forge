# ADR 0006: Any AI provider; correctness never depends on provider features

Date: 2026-10-21. Status: accepted. Plan decision D6.

**Context.** Companies will demand self-hosted models for their machine data. Provider
features differ: strict JSON schema, tool use, extended thinking and output limits vary, and
local models have none of the first two reliably.

**Decision.** Providers: Anthropic (native), OpenAI (native, Responses API), Google Gemini
(native), OpenAI-compatible (Ollama, vLLM, LM Studio, Azure, OpenRouter), plus the offline
mock. Each declares capability flags. The design loop is correct with none of the optional
features: validate-and-repair replaces strict schema, a plan/act JSON loop replaces tool use.
The mock provider must drive every feature end to end, so CI proves the degraded path.
