# Machine Forge

**Vibe-code automatic machines.** Describe a production problem ("pack 300 tablets per minute into
blisters"), get a first machine design, and refine it by prompting until it's right. Every
revision comes with a **spare-parts catalog**, and each part is compared across **your current
suppliers and external vendors** to find the best offer.

Think special-purpose machines like the ones IMA, Marchesini or Syntegon build: packaging,
filling, assembly, inspection.

> Status: **v0.1, early prototype.** The design loop, revisions, spare-parts catalog and supplier
> comparison work end to end. What the machine output should be (3D, PLC, CAD, documents) is still
> an open decision: see [docs/output-options.md](docs/output-options.md).

## What works today

- **Problem → machine.** The AI breaks the problem into stations along the product flow, adds
  infrastructure (frame, control cabinet, safety, utilities), and lists the components of each
  station with specs, suggested manufacturer, make/buy, wear parts, criticality (A/B/C) and
  recommended spares. It also records its assumptions and open questions.
- **Refine by prompting.** "Add vision inspection", "use Beckhoff instead of Siemens", "make it
  washdown-ready". Each prompt creates a new revision. You can view or restore any revision.
- **Spare-parts catalog.** An aggregated BOM per revision: identical parts are merged across
  stations, with a filter for parts to stock. CSV export.
- **Supplier comparison.** Import your own price list (Excel/CSV, English or Italian headers) and
  compare it with external offers (Mouser, Nexar/Octopart). Shows current vs. best supplier per
  part, scored on price, lead time and availability, with potential savings.
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
uvicorn app.main:create_app --factory --reload
```

Windows (PowerShell):
```powershell
cd backend
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env   # then edit .env
uvicorn app.main:create_app --factory --reload
```

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
cd backend && pytest          # 25 tests, no network or keys needed
cd frontend && npm run build  # type-check + production build
```

GitHub Actions runs both on every push.

## Project layout

```
backend/
  app/
    models.py            MachineDesign (the source of truth), catalog and sourcing types
    llm/                 provider interface, Claude, OpenAI-compatible, demo engine, prompts
    services/            designer (prompt loop), spare_parts, price_list import, sourcing
    suppliers/           external connectors (Mouser, Nexar)
    api/                 HTTP endpoints
    storage.py           SQLite
  tests/
frontend/src/
  pages/                 Home, ProjectPage (chat + design), Suppliers
  components/            Chat, DesignView, SparePartsView, RevisionsView
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

**Open:** which machine outputs to build first. See [docs/output-options.md](docs/output-options.md).
The recommendation there is a 3D layout plus specs/documents next.

## Roadmap

- [ ] Decide and build the first machine outputs ([options](docs/output-options.md))
- [ ] Verify the Mouser and Nexar connectors against the live APIs
- [ ] More connectors (Digi-Key, RS, Farnell, TME) and an RFQ workflow for parts without APIs
- [ ] Supplier rating (quality, delivery reliability) in the score
- [ ] Revision diff view (what changed between r3 and r4)
- [ ] Streaming progress while the AI designs
- [ ] Users and authentication before any shared deployment

## Limits, honestly

The AI produces **concept designs**. Part numbers it suggests must be checked, and nothing here
replaces engineering, a risk assessment (ISO 12100) or validation of safety functions
(ISO 13849 / IEC 62061).
