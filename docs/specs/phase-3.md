# Phase 3: throughput engine, simulation A

Status: **open questions answered by Greg on 2026-11-03** (spec written 2026-11-03). Plan reference:
`docs/PLAN.md` section 5, Phase 3, section 6 (public reference machine), section 7 (rules) and
section 9 (open items). Process rules: `docs/workflow.md`. Decisions behind it: ADR 0001 (concept
fidelity), ADR 0003 (results per revision, diffed), ADR 0012 and 0027 (derived `cycle_time_s`),
ADR 0013 (flat patches), ADR 0024 (editor uses existing patch operations), ADR 0025 (Playwright),
ADR 0028 (results stored on first read), ADR 0018 (no time estimates).

## Goal

The software tells the engineer how many good products per minute the line makes, which station
or conveyor limits it, how much of the time each station works, waits for products (starved),
waits for room downstream (blocked) or is broken down, how full the conveyors are, and how long a
product spends in the machine. It computes this by simulating the process graph: stations with the
cycle times the Phase 2 timing engine computes, joined by transports with a travel time and a
capacity, including parallel lanes, reject branches and optional breakdowns. The result is stored
per revision and compared between revisions, so a what-if ("one more buffer place here") shows what
it does to the rate. The simulation also writes an event trace that the Phase 4 viewer will play.
Changing a conveyor speed in the model editor changes the rate with no AI call. The AI proposes
structure and parameters; it never writes a rate (rule 3).

## Current state (verified 2026-11-03 on `main` at `4bf1368`)

- Backend suite: `cd backend && .venv/bin/pytest -q` gives `399 passed, 1 skipped`.
- `backend/app/models.py` (467 lines), schema version 3 (`MachineDesign.schema_version:
  Literal[3]`).
  - `Transport` already has every field a throughput model needs except the travel rule:
    `kind` (belt / indexing / rotary / pick_place / gravity), `length_mm`, `speed_mm_s`,
    `index_time_s`, `buffer_capacity` ("Products that can wait on the transport"),
    `products_per_move`, `reject_to`, `reject_rate`. **No code reads any of them yet** (only the
    validator checks their bounds, `services/patch.py:573-576`).
  - `Product` has `lanes` and `pitch_mm`; no code reads them either.
  - `MachineDesign.target_rate_text` is free text, display only. There is no numeric required
    rate. `services/documents.py` `cycle_check` shows the text and says it is "not compared with
    the cycle time"; `docs/parking-lot.md` says the check comes back with a numeric rate field in
    Phase 3.
  - `Station` has `target_cycle_time_s` and the derived `cycle_time_s` (timing engine, ADR 0027).
    No count of products per cycle, no breakdown data.
  - `MachineDesign.process_order()` sorts the graph topologically; reject branches leave the line
    and are not edges; a cycle raises.
- `backend/app/engines/`: `motion.py`, `timing.py` (`ENGINE_VERSION = 3`), `bounds.py`. No
  throughput engine. `tests/test_repo_rules.py::test_engines_do_no_io` forbids I/O imports in
  `engines/`. `docs/architecture.md` says engines use "no randomness"; Phase 3 needs seeded
  randomness (rule 5 allows it: "seeded where random").
- `backend/app/storage.py`: `revision_results` table keyed by `(project_id, revision, engine)`,
  with `engine_version` and `inputs_version`. ADR 0028 says Phase 3 adds `throughput` rows with
  no new migration. `services/timing.py` is the pattern for the new service.
- `backend/app/services/diff.py`: `DesignDiff.timing` block (ADR 0028). No throughput block.
- `backend/app/services/patch.py`: `set_param` sets the machine fields in `_MACHINE_FIELDS`
  (line 372) and the station fields in `_STATION_FIELDS` (line 379); a field kind is text,
  optional text, choice or number. No integer kind. No `set_transport`: the editor changes a
  transport by disconnect and connect in one request (`ModelEditor.tsx:889`).
- `backend/app/llm/prompts.py:37`: transport speed, index time, buffer capacity, products per move
  and reject branches are set "only when the engineer states them".
- `backend/app/llm/mock.py`: the cartoner (`_cartoner`, three process stations at 0.4 s fixed
  steps, required rate text "120 tubes/min") and every other scenario use `_belts`: belts with no
  length, speed or capacity. The shared `st-outfeed` station (kind `transport`) has no steps, so
  its cycle is not computable. The refinement adds `st-vision`, which has no steps either.
- No SimPy among the dependencies (`backend/pyproject.toml`); `import simpy` fails in the backend
  virtualenv. Open PR #15 (draft) moves the backend to a uv lock file.
- Frontend: tabs in `frontend/src/pages/ProjectPage.tsx:15` (design, model, timing, layout, parts,
  docs, plc, revisions). `TimingView.tsx` draws its diagram in SVG, no chart library. The model
  editor already edits transports (kind, length, speed, index time, buffer, rejects). Playwright
  (`frontend/playwright.config.ts`) starts one scratch backend with `MF_MOCK_SCENARIO=blister`.
- No `docs/trace.md`. Next ADR number: 0034 (0019 to 0022 are held by open pull requests).

## Scope (exact)

### A. Trace format (`docs/trace.md`), written before any engine code

The plan requires the trace format documented before code. The document defines:

- One event per move of one product: `(t, piece_id, from, to)`. `t` in seconds of simulated time
  from the start of the trace window; `piece_id` an integer in order of entry into the line;
  `from` and `to` node ids. Nodes are station ids, transport ids and two fixed names for outside
  the line (`source`, `sink`); a rejected product's last move goes to its reject station id.
- What each move means for the viewer: entering a transport, reaching its end, being taken by a
  station, starting and ending a cycle, leaving the line. Enough for Phase 4 to place a product at
  any time by interpolating between `from` and `to` (the unit test of Phase 4 reads this).
- The stored shape: compact arrays (a node list, then events as `[t, piece, from_index,
  to_index]`), times rounded to a stated precision, events sorted by `(t, piece_id)`.
- The window: which part of the run is traced (after warm-up), and a hard cap on the number of
  events so a result row stays small. The cap and the window length are stated as numbers in the
  document and are engine constants (a change bumps the engine version).
- A worked example of three products through a two-station line, written by hand.

No code in this step. The document is reviewed like code: the engine of step 3 implements it, and
its test checks the trace against it.

### B. Model additions (`backend/app/models.py`): schema change, plan approval needed

This section is the implementation plan for the schema change; Greg approves it with the spec
(open question 1).

- `MachineDesign.target_rate_per_min`: `float | None`, default `None`. "Required good products per
  minute at the line's outfeed, as the engineer stated it". A requirement, not a result: the AI
  copies it from the engineer's words, like `target_cycle_time_s`. `target_rate_text` stays as the
  words were stated.
- `Station.products_per_cycle`: `int`, default `1`. "Products one cycle of this station handles,
  all lanes and cavities included".
- `Station.mtbf_s` and `Station.mttr_s`: `float | None`, default `None`. "Mean working time between
  breakdowns" and "mean time to repair", in seconds (open question 2).
- `Transport.buffer_capacity`: same field, new description: "Products the transport holds at
  once, travelling or waiting at its end; null to take it from the length and the product pitch".
  The rule is in section C.4.
- `Product.lanes`: same field, new description: "Parallel product lanes, display only: the
  throughput reads each station's products_per_cycle and the process graph".
- `schema_version` becomes 4. `migrate_design` reads versions 1 to 4: version 3 data gets the
  defaults above and nothing else changes; versions 1 and 2 go through their migrations, then the
  same. Rows are not rewritten (rule 7). Project JSON import of version 3 exports migrates.
- `services/patch.py`: `set_param` accepts `target_rate_per_min` (machine field, number > 0) and
  `products_per_cycle` (station field, a new integer kind, ≥ 1), and `mtbf_s`, `mttr_s` (station
  fields, number > 0). No new operation (ADR 0024 stands), no change to `COMPUTED_FIELDS`.
- `tests/test_schema_compat.py` must still pass unedited.
- `frontend/src/types.ts` mirrors the new fields in this step (types only; the UI is step 7).

### C. Throughput engine (`backend/app/engines/throughput.py`)

Pure function `line_throughput(design, timing, settings) -> ThroughputResult` on **SimPy** (new
dependency `simpy`, MIT license). `timing` is the Phase 2 `TimingResult` of the same design, so
station cycle times come from one place. No I/O, no custom scheduler (plan brief). Rules, all
decided here (open question 5 for the bottleneck):

1. **Line.** The nodes are the stations of `design.process_order()`; the edges are the transports.
   An entry station (no incoming transport) never waits for products: the supply is unlimited. A
   product that finishes at an exit station (no outgoing transport) leaves the line as good output:
   the outfeed is never blocked. This is a saturated line, the standard setting for measuring a
   line's capacity.
2. **Station.** A station has `products_per_cycle` places. It takes products from the end of its
   input transports, one at a time in order of arrival (ties by transport id), until its places
   are full; then it runs one cycle of `cycle_time_s` (from `timing`); then it passes each product
   on. It starts the next cycle only when all of them are passed on (blocking after service:
   Y. Dallery, S. B. Gershwin, "Manufacturing flow line systems: a review of models and analytical
   results", *Queueing Systems* 12 (1992) 3-94; the agent confirms section and page or writes
   `TODO(source)`). Time is split into working, starved (waiting for products), blocked (waiting
   for room downstream) and down.
3. **Splits and merges.** A station with several outgoing transports puts each product on the
   first one, in transport id order, that has room; when none has room it is blocked. A station
   with several incoming transports takes products in order of arrival. Parallel lanes are parallel
   stations in the graph. Joining different parts into one (assembly) is out of scope: every
   product stays one product.
4. **Transport.** A first-in, first-out conveyor with a travel time `T` and a capacity `C`. A
   product enters when fewer than `C` products are on it, reaches the end `T` after entering (never
   before the product ahead), and leaves when the next station takes it.
   - `T`: belt and gravity: `length_mm / speed_mm_s`; indexing, rotary and pick_place:
     `index_time_s`.
   - `C`: `buffer_capacity` when set and at least 1. When null, for a belt or gravity transport
     with `length_mm` and the product's `pitch_mm`: `floor(length_mm / pitch_mm)`, the products
     that fit on it. The result records which of the two rules gave `C`. With this rule a belt
     carries at most `C / T = speed / pitch` products per second, so its speed matters.
   - `products_per_move` other than null or 1 is not supported in this phase (reason code below).
5. **Rejects.** On a transport with `reject_to` and `reject_rate`, each product that reaches the
   end is rejected with probability `reject_rate` (seeded draw) and leaves the line at once to the
   reject station, where it is counted as a reject; it takes no station time there.
6. **Breakdowns** (open question 2). A station with `mtbf_s` and `mttr_s` breaks
   down after an exponentially distributed working time with mean `mtbf_s` (only working time
   counts) and is repaired after an exponential time with mean `mttr_s`; the interrupted cycle
   resumes where it stopped. Source to confirm: A. M. Law, *Simulation Modeling and Analysis*,
   5th ed., McGraw-Hill 2015, the section on modelling machine downtimes (the agent confirms the
   section and page or writes `TODO(source)`). Changeover is out of scope (the model has one
   product).
7. **Randomness.** Every random stream (one per reject transport, one per station that breaks
   down) is a `random.Random` seeded from the run seed and the stream's id through SHA-256. Never
   Python's `hash()` (it changes between runs), never the module-level `random` functions. A line
   with no rejects and no breakdowns uses no random numbers at all.
8. **Run settings** (`ThroughputSettings`, engine constants, recorded in the result): seed 0,
   warm-up 500 products leaving the line, then 5,000 measured products. Statistics count only the
   measured window. A run in which no product leaves the line for 1,000 times the longest cycle or
   travel time raises `ThroughputError` (a deadlock is a bug, not a result).
9. **Not computable** is a normal result with reasons, each with a fixed code and the station or
   transport id: `no_flow_stations`, `station_not_connected` (a flow station with no transport when
   the line has more than one), `station_cycle_missing` (its timing is not computable; the reasons
   are on the Timing tab), `travel_time_missing`, `capacity_missing` (null with no length and
   pitch, or 0), `products_per_move_unsupported`, `reject_incomplete` (a rate with no reject
   station or the reverse), `availability_incomplete` (only one of `mtbf_s` and `mttr_s`). Values
   the validator forbids that still reach the engine raise `ThroughputError`.
10. **Results** (`ThroughputResult` and its parts, in `engines/throughput.py`, not in
    `MachineDesign`, ADR 0003):
    - good products per minute at the exits, rejects per minute per reject station, products per
      minute into the line;
    - per station: working, starved, blocked and down shares of the measured time (they add up to
      1), cycles done, capacity per minute (`60 · products_per_cycle / cycle_time_s`, times the
      availability `mtbf / (mtbf + mttr)` when it breaks down) and utilisation (section D);
    - per transport: `T`, `C` and the rule that gave it, mean and maximum products on it, capacity
      per minute (`60 · C / T`) and utilisation;
    - products in the line (mean), time in the line (mean, median, 90th percentile, maximum);
    - the bottleneck (section D);
    - target check: when `target_rate_per_min` is set, the margin (rate − target) and a
      `target_rate_not_met` warning naming the bottleneck when the rate is lower;
    - the run settings, `engine_version`, the timing engine version it used, and the trace
      (section A).

### D. Bottleneck (open question 5)

The bottleneck is the station or transport with the highest **utilisation**: the products per
minute it actually carried in the measured window divided by its capacity per minute (C.10). Ties
go to the earlier node in `process_order()`, then the lower id. This is the textbook definition (the
process centre with the highest long-term utilisation: W. J. Hopp, M. L. Spearman, *Factory
Physics*, 3rd ed., Waveland 2008, chapter 7; the agent confirms the page or writes
`TODO(source)`), extended to transports so a slow belt can be the bottleneck. It works with lanes
(each lane counts what it carried), rejects (less flow downstream) and breakdowns (lower
capacity). For a serial line with no breakdowns the bottleneck runs at utilisation 1 and the line
rate equals its capacity.

### E. Results storage, service, API, diff, documents, prompt

- **Storage**: rows with `engine = 'throughput'` in the existing `revision_results` table, no
  migration (ADR 0028). `inputs_version` is the timing engine version the result used, so a timing
  change recomputes the throughput too.
- **Service** (`backend/app/services/throughput.py`), same pattern as `services/timing.py`:
  `throughput_for(storage, project_id, revision)` returns the stored row when its versions match,
  else gets the timing through `timing_for`, computes, stores and returns. Computed on first read,
  nothing backfilled (ADR 0028).
- **API**: `GET /api/projects/{id}/throughput?revision=N` (latest when omitted) returns the
  `ThroughputResult`; 404 for an unknown project or revision. No AI call on this path.
- **Diff**: `GET /api/projects/{id}/diff` gains a `throughput` block from the two stored results:
  rate before and after, bottleneck before and after, per station and per transport the
  utilisation before and after, warnings and not-computable reasons added and removed (matched by
  code and the id they name). `DesignDiff` gets an optional `throughput` field; the other fields
  are unchanged.
- **Documents** (`services/documents.py` `cycle_check`, closes the parking-lot entry): when the
  throughput is computable, one line with the computed rate and the bottleneck, and, when
  `target_rate_per_min` is set, the target and the margin; when not, its reasons. The line about
  `target_rate_text` stays as it is. Nothing else in `documents.py` changes.
- **Prompt** (`backend/app/llm/prompts.py`, prompt change: approval with this spec, open question
  4): one clause each, nothing else changes:
  - copy the required output as a number into `target_rate_per_min` (products per minute) when
    the engineer states one, as well as the words into `target_rate_text`;
  - set `products_per_cycle` from the station's design (cavities, lanes), else leave 1;
  - leave `mtbf_s` and `mttr_s` null unless the engineer states them;
  - `buffer_capacity` follows the existing rule of line 37 (only when the engineer states it).
  The AI does not see throughput results in this phase (Phase 6).

### F. Golden line (`backend/tests/golden/`), open question 3

- **The spreadsheet is the data**, same format as Phase 2 (`tests/golden/README.md`):
  `throughput_line.xlsx`, a `Line` sheet (stations: id, cycle time, products per cycle, source id
  per number; transports: id, from, to, kind, length, speed or index time, capacity or pitch,
  source id per number), a `Calculation` sheet (capacity per node, utilisation, bottleneck, line
  rate, as spreadsheet formulas) and an `Expected` sheet; plus a `Sources` sheet. Recomputed and
  saved by a spreadsheet program, never by running the engine.
- Cases, all hand-calculable: the line as given (no rejects, no breakdowns): rate = the lowest
  node capacity, utilisation of every node = rate / its capacity; the same line with one belt
  slowed until it is the bottleneck; the same line with a 10 % reject branch (good rate = 90 % of
  the input rate).
- The line (question 3): the mock cartoner, whose stations are joined by belts as this
  phase models them. Its inputs are the cartoner's values from section G, each with a public source
  or recorded as a demo value.
- The DES matches every expected value within 1 % (plan). `README.md` gets the expected values as
  a plain table, checked against the sheet by a test.

### G. Mock cartoner (`backend/app/llm/mock.py`)

- The cartoner's first answer becomes a computable line: `target_rate_per_min` from its stated
  "120 tubes/min"; belts between its stations and into the outfeed with length, speed and either a
  capacity or a product pitch; a computable cycle for `st-outfeed`. Every number comes from a
  public catalog with its source in a comment, or is recorded in the design's `assumptions` as
  "demo format value, not catalog data" (as Phase 2 did for the blister). A cylinder stroke is a
  fixed step read from a manufacturer's chart (ADR 0029).
- Only the cartoner design changes. The shared `st-outfeed` and `st-vision` stations change only
  inside the cartoner design, so the blister, filling and assembly designs and their v1 fixtures
  stay the same. The refinement still adds `st-vision` with no steps; after it the cartoner's
  throughput is not computable with `station_cycle_missing` for `st-vision`, which is honest and
  stays.
- `tests/test_migration_v2.py` keeps its one listed exception, extended to the cartoner's exported
  `cycle_time_s` and new assumptions; every other field is still compared. A deliberate
  expectation change approved with this spec, not a loosening.

### H. Frontend (UI: Greg approves a written plan before any UI code)

Step 7a is a plan only: one page with a static sketch (an image under `.context/`) and the exact
test ids. Greg says yes or no; then step 7b writes the code. The plan must cover:

- `api.ts` gets `throughput(projectId, revision)`; `types.ts` mirrors `ThroughputResult`.
- A new **Throughput** tab (`?tab=throughput`):
  - **Rate vs target**: good products per minute, the target and the margin, rejects per minute,
    the bottleneck named.
  - **Utilisation bars**: one bar per station, split into working, starved, blocked and down; the
    bottleneck marked.
  - **Transport chart**: per transport the mean and maximum products on it against its capacity,
    and its capacity rule (set or from length and pitch).
  - **Time in the line**: mean, median, 90th percentile, maximum, and products in the line.
  - **Warnings and reasons**: `target_rate_not_met` and the not-computable reasons, each naming
    its station or transport.
  - The run settings (seed, warm-up, measured products) shown, so every number has provenance
    (rule 2). SVG drawn by our code, no chart library.
- Model editor: machine field `target_rate_per_min`; station fields `products_per_cycle`, `mtbf_s`
  and `mttr_s`; the transport form's buffer label follows the new description.
- Revision diff view: the throughput block of section E.
- Playwright on the cartoner: the plan says how a second scratch backend with
  `MF_MOCK_SCENARIO=cartoner` runs next to the blister one (own ports and database, ADR 0025 rules
  unchanged) so `npm run e2e` runs both.

### I. Docs

- ADRs, each written in the step that implements it, in the same change (rule 10): **0034** the
  schema version 4 fields (section B, questions 1 and 2; step 2); **0035** the line model and the
  bottleneck definition (sections C and D, question 5; step 3); **0036** the golden line machine
  (section F, question 3; step 4). The prompt clause (question 4) is recorded in this spec.
- `docs/trace.md` (section A, step 1).
- `docs/architecture.md`: the throughput engine in the "Engines" section; "no randomness" becomes
  "seeded randomness only". `README.md`: status and roadmap ticks.
- `docs/parking-lot.md`: remove the `cycle_check` entry (done in section E); add
  `products_per_move` above 1, assembly joins, rework loops, changeover, and the blister line's
  transports (Phase 4 needs them to play the blister).
- `backend/tests/golden/README.md` (section F).

## Out of scope

- Optimisation, buffer sizing, experiment design, confidence intervals over many seeds, OEE
  reporting (plan).
- Assembly joins (several parts become one), rework loops back upstream, changeover, scheduled
  stops, shifts.
- `products_per_move` above 1, a minimum spacing between products on a belt, transport speeds
  that change in time.
- The blister, filling and assembly demo lines' transports (the blister's comes with Phase 4).
- Anything in the 3D view; the trace is written and tested, not played (Phase 4).
- AI tools such as `run_throughput` and the AI reading results (Phase 6).
- New patch operations (ADR 0024 stands). Frozen modules (`app/suppliers/`, `services/rfq.py`,
  `services/plc.py`, `services/sourcing.py`, supplier ratings).

## Tests to add

All offline (rule 6). Names are expectations; agents may adjust a name only with a line in the
report. Statistical assertions use fixed seeds and tolerances written in the test (plan).

**Throughput (`backend/tests/test_throughput.py`, step 3)**
- `test_serial_line_without_buffers_runs_at_the_slowest_station`: capacity 1 everywhere; rate =
  60 / longest cycle within 0.1 %.
- `test_large_buffers_keep_the_rate_and_products_pile_up_before_the_bottleneck`: same rate; the
  mean products on the transport before the bottleneck grows from the first half of the run to the
  second.
- `test_two_identical_lanes_double_the_rate`
- `test_reject_branch_takes_its_share`: 10 % rejects give 90 % of the input at the exit within 2 %,
  and the rejects are counted at the reject station.
- `test_littles_law_holds_after_warm_up`: products in the line = rate × time in the line, within
  2 %.
- `test_slow_belt_becomes_the_bottleneck`: rate = `60 · C / T` of that belt.
- `test_belt_capacity_comes_from_length_and_pitch_when_not_set`
- `test_products_per_cycle_multiplies_station_capacity`
- `test_breakdowns_lower_the_rate_by_the_availability`: a one-station line
  gives `availability · 60 / cycle` within 2 %.
- `test_state_shares_add_up_to_one`
- `test_bottleneck_is_the_highest_utilisation_with_tie_rule`
- `test_target_rate_not_met_names_the_bottleneck` and `test_target_rate_met_gives_no_warning`
- `test_missing_values_make_the_line_not_computable_with_reasons`: one case per reason code.
- `test_invalid_values_raise`
- `test_throughput_ignores_names` (rule 1): renaming stations and transports gives the same result.
- `test_same_seed_gives_an_identical_trace_hash` and
  `test_different_seed_gives_the_same_rate_on_a_line_without_randomness`
- `test_10000_products_through_12_stations_in_under_2_s` (plan, CI).
- Hypothesis invariants (random valid serial lines without rejects or breakdowns):
  `test_rate_never_exceeds_the_lowest_capacity`, `test_more_buffer_never_lowers_the_rate`,
  `test_a_slower_station_never_raises_the_rate`, `test_throughput_is_deterministic`.

**Trace (`backend/tests/test_trace.py`, step 3)**
- `test_trace_matches_the_documented_format`: node list, event shape, rounding, sort order, as
  `docs/trace.md` states.
- `test_each_product_moves_without_gaps`: each move of a product starts where its previous one
  ended, from `source` to `sink` or a reject station.
- `test_trace_stays_under_the_event_cap` on the 12-station line.
- `test_trace_reproduces_the_worked_example` of `docs/trace.md`.

**Schema v4 (`backend/tests/test_migration_v4.py`, step 2)**
- `test_v3_revisions_migrate_to_v4_with_defaults`
- `test_v1_and_v2_revisions_still_migrate`
- `test_old_database_opens_after_phase_3`: a committed version 3 database fixture
  (`tests/fixtures/v3/phase2.db`, built by a script next to it from the demo machines) opens, reads
  back, and its rows are not rewritten (rule 7).
- `test_version_3_project_json_imports`
- In `test_patch.py`: `test_target_rate_must_be_positive`,
  `test_products_per_cycle_is_a_whole_number_of_at_least_1` and
  `test_mtbf_and_mttr_must_be_positive` (`invalid_value`).

**Results and API (`backend/tests/test_throughput_results.py`, step 5)**
- `test_throughput_is_computed_once_then_read_from_storage`
- `test_stale_engine_or_timing_version_is_recomputed`
- `test_recompute_reproduces_the_stored_result` (ADR 0003)
- `test_results_are_deleted_with_the_project`
- `test_throughput_endpoint_returns_the_revision_result` and `test_throughput_endpoint_404`
- `test_diff_reports_rate_and_bottleneck_changes`
- `test_one_more_buffer_place_gives_the_expected_delta_sign` (plan)
- `test_editing_a_belt_speed_changes_the_rate_without_an_ai_call`: patch endpoint, the provider is
  called zero times.
- In `test_documents.py`: `test_cycle_check_shows_the_computed_rate_and_the_target`.

**Golden (`backend/tests/test_golden_throughput.py`, step 4)**
- `test_golden_line`, `test_golden_line_with_slow_belt`, `test_golden_line_with_rejects`: the
  line built from the sheet; every expected value within 1 %; same bottleneck.
- `test_every_expected_cell_has_a_saved_value`,
  `test_every_golden_input_has_a_source_or_is_marked_demo`, `test_readme_table_matches_the_sheet`
  (as Phase 2).

**Mock (`backend/tests/test_mock_provider.py`, step 6)**
- `test_cartoner_line_has_a_rate_and_a_bottleneck`
- `test_other_demo_machines_are_unchanged`
- The v1-fixture exception of section G, in `test_migration_v2.py`.

**Repo rules (`backend/tests/test_repo_rules.py`, step 3)**
- `test_engines_use_only_seeded_randomness`: files under `app/engines/` call no module-level
  `random` function, never call `hash(`, and read no clock (`time`, `datetime.now`).

**Frontend (step 7b)**
- `npm run build` passes.
- `frontend/e2e/throughput.spec.ts` on the cartoner:
  - `the throughput tab shows the computed rate and bottleneck`: the readouts equal the API values.
  - `changing a belt speed in the model editor changes the rate with no AI call`: slow a belt
    enough to make it the bottleneck; the tab shows a different rate equal to the API value, and
    no request went to a prompt endpoint.

## Order of work and parallelism

One agent per step, each on its own branch, stopping with a report after each step
(`docs/workflow.md`). Never two agents on `models.py`.

1. **Trace format** (A): `docs/trace.md` only. Opus, high. Can run in parallel with step 2.
2. **Schema v4** (B): fields, migration, patch fields, v3 database fixture, `types.ts`. Opus,
   high.
3. **Throughput engine** (C, D), SimPy dependency, trace, repo rule. Needs 1 and 2. Opus, high;
   heaviest audit.
4. **Golden line** (F). The source search can start at once (data and README only); the golden
   tests need step 3.
5. **Results storage, service, API, diff, documents, prompt clause** (E). Needs 3.
6. **Mock cartoner** (G). Needs 3 and the sourced values of 4. Sonnet, medium.
7. **Frontend**: 7a the UI plan, for Greg's approval, no code; 7b Throughput tab, editor fields,
   diff view, Playwright. Needs 5 and 6.
8. **Docs** (I): architecture, README, parking lot (the ADRs come with steps 2, 3 and 4). Sonnet,
   medium.

## Open questions for Greg (answered 2026-11-03)

Greg's answer to all of them ("ok go on" after the recommendations): take the recommended
option.

1. **Schema change.** Add a numeric required rate (`target_rate_per_min`), a count of products per
   station cycle (`products_per_cycle`, default 1), and give `buffer_capacity` the meaning
   "products the transport holds at once", as schema version 4 (section B)?
   **Answer:** yes, as recommended. Without a numeric target the software cannot say whether the
   line meets it, and without a count per cycle a station that forms ten blisters at once looks
   ten times too slow. ADR 0034.
2. **Breakdowns.** Add mean time between breakdowns and mean time to repair per station now
   (two empty fields, filled only when the engineer knows them), or leave breakdowns for later?
   **Answer:** now, as recommended. The plan lists them for this phase, and breakdowns are a main
   reason a real line makes less than its stations' cycle times promise. Leaving them empty changes
   nothing. ADR 0034.
3. **Golden line machine.** The plan keeps the public reference machine open (section 9: blister
   line or cartoner). For the throughput golden test, use the blister line or the cartoner?
   **Answer:** the cartoner, as recommended. Its stations are joined by belts, which this phase
   models directly, and it is the machine of this phase's done criterion. In a blister machine every
   station moves with one film index, and that index is already inside the forming station's cycle
   time, so modelling the film as conveyors would count it twice. The blister stays the reference
   for timing (Phase 2) and for the 3D view (Phase 4). ADR 0036.
4. **Prompt.** The AI copies the stated required rate into the new number field, sets products per
   cycle from the station's design, and leaves breakdown times empty unless the engineer states
   them (section E)?
   **Answer:** yes, as recommended. It only copies requirements and design facts; it never writes
   a computed rate (rule 3).
5. **Which station is "the bottleneck".** The station or conveyor that runs closest to its own
   capacity (highest utilisation), or the station with the longest cycle time?
   **Answer:** highest utilisation, as recommended (section D). It is the textbook definition, it
   can point at a slow belt, and it stays right with parallel lanes, rejects and breakdowns, where
   the longest cycle can be the wrong answer. ADR 0035.

Also decided in this spec: SimPy, as the plan names it; a saturated line (unlimited supply,
outfeed never blocked); blocking after service; splits to the first transport with room;
transport capacity from length and pitch when not set; `products_per_move` above 1 reported as not
supported instead of guessed; fixed run settings recorded in the result, not editable in this
phase; results computed on first read (ADR 0028); the documents rate check, which the parking lot
assigned to this phase.

## Done criteria

- `cd backend && .venv/bin/pytest -q` green, `cd frontend && npm run build` green,
  `npm run e2e` green, CI green.
- The mock cartoner shows a rate, a bottleneck and a utilisation chart on the Throughput tab;
  changing a conveyor speed in the model editor changes the rate with no AI call; the revision diff
  shows the change. Greg checks this in the running app.
- Every golden input has a public source or is marked as a demo value; the golden tests pass.
- `test_plc.py` passes unedited and no frozen file appears in any step's diff.
- Reports and audit verdicts exist for every step (`docs/workflow.md`). ADRs written for every
  decision Greg made on the open questions.

## Agent brief

SimPy only; no custom scheduler. The trace format is written before the engine. Engines are pure
functions over the model: no I/O, seeded randomness only, every formula and rule cites its source
in the docstring (book, section, page). No "approximately" code paths: an unhandled case raises,
an incomplete line is reported as not computable with its reasons. Never invent an engineering
number: write `TODO(source)` and ask. Golden expected values come from the spreadsheet, never from
running the engine. Do only what the spec says; no "while we are here" changes.
