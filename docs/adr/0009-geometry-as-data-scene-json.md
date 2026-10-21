# ADR 0009: Geometry is data: backend scene JSON, frontend viewer only

Date: 2026-10-21. Status: accepted. Plan decision D9.

**Context.** v0.3 drew the machine in 1,600 lines of frontend code that invented what the model
did not know (fillers, regex-chosen shapes, hardcoded speeds). Geometry logic in a renderer
cannot be tested against the model and drifts from it.

**Decision.** The backend computes a scene JSON from design + layout + simulation results:
placed glTF assets from the library or labelled parametric envelopes, transports as paths,
mechanisms as animatable nodes, animation tracks from the trace and motion profiles. The
frontend renders the scene and nothing else. STEP → glTF conversion runs server-side as an
optional extra (`machine-forge[cad]`); direct glTF upload is the fallback. Scene JSON is
snapshot-tested per mock machine.
