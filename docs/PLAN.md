# Machine Forge: plan v1.0

Written 2026-10-21 after a full review of the v0.3 codebase. This is the reference for every
coding session (Claude Code, ChatGPT, agents). Read it before touching the repo. Decisions here
override older text in `README.md` and `docs/output-options.md` until those are updated (Phase 0).

## 1. What we are building

**Open-source, AI-assisted concept engineering for special-purpose automatic machines.**

An R&D or concept engineer describes a production problem, or imports an existing machine, and
works with the AI on a *machine model* that carries real geometry envelopes, mechanisms, timing,
product flow, BOM and cost. The software computes what the AI must never guess: cycle times,
throughput, bottlenecks, footprint, dimensions, I/O, documents. Every change is a revision, and
every revision can be compared with any other, including its simulation results. The user sees
the machine in 3D and watches the simulation play on it before anything is built.

Target users: machine builders (packaging, filling, assembly, inspection, handling) at the
concept and modification stage. Design new machines, modify existing ones, run what-if
("what happens to cycle time and cost if I replace this pick-and-place with a two-axis gantry").

### What it is not

- Not a CAD system. It reads STEP, it does not produce engineering geometry.
- Not a physics engine. No collisions, no dynamics, no FEM.
- Not a PLC IDE and never a source of safety logic.
- Not a renderer. Visual output exists to show the model and the simulation, never to impress.

### Market position (honest)

Throughput simulation (Plant Simulation, FlexSim, AnyLogic, open-source JaamSim) and
mechatronic simulation (NX MCD, Emulate3D, Visual Components) exist and are mature for detailed
engineering, closed, and priced per seat in the tens of thousands. Nobody offers the concept-stage
loop where one prompt moves time, throughput, footprint, BOM and cost together, and nobody offers
it open source. The timing diagram, the artifact that ties mechanisms to cycle time, is often
done in Excel; dedicated tools exist but are niche. That is the gap.

## 2. Verdict on the v0.3 codebase

### Keep as-is

- The architecture principle: `MachineDesign` is the only thing the AI edits; every output is
  computed from it by code. This is the anti-slop foundation and stays.
- Revisions, diff, restore. Streaming progress. Provider abstraction with strict JSON schema
  (`app/schema.py`). Prompt caching. Offline tests with `MockProvider` and `MockTransport`.
- Rule-based technical documents, I/O estimate, DXF/SVG top view (adapted to the new model).
- Spare-parts catalog and price-list import: they are the **cost** dimension of what-if.

### Keep, frozen (no new work, no removal)

- Supplier connectors (Mouser, Nexar), supplier ratings, RFQ workbooks.
- PLC skeleton (Structured Text + PLCopen XML). Later it can be generated from the same step
  sequences the simulation uses; not now.

### Replace

1. **Realistic 3D render** (`frontend/src/render/*`, `components/MachineRender.tsx`,
   ~1,600 lines). Procedural decoration: identical "balcony" cabinets for every process
   station, components placed on a grid by a priority table, empty cells filled with random fake
   hardware (`buildFiller`), product shape picked by regex on the machine name, reels drawn when
   the station text matches `/film|reel|web/`, products moving at a hardcoded 0.16 m/s. Nothing
   derives from geometry, kinematics or time. **Delete in Phase 0.** The concept block view
   (`Layout3D.tsx`) is honest and becomes the base of the new viewer.
2. **The model has no simulation data.** A station is an envelope, an integer `sequence` and
   one `cycle_time_s`. No product definition, no transport model, no mechanisms, no buffers, no
   lanes, no branches. `throughput` is free text parsed by regex. Replaced by the model v2
   (Phase 1).
3. **Full design on every AI turn.** Fine at 230 lines of schema, not with geometry and timing.
   Replaced by patch-based edits validated by code (Phase 1).
4. **Behaviour from display names.** `io_points`, `plc` and the render key off regexes over
   component names ("thermocouple", "ejector", "gun"). Replaced by structured fields the AI
   fills (`role`, `signals`, `motion`). Rule: no logic ever reads `.name` to decide behaviour.
5. **No import.** Only a Word template. Replaced by STEP, Excel BOM, AutomationML and the
   module library (Phases 5 and 7).

## 3. Decisions

| # | Decision | Why |
|---|---|---|
| D1 | Both simulation kinds, concept fidelity. **A = throughput (discrete-event)** first, **B = mechanism timing (motion profiles → cycle time → timing diagram)** second. No physics, no collision. Deep B (cam synthesis, swept-volume interference) is roadmap, gated on user demand. | A is computable from the data the AI can produce on day one; B-lite replaces the timing diagram often kept in Excel; deep B competes with NX MCD and never ends. |
| D2 | **Module library** is the core anti-slop mechanism. The AI selects and parametrizes library modules; it invents a custom station only when nothing fits, and the UI marks it as unverified. | Real parameters come from the library, not from the model's imagination. "Modify an existing machine" starts from real data. |
| D3 | Simulation results are stored per revision and **diffed** like the BOM. | What-if is the main use case. |
| D4 | Import priority: **STEP** (geometry, every CAD exports it) → **Excel/CSV BOM** → **AutomationML** (IEC 62714, neutral topology/layout) → PLCopen XML (exists). Project JSON export/import from Phase 1. | SolidWorks dominates SME machine builders; STEP covers SolidWorks, Inventor, NX, Creo. AutomationML is the only open format Siemens and Visual Components both speak. |
| D5 | **No confidential machine data in the repo, ever.** Calibration uses a public reference machine built from brochures, vendor catalogs and textbooks. | Git history is forever; IP contamination kills a future company and the open-source project. |
| D6 | **Any AI.** Providers: Anthropic (native), OpenAI (native, Responses API), Google Gemini (native), OpenAI-compatible (Ollama, vLLM, LM Studio, Azure, OpenRouter). Correctness never depends on tool use or strict schemas; weak models fall back to validate-and-repair. | Companies will demand self-hosted models. |
| D7 | **License: AGPL-3.0 with a CLA** (contributors grant relicensing rights). Open-core or commercial dual licensing later. | Open source now, company later. AGPL blocks closed SaaS forks, internal self-hosting is unaffected, the CLA keeps the Apache-2.0 door open. Confirm with a lawyer before the first external contribution. |
| D8 | Stack: **Python/FastAPI** backend (SimPy, numpy, OCP), **React + TypeScript** frontend moving to **react-three-fiber + drei**, SQLite now with a `workspace_id` on every table, Postgres when multi-user. | Python has the DES and CAD ecosystems; Node does not. R3F renders a scene from data declaratively, which is exactly the "scene JSON" design. |
| D9 | Geometry pipeline: backend produces a **scene JSON** (placed glTF assets + labelled parametric envelopes); frontend only renders it. STEP → glTF conversion server-side via OCP/cadquery as an optional extra (`pip install machine-forge[cad]`), with direct glTF upload as the fallback. | Geometry becomes data, not frontend code. OCCT is heavy, so it is optional. |
| D10 | Vendor CAD models and company libraries are **per-installation data**, never committed to the repo. The public seed library uses only our own parametric envelopes and permissively licensed assets. | Vendor CAD terms (TraceParts, PARTcommunity) forbid redistribution. |

## 4. Target architecture (v1.0)

```
frontend (React + R3F)                 backend (FastAPI)
  Chat / what-if                          AI layer
  Model editor (stations, params)           providers: anthropic | openai | gemini | openai_compatible | mock
  3D viewer + timeline playback             patch-based edits, validated by code
  Timing diagram, throughput charts         tools: search_library, run_timing, run_throughput, check_layout
  Revision diff (BOM + sim results)         explanation with citations to result fields
  Library manager, imports                  eval harness
                                          Model v2 (source of truth)
                                            product, process graph, stations, mechanisms, components, library refs
                                          Engines (deterministic, seeded, tested)
                                            timing   : motion profiles -> step durations -> station cycle -> timing diagram
                                            throughput: SimPy DES over the process graph -> rates, bottleneck, WIP, trace
                                            layout   : placement (auto + manual), footprint, clearances, overlaps
                                            scene    : design + layout + trace -> scene JSON + animation tracks
                                            bom/cost, documents, io_points, plc, drawing (adapted)
                                          Library
                                            modules: parameters, timing formulas, envelope/glTF, BOM template
                                          Import / export
                                            STEP -> glTF, Excel BOM, AutomationML, PLCopen XML, project JSON
                                          Storage: SQLite (workspace_id everywhere)
```

### Model v2 (sketch, finalized in Phase 1)

- **Product**: name, dimensions (mm), mass (g), orientation, lanes, carrier/pitch.
- **Process graph**: nodes are stations, edges are transports. Replaces `sequence: int`.
  Edges carry type (belt, indexing, rotary, pick-place, gravity), length, speed or index time,
  capacity (buffer), and the product count per move. Branches for reject and merge for lanes.
- **Station**: library ref (or `custom`), parameters, envelope, placement (pose, user-editable),
  **mechanisms** (axes: linear or rotary, stroke, max speed, acceleration or cam profile, dwell),
  **steps** (ordered operations, each either a motion of an axis or a fixed-duration process,
  with parallel groups), components, target cycle time, computed cycle time (stored result).
- **Component**: structured `role` (actuator, sensor, drive, controller, tooling, structure,
  consumable), `signals` (DI/DO/AI/AO/axis/fieldbus counts), `motion` link to a mechanism,
  specs, manufacturer, part number, make/buy, wear, criticality, spares. Display `name` is
  never read by any logic.
- **Design**: product, graph, stations, utilities, assumptions, open questions,
  `schema_version`, and per revision the stored **results** (timing, throughput, layout checks).
- **AI edit** = list of patch operations (`add_station`, `remove_station`, `set_param`,
  `replace_component`, `connect`, `set_product`, ...). Code validates each operation against the
  schema and the library, applies it, recomputes results, and returns errors the AI can fix.

## 5. Phases

Each phase lists: goal, scope, out of scope, tests, done criteria, agent brief. Phases are
sequential. A phase is done when its tests pass in CI and the done criteria are checked by Greg
in the running app. Nothing from a later phase starts early.

### Phase 0: Cleanup and guardrails (about 1 week)

**Goal.** Remove what misleads, write down the rules, make the repo ready for agents.

**Scope.**
- Delete `frontend/src/render/*` and `components/MachineRender.tsx`; keep `Layout3D.tsx` as
  the only 3D view. Remove the `?tab=layout&focus=` note from `CLAUDE.md`.
- Mark connectors, ratings and RFQ as frozen in `README.md` and `docs/architecture.md`.
- Add `LICENSE` (AGPL-3.0), `CONTRIBUTING.md`, CLA text (or DCO + relicensing clause).
- Write `docs/engineering-rules.md` (Section 7 of this file, expanded) and link it from
  `CLAUDE.md`. Add `docs/adr/` with one ADR per decision D1 to D10.
- Add a `workspace_id` column to every table (default workspace), with a migration.
- Add `schema_version` to stored designs (v1 = current).
- Update `README.md`: status, what was removed and why, the roadmap from this plan.

**Out of scope.** Any new feature.

**Tests.** Existing backend suite green. `npm run build` green. A test that fails if any file
under `frontend/src` imports from `render/`. A migration test that opens a v0.3 database copy
and reads all projects.

**Done when.** The app runs with the concept layout only, no visual regressions elsewhere,
CI green, docs updated.

**Agent brief.** Pure removal and documentation. No refactors "while we are here".

### Phase 1: Model v2 and patch-based AI edits (2 to 3 weeks)

**Goal.** A schema that can carry simulation, and an AI loop that edits it safely.

**Scope.**
- `models.py` v2 as in Section 4. Pydantic, strict-schema compatible (no free dicts, no
  numeric bounds in the schema; bounds are enforced in code with clear messages).
- Migration v1 → v2: `sequence` becomes a linear graph with default belt transports; `cycle_time_s`
  becomes a single fixed-duration step; categories map to roles; envelopes carried over.
- Patch operations and a validator (`services/patch.py`) that applies them and returns
  structured errors. The AI receives errors and retries up to N times.
- Prompts rewritten: the AI proposes structure, parameters, components and assumptions; it
  never writes coordinates, durations that are computable, or results.
- Project JSON export/import (own versioned format).
- `MockProvider` rewritten to emit v2 patches for the demo machines.
- Frontend: types mirror v2; a structured **model editor** (station list, parameters,
  mechanisms, steps, components) alongside the chat, so engineers can edit without prompting.
- Providers: add native OpenAI and Gemini; capability flags (`strict_schema`, `tools`,
  `thinking`); shared validate-and-repair loop for providers without strict mode.

**Out of scope.** Engines, 3D, library.

**Tests.**
- Migration: every fixture revision (v0.3 database copy, mock outputs) migrates and round-trips
  through JSON without loss of the v1 fields.
- Property tests (Hypothesis): random valid graphs stay valid after random valid patches;
  invalid patches are rejected with the right error code.
- Schema compatibility: the JSON schema is accepted by Anthropic strict mode, OpenAI strict mode
  and a plain JSON-mode validator (recorded fixtures, `MockTransport`).
- Provider tests with recorded payloads for OpenAI and Gemini (no network).
- Repair loop: a scripted provider returns two invalid answers then a valid one; the loop ends
  with a valid design and the attempts are logged.
- Frontend: `npm run build`; a Playwright smoke test that creates a demo project with the mock
  and edits a parameter in the editor.

**Done when.** A v0.3 project opens as v2, the chat produces patches, the editor edits the same
model, and one prompt that asks for something impossible returns a readable error instead of a
silent bad design.

**Agent brief.** Schema first, tests second, prompts third. Keep `MockProvider` honest (no
hidden shortcuts that only work for the demo prompts).

### Phase 2: Timing engine, simulation B-lite (2 weeks)

**Goal.** Cycle time per station computed from mechanisms and steps, shown as a timing diagram.

**Scope.**
- `engines/motion.py`: trapezoidal and S-curve (jerk-limited) point-to-point profiles. Inputs:
  distance, max speed, acceleration (and jerk). Outputs: time, and sampled position/velocity for
  animation. Rotary axes in degrees.
- `engines/timing.py`: steps → durations (motion-derived or fixed) → critical path over parallel
  groups → station cycle time, idle time, utilisation per axis → **timing diagram** (one row per
  axis/step, one cycle).
- Target vs computed: warnings when a station cannot meet the required cycle, with the limiting
  step named.
- Plausibility bounds per component role from a public catalog table (`data/catalog_bounds.yaml`:
  pneumatic cylinder speeds, servo accelerations, indexing table index times, from vendor
  catalogs with the source URL per row). Parameters outside bounds raise a warning, never a
  silent correction.
- Frontend: timing diagram (Gantt per station), cycle-time check panel, warnings list.

**Out of scope.** Cam profile synthesis, electronic cam tables, interference.

**Tests.**
- Closed-form: trapezoidal time for `s, v, a` equals the textbook formula to 1e-9; triangular
  case when the speed is never reached; S-curve reduces to trapezoidal when jerk → ∞.
- Golden stations hand-calculated in a spreadsheet committed under `tests/golden/` (pick-and-place
  with two axes and a dwell, indexing table, sealing station with heat dwell): engine output
  within 1e-6 of the sheet.
- Invariants: cycle time ≥ longest single step; parallel steps never shorten the critical path
  below the longest branch; removing a step never increases cycle time.
- Bounds: a servo acceleration of 500 m/s² produces a warning with the catalog row cited.
- UI: Playwright checks that the diagram's longest bar matches the computed cycle to the pixel
  tolerance of the scale.

**Done when.** For the mock blister machine, every station shows a computed cycle time with its
limiting step, and changing a stroke in the editor changes the time without any AI call.

**Agent brief.** The engine is pure functions over the model, no I/O. Every formula cites its
source in a comment (textbook or standard). No "approximately" code paths: if a case is not
handled, raise.

### Phase 3: Throughput engine, simulation A (2 to 3 weeks)

**Goal.** Pieces per minute, bottleneck, blocking/starving, WIP and time-in-system from the
process graph, with an event trace the 3D view can play.

**Scope.**
- `engines/throughput.py` on **SimPy**: stations as resources with the Phase 2 cycle times,
  transports with travel time and capacity (buffers), lanes and product-per-cycle counts,
  reject branches with a rate, optional MTBF/MTTR and changeover. Seeded, deterministic.
- Outputs: steady-state rate, per-station utilisation (busy/blocked/starved/down), buffer
  occupancy, WIP, time-in-system distribution, bottleneck (the station whose capacity bounds the
  line), warm-up excluded.
- **Trace**: ordered events `(t, piece_id, from, to)` compact enough to store per revision.
- Results stored on the revision; **what-if diff**: revision A vs B shows rate, bottleneck and
  utilisation deltas next to the BOM/cost deltas.
- Frontend: throughput panel (rate vs target, utilisation bars, buffer chart), diff view extended.

**Out of scope.** Stochastic experiment design, optimisation, OEE reporting.

**Tests.**
- Analytic cases: serial line, no buffers → rate = 1 / max cycle; infinite buffers → same rate,
  WIP grows at the bottleneck; two identical parallel lanes → double rate; a 10 % reject branch
  → 90 % of input at the outfeed; Little's law (WIP = rate × time-in-system) within 2 % after
  warm-up.
- Determinism: same seed, identical trace hash. Different seed, same steady-state rate within
  tolerance for the deterministic cases.
- Performance: 10,000 pieces through a 12-station line in under 2 s on CI.
- Golden line: the public reference machine (Section 6) has a spreadsheet model under
  `tests/golden/`; DES results match it within 1 %.
- Diff: two revisions differing by one buffer capacity produce the expected delta sign.

**Done when.** The mock cartoner shows a rate, a bottleneck and a utilisation chart; changing a
conveyor speed in the editor changes the rate; the diff view shows the change.

**Agent brief.** SimPy only; no custom scheduler. Trace format documented in `docs/trace.md`
before code. Statistical assertions use fixed seeds and tolerances written in the test.

### Phase 4: Layout v2, scene and playback (3 weeks)

**Goal.** An honest 3D view: real envelopes, editable placement, dimensions measured from
geometry, and the simulation playing on it.

**Scope.**
- `engines/layout.py` v2: auto styles inline, U, L, rotary; placement is **stored and
  user-editable** (drag in 3D, numeric in the editor); checks: overlaps, aisle and operator
  clearances (configurable), footprint from actual placed geometry.
- `engines/scene.py`: design + layout + results → **scene JSON**: per station a glTF asset
  reference (from the library, Phase 5) or a labelled parametric envelope (box/cylinder with
  the station name and dimensions), transports as paths, mechanisms as animatable nodes with
  axis definitions. Animation tracks: pieces from the DES trace, axes from Phase 2 profiles.
- Frontend: rewrite the viewer on **react-three-fiber + drei** (`GLTF` loader,
  `TransformControls` for dragging, orthographic/perspective toggle, measured dimension
  overlays). **Timeline** with play/pause/scrub at simulated time; pieces move exactly when the
  trace says. Station selection shows parameters, components, cycle time, utilisation.
- Dimension overlays read bounding boxes from the scene, never from typed text.
- Keep SVG/DXF top view, generated from the same layout.

**Out of scope.** Materials, lighting beyond a neutral studio, anything decorative. No product
shapes beyond the product's own box/cylinder dimensions.

**Tests.**
- Layout invariants: no two placed envelopes overlap after auto-layout; clearance violations are
  reported for a deliberately tight fixture; footprint equals the hull of placed boxes.
- Scene snapshots: golden scene JSON per mock machine, diffed in CI (fail on unintended change).
- Trace playback: at time t the piece's position in the scene equals the interpolation between
  the trace's `from`/`to` nodes (unit test on the interpolation function).
- Playwright: load mock project, drag a station, see footprint update; scrub the timeline and
  see the time readout change; select a station and read its cycle time.
- A test that fails if any file under `frontend/src` contains a regex over `design.name`,
  `station.name` or `component.name`.

**Done when.** Greg opens the mock blister machine, drags a station, the footprint and the DXF
update, presses play and watches pieces move at the simulated rate.

**Agent brief.** The viewer renders scene JSON and nothing else. If geometry is unknown, draw a
labelled envelope. No fillers, no regex, no random seeds in visuals.

### Phase 5: Module library and imports (3 to 4 weeks)

**Goal.** The AI composes from real modules; companies bring their own.

**Scope.**
- Library schema (`models/library.py`): module id, kind, parameters with ranges and units,
  timing formula (reference to a Phase 2 pattern with parameter mapping), envelope formula or
  glTF asset, mount frames (in/out product points), BOM template with roles and signals,
  source and license fields.
- Public **seed library** (12 to 15 modules, our own parametric envelopes): infeed timing screw
  + star wheel, belt conveyor, indexing conveyor, rotary indexing table, two-axis pick-and-place,
  three-axis gantry, thermoforming station, sealing station, punching station, labeller,
  checkweigher, vision inspection, reject pusher, carton magazine + erector, hot-melt flap
  closer.
- Company library: CRUD in the UI, per workspace, stored outside the repo.
- **STEP → glTF** import (`machine-forge[cad]`, OCP/cadquery): mesh, bounding box, optional
  mount frame picking in the viewer. Direct glTF upload as fallback.
- **Excel/CSV BOM import**: AI-assisted column mapping (EN/IT headers), user confirms, rows
  become components with roles; unmapped rows kept as `other` and flagged.
- AI loop: `search_library` tool (or injected catalog summary for providers without tools);
  prompt rule: library module first, custom station only with a stated reason; custom stations
  flagged `unverified` in the UI and in documents.

**Out of scope.** Vendor CAD downloads, PARTcommunity/TraceParts integrations, kinematic rigs
inside imported CAD.

**Tests.**
- Library validation: every seed module instantiates across its full parameter range without
  errors; timing and envelope formulas return finite values.
- STEP fixtures: permissively licensed sample STEP files (OCCT/FreeCAD test data) convert, and
  the bounding box matches known dimensions within 0.1 mm.
- BOM import fixtures in English and Italian; a messy sheet with merged headers maps with the
  expected warnings.
- AI eval: 20 golden prompts; library hit rate ≥ 80 % with the mock and recorded live fixtures;
  every custom station carries a reason.
- Playwright: import a STEP, see it placed with correct dimensions; import a BOM, see components.

**Done when.** A company can upload a STEP of their station, give it parameters and a BOM, and
the AI uses it in a new machine with correct dimensions and timing.

**Agent brief.** Library assets are data. No module logic in code paths except formula
evaluation. Imported files are untrusted: parse in isolation, size limits, no code execution.

### Phase 6: AI tools, what-if loop and evaluation (2 weeks)

**Goal.** Propose → compute → explain, across providers, measured.

**Scope.**
- Tools: `search_library`, `run_timing`, `run_throughput`, `check_layout`,
  `get_component_specs`. Native tool use where supported; for other providers a plan/act loop
  where the model emits a JSON action and the server executes it.
- Explanation step: the reply quotes only numbers present in the results object; the UI links
  each number to its source panel.
- What-if by prompt: "compare with revision 3" produces the diff view and a short commentary.
- Eval harness (`evals/`): golden prompts and expected outcomes (patch validity, target rate
  met, library usage, no uncited numbers). Runs in CI with the mock; nightly with live providers
  when keys are present.

**Out of scope.** Autonomous multi-step optimisation.

**Tests.**
- Citation check: a unit test extracts every number from a reply and asserts it exists in the
  results object or the design; a fixture reply with an invented number fails.
- Tool loop with a scripted provider: tool call → result → final patch; errors mid-loop are
  surfaced, never swallowed.
- Eval thresholds in CI: patch validity ≥ 95 %, uncited numbers = 0, library hit rate ≥ 80 %.

**Done when.** On the three mock machines, the AI's replies contain no number that the engines
did not compute, with any provider configured.

**Agent brief.** The AI explains; the engines compute. If a provider cannot do tools, degrade to
the plan/act loop, never to "let the model estimate".

### Phase 7: Interchange, deployment, multi-user basics (2 to 3 weeks)

**Scope.**
- **AutomationML** export (CAEX topology: stations, transports, placements; PLCopen XML attached)
  and import of topology/placement. Validated against the CAEX schema.
- Docker Compose for self-hosting (backend, frontend, optional Ollama). One-command start.
- Minimal auth: local accounts, workspaces, roles (viewer/editor). SSO later.
- Documentation site (`docs/`): user guide, library authoring guide, provider setup, import guide.

**Tests.** AML files validate against the schema; export → import round-trip preserves topology
and placements; manual acceptance: open the AML in Visual Components or AutomationML Editor;
Docker e2e in CI (compose up, create mock project, run throughput).

**Done when.** A stranger follows the README and runs a what-if on their own machine in 15 minutes.

### Roadmap after v1.0 (not scheduled)

- Deep B: cam profile synthesis (SVAJ), electronic cam tables for Siemens/Beckhoff, swept-volume
  interference checks with OCCT.
- PLC generation from the simulated step sequences (same model drives sim and code).
- Stochastic experiments and optimisation (buffer sizing, lane count).
- Vendor CAD integrations where terms allow.
- Postgres, SSO, audit trail.

## 6. The public reference machine

A "golden blister line" used for calibration and golden tests, built **only from public
sources**, each cited in `tests/golden/README.md`: throughput, footprint and power from
manufacturers' brochures; actuator speeds, accelerations and index times from Festo, SMC, SEW,
Weiss/Camco catalogs; motion formulas from standard texts. A spreadsheet model of its cycle time
and throughput is committed next to the engine tests. Nothing from any employer, customer or
NDA source enters the repo, the issue tracker or the commit history.

## 7. Engineering rules (the anti-slop contract)

These go into `docs/engineering-rules.md` and `CLAUDE.md`. Reviewers reject PRs that break them.

1. **No behaviour from display names.** Logic reads `role`, `signals`, `motion`, `kind`, never
   `.name` or free text. A CI test greps for it.
2. **Every number has provenance.** Anything shown to the user is either a model field or the
   output of a named engine function. The UI can show the source.
3. **The AI never writes** coordinates, computable durations, rates, dimensions derived from
   geometry, or compliance statements. It proposes structure, parameters, components, reasons.
4. **No decorative geometry.** Unknown geometry is a labelled envelope. No fillers, no random
   hardware, no product shapes from regex.
5. **Engines are deterministic and pure.** Seeded, no I/O, formulas cite their source, unhandled
   cases raise instead of approximating.
6. **Tests need no network or keys.** Recorded payloads and mock providers only. Live evals are
   separate and optional.
7. **Model changes ship with defaults, a migration, and a `schema_version` bump.** Every new
   field on a stored model has a default value, a migration step brings old data up to date,
   and a test opens a database from the previous version and checks that the data still reads back.
8. **Frozen modules stay frozen.** Connectors, ratings, RFQ, PLC: bug fixes only.
9. **One phase at a time, tests before code.** Each phase gets a spec file under
   `docs/specs/phase-N.md` with the acceptance tests listed; agents implement to the tests.
10. **Small PRs, one concern, docs and ADR updated in the same PR.**
11. **Untrusted inputs** (STEP, Excel, glTF, AML) are parsed with size limits, in isolation,
    never executed.
12. **No confidential data**, see Section 6.

## 8. How to brief Opus and agents

- Start every session with: "Read `docs/PLAN.md`, `docs/engineering-rules.md`, and
  `docs/specs/phase-N.md`. We are in Phase N. Do only what the spec says."
- The spec file for a phase is written first (by Greg with Claude), and contains: scope, the
  exact tests to add (names and assertions), files expected to change, and the done criteria.
- Implementation order inside a phase: schema/types → engine or service with unit tests →
  API → frontend → Playwright → docs. Stop and report after each step.
- Use `/code-review` before every merge, with the rules in Section 7 as the checklist.
- When an agent is unsure about a domain value (a speed, a formula), it must leave a `TODO(source)`
  and ask, not invent. Invented engineering numbers are a review failure.
- Subagents only for parallel, independent, test-backed work (e.g. one on the engine, one on
  the recorded provider fixtures). Never two agents on the same model file.

## 9. Open items to confirm

- D7 license wording and CLA vs DCO: confirm with a lawyer before the first external PR.
- Phase 4 viewer: react-three-fiber (recommended) vs staying on imperative three.js.
- Public reference machine type: blister line (recommended, matches the mock) or cartoner.
