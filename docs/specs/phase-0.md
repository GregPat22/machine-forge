# Phase 0: cleanup and guardrails

Status: **done** 2026-10-21 (verified in the running app with the mock provider; the v0.3
database migration is covered by `tests/test_migration.py`, no v0.3 database exists on the
current machine). Plan reference: `docs/PLAN.md` section 5, Phase 0.

## Goal

Remove what misleads, write down the rules, make the repo ready for agents. No new features.

## Scope (exact)

1. **Delete the realistic render.** Remove `frontend/src/render/` (materials, parts, machine) and
   `frontend/src/components/MachineRender.tsx`. `LayoutView` keeps two modes: concept 3D
   (`Layout3D.tsx`) and top view 2D. Default mode: concept. A stored `mf.layoutMode` of
   `realistic` falls back to concept.
2. **Freeze markers.** `README.md` and `docs/architecture.md` state that supplier connectors,
   supplier ratings, RFQ workbooks and the PLC skeleton are frozen (bug fixes only).
3. **License.** `LICENSE` = AGPL-3.0 verbatim from gnu.org. `CONTRIBUTING.md` with the
   workflow and a `CLA.md` (contributor grants the maintainer relicensing rights, DCO sign-off).
4. **Rules.** `docs/engineering-rules.md` (the twelve rules from PLAN section 7, with the
   concrete check for each). `CLAUDE.md` rewritten short and operational, pointing at PLAN,
   rules and the current spec.
5. **ADRs.** `docs/adr/0001` to `0010`, one per decision D1 to D10, two paragraphs each
   (context, decision + consequences).
6. **Storage.** `workspace_id TEXT NOT NULL DEFAULT 'default'` on every table; a migration
   step in `Storage.__init__` adds the column to databases created before this phase.
   `schema_version INTEGER NOT NULL DEFAULT 1` on `revisions`; exposed as `Revision.schema_version`.
   `MachineDesign` (the LLM-facing schema) does not change.
7. **Docs.** `README.md`: status, what was removed and why, roadmap from the plan.
   `docs/output-options.md`: realistic render paragraph replaced by a pointer to the plan.

## Out of scope

Any refactor not listed above. Any new field in `MachineDesign`. Any change under
`suppliers/`, `services/rfq.py`, `services/plc.py`, `services/sourcing.py`.

## Tests to add

- `backend/tests/test_repo_rules.py::test_frontend_does_not_import_the_deleted_render`
  scans `frontend/src/**/*.{ts,tsx}` and fails on `from "../render/` or `render/machine`
  imports, or on any file under `frontend/src/render/`.
- `backend/tests/test_migration.py::test_v03_database_opens_and_reads_projects`
  builds a database with the v0.3 schema (copied verbatim into the test), inserts a project,
  a revision, messages, a price-list row, a rating and a cached offer, opens it with `Storage`,
  and asserts: all projects listed, the revision loads, every table has `workspace_id` =
  `'default'`, `revisions.schema_version` = 1.
- `backend/tests/test_migration.py::test_migration_is_idempotent`: opening the same file twice
  does not fail and does not duplicate columns.

## Done criteria

- `cd backend && pytest -q` green, `cd frontend && npm run build` green, CI green.
- The app shows the concept 3D and top view only; every other tab unchanged.
- `LICENSE`, `CONTRIBUTING.md`, `CLA.md`, `docs/engineering-rules.md`, `docs/adr/*` exist.
- Greg opens an existing project from his v0.3 database without errors.

## Agent brief

Pure removal and documentation plus the two storage columns. No "while we are here".
