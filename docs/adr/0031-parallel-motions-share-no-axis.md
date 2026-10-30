# ADR 0031: Parallel motions cannot share a physical axis

Date: 2026-10-30. Status: accepted. Extends ADR 0027; review finding R2.

The timing engine could schedule several motions of the same mechanism at once, giving busy
time above the cycle and negative idle time. The options were to reject the model in the patch
validator, silently serialize the motions, or report the station as not computable. Greg
authorized the technically sound timing fix after reviewing the proposed plan.

The engine reports `mechanism_overlap`, naming the mechanism and parallel group, without
changing the design or guessing a sequence. Reuse in sequential blocks remains valid. Engine
version 2 invalidates older cached results. Property tests generate physically valid groups;
separate regression tests cover overlapping moves, the editor and the timing API.
