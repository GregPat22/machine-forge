# Phase 1: model v2 and patch-based AI edits

Status: **draft, waiting for Greg's approval** (written 2026-10-25). Plan reference:
`docs/PLAN.md` section 5, Phase 1, and section 4, "Model v2". Phase 0 is done (see
`docs/specs/phase-0.md`).

## Goal

A schema that can carry simulation, and an AI loop that edits it safely. After this phase the AI
no longer rewrites the whole design: it returns a list of patch operations, code validates and
applies them, and engineers can make the same edits by hand in a structured editor.

## Scope (exact)

1. **Model v2** (`backend/app/models.py`, mirrored in `frontend/src/types.ts`). Pydantic,
   strict-schema compatible: no free-form dicts, no numeric bounds, no recursion. Bounds are
   enforced in code with clear messages. Every new field has a default so old revisions load.
   - `Product`: name, dimensions (mm), mass (g), orientation, lanes, carrier/pitch.
   - Process graph: stations are nodes, `Transport` edges carry type (belt, indexing, rotary,
     pick_place, gravity), length, speed or index time, capacity, products per move. Reject
     branch and lane merge are representable (edge kind), not simulated.
   - `Station`: keeps `id`, `name`, `kind`, `function`, envelope (`length_mm`, `width_mm`,
     `height_mm`), `components`; adds `parameters`, `mechanisms` (axes: linear or rotary, stroke,
     max speed, acceleration, dwell), `steps` (ordered; each either a motion of an axis or a
     fixed-duration process, with a parallel-group label), and an optional user-only
     `placement` (stored, unused until Phase 4). `cycle_time_s` stays and means the target
     cycle time; `sequence` stays as a field computed by code from the graph (open question 1).
   - `Component`: keeps the current fields; adds structured `role` (actuator, sensor, drive,
     controller, tooling, structure, consumable), `signals` (DI/DO/AI/AO/axis/fieldbus counts)
     and `motion` (id of a mechanism of the same station, or null). `category` stays.
   - `MachineDesign`: adds `product` as a `Product` object (the v1 string moves to
     `Product.name`), the process graph, and `schema_version = 2`.
   - Not in this phase: stored simulation results and computed cycle times. They arrive with
     the engines (Phases 2 and 3), each with its own `schema_version` bump.
2. **Migration v1 to v2.** A pure function `migrate_design(v1) -> v2` in `app/migrations.py`.
   - `sequence` becomes a linear graph in sequence order with default belt transports;
     infrastructure stations (`sequence` 0) stay outside the graph.
   - `cycle_time_s` becomes one fixed-duration step and is kept as the target cycle time.
   - `category` maps to `role` and default `signals` through a static table keyed on the
     category enum, never on names (rule 1).
   - Envelopes are carried over unchanged.
   - Applied on read for revisions with `schema_version < 2`; stored rows are not rewritten
     (history stays append-only). New revisions are written with `schema_version = 2`.
     The `schema_version` column already exists (Phase 0), so no column is added.
3. **Patch operations and validator** (`backend/app/services/patch.py`).
   - Operations: `set_product`, `add_station`, `remove_station`, `update_station`,
     `set_param`, `add_component`, `replace_component`, `remove_component`, `add_mechanism`,
     `add_step`, `connect`, `disconnect`, `add_assumption`, `add_open_question`. The final list
     is fixed in step 2 and recorded in this file.
   - Wire shape for strict schemas: one flat `PatchOp` model with an `op` literal and nullable
     payload fields; code checks which fields each `op` requires.
   - `apply_patch(design, ops) -> PatchResult` is atomic: all operations apply or none do.
     Errors are structured: `code`, `op_index`, `path`, `message`.
   - Error codes: `unknown_op`, `missing_field`, `forbidden_field`, `unknown_station`,
     `unknown_component`, `unknown_mechanism`, `duplicate_id`, `dangling_edge`,
     `graph_cycle`, `out_of_range`.
   - `forbidden_field`: operations that set coordinates, `placement`, `sequence`, or any
     computed or result field are rejected (rule 3). `sequence` is recomputed by code from the
     graph; the AI and the editor never write it.
   - The first design of a project is built by applying patches to an empty design, so create
     and refine share one path.
4. **Retry loop.** `backend/app/llm/repair.py`: `run_with_repair(call, validate, max_attempts)`.
   The model gets the structured errors and tries again, up to `MF_PATCH_MAX_ATTEMPTS`
   (default 3). Each attempt is logged (attempt number, error codes). On exhaustion the API
   returns 422 with the structured errors and **no revision is stored**. The same loop is the
   validate-and-repair path for providers without strict schema.
5. **Prompts rewritten** (`backend/app/llm/prompts.py`). The AI returns `reply` plus
   `patch` (a list of `PatchOp`), not a full design. `DesignUpdate` changes accordingly. The
   prompt states that the AI never writes coordinates, durations that can be computed, rates,
   dimensions derived from geometry, compliance statements or results; it proposes structure,
   parameters, components, assumptions and reasons. The streaming progress estimate
   (`progress_from_text`) counts patch operations instead of `"function"` and `"category"`.
6. **Project JSON export/import** (`backend/app/services/project_json.py`, two API routes).
   Own versioned format: `{"format": "machine-forge-project", "format_version": 1, ...}` with
   the project, revisions and messages. Import is an untrusted input (rule 11): size limit,
   strict validation, never executed, older `schema_version` revisions migrated.
7. **MockProvider** (`backend/app/llm/mock.py`) rewritten to emit v2 patches for the demo
   machines. It is driven by an explicit scenario key and structured fields only. It must not
   read `problem` or `request` text with keywords or regex (this closes the three `mock.py`
   items in `docs/parking-lot.md`). An unknown scenario returns an empty patch and a reply that
   says so.
8. **I/O points from structured fields** (`backend/app/services/io_points.py`). `signals()`
   reads `role`, `signals` and `motion`, not `component.name` or spec text (parking-lot item
   "Phase 1 item"). `services/plc.py` is not edited; its tests must stay green unchanged.
9. **Consumers adapted, nothing more.** `spare_parts.py`, `layout.py`, `drawing.py`,
   `documents.py` and `diff.py` change only as far as needed to keep working on v2 (including
   the diff of the new station fields). No new behaviour in them.
10. **Frontend.** `src/types.ts` mirrors v2. A structured model editor (station list,
    parameters, mechanisms, steps, components) sits next to the chat. Editor changes go through
    the same patch validator as the AI (`POST /api/projects/{id}/patch`) and create a revision.
    Project JSON export/import buttons. Chat shows structured errors readably.
11. **Providers.**
    - Native OpenAI (Responses API) and Google Gemini providers.
    - Capability flags on every provider: `strict_schema`, `tools`, `thinking`.
    - Providers without `strict_schema` use the shared repair loop of item 4.
    - `make_provider` and `docs/ai-providers.md` updated.

## Out of scope

Engines (timing, throughput, layout v2, scene), 3D and the viewer, the module library, imports
(STEP, Excel, AutomationML), AI tools and the what-if loop, anything from Phase 2 onward. A
numeric `throughput_per_min` field (the `documents.py` regex stays, see the parking lot). Stored
results. Any change under `app/suppliers/`, `services/rfq.py`, `services/plc.py`,
`services/sourcing.py` or supplier ratings; the only exception is a change the migration
strictly requires, which must be stopped and reported first. No new field in `Project` or
`Revision` beyond what item 2 states.

## Work order

Strictly one agent per file; never two agents on `models.py`. Each step ends with its tests
green and a report to Greg. Implementation order follows PLAN section 8: schema, then
service with tests, then API, then frontend.

| Step | Work | Owns | Starts after |
|---|---|---|---|
| 1 | Model v2, `migrations.py`, `types.ts`, v1 fixtures, schema tests | `models.py`, `schema.py`, `migrations.py`, `storage.py`, `types.ts`, `tests/fixtures/v1/` | nothing |
| 2 | Patch operations, validator, Hypothesis tests | `services/patch.py` | 1 |
| 3 | Project JSON export/import | `services/project_json.py`, its routes | 1 |
| 4 | I/O points from structured fields, consumer adaptations | `services/io_points.py`, `spare_parts.py`, `layout.py`, `drawing.py`, `documents.py`, `diff.py` | 1 |
| 5 | Native OpenAI and Gemini, capability flags, schema compatibility fixtures | `llm/openai_provider.py`, `llm/gemini_provider.py`, `llm/base.py`, `llm/__init__.py` | 1 |
| 6 | Repair loop | `llm/repair.py` | 2 |
| 7 | Prompts, `DesignUpdate`, designer, MockProvider | `llm/prompts.py`, `services/designer.py`, `llm/mock.py` | 2 and 6 |
| 8 | API routes for patch and errors, model editor, Playwright smoke | `api/`, `frontend/src/` | 3 and 7 |

Parallel after step 1: steps 2, 3, 4 and 5 touch different files and can run at the same time.
Waiting: 6 waits for 2 (it needs the error type), 7 waits for 2 and 6, 8 waits for 3 and 7.
Step 1 is the only blocking one, so it is done first and merged alone. Each step is its own PR
(rule 10).

Step 1 must keep the v1 consumers working (compatibility fields, see open question 1) so the
suite stays green between PRs. Because step 1 changes `models.py`, the agent presents the
field-level plan and waits for Greg's approval before editing.

## Tests to add

All tests run offline (rule 6). Names are fixed; assertions are what the name says.

**Step 1** (`backend/tests/test_models_v2.py`, `backend/tests/test_migration_v2.py`)
- `test_schema_has_no_free_dicts_bounds_or_recursion`: walks the JSON schema of `DesignUpdate`.
- `test_v1_design_json_validates_as_v2_with_defaults`: every new field has a default.
- `test_every_v1_fixture_migrates_and_round_trips`: fixtures in `tests/fixtures/v1/*.json`
  are the output of the current MockProvider, captured before step 1 changes anything
  (synthetic, no confidential data). Every v1 field survives migrate, dump, load.
- `test_sequence_becomes_linear_graph_with_belt_transports`
- `test_infrastructure_stations_stay_outside_the_graph`
- `test_cycle_time_becomes_one_fixed_duration_step`
- `test_categories_map_to_roles_by_enum_not_name`: renaming a component does not change role.
- `test_envelopes_are_carried_over`
- `test_migration_is_idempotent_on_v2_input`
- `test_v03_database_revisions_read_as_v2`: extends the v0.3 schema fixture of
  `test_migration.py`; stored rows are unchanged afterwards.
- `test_new_revisions_are_written_with_schema_version_2`

**Step 2** (`backend/tests/test_patch.py`, `backend/tests/test_patch_properties.py`)
- One happy-path and one error-path test per operation; the error path asserts the `code`.
- `test_patch_is_atomic`: a failing operation 3 of 5 leaves the design unchanged.
- `test_errors_carry_code_op_index_path_message`
- `test_patch_rejects_coordinates_placement_sequence_and_computed_fields`: `forbidden_field`.
- `test_sequence_is_recomputed_from_the_graph`
- Hypothesis: `test_valid_patches_keep_the_graph_valid` (random valid graphs, random valid
  patches: no dangling edge, no cycle, ids unique, every `motion` resolves).
- Hypothesis: `test_invalid_patches_are_rejected_with_the_expected_code` (one strategy per
  error code).

**Step 3** (`backend/tests/test_project_json.py`)
- `test_export_import_round_trip_preserves_revisions_and_messages`
- `test_import_rejects_unknown_format_and_newer_format_version`
- `test_import_rejects_oversized_file` and `test_import_rejects_malformed_file` (rule 11)
- `test_import_migrates_v1_revisions`

**Step 4** (`backend/tests/test_io_points.py`, `backend/tests/test_repo_rules.py`)
- `test_io_points_follow_role_signals_and_motion`
- `test_renaming_a_component_does_not_change_io_points` (rule 1)
- `test_io_points_does_not_read_display_names` in `test_repo_rules.py`: fails on `.name`,
  `.lower()` or regex in `io_points.py`.
- Existing `tests/test_plc.py`, `test_layout.py`, `test_documents.py` and
  `test_diff_and_drawing.py` pass; any change to their expectations is explained in the PR.

**Step 5** (`backend/tests/test_llm_providers.py` extended, `backend/tests/test_schema_compat.py`)
- `test_openai_provider_with_recorded_payload` and `test_gemini_provider_with_recorded_payload`
  (`httpx.MockTransport`, fixtures under `tests/fixtures/providers/`).
- `test_provider_capability_flags`: every provider declares `strict_schema`, `tools`, `thinking`.
- `test_schema_accepted_by_anthropic_strict_mode`, `test_schema_accepted_by_openai_strict_mode`,
  `test_schema_passes_plain_json_mode_validator`: recorded request and response pairs
  replayed offline, plus a local checker for the documented strict-mode rules (all properties
  required, `additionalProperties: false`, no unsupported keywords). Live acceptance is a
  separate optional job, not part of CI.

**Step 6** (`backend/tests/test_repair_loop.py`)
- `test_two_invalid_answers_then_valid_ends_with_valid_design`: scripted provider.
- `test_attempts_are_logged`
- `test_gives_up_after_max_attempts_with_structured_errors`
- `test_strict_schema_provider_and_repair_provider_reach_the_same_design`

**Step 7** (`backend/tests/test_mock_provider.py`, `backend/tests/test_designer.py`)
- `test_mock_emits_patches_not_full_designs`
- `test_mock_does_not_read_problem_or_request_text` (in `test_repo_rules.py`: no keyword or
  regex branch on `problem` or `request` in `mock.py`).
- `test_mock_scenarios_use_the_same_code_path`: two scenarios, no per-demo special cases.
- `test_unknown_scenario_returns_empty_patch_and_says_so`
- `test_impossible_request_returns_readable_error_and_stores_no_revision`: scripted provider
  keeps returning an invalid patch.
- `test_system_prompt_lists_what_the_ai_must_not_write`: guards against silent prompt edits;
  the real check is the review of prompt diffs against rule 3.

**Step 8** (`frontend/e2e/smoke.spec.ts`, backend API tests in `tests/test_api.py`)
- `test_patch_endpoint_applies_valid_and_returns_422_with_errors_for_invalid`
- `test_project_export_import_routes`
- `smoke.spec.ts`: creates a demo project with the mock provider (scratch backend, see
  `CLAUDE.md`) and edits a parameter in the editor; a new revision appears.
- `npm run build` type-checks.

## Files expected to change

`backend/app/models.py`, `schema.py`, `storage.py`, `config.py`, new `migrations.py`, new
`services/patch.py`, new `services/project_json.py`, new `llm/repair.py`, new
`llm/openai_provider.py`, new `llm/gemini_provider.py`, `llm/base.py`, `llm/__init__.py`,
`llm/prompts.py`, `llm/mock.py`, `services/designer.py`, `services/io_points.py`,
`services/spare_parts.py`, `services/layout.py`, `services/drawing.py`,
`services/documents.py`, `services/diff.py`, `api/`, `pyproject.toml` (dependencies only:
Hypothesis, provider SDKs if used; no version bump), `frontend/src/types.ts`, `api.ts`, new
editor components, `frontend/e2e/`, `frontend/package.json` (Playwright dev dependency only),
`docs/architecture.md`, `docs/ai-providers.md`, `docs/parking-lot.md` (close the items this
phase resolves), `README.md` (tick Phase 1). Any file not on this list needs a reason in the PR.

## Done criteria

- `cd backend && .venv/bin/pytest -q` green, `cd frontend && npm run build` green, Playwright
  smoke green, CI green.
- A v0.3 project opens as v2 in the running app with no data loss (Greg checks with his own
  database or a project made on the previous version).
- The chat produces patches; the editor edits the same model and creates revisions.
- One prompt that asks for something impossible returns a readable error and stores no
  revision, instead of a silent bad design.
- Frozen areas are untouched; `git diff main --stat` shows none of them.
- Docs and parking lot updated in the same PRs as the changes. `pyproject.toml` and
  `package.json` move to `0.4.0` in the final PR of the phase, after Greg's check.

## Agent brief

Schema first, tests second, prompts third. Present the plan for step 1 and wait for Greg's
approval before touching `models.py`, the prompts or the viewer. Keep `MockProvider` honest: no
hidden shortcuts that only work for demo prompts. If you are unsure about an engineering value
(a speed, a stroke, a signal count), leave a `TODO(source)` and ask; do not invent it. No
refactors "while we are here". Stop and report after each step.

## Open questions for Greg

1. **`sequence` and `cycle_time_s`.** `services/plc.py` (frozen) reads `cycle_time_s`, and
   `spare_parts.py`, `layout.py`, `drawing.py`, `documents.py`, `io_points.py` and `diff.py`
   read `sequence`. Proposal: keep `cycle_time_s` as the station's target cycle time and keep
   `sequence` as a field recomputed by code from the graph, so no frozen file changes. Removing
   `sequence` is a later cleanup. Alternative: edit `plc.py` now.
2. **How the scenario key reaches the mock.** Request field on project creation, or the
   `MF_MOCK_SCENARIO` environment variable. Proposal: the environment variable, since the mock
   is a test and demo tool and the public API should not change for it.
3. **Retry count.** Default of 3 attempts proposed, configurable.
4. **`placement` in Phase 1.** The plan lists it in the station model. Proposal: store it, user
   only, unused until Phase 4. Alternative: add it in Phase 4 with its own version bump.
5. **ADR.** This spec makes no decision outside D1 to D10, so it adds no ADR. If you decide
   question 1 or 2 differently from the proposal, that decision gets ADR 0011.
