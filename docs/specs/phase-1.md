# Phase 1: model v2 and patch-based AI edits

Status: **not started** (spec written 2026-10-25). Plan reference: `docs/PLAN.md` section 4
("Model v2") and section 5, Phase 1. Process rules: `docs/workflow.md`.

## Goal

A model that can carry simulation data, and an AI loop that edits it safely. Today the AI
rewrites the whole `MachineDesign` on every turn and a station has only an envelope, an integer
`sequence` and one `cycle_time_s`. After this phase the AI sends small edits (patches), code
validates every one, and bad edits come back to the AI as precise errors instead of silently
corrupting the design. Nothing is computed from the new fields yet; that starts in Phase 2.

## Current state (verified 2026-10-25)

- `backend/app/models.py` (232 lines): `Component`, `Station`, `MachineDesign`, `DesignUpdate`
  (reply + full design), `Revision.schema_version` (default 1, column exists since Phase 0).
- `backend/app/services/designer.py`: `create`, `refine`, `restore`; each makes one
  `provider.structured(...)` call returning a full `DesignUpdate`.
- Providers in `backend/app/llm/`: `anthropic_provider.py`, `openai_compatible.py`, `mock.py`
  (316 lines), `base.py` (the `LLMProvider` protocol), `prompts.py`. No native OpenAI or Gemini.
- `backend/app/schema.py`: `strict_schema()` strips unsupported keys and closes objects.
- Consumers of the design that must keep working: `layout.py`, `documents.py`, `io_points.py`,
  `drawing.py`, `diff.py`, `spare_parts.py`, `plc.py` (frozen), `sourcing.py` (frozen).

## Scope (exact)

### A. Model v2 (`backend/app/models.py`)

Pydantic, strict-schema compatible: no free dicts, no recursion, no numeric bounds in the
schema (bounds are enforced in code, section C). Every new field has a default.

- **Product**: name, length/width/height (mm), mass (g), orientation (enum), lanes (int),
  pitch (mm, optional). Replaces the free-text `product` and `throughput` strings; the old
  strings stay as `description` and `target_rate_text` fields (display only, never parsed).
- **Process graph**: `Transport` edges (`id`, `from_station`, `to_station`, `kind` enum:
  belt / indexing / rotary / pick_place / gravity, `length_mm`, `speed_mm_s` or
  `index_time_s`, `buffer_capacity`, `products_per_move`) and an optional reject branch
  (`reject_to`, `reject_rate`). Replaces the stored `sequence` (it becomes a derived value,
  below). Parallel lanes are expressed with
  `Product.lanes`, merges and splits with several edges.
- **Station**: keeps `id`, `name`, `kind`, `function`, envelope fields, `components`. Adds
  `library_ref` (null = custom), `parameters` (list of name/value/unit entries, not a dict),
  `mechanisms`, `steps`, `target_cycle_time_s`, `placement` (x, y, rotation; null until Phase 4).
- **Derived read-only values** (ADR 0012). `Station.sequence` and `Station.cycle_time_s` keep
  their names so every current reader, including the frozen `plc.py`, works with no edit. They
  are no longer stored fields: they are plain Python properties computed from the model.
  - `sequence`: the station's position along the process graph (1, 2, ... from the entry
    station); 0 for stations outside the graph.
  - `cycle_time_s`: in Phase 1, the sum of the station's steps when every step is
    `fixed_duration` and none has a `parallel_group`; null otherwise (motion steps have no
    duration until the Phase 2 timing engine). After migration it equals the v1 value.
  - They are not stored, not in the JSON schema sent to the AI, not in `model_dump()` (so not
    in `<current_design>` either), and cannot be set by a patch. Use a plain `@property`, not
    Pydantic `computed_field`, which would serialize them.
  - No adapter in `plc.py` and no second stored copy of either value.
- **Mechanism**: `id`, `kind` (linear / rotary), `stroke` (mm or deg), `max_speed`,
  `acceleration`, optional `cam_profile` reference (text id, unused until later), `dwell_s`.
- **Step**: `id`, `order`, `kind` (motion / fixed_duration), `mechanism_id` or `duration_s`,
  `parallel_group` (int or null). Ordered operations of a station.
- **Component**: adds structured `role` enum (actuator, sensor, drive, controller, tooling,
  structure, consumable), `signals` (di, do, ai, ao, axes, fieldbus counts), `motion` (a
  `mechanism_id` link or null). `category` stays so existing consumers keep working.
- **MachineDesign v2**: product, `transports`, stations, utilities, assumptions, open
  questions, `schema_version = 2`. Results from engines are not stored here; they get their
  own place in Phases 2 and 3.
- Rule 1 holds: nothing reads `.name`, `.function` or other free text to decide behaviour.
  Existing regex-on-name code in `io_points.py` and the layout/documents consumers is
  migrated to read `role`, `signals`, `motion` in step 3 (Order of work) and left alone where
  it is in a frozen module (see Out of scope).

### B. Migration v1 to v2

- Keep the v1 shape as `MachineDesignV1` in `backend/app/migrations/design_v1.py`, used only to
  load old revisions.
- `migrate_design(raw: dict, from_version: int) -> MachineDesign`. `sequence` becomes a linear
  chain of belt `Transport`s in order (infrastructure stations, `sequence` 0, get no transport).
  `cycle_time_s` becomes one fixed-duration `Step` and `target_cycle_time_s`. Each `category`
  maps to a `role`. Envelopes carry over. `throughput` and `product` text move to the new text
  fields. Unknown or missing data stays null; nothing is guessed.
- Migration runs on read in `Storage`. Rows are not rewritten in bulk; a revision keeps its
  stored `schema_version` until a new revision is saved (always version 2 from then on).
- v1 fields survive a round trip: migrating and exporting back loses none of the v1 data
  (the extra v2 fields are additive).

### C. Patch operations and validator (`backend/app/services/patch.py`)

- `PatchOp`: one flat, strict-schema-friendly model with an `op` enum and nullable operand
  fields (a flat shape is used instead of a tagged union because it is accepted by every
  structured-output mode; this is recorded in ADR 0013). Operations: `add_station`,
  `remove_station`, `set_param`, `add_component`, `remove_component`, `replace_component`,
  `add_mechanism`, `set_mechanism`, `add_step`, `remove_step`, `connect`, `disconnect`,
  `set_product`, `set_utility`, `add_assumption`, `add_open_question`.
- `PatchUpdate` replaces `DesignUpdate` as the AI's answer: `reply` plus `patches: list[PatchOp]`.
  The first turn is the same call applied to an empty design.
- `apply_patches(design, patches) -> PatchResult`: applies in order on a copy, returns the new
  design, or a list of `PatchError(index, code, message)`. All-or-nothing: if any op fails,
  the design is unchanged and every error is reported.
- Error codes (fixed, documented in the module): `unknown_station`, `unknown_component`,
  `unknown_mechanism`, `duplicate_id`, `missing_operand`, `invalid_value` (with the bound named),
  `computed_field` (the AI tried to set a computed or result field, rule 3), `graph_cycle`,
  `orphan_transport`, `unknown_op`.
- Bounds are code, not schema: e.g. mass > 0, lanes >= 1, `reject_rate` in [0, 1], speeds and
  acceleration > 0, ids unique and slug-shaped. Messages say which value, which limit.
- The AI never edits: `sequence`, `cycle_time_s` (derived, section A), `placement`, any
  stored result (rule 3).
- A **repair loop** in `services/designer.py`: validation errors go back to the model as the
  next turn; up to `MF_MAX_REPAIR_ATTEMPTS` attempts (default 3), each attempt logged. After
  the last failure the user gets a readable message and the design is unchanged.

### D. Prompts (`backend/app/llm/prompts.py`)

Rewritten for patches. The AI proposes structure, parameters, components, mechanisms,
assumptions and reasons. It never writes coordinates, durations that can be computed, rates, or
results. When it does not know a domain value it leaves the field null and adds an open
question; it does not invent numbers.

### E. Project JSON export/import

- `GET /api/projects/{id}/export` returns a versioned JSON (`format: "machine-forge-project"`,
  `format_version: 1`, project, all revisions, messages). `POST /api/projects/import` accepts it.
- Import validates size (limit configurable, default 20 MB) and `format_version`, migrates
  designs from older `schema_version`, and creates a new project (never overwrites).
- Own format only. No third-party formats in this phase.

### F. Providers

- Capability flags on the `LLMProvider` protocol: `strict_schema`, `tools`, `thinking` (bool).
- Native **OpenAI** (Responses API) and native **Google Gemini** providers, plus the existing
  Anthropic and OpenAI-compatible ones updated to the flags.
- Shared validate-and-repair loop for providers where `strict_schema` is false: the JSON is
  parsed and validated by Pydantic, failures return to the model as errors. Correctness never
  depends on strict mode or tool use (decision D6).
- `MockProvider` rewritten to emit v2 patches for the demo machines. No shortcuts that only
  work for the demo prompts: it goes through the same validator as a real provider.
- The mock picks its demo machine from an explicit scenario id (`MF_MOCK_SCENARIO`, or an id
  sent by the demo button), default `blister`. It never reads the problem or request text to
  choose (this closes the `mock.py` items in `docs/parking-lot.md`).

### G. Frontend

- `frontend/src/types.ts` mirrors v2.
- A structured **model editor** next to the chat: station list, parameters, mechanisms, steps,
  components, transports. Edits go through the same patch endpoint and validator as the AI
  (`POST /api/projects/{id}/patches`), so the editor creates revisions like a chat turn does.
- Existing tabs (layout, documents, parts, sourcing, diff) keep working on migrated designs.
- Revision diff shows added/removed/changed stations, transports and parameters, not only BOM.

## Out of scope

- Any engine (timing, throughput), any 3D or viewer change, the module library, imports other
  than project JSON, and anything in Phase 2 onward.
- Frozen modules (`app/suppliers/`, `services/rfq.py`, `services/plc.py`,
  `services/sourcing.py`, supplier ratings): no changes and no adapters. The derived
  `sequence` and `cycle_time_s` (section A, ADR 0012) keep them reading a v2 design. If they
  still cannot, stop and report.
- Cam synthesis, collision, optimisation, authentication, multi-user.

## Tests to add

All offline: no network, no keys (rule 6). Names are expectations; agents may adjust only with
a line in the report.

**Migration (`backend/tests/test_migration_v2.py`)**
- `test_v1_fixture_revisions_migrate_to_v2`: every fixture revision (mock outputs and the v0.3
  database built in `test_migration.py`) migrates and validates.
- `test_v1_to_v2_round_trip_keeps_all_v1_fields`.
- `test_sequence_becomes_linear_transport_chain` and `test_cycle_time_becomes_fixed_step`.
- `test_old_database_opens_after_phase_1` (rule 7: a committed old-database fixture is added
  here, closing the parking-lot item).

**Derived values (`backend/tests/test_models_v2.py`, step 1)**
- `test_sequence_is_derived_from_the_process_graph`
- `test_cycle_time_s_is_derived_from_fixed_steps_and_null_with_motion_or_parallel_steps`
- `test_derived_values_are_not_stored_dumped_or_in_the_ai_schema`: absent from `model_dump()`,
  from the stored revision JSON and from `strict_schema(PatchUpdate)`.
- Not a new test, a requirement for step 1: the current `test_plc.py`, `test_layout.py`,
  `test_documents.py` and `test_diff_and_drawing.py` pass with no edit to their expectations.

**Consumers on structured fields (`backend/tests/test_io_points.py`, step 3)**
- `test_io_points_follow_role_signals_and_motion`
- `test_renaming_a_component_does_not_change_io_points` (rule 1), then one rename test per
  other service the step moves.

**Mock (`backend/tests/test_mock_provider.py`, step 4)**
- `test_mock_picks_the_machine_from_the_scenario_id_default_blister`
- `test_mock_ignores_problem_and_request_text`: two different texts, same scenario, same patches.

**Patches (`backend/tests/test_patch.py`)**
- Property tests (Hypothesis): random valid designs stay valid after random valid patch
  sequences; random invalid patches are rejected with the expected error code and leave the
  design unchanged.
- One test per error code with a minimal example and exact message check.
- `test_computed_fields_cannot_be_set_by_patch` (rule 3).
- `test_apply_is_all_or_nothing`.

**Repair loop (`backend/tests/test_repair_loop.py`)**
- A scripted provider returns two invalid answers then a valid one: the design ends valid and
  three attempts are logged. A provider that never recovers: user-readable error, design
  unchanged, attempts stop at the configured maximum.

**Schema compatibility (`backend/tests/test_schema_compat.py`)**
- `strict_schema(PatchUpdate)` has no free dicts, no recursion, no numeric bounds, every object
  closed. Recorded request fixtures are accepted by Anthropic strict, OpenAI strict and a plain
  JSON-mode validator via `MockTransport`.

**Providers (`backend/tests/test_llm_providers.py`)**
- Recorded payloads for OpenAI Responses and Gemini; capability flags reported correctly;
  non-strict provider goes through the repair path.

**Export/import (`backend/tests/test_project_json.py`)**
- Export then import reproduces designs and revisions; oversized and wrong-version files are
  rejected with clear errors; importing a v1-era export migrates.

**Repo rules (`backend/tests/test_repo_rules.py`)**
- New: a frozen-paths guard. It lists `app/suppliers/`, `services/rfq.py`, `services/plc.py`,
  `services/sourcing.py` and fails when their content differs from a committed hash manifest.
  The manifest may be updated only with a stated reason in the step's report.
- New: fails if a backend or frontend file branches on `.name` of a station, component or
  design (grep with an allowlist for display-only use).

**Frontend**
- `npm run build` passes. Playwright smoke test (`frontend/e2e/model-editor.spec.ts`): create a
  demo project with the mock provider, edit a station parameter in the editor, see a new
  revision and the changed value after reload.

## Order of work and parallelism

Steps are independent branches, one agent each, stopping with a report after each (see
`docs/workflow.md`). Model files are touched by one agent at a time.

1. **Schema and migration** (A, B), including the derived `sequence` and `cycle_time_s`, so the
   existing services keep working with no edits. First. Everything else waits for it. Opus, high.
2. **Patch validator and repair loop** (C). Needs step 1. Opus, high. Heaviest audit.
3. **Services on structured fields.** Moves the services that read the design to `role`,
   `signals` and `motion`: `io_points.py` first (it matches on component names, rule 1), then
   `layout.py`, `documents.py`, `drawing.py`, `diff.py`, `spare_parts.py`. One agent for the
   whole step, since all of them read the same model. Frozen modules are not touched. Needs
   step 2; can run in parallel with steps 4, 5 and 6 (different files).
4. **Prompts and MockProvider** (D, part of F). Needs step 2.
5. **Providers and capability flags** (rest of F). Needs step 2; can run in parallel with step 4
   (different files: `llm/openai_*`, `llm/gemini_*`, `base.py` flags vs `prompts.py`, `mock.py`).
6. **Project JSON export/import** (E). Needs step 1; can run in parallel with steps 3, 4 and 5.
7. **Frontend types and model editor** (G). Needs steps 2, 3 (the revision diff reads
   `diff.py`) and 6 on the API side. Last.
8. **Docs**: README roadmap, `docs/architecture.md`, ADR 0013, parking-lot update.

## Open questions for Greg (answer before step 1 starts)

1. Product orientation and carrier/pitch: are the fields in section A enough for the first
   mock machines (blister, cartoner), or should anything else be modelled now?
2. Should the model editor be able to add and remove stations, or only edit values in this
   phase? (Default in this spec: both, through patches.)
3. `MF_MAX_REPAIR_ATTEMPTS` default 3: acceptable cost in tokens per turn?
4. `sequence` and `cycle_time_s` are read today by `services/plc.py` (frozen, line 230 reads
   `station.cycle_time_s`) and by `layout.py`, `drawing.py`, `documents.py`, `io_points.py`,
   `spare_parts.py` and `diff.py` (`sequence`). Section A replaces both. Either keep `sequence`
   as a field computed by code from the transports and `cycle_time_s` as the target, so no
   frozen file changes, or add the smallest adapter in `plc.py` (section "Out of scope").
   **Answer (Greg, 2026-10-25):** keep both names as read-only values derived from the new
   model: `sequence` from the process graph, `cycle_time_s` from the station's steps. The AI
   never sees or writes them and they are not stored. No adapter in `plc.py`, no second stored
   copy of the same fact. Recorded in ADR 0012 and section A.
5. How does `MockProvider` choose a demo machine without reading the problem text? Today it
   uses `"blister" in problem.lower()` (`docs/parking-lot.md`). Options: an `MF_MOCK_SCENARIO`
   environment variable, or a scenario field on the create request.
   **Answer (Greg, 2026-10-25):** an explicit scenario id (`MF_MOCK_SCENARIO=blister` or an id
   sent by the demo button), default blister. Matching on text is a hidden shortcut. Section F.
6. Which step owns the consumer changes (`io_points.py` to `role`/`signals`/`motion`,
   `layout.py`, `documents.py`, `drawing.py`, `diff.py`, `spare_parts.py`)? Step 1 has to keep
   them working on v2; the `io_points.py` rewrite could be its own step after step 1.
   **Answer (Greg, 2026-10-25):** split it. Step 1 owns the derived values, so the services
   keep working with no edits. A new step 3 moves them to the structured fields, `io_points.py`
   first (rule 1), with a single agent. See "Order of work".

## Done criteria

- `cd backend && .venv/bin/pytest -q` green, `cd frontend && npm run build` green, CI green.
- A v0.3 project opens as v2, the chat produces patches, the editor edits the same model, and a
  prompt asking for something impossible (for example a negative lane count) returns a readable
  error instead of a silent bad design. Greg checks this in the running app.
- Reports and audit verdicts exist for every step (`docs/workflow.md`).
- ADR 0013 records the flat patch-operation shape. README and architecture docs describe v2.

## Agent brief

Schema first, tests second, prompts third. Keep `MockProvider` honest. Use `TODO(source)` for
any domain value you cannot cite; never invent engineering numbers. No "while we are here"
changes.
