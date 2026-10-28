# ADR 0024: The model editor uses only the existing patch operations

Date: 2026-10-28. Status: accepted.

**Context.** The model editor (Phase 1 step 7) saves its edits through the same patch validator
as the AI, so the engineer and the AI follow the same rules. The patch operations of ADR 0013
cannot remove a mechanism or a station parameter (a parameter can only be set to no value), and
cannot edit or remove an assumption or an open question. The options were to add those
operations now, which reopens `services/patch.py` (the foundation that needs the heaviest
audit), or to ship the editor without them.

**Decision.** Ship without them, chosen by Greg on 2026-10-28. The editor offers what the
existing operations allow and nothing more; the missing ones are in `docs/parking-lot.md` and
come with a spec that reopens the patch operations. The editor gets no operations of its own and
no shortcut around the validator.
