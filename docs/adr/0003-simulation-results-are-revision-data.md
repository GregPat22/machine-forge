# ADR 0003: Simulation results are stored per revision and diffed

Date: 2026-10-21. Status: accepted. Plan decision D3.

**Context.** The main use case is what-if: change a component or a buffer, see what moves.
v0.3 diffs stations and components only.

**Decision.** Timing, throughput and layout-check results are computed and stored with each
revision. The diff view compares them alongside the BOM and cost. Results are derived data: a
recompute must reproduce them (deterministic engines, ADR 0001), so storing them is a cache
with provenance, not a second source of truth.
