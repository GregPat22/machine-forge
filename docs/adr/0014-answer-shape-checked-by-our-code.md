# ADR 0014: Our code checks the shape of the AI's answer, not the provider's strict mode

Date: 2026-10-27. Status: accepted. Phase 1 step 5. Resolves the open limit in ADR 0013.

**Context.** Claude strict mode allows at most 16 fields that may be null per request (Anthropic,
"Structured outputs", schema complexity limits) and the patch answer schema has 51, so every Claude
request would fail. The options were: (A) send the schema as text and let our code validate the
answer, sending errors back for another attempt; (B) shrink the schema under 16 nullable fields,
which means rewriting the model and putting placeholders where a value is unknown, and breaks again
as the model grows; (C) one strict tool per patch operation, still over the limit for operations
that carry a station or component, more code, and Claude cannot be forced to call a tool; (D) rely
on a provider without this limit, against "any AI provider" (ADR 0006).

**Decision.** Option A, chosen by Greg on 2026-10-27. Each provider declares `strict_schema`.
Claude gets the schema in the system prompt. So does Gemini until a live test shows it accepts
the schema (Google documents that complex schemas can be rejected; untested). OpenAI and
OpenAI-compatible servers keep strict mode, since the schema fits OpenAI's limits. Every
provider's answer goes through the same check in `llm/base.py`: parsed and validated by Pydantic
with unknown keys rejected (as strict mode would), and on a mismatch sent back with the error, up
to two answers per call. The meaning of the patches is still checked by the patch validator and the
designer's repair loop (ADR 0013). Cost: an occasional extra answer when the shape is wrong.
