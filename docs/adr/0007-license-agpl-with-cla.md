# ADR 0007: AGPL-3.0 with a contributor license agreement

Date: 2026-10-21. Status: accepted, pending legal review. Plan decision D7.

**Context.** The project is open source now and may become a company later. Apache-2.0 would
maximise adoption but lets a cloud vendor host a closed fork. Source-available licenses (BSL,
FSL) are not open source.

**Decision.** GNU AGPL-3.0 for the code, with a CLA (`CLA.md`) under which contributors grant
the maintainer relicensing rights and sign off under the DCO. AGPL blocks closed SaaS forks;
companies self-hosting internally are unaffected. The CLA keeps the door open to dual
licensing, open-core, or a later move to Apache-2.0 if adoption matters more than protection.
Library assets, vendor CAD and company data are per-installation and outside this license.
Legal counsel reviews the wording before the first external contribution.
