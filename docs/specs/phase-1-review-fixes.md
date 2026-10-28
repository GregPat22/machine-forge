# Phase 1: fixes from the whole-repository review

Scope authorized by Greg's request to plan and execute fixes for the ten confirmed review
findings. These are separate bug fixes on the current workspace branch, left uncommitted for
review. This does not complete or expand the model-editor work in Phase 1 section G.

## Scope and expected files

1. **Stale revision saves:** `storage.py`, `services/designer.py`, `main.py`, `api/projects.py`.
   A write that was prepared against an older revision must fail without changing the design,
   chat or revision list. Return HTTP 409, or an SSE error with status 409, and a readable retry
   instruction. Check the expected revision inside the write transaction. Protect project
   reads on the shared SQLite connection from overlapping writes.
2. **Offline restore:** `services/designer.py`, `api/projects.py`. Restoring stored revisions
   must not resolve or require an AI provider.
3. **Import invariants:** `services/patch.py`, `services/project_json.py`. Reuse the existing
   patch bounds and reference checks before storing a complete imported design. Reject invalid
   numbers, duplicate IDs and dangling references with HTTP 400 and no partial import. Keep
   valid v1 migration and stored placement round trips working.
4. **Currency input:** `services/price_list.py`, `frontend/src/api.ts`. Accept three-letter
   currency syntax, reject malformed codes before storage, and display legacy invalid rows
   without a rendering exception. No new exchange-rate source.
5. **Malformed workbooks:** `services/price_list.py`. Translate expected workbook/archive/XML
   parse errors into readable HTTP 400 responses and close workbooks after reading.
6. **Spreadsheet text safety:** `services/spreadsheet.py`, `services/spare_parts.py`,
   `services/rfq.py`. Preserve XLSX labels explicitly as strings; escape formula prefixes in
   CSV textual fields while retaining numeric quantities and normal labels.
7. **Exact part matching:** `services/sourcing.py`. Conflicting known manufacturers must not
   produce an exact match. Missing manufacturers and equivalent case/outer whitespace keep
   working as before.
8. **RFQ currency comparison:** `services/sourcing.py`, `services/rfq.py`, `api/projects.py`.
   Compare normalized prices using the same configured conversion policy as sourcing. Do not
   compare unconverted numbers when a rate is unavailable.
9. **Complete v2 differences:** `services/diff.py`. Report structured product fields,
   transports, parameters, mechanisms, steps and target cycle times. Match items by stable IDs
   or parameter keys and retain the existing FieldChange response shape.
10. **Throughput display:** `frontend/src/types.ts`, `frontend/src/components/DesignView.tsx`.
    Mirror the existing v2 API fields and display `target_rate_text`.

The frozen-path exception is limited to the named fixes in `services/sourcing.py` and
`services/rfq.py`. Supplier connectors, supplier ratings and PLC generation stay frozen.
`models.py`, prompts, layout geometry and the 3D viewer are excluded. No persisted schema
change, schema-version bump, engine, editor, new provider or dependency is part of this work.

## Acceptance tests

`backend/tests/test_review_fixes.py` covers the ten findings and compatibility cases:

- Overlapping prompts produce one saved edit and one explicit conflict; only one chat pair is
  added. Separate database connections also cannot commit stale revisions.
- Both normal HTTP and streaming endpoints report a conflict and preserve the newer edit.
- Restore works with an unconfigured provider.
- Invalid imported quantities, IDs, signals, mechanisms, products and transports return 400
  without adding a project; valid stored placement remains intact.
- Malformed XLSX and invalid currency uploads return 400.
- Exported XLSX labels are strings, and CSV formula prefixes are escaped.
- Exact matches reject conflicting known manufacturers but accept missing/equivalent ones.
- USD 100 beats EUR 95 when USD→EUR is 0.9, including through the RFQ endpoint.
- Revision differences identify the changed fields and transport additions/removals; reordering
  parameters or mechanisms without changing their values produces no difference.

Run the existing full backend suite and frontend build. Exercise the actual frontend rendering
and currency formatter with a v2 demo response. Preserve before/after evidence and an independent
audit under `.context/`; leave all changes uncommitted until Greg reviews the diff and approves.
