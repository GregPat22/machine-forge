# ADR 0001: Both simulation kinds, at concept fidelity

Date: 2026-10-21. Status: accepted. Plan decision D1.

**Context.** "Simulate before building" hides two products: throughput simulation (stations,
cycle times, buffers, transports → rate, bottleneck, WIP) and mechanism simulation (motion
profiles, cam timing, interference → per-station cycle time). Detailed-engineering tools exist
for both (Plant Simulation, FlexSim, JaamSim; NX MCD, Emulate3D, Visual Components). None is
open, prompt-driven or concept-stage, and timing diagrams in machine builders live in Excel.

**Decision.** Build both at concept fidelity: throughput first (discrete-event, SimPy), then
mechanism timing (closed-form motion profiles → step durations → timing diagram). No physics,
no collision detection. Deep mechanism work (cam synthesis, swept volumes) is roadmap, gated on
users asking. Consequence: cycle times become computed values, never AI estimates.
