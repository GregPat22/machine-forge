# ADR 0012: `sequence` and `cycle_time_s` become derived, read-only values

Date: 2026-10-25. Status: accepted. Phase 1 spec, open question 4.

**Context.** Model v2 replaces the stored `Station.sequence` with a process graph and the
stored `Station.cycle_time_s` with steps. The frozen `services/plc.py` reads `cycle_time_s`,
and six services read `sequence`. The options were to add a small adapter in `plc.py` (breaks
the frozen rule), to keep both as stored fields next to the new model (two copies of the same
fact that can drift apart), or to keep the names as values computed from the new model.

**Decision.** Keep both names as read-only values derived by code: `sequence` from the process
graph, `cycle_time_s` from the station's steps. They are not stored, not shown to the AI and
cannot be set by a patch. This keeps `plc.py` untouched and leaves one source of truth. Until
the Phase 2 timing engine exists, `cycle_time_s` is known only when every step has a fixed
duration and none run in parallel; otherwise it is null.
