# ADR 0002: The module library is the core anti-slop mechanism

Date: 2026-10-21. Status: accepted. Plan decision D2.

**Context.** Without real parameters the AI invents strokes, speeds and envelopes, and every
downstream number inherits the invention. v0.3 showed the failure mode: plausible-looking output
with no engineering content.

**Decision.** Real parameters come from a module library: parametrized stations and mechanisms
with envelopes or glTF geometry, timing formulas, BOM templates and sources. The AI selects and
parametrizes library modules; it creates a custom station only when nothing fits, states why,
and the UI and documents mark it unverified. Companies maintain their own library per
installation; a public seed library ships with the repo using only our own parametric envelopes.
