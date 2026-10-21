# ADR 0010: Vendor CAD and company libraries are per-installation data

Date: 2026-10-21. Status: accepted. Plan decision D10.

**Context.** Vendor CAD models (via TraceParts, PARTcommunity, manufacturer sites) carry terms
that forbid redistribution. Company module libraries are proprietary by nature.

**Decision.** Libraries and their assets live in the installation's data directory, never in
the repository. The public seed library uses only our own parametric envelopes and assets
under permissive licenses, with the license recorded per module. Importers accept STEP and glTF
from the user; the project never downloads vendor models on the user's behalf.
