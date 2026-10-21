# ADR 0008: Stack: Python/FastAPI, React + react-three-fiber, SQLite with workspaces

Date: 2026-10-21. Status: accepted. Plan decision D8.

**Context.** The new core is simulation and geometry: discrete-event simulation (SimPy),
numerics (numpy), STEP handling (OCP/cadquery) live in Python. The 3D view must render data
(scene JSON) rather than hand-written geometry code.

**Decision.** Keep the Python/FastAPI backend and the React/TypeScript frontend. Move the 3D
viewer to react-three-fiber + drei in Phase 4 so the scene is declared from data. SQLite stays,
with `workspace_id` on every table from Phase 0 so the move to Postgres and multi-user (Phase 7)
is a storage change, not a model change. No Node backend, no game engine, no WebGPU framework.
