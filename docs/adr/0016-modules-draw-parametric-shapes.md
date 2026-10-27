# ADR 0016: Library modules draw a shape built from their parameters, shown with materials

Date: 2026-10-27. Status: accepted. Extends ADR 0009 and ADR 0010.

**Context.** The plan had two levels of geometry: a labelled box when nothing is known, and real
CAD when a user imports STEP or glTF. The public project ships no CAD (ADR 0010), so a fresh
install or a public demo would show only boxes, and Greg wants the demo to look like a real
machine (his reference: Vention MachineBuilder, with profile frames, roller conveyors, clear
guards and cardboard boxes, lit and shaded). The options were: (A) keep boxes until a user
imports CAD; (B) each library module draws a shape built from its own parameters; (C) ship
hand-made detailed models per module. A misses the goal. C draws parts the model knows nothing
about, which rule 4 forbids and Phase 0 removed. Most of the reference picture is parametric
anyway; what boxes lack is mainly materials and light, which Phase 4 had excluded.

**Decision.** Option B, chosen by Greg on 2026-10-27. A module's shape is built by the backend
into the scene JSON from a fixed kit of generic parts: profile frame, guard panel, roller and
belt conveyor, sheet-metal cabinet, feet, pallet, product box, and a simple robot arm sized from
its reach. Every solid is sized from a module parameter that the user can see and change, and
records which one; a feature with no parameter is not drawn. Every solid also carries a material
kind set by the module definition (aluminium profile, clear guard, painted steel, product, moving
part), never chosen from a name; the viewer maps kinds to materials, with neutral environment
lighting and soft shadows. Unknown geometry stays a labelled box, and imported CAD is shown as it
is. Phase 4 adds the kit, materials and light (3 weeks become 4); Phase 5 gives each seed module
its shape (3 to 4 weeks become 5 to 7). Vendor robot models enter the public library only where
their licence allows. Also decided: STEP export of the concept layout goes on the roadmap after
v1.0, so a designer can open it in any CAD as a starting point. It is concept geometry, not
engineering geometry.
