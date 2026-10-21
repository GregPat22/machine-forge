# ADR 0005: No confidential machine data in the repository, ever

Date: 2026-10-21. Status: accepted. Plan decision D5.

**Context.** Calibration needs real numbers. Real numbers are easiest to obtain from machines
one has worked on, which are confidential to an employer or customer. Git history is permanent;
contaminated IP ends an open-source project and any company built on it.

**Decision.** Nothing from an employer, customer or NDA source enters the repo, tests, issues or
commits, in any form, including "anonymised". Calibration uses a public reference machine built
from manufacturers' brochures, vendor catalogs and textbooks, each cited in
`tests/golden/README.md`. Reviewers ask for the source of every engineering constant.
