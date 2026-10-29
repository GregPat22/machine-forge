# ADR 0030: The golden indexing table uses the textbook's double-S example

Date: 2026-10-29. Status: accepted. Phase 2 spec, section F.

**Context.** The golden indexing table is a rotary axis with an S-curve profile, so it needs a
jerk. The step 4 source search found no manufacturer's page that prints a jerk limit (Festo,
SCHUNK, HIWIN, Beckhoff, B&R and LinMot were read). Jerk is a tuning setting in their software,
not a catalog figure. The options were to leave the jerk `TODO(source)`, so the golden test fails
until a source appears (maybe never), or to switch that station to a trapezoidal profile (sourced,
but then no golden station covers the S-curve). The third option was to take all three limits
from the S-curve example the textbook prints: Biagiotti & Melchiorri (2008, ISBN
978-3-540-85628-3), p. 93, rest to rest, q1 − q0 = 10, vmax = 10, amax = 20, jmax = 30, printed
result Tj = 0.5503, Ta = 1.1006, Tv = 0.

**Decision.** Greg asked for the better option on 2026-10-29: the third. The golden indexing table
has 36 stations, so its index angle is 360°/36 = 10°, the book's move, and its rotary axis uses the
book's limits read as degrees (10 deg/s, 20 deg/s², 30 deg/s³). Every input is a published
textbook value (rule 12 allows textbooks), the S-curve stays covered, and the sheet's hand
calculation can be checked against the book's printed times. The book's numbers have no unit and
give a slow move (about 2.2 s), which is fine for a check of the arithmetic, not a claim about real
tables. The two process steps in the dwell keep their Festo gripper times. The Festo ERMS data
proposed earlier for this station is dropped.
