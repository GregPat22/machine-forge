# Phase 2: timing engine, simulation B-lite

Status: **draft, open questions answered by Greg on 2026-10-29, not yet committed** (spec written
2026-10-29). Plan reference: `docs/PLAN.md`
section 5, Phase 2, section 6 (public reference machine) and section 7 (rules). Process rules:
`docs/workflow.md`. Decisions behind it: ADR 0001 (concept fidelity), ADR 0003 (results per
revision, diffed), ADR 0012 (derived `cycle_time_s`), ADR 0013 (flat patches), ADR 0016,
ADR 0018 (no time estimates).

## Goal

A station's cycle time is computed by code from its mechanisms and steps, and shown as a timing
diagram. Today a station has a cycle time only when every step is a fixed duration typed in by
someone; a motion step has no duration at all. After this phase every motion step gets its time
from a motion profile (stroke, speed, acceleration, and jerk for S-curves), the steps of a station
are laid out in time (in sequence or in parallel), and the software tells the engineer the cycle
time, the step that limits it, whether it meets the target, and which input values look
implausible against public catalog data. Changing a stroke in the model editor changes the time
with no AI call. The AI still proposes only structure and parameters; it never writes a duration
that can be computed (rule 3).

## Current state (verified 2026-10-29 on `main` at `f7ed9d9`)

- Backend suite: `cd backend && .venv/bin/pytest -q` gives `215 passed, 1 skipped`.
- `backend/app/models.py` (461 lines), schema version 2 (`MachineDesign.schema_version:
  Literal[2]`, line 267).
  - `Mechanism` (lines 121-130): `id`, `kind` (linear / rotary), `stroke`, `max_speed`,
    `acceleration`, `cam_profile` (unused), `dwell_s`. No jerk, no profile type.
  - `Step` (lines 133-141): `id`, `order`, `kind` (motion / fixed_duration), `mechanism_id`,
    `duration_s`, `parallel_group`. A step has no distance: a motion step moves its mechanism
    through one full stroke.
  - `Station.cycle_time_s` (lines 231-242) is a plain property (ADR 0012): the sum of the steps
    when every step is fixed-duration with a known duration and none is parallel; `None`
    otherwise. Never stored, not in the AI schema, not in `model_dump()`.
- `backend/app/storage.py`: tables `projects`, `revisions`, `messages`, `price_list`,
  `supplier_ratings`, `offer_cache`. **No place for engine results.** New columns are added by
  the `MIGRATIONS` list (line 92); stored designs are migrated on read and rows are never
  rewritten.
- `backend/app/migrations/design_v1.py`: `migrate_design` (line 119) reads version 1 and the
  current version 2 only; any other version raises. `to_v1` (line 169) exports the derived
  `cycle_time_s`.
- `backend/app/services/patch.py`: a motion step with a `duration_s` is rejected with
  `computed_field` (line 284); `stroke`, `max_speed`, `acceleration` must be > 0 and `dwell_s`
  ≥ 0 (lines 272-276). It does not check that the members of a `parallel_group` are next to each
  other in `order`.
- Readers of `cycle_time_s` today:
  - `services/plc.py:230` (frozen) prints it in the station comment labelled
    **"Target cycle time"**.
  - `services/documents.py:144-149` (`cycle_check`, slowest station) and `:197`. Its empty case
    says "ask the AI to estimate them" (line 146), which contradicts rule 3.
  - `services/diff.py:23` (`STATION_FIELDS`), `api/projects.py:69-76` (`_design_out` adds it to
    every station in API responses), `frontend/src/components/DesignView.tsx:37`,
    `ModelEditor.tsx:536` ("not computable yet").
- `backend/app/llm/mock.py`, blister scenario (lines 98-140): every station has one fixed step of
  1.2 s that equals its target (the v1 cycle time). Mechanisms have a stroke only where a
  component spec states it, and no speed or acceleration. `st-feeding` (brush feeder) has no
  mechanism. Other scenarios (cartoner, filling, assembly) are the same pattern.
- Tests that pin today's behaviour and will change on purpose (see "Tests to add"):
  `tests/test_models_v2.py:84` (parallel fixed steps give `None`) and
  `tests/test_migration_v2.py:158` (`test_mock_output_matches_its_v1_fixture`, which compares the
  exported `cycle_time_s` of the demo machines with the v1 fixtures).
- No `backend/app/engines/`, no `data/` folder, no `tests/golden/`. No YAML parser among the
  dependencies (`backend/pyproject.toml`); `hypothesis` is a dev dependency.
- The frozen-paths hash guard listed in the Phase 1 spec is not in
  `tests/test_repo_rules.py` (only the render-import and display-name tests are). Frozen files are
  checked by reading the diff.
- Frontend: tabs in `frontend/src/pages/ProjectPage.tsx:14` (design, model, layout, parts, docs,
  plc, revisions); no chart library; one Playwright test (`frontend/e2e/model-editor.spec.ts`),
  whose config starts a scratch backend with `MF_MOCK_SCENARIO=blister` (ADR 0025).
- `README.md` status still says Phase 1 is "in its final check". Next ADR number: 0026.

## Scope (exact)

### A. Model additions (`backend/app/models.py`): schema change, plan approval needed

This section is the implementation plan for the schema change; Greg approves it with the spec.

- `Mechanism.profile`: `Literal["trapezoidal", "s_curve"]`, default `"trapezoidal"`.
- `Mechanism.jerk`: `float | None`, default `None` (mm/s³ or deg/s³). Used only by `s_curve`.
- Moves are rest to rest, with deceleration equal to acceleration. No other new field. Stated in
  the field descriptions so the AI sees it.
- `schema_version` becomes 3. `migrate_design` reads versions 1, 2 and 3: version 2 data gets the
  defaults above and nothing else changes; version 1 goes through the v1 migration, then the same.
  Rows are not rewritten (same rule as Phase 1). Project JSON import of version 2 exports migrates.
- `services/patch.py`: `_check_mechanism_values` also checks `jerk` > 0. No new operation
  (ADR 0024 stands), no change to `COMPUTED_FIELDS`.
- The answer schema gains one nullable field (ADR 0013 notes the strict-mode union limit);
  `tests/test_schema_compat.py` must still pass unedited.

### B. Motion engine (`backend/app/engines/motion.py`)

Pure functions over numbers, no I/O, no model imports. Units pass through: mm, mm/s, mm/s², mm/s³
for linear axes, the same in degrees for rotary axes.

- `trapezoidal(distance, max_speed, acceleration) -> MoveProfile`. Rest to rest, symmetric.
  If `distance ≥ max_speed² / acceleration`: `T = distance / max_speed + max_speed / acceleration`.
  Otherwise the speed is never reached (triangular case): `T = 2·√(distance / acceleration)`, peak
  speed `√(distance · acceleration)`.
- `s_curve(distance, max_speed, acceleration, jerk) -> MoveProfile`. Rest-to-rest double-S
  (seven-segment) profile with symmetric limits, including the cases where the maximum
  acceleration, the maximum speed, or both are not reached.
- `MoveProfile`: `duration_s`, `peak_speed`, `peak_acceleration`, the phase durations, and
  `sample(n) -> list[(t, position, speed)]` with `n` evenly spaced points from 0 to `duration_s`
  (for Phase 4 animation; nothing stores or draws samples in this phase).
- Zero, negative, NaN or infinite inputs raise `MotionError`. No clamping, no fallback.
- **Sources**, cited in each function's docstring with section and page:
  - L. Biagiotti, C. Melchiorri, *Trajectory Planning for Automatic Machines and Robots*,
    Springer, 2008, ISBN 978-3-540-85628-3: chapter 3, the trapezoidal velocity profile (linear
    trajectory with parabolic blends, section 3.2) and the double-S velocity profile
    (section 3.4), including its case analysis for limits not reached.
  - Cross-check: P. Lambrechts, M. Boerlage, M. Steinbuch, "Trajectory planning and feedforward
    design for electromechanical motion systems", *Control Engineering Practice* 13 (2005)
    145-157 (jerk-limited third-order profiles).
  - The implementing agent confirms the section and page numbers against the book before writing
    code and writes `TODO(source)` where it cannot; it does not cite from memory.

### C. Timing engine (`backend/app/engines/timing.py`)

Pure function `station_timing(station) -> StationTiming`, and `design_timing(design) ->
TimingResult` over all stations. No I/O. Rules, all decided here:

1. **Order.** Steps are sorted by `(order, id)`.
2. **Blocks.** A step with no `parallel_group` is a block on its own. Steps that share a
   `parallel_group` form one block. Blocks run one after another, ordered by their smallest
   `order`; a block starts when the previous one ends; its duration is its longest member. A group
   whose members are not next to each other in the sorted order (another step sits between them)
   makes the station not computable (code `parallel_group_split`). This is the critical path of a
   series-parallel plan (critical-path method: J. E. Kelley, M. R. Walker, "Critical-path planning
   and scheduling", Proc. Eastern Joint Computer Conference, 1959), which the docstring cites.
3. **Durations.** A fixed-duration step lasts `duration_s`. A motion step lasts the profile time of
   one full stroke of its mechanism (section B, using `Mechanism.profile`), plus the mechanism's
   `dwell_s` when set (open question 3).
4. **Cycle time** = sum of the block durations. **Critical path** = the longest member of each
   block. **Limiting step** = the longest step on the critical path; ties go to the lower `order`,
   then the lower id.
5. **Per mechanism**: busy time (sum of its motion steps, dwell included), idle time (cycle − busy),
   utilisation (busy / cycle).
6. **Timing diagram** for one cycle: one row per mechanism (a bar per motion step) and one row per
   fixed-duration step, in order of first start. Each bar: step id, start, end, duration, whether
   it is on the critical path, and its source (`trapezoidal`, `s_curve` or `fixed`).
7. **Target check.** When `target_cycle_time_s` is set: margin = target − cycle (computed here, so
   the UI shows an engine number, rule 2), and a `target_not_met` warning naming the limiting step
   when the cycle is longer.
8. **Not computable** is a normal result, not an error: no steps; a fixed step with no duration; a
   motion step whose mechanism is missing or lacks `stroke`, `max_speed` or `acceleration`; an
   `s_curve` mechanism with no `jerk`; a split parallel group; motions of the same mechanism in one
   parallel block (`mechanism_overlap`, ADR 0031). The result lists every reason with a
   fixed code and the step or mechanism id. Values that the validator forbids (zero, negative) and
   that still reach the engine raise, they are not reported as warnings.

Result models (`StationTiming`, `TimingResult`, `TimingWarning`, reason and warning codes) live in
`engines/timing.py`, not in `MachineDesign` (ADR 0003). `TimingResult` carries
`engine_version: int` (bumped whenever a formula or rule here changes) and `bounds_version`
(section E).

### D. Derived `cycle_time_s` after this phase (extends ADR 0012)

- `Station.cycle_time_s` keeps its name and stays a plain read-only property, never stored, not in
  the schema, not settable by a patch. It now returns the cycle time from `station_timing` (lazy
  import, to avoid an import cycle), or `None` when the station is not computable.
- For a station whose steps are all fixed and none parallel, the value is the same as today, so
  migrated v1 designs keep their numbers. New: parallel fixed steps give the longest member of each
  block; motion steps give their computed time.
- `services/plc.py` keeps reading `station.cycle_time_s` with no edit and now gets the computed
  time. Its comment label still says "Target cycle time" (line 230). `plc.py` is frozen: no edit in
  this phase; the label goes to `docs/parking-lot.md` (open question 5).
- `services/documents.py` `cycle_check`: the empty-case message "ask the AI to estimate them"
  becomes "No computable cycle times yet: complete the mechanisms and steps in the model editor."
  Nothing else in `documents.py` changes.
- The limiting step and the warnings are not station properties; they are in the timing result.

### E. Plausibility bounds (`backend/app/data/catalog_bounds.yaml`)

The public table ships as `app` package data and is loaded through `importlib.resources`, so
source installs and wheels use the same file. An offline wheel test checks the packaged table
and the timing/diff endpoints without access to the source checkout (review fix R8).

- One YAML file, read with `yaml.safe_load` (new dependency `pyyaml`), validated by a Pydantic
  model when the service loads it. `bounds_version` = SHA-256 of the file, so cached results are
  recomputed when the table changes.
- Row shape:

  ```yaml
  - id: servo-linear-axis-acceleration      # slug, unique
    applies_to:                             # structured fields only, never names (rule 1)
      component_category: servo_motor       # a ComponentCategory, or
      transport_kind: null                  # a TransportKind (exactly one of the two)
      mechanism_kind: linear                # with component_category: linear or rotary
    field: acceleration                     # stroke | max_speed | acceleration | jerk | index_time_s | speed_mm_s
    unit: mm/s2                             # the model's unit for that field
    min: null                               # TODO(source)
    max: null                               # TODO(source)
    as_printed: null                        # the value and unit exactly as the source prints them
    source_title: null                      # TODO(source)
    source_url: null                        # TODO(source)
    accessed: null                          # date the source was read
  ```

- Matching: a mechanism is checked against the rows whose `component_category` is the category of
  a component in the same station with `motion` equal to the mechanism id, and whose
  `mechanism_kind` is the mechanism's kind. A transport is checked against the rows of its `kind`.
  A mechanism that no component drives is not checked; the result says so (no warning).
- A row is **active** only when it has `source_url`, `source_title`, and `min` or `max`. Inactive
  rows (`TODO(source)`) produce no warning. A value outside an active row gives an `out_of_bounds`
  warning with the value, the bound, the row id, the title and the URL. Never a correction: the
  design is not changed.
- The check is a pure function `engines/bounds.py: check_bounds(design, table)`; only the service
  reads the file (rule 5).
- **Rows to source** (every value `TODO(source)` until a public source is found and cited; no
  numbers are written in this spec on purpose):
  1. Pneumatic cylinder, linear (`pneumatic_actuator`): piston speed range. Candidate sources to
     check: Festo and SMC standard-cylinder catalogs (technical data or sizing pages).
  2. Servo-driven linear axis (`servo_motor`, linear): maximum speed and maximum acceleration.
     The PLAN test (500 m/s² must warn) needs this row's maximum acceleration. Candidate: an
     electric axis catalog (for example Festo toothed-belt or spindle axes). Motor catalogs give
     rpm, not axis speed, so they do not fit this row.
  3. Servo-driven rotary axis (`servo_motor`, rotary): maximum speed and acceleration in degrees.
  4. Electric linear axis without a servo category (`linear_motion`, linear): speed and
     acceleration.
  5. Indexing or rotary transport (`transport_kind: indexing` and `rotary`): index time range.
     Candidate: rotary indexing table brochures (for example Weiss, CDS/Camco).
  6. Jerk for any axis: only if a public catalog states it; otherwise no row.
- Not in this phase: bounds on fixed-duration process steps (a sealing time is not linked to a
  component or kind in the model).

### F. Golden stations (`backend/tests/golden/`)

- Three stations, as the plan lists: **pick-and-place** (two linear axes and a dwell; one move
  short enough to be triangular; one parallel group), **indexing table** (a rotary axis with an
  `s_curve` profile, the index angle 360°/stations, then two process steps of different length in
  one parallel group during the dwell), **sealing station** (a linear lift, a heat-sealing dwell as
  a fixed step, the lift back).
  **Decided 2026-10-29 (ADR 0030):** no manufacturer's page read gives a jerk, so the indexing table has 36
  stations (10°) and takes its axis limits from the textbook's printed S-curve example (p. 93).
- **The spreadsheet is the data** (Greg, 2026-10-29): `timing_stations.xlsx`, one sheet per
  station plus a `Sources` sheet. A station sheet has four tables: `Mechanisms` (id, kind,
  profile, stroke, max speed, acceleration, jerk, dwell, unit, source id per number), `Steps` (id,
  order, kind, mechanism id or duration, parallel group, source id for a duration),
  `Calculation` (the hand calculation as spreadsheet formulas, one row per step: which profile
  case applies, its phase times, start, end) and `Expected` (each step's duration, the cycle time,
  the limiting step, the margin, all as formulas over `Calculation`). The `Sources` sheet lists
  every source id with title, URL or ISBN, page, the value as printed, and the date read.
- The test reads the sheet with `openpyxl` (already a dependency), builds the station from the
  `Mechanisms` and `Steps` tables, runs the engine, and compares with the `Expected` values.
  `openpyxl` reads the values a spreadsheet program last computed and saved; it does not compute
  formulas itself. So the committed file must have been recomputed and saved by LibreOffice
  (`soffice --headless --convert-to xlsx`, run by the agent if installed) or by Greg opening and
  saving it in Excel. An expected cell with no saved value fails the test with that instruction.
  This keeps the expected values independent of our code: **they are computed by the spreadsheet,
  never by running the engine**.
- `README.md`: what each station is, the formula used with its citation (section B), how to read
  and recompute the sheet, and the expected values copied as a plain table (a reviewer can read
  them in the pull request, which cannot show a diff of the binary sheet; a test checks the table
  and the sheet agree).
- Inputs are public catalog or textbook values only (rule 12, PLAN section 6). Where a source is
  not found yet, the input is `TODO(source)` and the golden test for that station fails: that is
  intended, the step is not done until it passes.
- Where the textbook prints a worked rest-to-rest example of either profile, it becomes an extra
  closed-form test with the book's numbers and printed result.

### G. Results storage, service and API

- **Storage** (ADR 0003, rule 7): a new table, created by `CREATE TABLE IF NOT EXISTS` in
  `SCHEMA`, so an old database gets it the first time it is opened:

  ```sql
  CREATE TABLE IF NOT EXISTS revision_results (
      project_id TEXT NOT NULL,
      workspace_id TEXT NOT NULL DEFAULT 'default',
      revision INTEGER NOT NULL,
      engine TEXT NOT NULL,              -- 'timing'; Phase 3 adds 'throughput', no new migration
      engine_version INTEGER NOT NULL,
      inputs_version TEXT NOT NULL,      -- bounds_version for timing
      result TEXT NOT NULL,              -- JSON of TimingResult
      created_at TEXT NOT NULL,
      PRIMARY KEY (project_id, revision, engine),
      FOREIGN KEY (project_id, revision) REFERENCES revisions(project_id, number) ON DELETE CASCADE
  );
  ```

  A result is a cache with provenance (ADR 0003): recomputing it from the revision's design must
  give the same JSON. The revision's design is never changed.
- **Service** (`backend/app/services/timing.py`): loads the bounds table once, and
  `timing_for(storage, project_id, revision) -> TimingResult` returns the stored row when its
  `engine_version` and `inputs_version` match, else computes, stores and returns it (open
  question 2). Old revisions are filled the first time they are read; nothing is backfilled in bulk.
- **API**: `GET /api/projects/{id}/timing?revision=N` (latest when omitted) returns the
  `TimingResult`; 404 for an unknown project or revision. No AI call on this path.
- **Diff**: `GET /api/projects/{id}/diff` gains a `timing` block from the two stored results: per
  station the cycle time before and after, the limiting step before and after, and warnings added
  and removed (matched by code and the id they name). `DesignDiff` gets an optional `timing` field;
  the existing fields are unchanged.
- **Prompt** (`backend/app/llm/prompts.py`, prompt change: needs approval with this spec): the
  mechanisms paragraph gains one clause: set `profile` to `s_curve` and `jerk` only from the
  catalog data of the chosen drive, else leave the default and null. Nothing else in the prompt
  changes. The AI does not see timing results in this phase (Phase 6).

### H. Mock blister machine (`backend/app/llm/mock.py`)

- The blister scenario gets motion steps for its mechanisms, with `max_speed`, `acceleration` (and
  `jerk` where a profile is `s_curve`) taken from the public catalog data of the components the mock
  already names, each cited in a comment, or `TODO(source)`. `target_cycle_time_s` stays 1.2 s.
- Fixed process times (the sealing dwell, the forming heat time) are demo inputs: each one is
  recorded in the design's `assumptions` as "demo process time, not catalog data".
- The brush feeder (`st-feeding`) has no axis: it fills the cavities while the web stands still,
  so its time is set by the process, not by a mechanism. It keeps its 1.2 s fixed step, recorded
  the same way as a demo process time. It gets no invented mechanism (rule 4 in spirit: the model
  shows only what it knows).
- The done criterion needs every blister process station computable, so this step waits for the
  sources of section E rows 1 and 2. Pneumatic catalogs often give a speed range but no
  acceleration. If no public source gives one, step 4 stops and reports; no value is invented, and
  Greg decides then (for example: model those cylinders as fixed steps with a cited stroke time).
  **Decided 2026-10-29 (ADR 0029):** no manufacturer's page read gives one; each pneumatic cylinder stroke is a
  fixed-duration step whose time is read from a manufacturer's full-stroke-time chart (SMC "Full
  Stroke Time & Stroke End Velocity"), with chart, page, load ratio and conditions cited.
- `tests/test_migration_v2.py::test_mock_output_matches_its_v1_fixture` and
  `test_mock_refinements_match_their_v1_fixtures` get one listed exception: the exported
  `cycle_time_s` of the blister stations (it now comes from the engine). Every other field is still
  compared. This is a deliberate expectation change approved with this spec, not a loosening.
- The cartoner, filling and assembly scenarios do not change.

### I. Frontend (UI: Greg approves a written plan before any UI code)

Step 7a is a plan only: a one-page description with a static sketch (an image under `.context/`)
of the tab, the diagram, the panel and the list, and the exact test ids for Playwright. Greg says
yes or no; then step 7b writes the code. What the plan must cover:

- `frontend/src/types.ts` mirrors `Mechanism.profile`, `Mechanism.jerk` and the `TimingResult`
  models; `api.ts` gets `timing(projectId, revision)`.
- A new **Timing** tab (`?tab=timing`):
  - **Timing diagram** (Gantt), one per station: SVG drawn by our code (no chart library), a time
    axis from 0 to the cycle time in seconds, one row per mechanism and per fixed step (section C.6),
    critical-path bars marked, a vertical line at the computed cycle and one at the target when set.
    Each bar shows its step id and duration, and on hover its source (profile and inputs or
    "fixed"), so every number has provenance (rule 2).
  - **Cycle-time check panel**: one line per station: target, computed, margin, limiting step,
    status (meets target / misses target / no target / not computable, with the reasons).
  - **Warnings list**: `target_not_met`, `out_of_bounds` (with the catalog row and a link to its
    source) and not-computable reasons, grouped by station.
- Model editor: the mechanism form gets the profile and jerk fields; the station header shows the
  not-computable reason instead of "not computable yet".
- Revision diff view: the timing block of section G.
- Playwright (`frontend/e2e/timing.spec.ts`), see "Tests to add".

### J. Docs

- ADRs for the decisions Greg made on 2026-10-29 (see "Open questions"), each written in the step
  that implements it, in the same change (rule 10): **0026** motion profile fields, schema
  version 3 (section A, question 1; step 1); **0027** the timing rules and `cycle_time_s` from
  the timing engine, extending ADR 0012 (sections C and D, questions 3, 4 and 5; step 3);
  **0028** where results are stored and when they are computed (section G, questions 2 and 8;
  step 5). The golden spreadsheet format (question 7) is recorded in this spec and in
  `tests/golden/README.md`.
- `docs/architecture.md`: an "Engines" section (motion, timing, bounds; pure functions; the results
  table). `README.md`: status (Phase 1 done, Phase 2 in progress, then done) and the roadmap ticks.
- `docs/parking-lot.md`: the `plc.py` label (section D), split parallel groups not rejected by the
  validator, a step cannot move part of a stroke, the inactive bounds rows still without a source.
- `backend/tests/golden/README.md` (section F).

## Out of scope

- Throughput, line rate, bottleneck across stations, transport travel times, buffers (Phase 3).
- Cam profile synthesis, electronic cam tables, interference (`cam_profile` stays unused).
- Asymmetric acceleration and deceleration, non-zero start or end speed, blended or coordinated
  multi-axis moves, partial strokes.
- Anything in the 3D view and any animation (Phase 4); `MoveProfile.sample` is tested but not used.
- Library modules and their timing formulas (Phase 5). AI tools such as `run_timing`, and the AI
  reading results (Phase 6).
- New patch operations (ADR 0024 stands). Validator rejection of split parallel groups.
- Frozen modules (`app/suppliers/`, `services/rfq.py`, `services/plc.py`, `services/sourcing.py`,
  supplier ratings): no change. The cartoner, filling and assembly demo machines.
- Bounds on fixed-duration process times.

## Tests to add

All offline (rule 6). Names are expectations; agents may adjust a name only with a line in the
report.

**Motion (`backend/tests/test_motion.py`, step 2)**
- `test_trapezoidal_time_matches_closed_form`: several `s, v, a` with the speed reached; the time
  equals `s/v + v/a` to 1e-9.
- `test_triangular_case_when_max_speed_is_not_reached`: time `2·√(s/a)`, peak speed `√(s·a)` < `v`.
- `test_trapezoidal_is_continuous_at_the_triangular_boundary`: at `s = v²/a` both branches agree.
- `test_s_curve_cases_match_closed_form`: one case each for acceleration and speed reached or not,
  expected values from the book's formulas written out in the test.
- `test_s_curve_reduces_to_trapezoidal_as_jerk_grows`: the gap shrinks as jerk grows and is below
  1e-6 at large jerk.
- `test_s_curve_matches_textbook_worked_example`: only if the book prints a rest-to-rest example
  (section F); otherwise left out with a line in the report.
- `test_rotary_axis_uses_degrees_unchanged`: same numbers in degrees give the same time.
- `test_samples_start_and_end_at_rest_and_cover_the_distance`: position 0 and `s`, speed 0 at both
  ends, speed never above `v`.
- `test_invalid_inputs_raise`: zero, negative, NaN, infinity.
- `test_profiles_are_deterministic`.

**Timing (`backend/tests/test_timing.py`, step 3)**
- `test_fixed_steps_in_sequence_add_up`
- `test_parallel_group_takes_its_longest_member`
- `test_motion_step_is_profile_time_plus_dwell`
- `test_limiting_step_is_the_longest_on_the_critical_path_with_tie_rule`
- `test_axis_busy_idle_and_utilisation`
- `test_diagram_has_one_row_per_mechanism_and_fixed_step`
- `test_missing_values_make_the_station_not_computable_with_reasons`: one case per reason code.
- `test_split_parallel_group_is_not_computable`
- `test_target_not_met_names_the_limiting_step` and `test_target_met_gives_no_warning`
- Hypothesis invariants (random valid stations): `test_cycle_time_is_at_least_the_longest_step`,
  `test_parallel_steps_never_shorten_below_the_longest_branch`,
  `test_removing_a_step_never_increases_cycle_time`,
  `test_longer_stroke_never_shortens_a_motion_step`,
  `test_more_speed_or_acceleration_never_lengthens_a_motion_step`,
  `test_timing_is_deterministic`.

**Derived value (`backend/tests/test_models_v2.py`, step 3)**
- Changed expectation, approved here: in
  `test_cycle_time_s_is_derived_from_fixed_steps_and_null_with_motion_or_parallel_steps` (renamed
  `test_cycle_time_s_comes_from_the_timing_engine`), two fixed steps in one parallel group now give
  the longer one (0.5 s, line 84) instead of `None`. The other assertions stay.
- `test_cycle_time_s_equals_the_timing_engine_for_every_demo_station`
- Not a new test, a requirement: `test_plc.py`, `test_layout.py`, `test_diff_and_drawing.py` and
  `test_schema_compat.py` pass with no edit.

**Schema v3 (`backend/tests/test_migration_v3.py`, step 1)**
- `test_v2_revisions_migrate_to_v3_with_profile_defaults`
- `test_v1_revisions_still_migrate`
- `test_old_database_opens_after_phase_2`: a committed version 2 database fixture
  (`tests/fixtures/v2/phase1.db`, built by a script next to it from the demo machines) opens,
  reads back, and its rows are not rewritten (rule 7).
- `test_version_2_project_json_imports`
- In `test_patch.py`: `test_jerk_must_be_positive` (`invalid_value`).

**Bounds (`backend/tests/test_bounds.py`, step 4)**
- `test_bounds_file_validates`: known categories, kinds and fields, unit matches the field,
  `min` ≤ `max`, unique ids, exactly one of `component_category` and `transport_kind`.
- `test_every_active_row_has_a_source` (URL and title).
- `test_rows_without_a_source_give_no_warning`
- `test_out_of_bounds_value_warns_and_is_not_corrected`: a synthetic table, labelled as a fixture
  in the test, not data.
- `test_servo_acceleration_of_500_m_s2_warns_with_the_catalog_row`: real table, 500,000 mm/s², the
  warning names row id and URL. Fails until row 2 is sourced.
- `test_bounds_ignore_component_names` (rule 1): renaming the component gives the same warnings.

**Golden (`backend/tests/test_golden_timing.py`, step 4)**
- `test_golden_pick_and_place`, `test_golden_indexing_table`, `test_golden_sealing_station`:
  the station built from its sheet; engine within 1e-6 of the sheet's `Expected` values for every
  step and the cycle; same limiting step.
- `test_every_expected_cell_has_a_saved_value`: fails, with the recompute instruction, when the
  sheet was written by code and never recomputed by a spreadsheet program.
- `test_every_golden_input_has_a_source`: every number in `Mechanisms` and `Steps` has a source id
  listed on the `Sources` sheet with a URL or ISBN; no `TODO(source)` left.
- `test_readme_table_matches_the_sheet`: the expected values in `README.md` equal the sheet's.

**Results and API (`backend/tests/test_timing_results.py`, step 5)**
- `test_results_table_is_created_on_an_old_database`
- `test_timing_is_computed_once_then_read_from_storage`
- `test_stale_engine_or_bounds_version_is_recomputed`
- `test_recompute_reproduces_the_stored_result` (ADR 0003)
- `test_results_are_deleted_with_the_project`
- `test_timing_endpoint_returns_the_revision_result` and `test_timing_endpoint_404`
- `test_diff_reports_cycle_time_and_limiting_step_changes`
- `test_editing_a_stroke_changes_the_timing_without_an_ai_call`: patch endpoint, the provider is
  called zero times.
- In `test_documents.py`: `test_cycle_check_without_computable_times_points_to_the_model`.

**Mock (`backend/tests/test_mock_provider.py`, step 6)**
- `test_blister_process_stations_have_a_computed_cycle_and_limiting_step`
- The v1-fixture exception of section H, in `test_migration_v2.py`.

**Repo rules (`backend/tests/test_repo_rules.py`, step 2)**
- `test_engines_do_no_io`: files under `app/engines/` import no I/O module (`sqlite3`, `httpx`,
  `yaml`, `pathlib`, `os`, `app.storage`, `app.llm`), never call `open(`, and contain no
  `except ...: pass`.

**Frontend (step 7b)**
- `npm run build` passes.
- `frontend/e2e/timing.spec.ts`:
  - `the cycle bar of each blister station spans the computed cycle time`: for every station, the
    right end of the last critical-path bar sits at the computed cycle time on the drawn scale,
    within one pixel of that scale, and the readout equals the API value. (This is how the spec
    reads the plan's "longest bar matches the computed cycle".)
  - `changing a stroke in the model editor changes the cycle time with no AI call`: edit the
    stroke of a blister mechanism on a critical path (the sealing lift, unless section H made it a
    fixed step), the timing tab shows a different cycle equal to the API value, and no
    request went to a prompt endpoint.

## Order of work and parallelism

One agent per step, each on its own branch, stopping with a report after each step
(`docs/workflow.md`). Never two agents on `models.py`.

1. **Schema v3** (A): fields, migration, patch bound, v2 database fixture. Opus, high. First for
   anything that reads the new fields.
2. **Motion engine** (B) and the engines repo rule. Pure numbers, no model: can run in parallel
   with step 1. Opus, high.
3. **Timing engine and derived `cycle_time_s`** (C, D). Needs 1 and 2. Opus, high; heaviest audit
   (it changes what the frozen `plc.py` prints).
4. **Bounds table and golden stations** (E, F). The source search can start at once, in parallel
   with 1 to 3 (data and README only); the bounds and golden tests need step 3. The agent finds
   the sources as answered in question 9.
5. **Results storage, service, API, diff, prompt clause** (G). Needs 3 and the bounds loader of 4.
6. **Mock blister** (H). Needs 3 and the sourced rows of 4. Sonnet, medium.
7. **Frontend**: 7a the UI plan, for Greg's approval, no code; 7b types, Timing tab, editor fields,
   diff view, Playwright. Needs 5 and 6.
8. **Docs** (J): architecture, README, parking lot (the ADRs come with steps 1, 3 and 5).
   Sonnet, medium.

## Open questions for Greg (answered 2026-10-29)

Greg's answer to all of them: take the recommended option where it is technically sound; a
spreadsheet for the golden data.

1. **Schema change.** Add `Mechanism.profile` (trapezoidal / s_curve) and `Mechanism.jerk`, with
   symmetric rest-to-rest moves, as schema version 3?
   **Answer:** yes, as in section A. ADR 0026.
2. **When results are computed.** The first time a revision's timing is read, then stored, or at
   every save?
   **Answer:** on first read, then stored (section G). No change to the save paths, and old
   revisions are handled the same way as new ones. Timing is cheap, so in this phase the stored
   copy serves the diff and prepares Phase 3, where the throughput simulation is slow. ADR 0028.
3. **Dwell.** What does the existing `Mechanism.dwell_s` mean for the timing?
   **Answer:** a pause at the end of every stroke of that mechanism, added to each of its motion
   steps (section C.3). A pause that happens once per cycle is a fixed-duration step. ADR 0027.
4. **Pneumatic cylinders and cam indexers.**
   **Answer:** a pneumatic cylinder is a trapezoidal axis with catalog speed and acceleration,
   a concept-level simplification stated in ADR 0027 (real cylinders depend on load, pressure and
   cushioning). If no public source gives a pneumatic acceleration, the step stops and reports
   (section H). A mechanical cam indexer is a fixed-duration step with its catalog index time,
   since cam laws are out of scope.
   **Follow-up (2026-10-29):** no manufacturer's page read gives a pneumatic acceleration, so the cylinder
   part is replaced by ADR 0029 (fixed-duration step with a charted stroke time; see section H).
   ADR 0027 records only the cam indexer part of this answer.
5. **`plc.py` label** ("Target cycle time" printing the computed cycle).
   **Answer:** the frozen file is not touched; a parking-lot entry records it (section D).
6. **Mock numbers and the brush feeder.**
   **Answer:** speeds and accelerations from public catalogs only. The brush feeder keeps its
   1.2 s fixed step, recorded in the design's assumptions as a demo process time; it gets no
   invented mechanism (section H).
7. **Golden format.**
   **Answer:** a spreadsheet is the data (section F): the test reads its inputs and its expected
   values, which the spreadsheet computes with its own formulas.
8. **Timing in the revision diff.** When two revisions are compared, should the comparison also
   show what happened to the timing (for example "sealing: cycle 1.2 s → 1.4 s, limiting step
   changed from lift-down to seal-dwell", plus new or cleared warnings), or only the stations and
   parts as today?
   **Answer:** yes, in this phase (section G). ADR 0003 already says results are compared between
   revisions, and the what-if question ("what does this change do to my cycle?") is the main use.
   ADR 0028.
9. **Who finds the public sources** for the catalog numbers (cylinder speeds, servo axis
   accelerations, index times, golden inputs)?
   **Answer:** the step 4 agent searches manufacturers' and publishers' own pages (no forums,
   no resellers), and records title, URL or ISBN, page, the value exactly as printed and the date
   read. The independent audit agent opens every URL and confirms the printed value. Greg sees the
   list in the report and does not have to check each source.

Also decided in this spec: YAML with `pyyaml` as the plan names it, rather than TOML from the
standard library; files under `backend/data/` and `backend/tests/golden/` so they sit next to the
code that reads them; split parallel groups are reported by the engine, not rejected by the
validator (that would reopen `patch.py`); bounds match on component category, mechanism kind and
transport kind; no chart library.

## Done criteria

- `cd backend && .venv/bin/pytest -q` green, `cd frontend && npm run build` green,
  `npm run e2e` green, CI green.
- For the mock blister machine, every process station shows a computed cycle time with its
  limiting step on the Timing tab, and changing a stroke in the model editor changes the time with
  no AI call. Greg checks this in the running app.
- The servo acceleration row and every golden input have a public source; inactive bounds rows are
  listed in the parking lot.
- `test_plc.py` passes unedited and no frozen file appears in any step's diff.
- Reports and audit verdicts exist for every step (`docs/workflow.md`). ADRs written for every
  decision Greg made on the open questions.

## Agent brief

Engines are pure functions over the model: no I/O, deterministic, every formula cites its source
in the docstring (book, section, page). No "approximately" code paths: an unhandled case raises,
an incomplete design is reported as not computable with its reasons. Never invent an engineering
number: write `TODO(source)` and ask. Golden expected values come from the hand calculation, never
from running the engine. Do only what the spec says; no "while we are here" changes.
