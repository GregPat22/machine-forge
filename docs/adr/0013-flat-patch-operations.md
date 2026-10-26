# ADR 0013: The AI edits the design with flat patch operations

Date: 2026-10-26. Status: accepted. Phase 1 spec, section C.

**Context.** Until Phase 1 the AI rewrote the whole `MachineDesign` on every turn, so one bad
answer could silently corrupt any part of the design. The AI now sends a list of small edits
(patches) that code validates before anything changes. An edit could be modelled as a tagged
union (one schema per operation, chosen by `op`) or as one flat object: an `op` name plus
nullable operands, of which each operation uses a few. Tagged unions are the more precise
schema, but not every structured-output mode accepts them.

**Decision.** One flat `PatchOp` (`backend/app/services/patch.py`): `op` plus nullable operands.
It uses only constructs that every structured-output mode and plain JSON mode support (no tagged
unions or discriminators). Which operands an operation needs, and every bound on a value, are
checked in code, which reports precise error codes. Known limit, still open: each nullable field
counts against Anthropic strict mode's documented limit of 16 union-typed parameters per request.
The flat operation alone uses 15, and the full answer schema 51 (the model v2 schema on its own
already had 38). So the schema is supported in kind but too large in size for Claude strict mode.
The fix belongs to the providers step (Phase 1 step 5); correctness never depends on strict mode (D6). Patches are applied all or nothing, and the errors go back to the AI for up to
`MF_MAX_REPAIR_ATTEMPTS` answers (default 3) before the user sees a readable error and the design
stays unchanged. Machine and station fields are set with `set_param`, and the AI cannot set values
the software computes (`sequence`, `cycle_time_s`, placement, `schema_version`, footprint, the
duration of a motion step).
