# Machine Forge

**Vibe-code automatic machines.** Describe a production problem ("pack 300 tablets per minute into
blisters"), get a first machine design, and refine it by prompting until it's right. Every
revision comes with a **spare-parts catalog**, and each part is compared across **your current
suppliers and external vendors** to find the best offer.

Think special-purpose machines: packaging, filling, assembly, inspection.

> Status: **Phase 0 done. Phase 1 (model v2 and patch edits) built, in its final check, see
> [docs/PLAN.md](docs/PLAN.md) and [docs/specs/phase-1.md](docs/specs/phase-1.md).** The project was
> redefined on 2026-10-21: AI-assisted concept engineering with real timing, throughput,
> geometry, BOM and cost, simulated before anything is built. The v0.3 design loop, revisions and
> diffs, concept 3D, 2D top view (SVG/DXF), technical documents, PLC skeleton, spare-parts catalog
> and supplier comparison still work end to end. The v0.3 "realistic 3D" render was removed:
> it drew cabinets, hardware and products the model knew nothing about (see
> [ADR 0009](docs/adr/0009-geometry-as-data-scene-json.md)). Since Phase 1 the model can carry
> simulation data (product, process graph, mechanisms, steps) and the AI edits it in small checked
> steps. Simulation, an honest 3D view and the module library arrive with Phases 2 to 5.

## What works today

- **Problem → machine.** The AI breaks the problem into stations along the product flow, adds
  infrastructure (frame, control cabinet, safety, utilities), and lists the components of each
  station with specs, suggested manufacturer, make/buy, wear parts, criticality (A/B/C) and
  recommended spares. It also records its assumptions and open questions. The model holds the
  product (dimensions, mass, lanes), the process graph (the transports between stations), and
  per station its mechanisms (axes) and ordered steps. Where the AI does not know a value it
  leaves it empty and asks, instead of inventing a number.
- **Refine by prompting.** "Add vision inspection", "use Beckhoff instead of Siemens", "make it
  washdown-ready". Each prompt creates a new revision. While the AI works you see what it's doing
  (its thinking, then "writing: 6 stations, 41 components so far").
- **Checked edits.** The AI does not rewrite the design: it sends small edits (patches) that code
  checks before anything changes. A bad edit goes back to the AI with the exact error (three
  answers at most, `MF_MAX_REPAIR_ATTEMPTS`); if it still fails, you get a readable message and the
  design stays as it was. Values the software computes (station order, cycle time, positions)
  cannot be set by the AI.
- **Model editor.** The "Model" tab edits the same model by hand: stations, parameters,
  mechanisms, steps, components and transports. Saves go through the same checks as the AI and
  create a revision like a chat turn does.
- **Revisions and diffs.** View, restore or compare any two revisions: stations, components,
  transports, parameters, mechanisms and steps added, removed or changed, field by field.
- **Project files.** Export a project with all its revisions and chat as one JSON file and import
  it again as a new project (API only for now: `GET /api/projects/{id}/export`,
  `POST /api/projects/import`). Projects from v0.3 open and are upgraded on read.
- **Concept 3D and 2D top view.** The layout as labelled blocks (one per station envelope), and
  as a dimensioned top view to download as SVG or as DXF (R12, mm) for CAD. Inline or U-shape
  ("make the line U-shaped"). Positions are computed by code from the station envelopes the AI
  proposes. Nothing is drawn that the model does not contain.
- **Technical documents.** Functional description, sequence of operations with each station's
  cycle time (the comparison with the required rate returns with the throughput engine), I/O list
  from each component's signals with PLC sizing, recommended spare parts, a hazard
  checklist along ISO 12100 and the safety functions to specify. Export to Word, Markdown or
  print/PDF, optionally on your company's Word template (headers, footers, styles, cover page).
  They are derived from the design by rules, so they never claim compliance.
- **PLC skeleton.** IEC 61131-3 Structured Text from the design: a PackML state machine, one
  function block per station with step sequences for its actuators and timeouts, a global I/O
  list and a main program that chains the stations. Download as .st files or PLCopen XML
  (validated against the TC6 v2.01 schema). No safety logic, by design.
- **Spare-parts catalog.** An aggregated BOM per revision: identical parts are merged across
  stations, with a filter for parts to stock. CSV export.
- **Supplier comparison.** Import your own price list (Excel/CSV, English or Italian headers) and
  compare it with external offers (Mouser, Nexar/Octopart). Shows current vs. best supplier per
  part, scored on price, lead time, availability and your own supplier ratings, with potential
  savings. **RFQ workbooks**: one Excel sheet per supplier (no prices go out); import the answered
  file as it is.
- **Pluggable AI.** Claude API by default; native OpenAI and Google Gemini; any OpenAI-compatible
  endpoint (Ollama, vLLM, Azure OpenAI) for private deployments; an offline demo engine for
  testing without a key. Every answer is checked by our code, whatever the provider.

## Quick start

Requirements: **Python 3.11+**, **Node.js 20+**, git.

```bash
git clone https://github.com/GregPat22/machine-forge.git
cd machine-forge
```

### 1. Backend (FastAPI, port 8000)

macOS / Linux:
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # then edit .env (see "Configure the AI")
uvicorn app.main:create_app --factory --reload --reload-dir app --timeout-graceful-shutdown 2
```

Windows (PowerShell):
```powershell
cd backend
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env   # then edit .env
uvicorn app.main:create_app --factory --reload --reload-dir app --timeout-graceful-shutdown 2
```

(`--reload-dir app` and `--timeout-graceful-shutdown` keep auto-reload from hanging when packages
are installed or the dev proxy keeps connections open.)

### 2. Frontend (React + Vite, port 5173)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

### Configure the AI

Edit `backend/.env`:

```ini
MF_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...     # from console.anthropic.com
```

No key yet? Set `MF_LLM_PROVIDER=mock` to try the whole flow with the offline demo engine.
For private / on-premise models see [docs/ai-providers.md](docs/ai-providers.md).

### Try the supplier comparison

1. **Suppliers** page → import your own price list (Excel/CSV; the accepted columns are in
   [docs/suppliers.md](docs/suppliers.md)).
2. Create a blister or cartoning machine and open **Spare parts & suppliers** → **Compare with my
   price list**.
3. For external offers, add `MOUSER_API_KEY` and/or `NEXAR_CLIENT_ID` + `NEXAR_CLIENT_SECRET` to
   `backend/.env` and use **Compare with external suppliers**.

### Tests

```bash
cd backend && pytest          # no network or keys needed
cd frontend && npm run build  # type-check + production build
cd frontend && npm run e2e    # browser test of the model editor (once: npx playwright install chromium)
```

GitHub Actions runs all three on every push. The browser test starts its own scratch backend with
the demo engine, so it never touches your data ([ADR 0025](docs/adr/0025-playwright-end-to-end-test.md)).

## Project layout

```
backend/
  app/
    models.py            MachineDesign v2 (the source of truth), catalog and sourcing types
    migrations/          the v1 design shape, used only to load old revisions
    llm/                 provider interface, Claude, OpenAI, Gemini, OpenAI-compatible, demo engine, prompts
    services/            designer (prompt loop + repair), patch (edits and their checks), diff, layout,
                         drawing (SVG/DXF), documents, io_points, plc, spare_parts, price_list,
                         sourcing, rfq, spreadsheet, project_json (export/import)
    suppliers/           external connectors (Mouser, Nexar)
    api/                 HTTP endpoints
    storage.py           SQLite
  tests/
frontend/src/
  pages/                 Home, ProjectPage (chat + tabs), Suppliers
  components/            Chat, DesignView, ModelEditor, Layout3D (three.js, concept blocks), LayoutView,
                         DocumentsView, PlcView, SparePartsView, RevisionsView + DiffView,
                         SupplierRatings
frontend/e2e/            Playwright browser test
docs/                    PLAN (read first), engineering-rules, specs/ (one per phase), adr/,
                         architecture, output options, suppliers, AI providers
```

## Decisions

| Date | Decision |
|---|---|
| 2026-10-20 | Private repo; standalone project. |
| 2026-10-20 | Suppliers: import your own list **and** query external vendor APIs, to compare current suppliers with other offers. |
| 2026-10-20 | AI: external model (Claude API) for now; must support private deployment for companies (provider interface). |
| 2026-10-20 | Stack: Python/FastAPI backend (keeps CadQuery/CAD and data tooling open), React/TypeScript frontend, SQLite. |
| 2026-10-20 | Next phase (v0.2): 3D concept layout + technical documents, as recommended in [output-options](docs/output-options.md). Both are derived from the design in code. |
| 2026-10-20 | v0.3: rest of the roadmap that needs no keys or decisions (diffs, 2D/DXF, PLC skeleton, ratings + RFQ, Word templates, streaming progress), plus a realistic 3D render. |
| 2026-10-21 | **Redefinition, see [docs/PLAN.md](docs/PLAN.md) and [docs/adr/](docs/adr/).** Concept engineering with simulation (throughput + mechanism timing), module library, STEP/Excel/AutomationML import, any AI provider, AGPL-3.0 + CLA. Realistic render deleted. Supplier connectors, ratings, RFQ workbooks and the PLC skeleton are **frozen** (bug fixes only). |
| 2026-10-28 | **Repository public** ([ADR 0023](docs/adr/0023-public-repository.md)). Replaces the private-repo decision of 2026-10-20. Example price list removed. |

**Open:** see `docs/PLAN.md` section 9.

## Roadmap

- [x] 3D concept layout (inline / U-shape) — v0.2
- [x] Technical documents with Word export — v0.2
- [x] PLC skeleton (PackML state machine per station, .st + PLCopen XML) — v0.3
- [x] Company document templates (your own .docx) — v0.3
- [x] 2D top-view drawing (SVG/DXF) — v0.3
- [x] RFQ workbooks for parts without APIs, re-importable — v0.3
- [x] Supplier rating (quality, delivery reliability) in the score — v0.3
- [x] Revision diff view — v0.3
- [x] Streaming progress while the AI designs — v0.3
- [x] Realistic 3D render — v0.3, **removed 2026-10-21** (decoration, not a model)

The plan from here is `docs/PLAN.md`, section 5:

- [x] Phase 0: cleanup and guardrails — done 2026-10-21
- [ ] Phase 1: model v2 (product, process graph, mechanisms, structured roles), patch-based AI edits, OpenAI + Gemini providers
- [ ] Phase 2: timing engine (motion profiles → cycle time → timing diagram)
- [ ] Phase 3: throughput engine (discrete-event, SimPy) with results diffed per revision
- [ ] Phase 4: editable layout, scene JSON, react-three-fiber viewer, simulation playback
- [ ] Phase 5: module library, STEP → glTF and Excel BOM import
- [ ] Phase 6: AI tools, what-if loop, evaluation harness
- [ ] Phase 7: AutomationML, Docker Compose, minimal auth, docs

Frozen (bug fixes only): Mouser/Nexar connectors, more connectors, supplier ratings, RFQ
workbooks, PLC skeleton (CODESYS/TwinCAT import test, Siemens SCL). CAD (STEP) export stays out.

## Limits, honestly

The AI produces **concept designs**. Part numbers it suggests must be checked, and nothing here
replaces engineering, a risk assessment (ISO 12100) or validation of safety functions
(ISO 13849 / IEC 62061).
