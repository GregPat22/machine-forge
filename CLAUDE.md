# Machine Forge — notes for Claude Code

- Read `README.md` (decisions, roadmap) and `docs/architecture.md` before changing structure.
- `backend/app/models.py` `MachineDesign` is the source of truth: outputs are derived from it in
  code, the LLM only edits it. Keep its schema compatible with strict structured outputs (no free-form
  dicts, no numeric bounds); new fields need defaults so old revisions still load.
- Backend: `cd backend && .venv/Scripts/python -m pytest -q` (Windows) or `.venv/bin/pytest -q`.
  Tests must not need network or API keys: use `MockProvider`, `httpx.MockTransport` (connectors,
  OpenAI-compatible) and `httpx2.MockTransport` (Anthropic SDK 1.x).
- Frontend: `cd frontend && npm run build` type-checks. Types in `src/types.ts` mirror `models.py`.
- Run locally: `uvicorn app.main:create_app --factory --reload --reload-dir app` + `npm run dev`
  (`--reload-dir app` matters: watching `.venv` makes pip installs hang the reloader).
  `MF_LLM_PROVIDER=mock` works without a key.
- Outputs (layout, documents) are computed from the design by code, never written by the LLM.
- Commits: the repo is private; author email for this repo is set locally.
