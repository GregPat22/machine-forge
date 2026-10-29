# ADR 0027: Timing rules, and `cycle_time_s` from the timing engine

Date: 2026-10-29. Status: accepted. Phase 2 spec, sections C and D, open questions 3, 4 and 5.
Extends ADR 0012.

**Context.** Until Phase 2 a station had a cycle time only when every step was a fixed duration
and none ran in parallel (ADR 0012); a motion step had no time at all. The timing engine needs
fixed rules for how steps add up, what the existing `Mechanism.dwell_s` means, how pneumatic
cylinders and cam indexers are timed, and what the frozen `services/plc.py` prints once
`cycle_time_s` is computed. For the dwell the options were a pause after every stroke of the
mechanism or once per cycle; for cylinders, a load-and-pressure model or a concept-level axis;
for `plc.py`, relabelling its "Target cycle time" comment (an edit to a frozen file) or leaving
it and parking the label.

**Decision.** Chosen by Greg on 2026-10-29 (recommended options). Steps are sorted by order then
id; steps with no group are blocks of their own, steps sharing a `parallel_group` form one block;
blocks run in sequence and each lasts as long as its longest member (critical path of a
series-parallel plan, Kelley and Walker 1959). A group whose members are not next to each other is
reported as not computable, not rejected by the validator. A motion step is one full rest-to-rest
stroke with the mechanism's profile plus its `dwell_s`, a pause at the end of every stroke; a
pause once per cycle is a fixed step. A pneumatic cylinder is a trapezoidal axis with catalog speed
and acceleration (a concept-level simplification: real cylinders depend on load, pressure and
cushioning); a mechanical cam indexer is a fixed step with its catalog index time. The limiting
step is the longest on the critical path, ties to the lower order then the lower id. An incomplete
station is a normal result listing every reason. `Station.cycle_time_s` keeps its name and stays a
read-only derived value, now the engine's cycle (or null); all-fixed sequential stations keep
their old numbers, parallel fixed steps now give their longest member. `plc.py` is not edited and
now prints the computed cycle under its old label, which goes to the parking lot.
