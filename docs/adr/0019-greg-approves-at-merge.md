# ADR 0019: Greg approves at merge, agents audit and summarise

Date: 2026-10-28. Status: accepted. Replaces the approval rules in ADR 0011 (agents never
commit or push without Greg's go-ahead, a report and an app check per step); the rest of
ADR 0011 stands.

**Context.** The bottleneck is what Greg has to read and decide, not development time. Under
ADR 0011 he approved every diff before a commit (though he does not read code), read a full
report per step including naming choices, started each audit and tried every step in the app.
The options were to keep that, to drop the reviews and trust agents, or to keep every check
but move Greg's gate to the merge and have agents do the routine work. Dropping checks was
ruled out: security, tests and code quality must not weaken.

**Decision.** The third option, chosen by Greg on 2026-10-28. Agents commit and push to their
own branch and open draft PRs. They never push to `main` or merge, and they ask before
rewriting pushed history, deleting branches, or editing CI, workflow or agent-rule files. One
task per PR. Before a PR leaves draft, a fresh agent that did not write the code audits it and
posts its report unedited in the PR. Greg reads a short summary (what changed, why, what is
uncertain) and decides only level A questions; agents decide the rest, logging the ones that
matter. Parallel steps share one app check unless they change the screen or how the app is used,
and agents attach screenshots. Bigger visual changes start with a rough version or options.
Agents may add AGPL-compatible libraries with exact versions, listed in the summary and approved
with the merge. Agreed parking-lot items may go in as small fixes without a spec. Details:
`docs/workflow.md`.
