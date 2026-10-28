# ADR 0025: Playwright for the end-to-end browser test

Date: 2026-10-28. Status: accepted.

**Context.** The Phase 1 spec asks for a smoke test of the model editor in a real browser: create
a demo project, edit a station parameter, see a new revision and the changed value after a
reload. Until now the frontend had only the type check (`npm run build`), so nothing checked
that the app and the backend work together. The options were Playwright, Cypress, or no browser
test and a manual check by Greg.

**Decision.** Playwright (`@playwright/test`, a dev dependency of `frontend/`), chosen by Greg
on 2026-10-28: it runs headless Chromium in CI, and its config starts its own scratch backend
(a new SQLite file in the temp folder, the mock provider, port 8010) and Vite (port 5180), so
the test never touches the user's data and needs no network or keys (rule 6). It refuses to
start if either port is already in use. CI runs it as a third job, `e2e`, next to `backend` and
`frontend`. Locally: `cd frontend && npx playwright install chromium` once, then `npm run e2e`.
