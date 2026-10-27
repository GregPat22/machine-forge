# ADR 0017: Whole-machine STEP import, stations assigned by the user

Date: 2026-10-27. Status: accepted. Extends ADR 0004.

**Context.** Phase 5 imported STEP one station at a time. Greg wants to import a whole machine
he modelled in any CAD and get its numbers. A STEP file carries shapes, dimensions, positions
and the assembly tree with part names; it carries no motion, speeds, strokes, timing or the
function of each part. So cycle time and throughput cannot come from the file alone. The options
were: (A) station-by-station import only; (B) import the whole assembly and let the user assign
subassemblies to stations, then add mechanisms and steps; (C) recognise stations and mechanisms
automatically from the geometry. A is slow for a full machine. C is research-grade and would
guess, which rules 3 and 4 forbid.

**Decision.** Option B, chosen by Greg on 2026-10-27. The import shows the assembly tree; the
user assigns subassemblies to stations. The AI may propose an assignment from the part names,
but the user confirms it, as in the Excel BOM mapping (names feed a proposal, never logic).
Each assigned subassembly becomes a station with its CAD geometry, an envelope measured from it,
and a placement read from the file, not written by the AI. Unassigned parts stay visible as
labelled unassigned geometry. Mechanisms and steps are then added by prompt or in the editor,
and the engines compute timing and throughput. Large files get a size limit and mesh
simplification. Phase 5 grows from 5 to 7 weeks to 6 to 9 weeks.
