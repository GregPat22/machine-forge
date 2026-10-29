# Architecture

```
frontend (React + Vite)  ──/api──>  backend (FastAPI)
                                      ├── Designer      prompting loop, repair loop, model editor, revisions
                                      │     ├── LLMProvider  anthropic | openai | gemini | openai_compatible | mock
                                      │     └── patch     patch operations -> checked new design, or errors
                                      ├── diff          revision a vs b -> stations, components, transports, steps changed
                                      ├── layout        design -> layout (boxes, flow line) -> drawing (SVG/DXF)
                                      ├── documents     design -> technical description (+ .docx / .md, company template)
                                      ├── io_points     design -> estimated I/O points (documents, PLC)
                                      ├── plc           design -> Structured Text + PLCopen XML
                                      ├── rfq           catalog x price list -> RFQ workbook
                                      ├── spare_parts   design -> aggregated catalog (BOM)
                                      ├── Sourcing      catalog x (your price list + connectors) -> comparison
                                      │     └── SupplierConnector  mouser | nexar | ...
                                      ├── project_json  project <-> versioned JSON file (export/import)
                                      └── Storage       SQLite: projects, revisions, chat, price list, offer cache
```

## The machine model is the source of truth

`backend/app/models.py` → `MachineDesign` (schema version 2). The AI never edits text documents
or files, and since Phase 1 it no longer rewrites the design either: it answers with a list of
patch operations (see "The prompting loop"). Everything else is derived from the design in code:

- the spare-parts catalog (`services/spare_parts.py`), where identical part numbers across stations
  are merged;
- the supplier comparison (`services/sourcing.py`);
- the 3D concept layout (`services/layout.py`): the AI proposes station envelopes and the layout
  style; positions are computed in code, since language models are unreliable with coordinates;
- the technical documents (`services/documents.py`): rule-based, so they stay consistent with the
  design and never claim compliance;
- the I/O list (`services/io_points.py`) and the PLC skeleton (`services/plc.py`), from each
  component's `signals`, never from its name (ADR 0015).

What the model holds (v2):

- **Product**: dimensions, mass, orientation, lanes, pitch. The v1 text (`description`,
  `target_rate_text`) is kept for display and never parsed.
- **Process graph**: `transports` are the edges between stations (belt, indexing, rotary,
  pick-and-place, gravity), with length, speed or index time, buffer and an optional reject branch.
- **Station**: envelope, `parameters` (name/value/unit list), `mechanisms` (linear or rotary axes),
  ordered `steps` (a motion of an axis or a fixed duration), `target_cycle_time_s`, components.
- **Component**: structured `role`, `signals` (DI/DO/AI/AO/axes/fieldbus counts), `motion` link to
  a mechanism.
- **Derived values** (ADR 0012): `Station.sequence` (position along the process graph) and
  `Station.cycle_time_s` (sum of fixed-duration steps, null when a step is a motion or runs in
  parallel) are plain Python properties. They are not stored, not sent to the AI and cannot be
  set by a patch; current readers, including the frozen `plc.py`, read them unchanged.

Every revision is a complete snapshot: you can view, diff or restore any of them. Ids are kept
stable across revisions (patches refer to them), so revisions can be compared item by item.

Old revisions are migrated on read (`migrations/design_v1.py`, `migrate_design`): `sequence`
becomes a chain of belt transports, `cycle_time_s` one fixed-duration step, each `category` a
`role`; nothing unknown is guessed. A stored row keeps its `schema_version` until a new revision
is saved, which is always version 2.

The model avoids JSON-schema features that strict structured-output modes reject (free-form maps,
numeric bounds, recursion). Specs and parameters are lists of `{name, value}` pairs for that
reason, and bounds are checked in code by the patch validator. `app/schema.py` tightens the
Pydantic schema (all properties required, `additionalProperties: false`).

## Live progress

`POST /api/projects/stream` and `POST /api/projects/{id}/prompt/stream` return server-sent events:
`progress` (phase `waiting` / `thinking` / `writing`, characters, stations and components written so
far, the latest line of the model's thinking summary), then one `done` (the project) or `error`.
The design call runs in a worker thread; the Claude provider reports from the stream deltas. The
frontend reads the stream with `fetch` (`streamDesign` in `src/api.ts`).

## 3D view

`components/Layout3D.tsx` renders the layout boxes from `services/layout.py` as labelled blocks.
The v0.3 procedural "realistic render" was removed in Phase 0 (ADR 0009): geometry becomes
backend data (scene JSON) in Phase 4, and the frontend only renders it.

## Frozen modules

Supplier connectors (`suppliers/`), supplier ratings, RFQ workbooks (`services/rfq.py`) and the
PLC skeleton (`services/plc.py`) are frozen: bug fixes only, no new work, until a phase spec
reopens them. See `docs/PLAN.md` section 2.

## The prompting loop

`services/designer.py`:

1. **Create:** system prompt + `<problem>` → `PatchUpdate` (reply + patches), applied to an empty
   design → revision 1.
2. **Refine:** system prompt + the last 10 chat turns + `<current_design>` JSON + `<request>` →
   `PatchUpdate`, applied to the latest design → revision n+1.
3. **Restore:** copies an old revision forward as a new revision (history is append-only). No AI
   call.
4. **Model editor:** `POST /api/projects/{id}/patches` with `expected_revision` and a list of
   patches → the same validator, no AI call → revision n+1 (ADR 0024).

`services/patch.py` (ADR 0013) applies the patches in order on a copy, all or nothing. Each
operation (`add_station`, `set_param`, `connect`, `add_step`, ...) is one flat `PatchOp` with an
`op` name and nullable operands. Bounds (mass > 0, lanes ≥ 1, `reject_rate` in [0, 1], ...),
references, unique ids and an acyclic graph are checked in code; a failure is a
`PatchError(index, code, message)` with a fixed code (`unknown_station`, `invalid_value`,
`computed_field`, `graph_cycle`, ...). Values the software computes (`sequence`, `cycle_time_s`,
placement, motion step durations) are rejected as `computed_field`.

**Repair loop.** Rejected patches go back to the AI as the next turn, up to
`MF_MAX_REPAIR_ATTEMPTS` answers in total (default 3), each attempt logged. After the last one the
user gets a readable error and the design is unchanged. The model editor gets the errors back
directly (HTTP 400, nothing saved).

**Stale saves.** A refine, restore or editor save states the revision it was prepared against.
If another write got there first, nothing is saved and the API answers 409 with a reload message.

The system prompt (`llm/prompts.py`) is byte-stable so Claude can cache it.

## LLM providers

`llm/base.py` defines one method, `structured(system, turns, output) -> output`, and three
capability flags per provider: `strict_schema`, `tools`, `thinking`. Correctness never depends on
them (D6, ADR 0014): every answer is parsed and validated by our code, unknown keys rejected, and a
wrong shape goes back to the model once more before the patch validator checks what it means.

| Provider | Use | Notes |
|---|---|---|
| `anthropic` | Default. Claude API | Streaming, adaptive thinking, schema sent in the prompt (too large for Claude strict mode), prompt caching, server-side refusal fallback |
| `openai` | OpenAI, Responses API | Strict JSON schema, `store: false` |
| `gemini` | Google Gemini | JSON mode, schema sent in the prompt |
| `openai_compatible` | Private deployments: Ollama, vLLM, LM Studio, Azure OpenAI | JSON-schema response format |
| `mock` | Tests, demos without a key | Fixed demo machine picked by `MF_MOCK_SCENARIO` (default blister); never reads your text, each request applies its next scripted edit through the same validator |

See [ai-providers.md](ai-providers.md) for private / on-premise options.

## Supplier connectors

`suppliers/base.py` defines `search(part) -> list[Offer]`. A connector is enabled only when its
credentials are set. Results are cached in SQLite (`MF_OFFER_CACHE_HOURS`, default 24h) because
distributor APIs have daily quotas. See [suppliers.md](suppliers.md).

## Extending

- **New connector:** add `suppliers/<name>.py` with a class exposing `name`, `label`, `search()`;
  register it in `suppliers/__init__.py` (`make_connectors` and `connector_status`); add a test
  with a recorded payload (see `tests/test_connectors.py`).
- **New LLM provider:** implement `structured()` and the three capability flags, register it in
  `llm/__init__.py`, and add a test with a recorded payload (see `tests/test_llm_providers.py`).
- **New output (3D, PLC, docs…):** add `services/<output>.py` that takes a `MachineDesign` and
  returns the artifact, plus an endpoint `GET /api/projects/{id}/<output>?revision=n`. If it needs
  new fields, add them to the model with defaults so old revisions still load, a migration step and
  a `schema_version` bump (rule 7).

## Storage

SQLite at `backend/data/machine-forge.db` (git-ignored). It is fine for one user or a small team.
For a shared server, move to Postgres. The `Storage` class is the only code that touches SQL.

## Project JSON export and import

`GET /api/projects/{id}/export` returns the project, every revision (designs at the current
schema version) and the chat messages as one JSON file (`format: "machine-forge-project"`,
`format_version: 1`). `POST /api/projects/import` takes that file as the request body, checks its
size (`MF_MAX_IMPORT_MB`, default 20) and versions, migrates designs written with an older
`schema_version`, and always creates a new project. A bad file changes nothing. Code:
`services/project_json.py`. Own format only.
