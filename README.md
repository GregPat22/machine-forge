# Machine Forge

**Vibe-code automatic machines.** Describe a production problem ("pack 300 tablets per minute into
blisters"), get a first machine design, and refine it by prompting until it's right. Every
revision comes with a **spare-parts catalog**, and each part is compared across **your current
suppliers and external vendors** to find the best offer.

Think special-purpose machines like the ones IMA, Marchesini or Syntegon build: packaging,
filling, assembly, inspection.

> Status: **v0.3, prototype.** Design loop with live progress, revisions and diffs, realistic and
> concept 3D, 2D top view (SVG/DXF), technical documents (Word, with your company template), PLC
> skeleton (Structured Text + PLCopen XML), spare-parts catalog, supplier comparison with ratings,
> and RFQ workbooks all work end to end. CAD (STEP) export is not built
> (see [docs/output-options.md](docs/output-options.md)).

## What works today

- **Problem → machine.** The AI breaks the problem into stations along the product flow, adds
  infrastructure (frame, control cabinet, safety, utilities), and lists the components of each
  station with specs, suggested manufacturer, make/buy, wear parts, criticality (A/B/C) and
  recommended spares. It also records its assumptions and open questions.
- **Refine by prompting.** "Add vision inspection", "use Beckhoff instead of Siemens", "make it
  washdown-ready". Each prompt creates a new revision. While the AI works you see what it's doing
  (its thinking, then "writing: 6 stations, 41 components so far").
- **Revisions and diffs.** View, restore or compare any two revisions: stations and components
  added, removed or changed, field by field.
- **Realistic 3D.** A procedural render of the machine: brushed-steel base and upper cabinets,
  mechanism plates with the station's components (servo motors, cylinders with hoses, sensors,
  cameras, reels, drive wheels, valve terminals…), glass guards, HMI on an arm, stack light,
  conveyors and products moving through the line, studio lighting with soft shadows and floor
  reflections. Click a station for its components, double-click to zoom to it, save an image,
  change the accent colour. Not engineering geometry.
- **Concept 3D and 2D top view.** The same layout as simple blocks, and as a dimensioned top view
  to download as SVG or as DXF (R12, mm) for CAD. Inline or U-shape ("make the line U-shaped").
  Positions are computed by code from the station envelopes the AI proposes.
- **Technical documents.** Functional description, sequence of operations with a cycle-time vs
  throughput check, estimated I/O list with PLC sizing, recommended spare parts, a hazard
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
- **Pluggable AI.** Claude API by default; any OpenAI-compatible endpoint (Ollama, vLLM, Azure
  OpenAI) for private deployments; an offline demo engine for testing without a key.

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

1. **Suppliers** page → import `examples/price-list-example.csv`.
2. Create a blister or cartoning machine and open **Spare parts & suppliers** → **Compare with my
   price list**.
3. For external offers, add `MOUSER_API_KEY` and/or `NEXAR_CLIENT_ID` + `NEXAR_CLIENT_SECRET` to
   `backend/.env` and use **Compare with external suppliers**.

### Tests

```bash
cd backend && pytest          # 52 tests, no network or keys needed
cd frontend && npm run build  # type-check + production build
```

GitHub Actions runs both on every push.

## Project layout

```
backend/
  app/
    models.py            MachineDesign (the source of truth), catalog and sourcing types
    llm/                 provider interface, Claude, OpenAI-compatible, demo engine, prompts
    services/            designer (prompt loop), diff, layout, drawing (SVG/DXF), documents, io_points,
                         plc, spare_parts, price_list, sourcing, rfq
    suppliers/           external connectors (Mouser, Nexar)
    api/                 HTTP endpoints
    storage.py           SQLite
  tests/
frontend/src/
  pages/                 Home, ProjectPage (chat + tabs), Suppliers
  components/            Chat, DesignView, MachineRender + Layout3D (three.js), DocumentsView, PlcView,
                         SparePartsView, RevisionsView + DiffView, SupplierRatings
  render/                realistic render: materials, component models (parts), machine assembly
docs/                    architecture, output options, suppliers, AI providers
examples/                sample price list
```

## Decisions

| Date | Decision |
|---|---|
| 2026-10-20 | Private repo; standalone project. |
| 2026-10-20 | Suppliers: import your own list **and** query external vendor APIs, to compare current suppliers with other offers. |
| 2026-10-20 | AI: external model (Claude API) for now; must support private deployment for companies (provider interface). |
| 2026-10-20 | Stack: Python/FastAPI backend (keeps CadQuery/CAD and data tooling open), React/TypeScript frontend, SQLite. |
| 2026-10-20 | Next phase (v0.2): 3D concept layout + technical documents, as recommended in [output-options](docs/output-options.md). Both are derived from the design in code. |
| 2026-10-20 | v0.3: rest of the roadmap that needs no keys or decisions (diffs, 2D/DXF, PLC skeleton, ratings + RFQ, Word templates, streaming progress), plus a realistic 3D render, the long-term goal for the 3D view. |

**Open:** CAD (STEP) export, which only pays off with a template library from the mechanical team;
users and authentication (which login: local accounts or company SSO?).

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
- [x] Realistic 3D render — v0.3 (procedural; see below for the next step)
- [ ] Verify the Mouser and Nexar connectors against the live APIs (needs keys)
- [ ] More connectors (Digi-Key, RS, Farnell, TME)
- [ ] Users and authentication before any shared deployment (needs a decision)
- [ ] Realistic 3D, next level: real vendor CAD models (STEP → glTF) for catalog parts, ambient
      occlusion, per-machine-type body styles
- [ ] Test the PLCopen XML import in CODESYS / TwinCAT; Siemens SCL export
- [ ] CAD (STEP) export, with a template library

## Limits, honestly

The AI produces **concept designs**. Part numbers it suggests must be checked, and nothing here
replaces engineering, a risk assessment (ISO 12100) or validation of safety functions
(ISO 13849 / IEC 62061).
