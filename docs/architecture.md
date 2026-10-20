# Architecture

```
frontend (React + Vite)  ──/api──>  backend (FastAPI)
                                      ├── Designer      prompting loop, revisions
                                      │     └── LLMProvider  anthropic | openai_compatible | mock
                                      ├── spare_parts   design -> aggregated catalog (BOM)
                                      ├── Sourcing      catalog x (your price list + connectors) -> comparison
                                      │     └── SupplierConnector  mouser | nexar | ...
                                      └── Storage       SQLite: projects, revisions, chat, price list, offer cache
```

## The machine model is the source of truth

`backend/app/models.py` → `MachineDesign`. The AI never edits text documents or files. It returns
a complete, schema-validated `MachineDesign` on every turn (`DesignUpdate` = reply + design).
Everything else is derived from it in code:

- the spare-parts catalog (`services/spare_parts.py`), where identical part numbers across stations
  are merged;
- the supplier comparison (`services/sourcing.py`);
- later, the 3D layout, PLC, CAD and documents (see [output-options.md](output-options.md)).

Because each turn returns the full design, every revision is a complete snapshot: you can view,
diff or restore any of them. Component and station ids are kept stable across revisions (the
system prompt requires it), so revisions can be compared item by item.

The model avoids JSON-schema features that strict structured-output modes reject (free-form maps,
numeric bounds, recursion). Specs are a list of `{name, value}` pairs for that reason.
`app/schema.py` tightens the Pydantic schema (all properties required, `additionalProperties:
false`) so the same schema works with Claude structured outputs and OpenAI-style strict mode.

## The prompting loop

`services/designer.py`:

1. **Create:** system prompt + `<problem>` → `DesignUpdate` → revision 1.
2. **Refine:** system prompt + the last 10 chat turns + `<current_design>` JSON + `<request>` →
   `DesignUpdate` → revision n+1.
3. **Restore:** copies an old revision forward as a new revision (history is append-only).

The system prompt (`llm/prompts.py`) is byte-stable so Claude can cache it.

## LLM providers

`llm/base.py` defines one method: `structured(system, turns, output_model) -> output_model`.

| Provider | Use | Notes |
|---|---|---|
| `anthropic` | Default. Claude API | Streaming, adaptive thinking, structured outputs (JSON schema), prompt caching, server-side refusal fallback |
| `openai_compatible` | Private deployments: Ollama, vLLM, LM Studio, Azure OpenAI | JSON-schema response format, one retry with the validation error |
| `mock` | Tests, demos without a key | Keyword-based demo engine, understands "add vision inspection" |

See [ai-providers.md](ai-providers.md) for private / on-premise options.

## Supplier connectors

`suppliers/base.py` defines `search(part) -> list[Offer]`. A connector is enabled only when its
credentials are set. Results are cached in SQLite (`MF_OFFER_CACHE_HOURS`, default 24h) because
distributor APIs have daily quotas. See [suppliers.md](suppliers.md).

## Extending

- **New connector:** add `suppliers/<name>.py` with a class exposing `name`, `label`, `search()`;
  register it in `suppliers/__init__.py` (`make_connectors` and `connector_status`); add a test
  with a recorded payload (see `tests/test_connectors.py`).
- **New LLM provider:** implement `structured()`, register it in `llm/__init__.py`.
- **New output (3D, PLC, docs…):** add `services/<output>.py` that takes a `MachineDesign` and
  returns the artifact, plus an endpoint `GET /api/projects/{id}/<output>?revision=n`. If it needs
  new fields (e.g. station envelopes for 3D), add them to the model with defaults so old revisions
  still load.

## Storage

SQLite at `backend/data/machine-forge.db` (git-ignored). It is fine for one user or a small team.
For a shared server, move to Postgres. The `Storage` class is the only code that touches SQL.
