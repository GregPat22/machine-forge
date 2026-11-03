# Frontend renewal: deep cobalt

Approved by Greg on 2026-11-03 after review of the written implementation plan, including viewer
presentation and the specifically named frontend PLC/rating presentation. Commit approval remains
separate. Companion scope to the Phase 2 UI; no later engine phase is started.

## Scope and sequence

1. Shared theme, final assets, responsive shell, fonts and controls as recorded in DESIGN.md.
2. Machines/create-project view and live project Overview: model-derived counts/requirements,
   open questions, station register, layout-derived envelope preview and station inspector.
3. Existing model editor and streaming assistant in an on-demand panel. Preserve draft/stream
   state, patch validation/conflicts and historical read-only behavior. Preserve existing tab URLs.
4. Restyle Timing, layout, comparison/history, documents, parts, suppliers and PLC views while
   retaining every existing calculation, operation, download and import. All pages remain reachable.
5. Existing/new browser tests, full build/backend checks, actual-app visual review, report and
   independent audit. No code is committed or pushed without a separate explicit go-ahead.

The viewer change is limited to presentation: Overview envelopes use existing layout-response
coordinates/dimensions; the existing imperative three.js view retains geometry, controls and
downloads. No scene JSON, R3F migration, dragging, new geometry or playback. No name-driven logic.
No model, prompt, backend, API/type contract, dependency or lockfile change.

## Allowed files

- frontend/src/index.css; App.tsx; pages/Home.tsx; pages/ProjectPage.tsx; pages/Suppliers.tsx.
- frontend/src/components/AppShell.tsx; ProjectSidebar.tsx; Icon.tsx; StationInspector.tsx;
  ConceptPreview.tsx; conceptProjection.ts (new presentation components/helpers).
- frontend/src/components/DesignView.tsx; ModelEditor.tsx; Chat.tsx; TimingView.tsx;
  LayoutView.tsx; Layout3D.tsx; RevisionsView.tsx; DiffView.tsx; DocumentsView.tsx;
  SparePartsView.tsx; PlcView.tsx; SupplierRatings.tsx.
- The latter two protected frontend screens are explicitly named for presentation-only work;
  their handlers, persistence, generated outputs and rating semantics are unchanged. Backend
  supplier connectors, sourcing, RFQ and PLC modules remain frozen.
- frontend/public/brand/mf-eagle.png; frontend/public/fonts/IBMPlexSans.ttf;
  IBMPlexMono-Regular.ttf; IBM-Plex-Sans-OFL.txt; IBM-Plex-Mono-OFL.txt.
- frontend/e2e/frontend-renewal.spec.ts (new); navigation adjustments in model-editor.spec.ts,
  timing.spec.ts and revision-comparison.spec.ts, preserving all behavioral assertions.
- DESIGN.md; this spec; ADR 0034; README.md; docs/architecture.md; docs/PLAN.md.
- Local .context artifacts for plans, evidence, screenshots and reports.

Anything outside this boundary requires a report before expansion. No drafts go to GitHub.

## Acceptance and tests

frontend/e2e/frontend-renewal.spec.ts must prove live counts/requirements across different valid
designs, station inspection → actual selected editor, assistant draft persistence and no implicit
prompt, historical read-only behavior and revision-correct downloads, all destinations and URL
reload, mobile keyboard dismissal/focus return, empty/missing inputs and retryable layout errors.

Retain the existing editor persistence, timing critical-path one-pixel scale, timing edit without
AI, revision race/recovery and Vite security tests. No weakening, skipping or deletion. New tests
are run before implementation to record the expected red result.

Run `cd backend && .venv/bin/pytest -q`, `cd frontend && npm run build` and
`cd frontend && npm run e2e`. Report the actual commands, output and exit codes. Check the running
app at 1600/1280/390px, OS-dark preference, keyboard access, critical text contrast, long/missing
content, reduced motion and document printing. Use mock data and a scratch database only.

Done: chosen design is applied throughout the working app, existing capabilities and relevant
tests remain, app screenshots and a report exist, and the independent audit is available for
Greg's final review. No time estimates. Any baseline-failure claim needs clean-base evidence.
