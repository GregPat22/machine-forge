# Engineering rules

The anti-slop contract. Every PR is checked against these; reviewers reject PRs that break them.
Each rule names how it is checked. Rationale is in `docs/PLAN.md` section 2 (what went wrong in
v0.3) and section 7.

1. **No behaviour from display names.** Logic reads structured fields (`kind`, `category`, and
   from model v2 `role`, `signals`, `motion`), never `.name`, `.function`, `.summary` or any
   free text, to decide what to draw, compute or generate.
   *Check:* `tests/test_repo_rules.py` greps `backend/app` and `frontend/src` for a comparison,
   keyword or regex test written directly on `.name`, `.function`, `.summary`, `.description`,
   `.target_rate_text` or `.machine_type`, with a short allowlist for display and non-design
   names. It misses indirect cases (text copied into a variable first, other fields): the
   supplier-name matching in `sourcing.py` and `storage.py` (parking lot) passes it. A reviewer
   still reads every new string comparison.

2. **Every number has provenance.** Anything shown to the user is a model field or the output of
   a named engine function. The UI can show which.
   *Check:* a reviewer can answer "where does this number come from" for every value in a new
   panel. From Phase 6 the citation test enforces it for AI replies.

3. **The AI never writes** coordinates, durations that can be computed, rates, dimensions
   derived from geometry, or compliance statements. It proposes structure, parameters,
   components, assumptions and reasons.
   *Check:* prompt diffs are reviewed against this list; patch operations that set computed
   fields are rejected by the validator (Phase 1).

4. **No decorative geometry.** Unknown geometry is a labelled envelope with its dimensions. A
   library module draws a shape of simple solids, each sized from a module parameter and
   recording which one; a feature with no parameter is not drawn. A solid's material comes from
   its material kind, never from a name (ADR 0016). No fillers, no random hardware, no product
   shapes guessed from text, no hardcoded speeds.
   *Check:* `tests/test_repo_rules.py` fails on imports of the deleted render; reviewers reject
   any geometry that does not come from the scene JSON (Phase 4).

5. **Engines are deterministic and pure.** Seeded where random, no I/O, formulas cite their
   source in the docstring, unhandled cases raise instead of approximating silently.
   *Check:* unit tests assert identical output for identical input; no `try/except: pass` in
   `engines/`.

6. **Tests need no network or keys.** Recorded payloads and mock providers only. Live
   evaluations are a separate, optional job.
   *Check:* CI has no secrets; a test that needs one is a bug.

7. **Model changes ship with defaults, a migration, and a `schema_version` bump.** Every new
   field on a stored model has a default value. `schema_version` is bumped. A migration step
   brings old data up to date,
   and a test opens a database from the previous version and checks that the data still reads back.
   *Check:* `tests/test_migration.py` builds a v0.3 database in code (the v0.3 schema is pasted
   into the test), opens it with the current `Storage`, and asserts that the data reads back,
   the migrated columns exist, and the stored `schema_version` is set. It does not yet load a
   committed database file, and only v0.3 is covered (see `docs/parking-lot.md`).

8. **Frozen modules stay frozen.** `app/suppliers/`, `services/rfq.py`, `services/plc.py`,
   supplier ratings: bug fixes only until a spec reopens them.
   *Check:* the PR diff touches none of them unless the phase spec lists them.

9. **One phase at a time, tests before code.** Each phase has `docs/specs/phase-N.md` with
   the tests to add; agents implement to the tests. A small fix Greg already agreed to in
   `docs/parking-lot.md` needs no spec (`docs/workflow.md`, "Small agreed fixes").
   *Check:* the spec, or the parking-lot entry, exists and is linked from the PR before any code
   is reviewed.

10. **Small PRs, one concern, docs and ADR updated in the same PR.**
    *Check:* a PR that changes a decision without an ADR is sent back.

11. **Untrusted inputs** (STEP, Excel, glTF, AutomationML, price lists) are parsed with size
    limits, in isolation, and never executed.
    *Check:* every importer has a test with an oversized and a malformed file.

12. **No confidential data**, from any employer, customer or NDA source, in the repo, the
    tracker or the commit history. Public brochures, catalogs and textbooks only, cited in
    `tests/golden/README.md`.
    *Check:* reviewers ask for the source of every engineering constant.
