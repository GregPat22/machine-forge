# ADR 0028: Timing results are computed on first read, stored per revision, and diffed

Date: 2026-10-30. Status: accepted. Phase 2 spec, section G, open questions 2 and 8. Applies
ADR 0003.

**Context.** ADR 0003 says results are stored with each revision and compared between revisions,
but not where they live or when they are computed. The options were to compute at every save
(every save path changes, and old revisions still need filling) or the first time a revision's
timing is read; and for the revision comparison, to show only stations and parts as today or to
add what happened to the timing.

**Decision.** Chosen by Greg on 2026-10-29 (recommended options). A new `revision_results` table
holds one row per revision and engine (`timing` now; Phase 3 adds `throughput` with no new
migration), with the engine version and the inputs version (for timing, the SHA-256 of the bounds
table). A revision's timing is computed the first time it is read, then stored; a row whose
versions no longer match is recomputed and replaced. Old revisions are handled the same way, never
filled in bulk, and the save paths do not change. A stored result is a cache: recomputing it from
the revision's design gives the same JSON, and the design is never changed. The plausibility
warnings are part of the stored timing result: a mechanism's go to its station, a transport's to
the machine. The revision diff gains a timing block: per station the cycle time and the limiting
step before and after, and the warnings added and removed, matched by code and every id they name.
