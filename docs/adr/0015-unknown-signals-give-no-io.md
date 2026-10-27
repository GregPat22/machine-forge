# ADR 0015: A component with unknown signals gets no I/O points

Date: 2026-10-27. Status: accepted. Phase 1 step 3.

**Context.** The I/O list and the PLC skeleton now count each component's I/O from
`Component.signals`; in v0.3 they came from keywords in component names, which rule 1 forbids.
Designs migrated from v1 have no signals, because the migration guesses nothing (Phase 1 spec,
section B). The options were: (A) such a component gets no I/O points, and the I/O list names it;
(B) estimate its I/O from its category and mark it estimated; (C) fill the signals once during the
migration from the old name rules. B is often wrong: a category alone cannot tell a digital sensor
from an analog one, a suction cup from a vacuum ejector, or a door switch from a safety relay.
It would also be a hidden second source of I/O next to `signals`. C reads names and reverses the
migration decision.

**Decision.** Option A, chosen by Greg on 2026-10-27. Every I/O point comes from a `signals`
field. Missing signals are shown, never filled in: the I/O section of the documents lists the
components that have none. Cost: projects from v0.3 show an empty I/O list and PLC sequence until
signals are set, with one AI turn now or in the model editor (Phase 1 step 7). The PLC view does
not explain why, because `plc.py` is frozen.
