# ADR 0026: Motion profile fields on the mechanism, schema version 3

Date: 2026-10-29. Status: accepted. Phase 2 spec, section A, open question 1.

**Context.** The Phase 2 timing engine computes a motion step's time from its mechanism. Stroke,
speed and acceleration give a trapezoidal move; an S-curve move also needs a jerk limit, and the
model had no place for either the profile type or the jerk. The options were to add the two
fields to `Mechanism` (one place, shown to the AI with the other axis data), to keep the profile
and jerk outside the design (a second source of truth for the same axis), or to also model
asymmetric deceleration and non-zero start and end speeds (more fields than any Phase 2 engine
reads, out of scope for concept timing).

**Decision.** Add `Mechanism.profile` (`trapezoidal` or `s_curve`, default `trapezoidal`) and
`Mechanism.jerk` (mm/s³ or deg/s³, default null, used only by `s_curve`), chosen by Greg on
2026-10-29. Every move is rest to rest over one full stroke, with deceleration equal to
acceleration; the field descriptions say so, so the AI sees it. `schema_version` becomes 3:
version 2 designs read with the defaults and nothing else changes, version 1 designs go through
the v1 migration first, and stored rows are never rewritten. The patch validator checks that
`jerk` is greater than 0, as it does for the other axis values; no new patch operation (ADR 0024
stands). The answer schema gains one nullable field.
