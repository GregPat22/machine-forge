# ADR 0023: The repository is public

Date: 2026-10-28. Status: accepted. Replaces the "private repo" decision of 2026-10-20 in the
`README.md` decisions table.

**Context.** The repository started private while the plan settled. The project is open source
under AGPL-3.0 (ADR 0007) and meant to be built in public. The options were to stay private
until a first shareable version, or to open the repository now. Opening it means every commit,
pull request, issue and CI log is published and stays in the history.

**Decision.** Public from 2026-10-28, chosen by Greg. Before opening, the full public history
(every branch and pull request) was checked for secrets and for employer or customer data; none
was found. GitHub secret scanning and push protection are on. The example price list was removed
because the origin of its prices could not be confirmed (ADR 0005). Rule 12 and ADR 0005 apply
to everything pushed from now on, and Conductor's local checkpoint refs are never pushed.
