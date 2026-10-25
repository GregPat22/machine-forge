# ADR 0011: Review by evidence, not by reading code

Date: 2026-10-25. Status: accepted.

**Context.** Greg does not read code. Agents do most of the implementation, and an agent's own
summary of its work is not reliable evidence that the work is correct or in scope.

**Decision.** Approval rests on evidence: tests written first and shown failing, pasted test and
build output, a fixed one-page report per step, an independent audit by a fresh agent, and Greg
using the running app. Agents never commit, push, merge or approve without Greg's go-ahead.
The full procedure, the report template and the audit prompt are in `docs/workflow.md`. The
options considered were Greg reading every diff (too slow, and he would not catch much) and
trusting agent summaries alone (no independent check). The chosen approach costs extra test and
audit work per step in exchange for a short, checkable review.
