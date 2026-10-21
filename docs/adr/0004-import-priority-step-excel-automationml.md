# ADR 0004: Import priority: STEP, Excel BOM, AutomationML

Date: 2026-10-21. Status: accepted. Plan decision D4.

**Context.** Companies must bring their existing machines and templates. SolidWorks dominates
SME machine builders, followed by Inventor, NX and Creo; all export STEP. BOMs are Excel.
Layout and simulation tools have no dominant file format; the open neutral one is AutomationML
(IEC 62714), spoken by Siemens and Visual Components. PLCopen XML export already exists.

**Decision.** Import in this order: STEP (geometry, converted to glTF server-side, optional
dependency), Excel/CSV BOM (AI-assisted column mapping, user confirms), AutomationML (topology
and placement), with a versioned project JSON export/import from Phase 1. Proprietary formats
(Visual Components, Plant Simulation, SolidWorks native) are not targeted.
