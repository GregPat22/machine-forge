# Golden timing stations

Three stations whose cycle time is worked out by hand in a spreadsheet and compared with the timing
engine (Phase 2, `docs/specs/phase-2.md` section F). Every input is a public catalog or textbook
value (engineering rule 12); every number below cites its source id from the table at the end.

**Status (2026-10-30):** the sheet `timing_stations.xlsx` holds the three stations, their hand
calculation and expected values; `tests/test_golden_timing.py` compares them with the engine. Every
input has a source; none is `TODO(source)`.

## The sheet

`timing_stations.xlsx` is the data. It has one sheet per station (`pick_and_place`,
`indexing_table`, `sealing_station`) and a `Sources` sheet. A station sheet starts with the station
id and its target cycle time, then four tables, each a bold title in column A over a header row:

- `Mechanisms`: one row per axis, every number followed by the id of its source.
- `Steps`: one row per step in `(order, id)` order; a fixed duration has its source id.
- `Calculation`: the hand calculation as spreadsheet formulas, one row per step: the profile case
  that applies (the `Tv if max speed reached` column decides it, see "Formulas"), `Tj`, `Ta`,
  `Tv`, the move time `2·Ta + Tv`, the duration (move plus dwell, or the fixed duration), start and
  end. A block (one step, or the steps of one parallel group) starts at the end of the previous
  block. `critical` marks the first longest member of each block.
- `Expected`: each step's duration, the cycle time (the last end), the limiting step (the first
  longest critical step, so a tie goes to the lower order) and the margin (target minus cycle),
  all formulas over `Calculation`.

The test reads the values the spreadsheet program last saved: openpyxl does not compute formulas.
After editing the sheet, recompute and save it with a spreadsheet program, either
`soffice --headless --convert-to xlsx --outdir <dir> timing_stations.xlsx` (LibreOffice) or open,
recalculate and save it in Excel. The committed file was recomputed and saved by Microsoft Excel
for Mac on 2026-10-30. Then update the table under "Expected values" from the sheet.

The target cycle times are requirements chosen for this test, not catalog data. The indexing
table's target is missed on purpose, so one station has a negative margin.

## Formulas

- Trapezoidal (rest to rest, deceleration = acceleration): Biagiotti & Melchiorri [B1], section 3.2
  "Linear Trajectory with Parabolic Blends (Trapezoidal)", p. 62, with preassigned acceleration and
  speed in 3.2.2, p. 65 (pages from the book's table of contents; of section 3.2 only Example 3.3 on
  pp. 66-67 was read).
- Double S (S-curve) with null initial and final speed and symmetric limits: [B1] section 3.4.3
  "Double S with null initial and final velocities", pp. 90-93. The case analysis (acceleration
  limit reached or not, speed reached or not) is printed on pp. 92-93. Read as the scanned text of
  the Google Books preview (search inside the book); the page images could not be opened, and the
  formulas come through that text garbled, so equation numbers are not recorded.
- Trapezoidal book example used as a test: [B1] Example 3.3, p. 67, actuator a, "q0,a = 0,
  q1,a = 50", "vmax = 20 and amax = 20", printed "Ta = 1, T = 3.5". It is
  `tests/test_motion.py::test_trapezoidal_matches_textbook_worked_example`.
- S-curve book example used as a test: [B1] p. 93, the example of Fig. 3.19, printed "The boundary
  conditions are q0 = 0, q1 = 10, v0 = 0, v1 = 0, while the constraints are vmax = 10, amax = 20,
  jmax = 30. The resulting time intervals are Tj = 0.5503, Ta = 1.1006, Tv = 0." It is
  `tests/test_motion.py::test_s_curve_matches_textbook_worked_example`. The same sentence prints
  "vlim = 8.6329" and "alim,a = 6.9641, alim,d = -6.9641"; these do not fit the printed times
  (vlim · Ta = 9.50, not q1 - q0 = 10) and are not used. P. 84 prints the same values for another
  example (Tj1 = Tj2 = 0.2321), so p. 93 repeats them in error.

## Stations and their inputs

Units are the model's: mm, mm/s, mm/s² for linear axes, degrees for rotary axes, seconds for
durations. A unit conversion of a printed value is shown next to it. The order of the steps and the
parallel groups are structure, not catalog data; they are fixed when the sheet is built.

### Pick-and-place

Two linear axes and a dwell; one move short enough to be triangular; one parallel group. The dwell
is the gripper: it closes once per pick and opens once per place, with different printed times, so
it is two fixed-duration steps, not the Z axis's `dwell_s` (which would add a pause after every Z
stroke, answer to open question 3). The `dwell_s` rule is covered by the step 3 unit tests.

| Mechanism | Field | Value | As printed | Source |
|---|---|---|---|---|
| `pp-x` (linear, trapezoidal) | stroke | 400 mm | "Working stroke 400 mm" | S02 |
| | max_speed | 5000 mm/s | "Max. speed 5 m/s" | S02 |
| | acceleration | 50000 mm/s² | "Max. acceleration 50 m/s²" | S02 |
| `pp-z` (linear, trapezoidal) | stroke | 100 mm | "Working stroke ... 100 mm, 200 mm" (size 45) | S03 |
| | max_speed | 1000 mm/s | "Max. speed ... 1 m/s" (size 45, spindle pitch 10 mm/U) | S03 |
| | acceleration | 25000 mm/s² | "Max. acceleration 25 m/s²" | S03 |
| step `pp-grip-close` | duration_s | 0.041 s | "Min. closing time at 0.6 MPa ... 41 ms" (DHPS-16, gripping force backup none) | S04 |
| step `pp-grip-open` | duration_s | 0.033 s | "Min. opening time at 0.6 MPa ... 33 ms" (DHPS-16, gripping force backup none) | S04 |

`pp-x` is the triangular move: its stroke, 400 mm, is shorter than v²/a = 5000²/50000 = 500 mm.

Station `st-pick-place`, target 1.0 s. Steps, in order: `pp-z-down-pick` (Z), `pp-grip-close`,
`pp-z-up-pick` (Z), `pp-x-to-place` (X), `pp-z-down-place` (Z), `pp-grip-open`, then parallel
group 1: `pp-x-to-pick` (X) with `pp-z-up-place` (Z). The two X moves last the same, so the
limiting step is decided by the tie rule (lower order): `pp-x-to-place`.

### Indexing table

A rotary axis with an S-curve profile, index angle 360°/stations, then two process steps of
different length in one parallel group during the dwell.

| Mechanism or step | Field | Value | As printed | Source |
|---|---|---|---|---|
| `it-table` (rotary, s_curve) | stroke | 10° | 360° / 36 stations; the book's "q0 = 0, q1 = 10" | B1 (p. 93) |
| | max_speed | 10 deg/s | "vmax = 10" | B1 (p. 93) |
| | acceleration | 20 deg/s² | "amax = 20" | B1 (p. 93) |
| | jerk | 30 deg/s³ | "jmax = 30" | B1 (p. 93) |
| step `it-grip-small` | duration_s | 0.041 s | "Min. closing time at 0.6 MPa ... 41 ms" (DHPS-16, backup none) | S04 |
| step `it-grip-large` | duration_s | 0.087 s | "Min. closing time at 0.6 MPa ... 87 ms" (DHPS-20, backup none) | S04 |

No manufacturer's page read prints a jerk limit, so the axis takes all its limits from the book's
printed S-curve example, read as degrees (ADR 0030). The book prints the move's times
(Tj = 0.5503, Ta = 1.1006, Tv = 0), so the sheet's calculation for this axis has a printed check.
The numbers have no unit in the book and make a slow move; the station checks the arithmetic, not a
real table. The sheet computes Tj = 0.550321, Ta = 1.100642, Tv = 0, which round to the printed
times.

Station `st-indexing-table`, target 2.0 s. Steps, in order: `it-index` (table), then parallel
group 1: `it-grip-small` with `it-grip-large`.

### Sealing station

A linear lift, a heat-sealing dwell as a fixed step, the lift back.

| Mechanism or step | Field | Value | As printed | Source |
|---|---|---|---|---|
| `seal-lift` (linear, trapezoidal) | stroke | 100 mm | ordering table, "Stroke [mm] 50, 75, 100, ..." | S06 (p. 26) |
| | max_speed | 460 mm/s | "Max. speed [mm/s] ... 460" (size 40, spindle pitch 12.7) | S06 (p. 9) |
| | acceleration | 10000 mm/s² | "Max. acceleration [m/s2] 10" | S06 (p. 9) |
| step `seal-dwell` | duration_s | 0.5 s | "Recommended seal conditions: ... time : 0.5 – 1.0 s" (lower end) | S07 |

Station `st-sealing`, target 1.2 s. Steps, in order: `seal-lift-down` (lift), `seal-dwell`,
`seal-lift-up` (lift).

## Expected values

Copied from the sheet's `Expected` tables (seconds, six decimals);
`tests/test_golden_timing.py::test_readme_table_matches_the_sheet` checks they agree.

| Station | Quantity | Step | Value |
|---|---|---|---|
| `pick_and_place` | `duration_s` | `pp-z-down-pick` | 0.140000 |
| `pick_and_place` | `duration_s` | `pp-grip-close` | 0.041000 |
| `pick_and_place` | `duration_s` | `pp-z-up-pick` | 0.140000 |
| `pick_and_place` | `duration_s` | `pp-x-to-place` | 0.178885 |
| `pick_and_place` | `duration_s` | `pp-z-down-place` | 0.140000 |
| `pick_and_place` | `duration_s` | `pp-grip-open` | 0.033000 |
| `pick_and_place` | `duration_s` | `pp-x-to-pick` | 0.178885 |
| `pick_and_place` | `duration_s` | `pp-z-up-place` | 0.140000 |
| `pick_and_place` | `cycle_time_s` |  | 0.851771 |
| `pick_and_place` | `limiting_step` |  | `pp-x-to-place` |
| `pick_and_place` | `margin_s` |  | 0.148229 |
| `indexing_table` | `duration_s` | `it-index` | 2.201285 |
| `indexing_table` | `duration_s` | `it-grip-small` | 0.041000 |
| `indexing_table` | `duration_s` | `it-grip-large` | 0.087000 |
| `indexing_table` | `cycle_time_s` |  | 2.288285 |
| `indexing_table` | `limiting_step` |  | `it-index` |
| `indexing_table` | `margin_s` |  | -0.288285 |
| `sealing_station` | `duration_s` | `seal-lift-down` | 0.263391 |
| `sealing_station` | `duration_s` | `seal-dwell` | 0.500000 |
| `sealing_station` | `duration_s` | `seal-lift-up` | 0.263391 |
| `sealing_station` | `cycle_time_s` |  | 1.026783 |
| `sealing_station` | `limiting_step` |  | `seal-dwell` |
| `sealing_station` | `margin_s` |  | 0.173217 |

## Sources

All read on 2026-10-29: the S sources on the manufacturer's own site, B1 in its Google Books
preview. Page numbers are the numbers printed on the page.

| Id | Title | URL or ISBN | Page | Value as printed |
|---|---|---|---|---|
| B1 | L. Biagiotti, C. Melchiorri, *Trajectory Planning for Automatic Machines and Robots*, Springer, 2008 | ISBN 978-3-540-85628-3; preview read at https://books.google.com/books?id=FiX1ceRT5zoC | 62, 65, 67, 84, 90-93 | see "Formulas" |
| S02 | Festo, Toothed belt axis EGC-70-400-TB-KF-0H-GK, part number 3012493, data sheet | https://ftp.festo.com/public/PNEUMATIC/SOFTWARE_SERVICE/DataSheet/EN_GB/3012493.pdf | 1 | "Working stroke 400 mm", "Max. acceleration 50 m/s²", "Max. speed 5 m/s" |
| S03 | Festo, Mini slide EGSL, catalog 2025/02, Datasheet, General technical data | https://ftp.festo.com/public/PNEUMATIC/SOFTWARE_SERVICE/Documentation/2026/EN/EGSL_EN.PDF | 4 | size 45: "Working stroke 100 mm, 200 mm"; size 45, pitch 10 mm/U: "Max. speed 1 m/s"; "Max. acceleration 2) 25 m/s²" |
| S04 | Festo, Parallel gripper DHPS, catalog 2026/08, Opening and closing times | https://ftp.festo.com/public/PNEUMATIC/SOFTWARE_SERVICE/Documentation/2026/EN/DHPS_EN.PDF | 15 | DHPS-16, backup none: "Min. closing time at 0.6 MPa (6 bar, 87 psi) 41 ms", "Min. opening time at 0.6 MPa (6 bar, 87 psi) 33 ms"; DHPS-20, backup none: closing "87 ms" |
| S06 | Festo, Electric cylinders EPCO, with spindle drive, catalog 2022/07 | https://ftp.festo.com/public/PNEUMATIC/SOFTWARE_SERVICE/Documentation/2023/EN/EPCO_EN.PDF | 9, 26 | size 40, pitch 12.7: "Max. speed [mm/s] 460"; "Max. acceleration [m/s2] 10"; ordering table "Stroke [mm] 50 75 100 ..." |
| S07 | BASF, Joncryl® HSL 9012, technical data sheet, Mar22 | https://download.basf.com/p1/8a8083fb9ebb3333019ebd2e6a57008d/en/Joncryl_HSL_9012 | 3 of 4 | "Recommended seal conditions: temperature : 160 – 220 °C, pressure : >30 N/cm², time : 0.5 – 1.0 s" |

The plausibility bounds (`backend/data/catalog_bounds.yaml`) carry their own sources row by row.
