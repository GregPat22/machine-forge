# ADR 0029: Pneumatic cylinders are fixed-duration steps with a catalog stroke time

Date: 2026-10-29. Status: accepted. Phase 2 spec, sections E and H, open question 4. Replaces the
"trapezoidal axis with catalog speed and acceleration" part of the answer to question 4, which
ADR 0027 was to record.

**Context.** The spec modelled a pneumatic cylinder as a trapezoidal axis, which needs a speed and
an acceleration from a public catalog. The step 4 source search found piston speeds (SMC CP96
"Operating piston speed 50 to 1000 mm/s") but no manufacturer's page that prints a pneumatic
acceleration: SMC CP96, Festo DSBC, DFM and ADN were read, and a cylinder's acceleration depends on
load, pressure, valve, tubing and cushioning, so catalogs do not give one. The options were to
invent an acceleration (forbidden by rule 12 and the spec), to keep the trapezoidal model and leave
the blister cylinders not computable, or the spec's alternative: model each cylinder stroke as a
fixed-duration step whose time a manufacturer publishes. SMC publishes full stroke times as charts
for each bore, stroke and load ratio ("Air Cylinders' Drive System, Full Stroke Time & Stroke End
Velocity", https://ca01.smcworld.com/catalog/BEST-Guide-en/pdf/1-m30-45_en.pdf: conditions 0.5 MPa,
meter-out, vertically upward on front matter p. 30; series MB ø63 to ø100 on front matter p. 39).

**Decision.** Greg asked for the better option on 2026-10-29: a pneumatic cylinder stroke is a
fixed-duration step, not a motion step. Its duration is a full stroke time read from a
manufacturer's published chart for the cylinder's bore and stroke. The comment next to the value
and the design's `assumptions` state the chart, page, load ratio, conditions and "read from chart".
SMC defines full stroke time as the time from the valve signal to the stroke end, so it includes
valve and start-up delay, which a trapezoid would not. The cost: changing that cylinder's stroke in
the editor does not change its time, so the end-to-end stroke test edits a servo axis instead. The
rule holds for every design. In the mock, the step 6 agent reads the chart. In a design the AI
writes, the engineer types the charted time in the model editor; until then the step has no
duration and the station is reported not computable. The prompt does not change in this phase, so
nothing yet stops the AI from proposing a cylinder time itself; that gap goes to the parking lot
(step 8). The engine and the schema do not change. The pneumatic acceleration row
stays inactive. The pneumatic speed row stays, but it checks only a cylinder still modelled as a
motion axis, so it checks nothing in the mock.
