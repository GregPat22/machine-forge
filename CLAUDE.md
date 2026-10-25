# Machine Forge: notes for Claude Code and other agents

## Read first, every session

1. `docs/PLAN.md`: what we build, decisions D1-D10, phases.
2. `docs/engineering-rules.md`: the twelve rules every PR is checked against.
3. `docs/specs/phase-N.md` for the current phase (see "Status" in `README.md`). Do only what
   the spec says. No "while we are here" refactors.
4. `docs/workflow.md`: how work is reported and approved. Greg does not read code. Never
   commit, push, merge or approve without his go-ahead; end every step with the report.

## Non-negotiable

- `backend/app/models.py` `MachineDesign` is the source of truth. The LLM edits it; every output
  (layout, documents, I/O, PLC, catalog, and later timing, throughput, scene) is computed from it
  by code. The LLM never writes coordinates, computable durations, rates or results.
- No logic reads a display `name` or free text to decide behaviour.
- Keep the LLM-facing schema compatible with strict structured outputs: no free-form dicts, no
  numeric bounds, no recursion. New fields need defaults so old revisions still load, and a
  storage migration when a column changes.
- Tests need no network or API keys: `MockProvider`, `httpx.MockTransport` (connectors,
  OpenAI-compatible), `httpx2.MockTransport` (Anthropic SDK 1.x).
- Frozen (bug fixes only): `app/suppliers/`, `services/rfq.py`, `services/plc.py`, supplier
  ratings. Do not touch them unless the spec names them.
- No confidential data (machine specs, BOMs, CAD, prices from employers or customers) in the repo,
  tests, issues or commits. Public sources only, cited.
- When Greg says we've made a decision, write a new short note in `docs/adr/` with the next
  four-digit number (0013 is next): what we decided, the options, and why. Two short paragraphs.
  Never edit old notes. If a decision replaces an older one, the new note says so.

## Run and test

- Backend: `cd backend && .venv/bin/pytest -q` (Windows: `.venv/Scripts/python -m pytest -q`).
- Frontend: `cd frontend && npm run build` type-checks. `src/types.ts` mirrors `models.py`.
- Run locally: `uvicorn app.main:create_app --factory --reload --reload-dir app --timeout-graceful-shutdown 2`
  + `npm run dev` (both flags keep the reloader from hanging on pip installs and Vite keep-alive).
- Scratch backend that leaves the user's data alone:
  `MF_DB_PATH=<scratch>.db MF_LLM_PROVIDER=mock uvicorn ... --port 8010` and
  `MF_API_URL=http://localhost:8010 npx vite --port 5180`. `MF_LLM_PROVIDER=mock` needs no key.
- PLCopen XML schema test runs only when `MF_PLCOPEN_XSD` points to a local `tc6_xml_v201.xsd`.

## Commits

Private repo for now. Author email for this repo is set locally. One concern per commit; update
docs and ADRs in the same commit as the change they describe.
