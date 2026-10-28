# ADR 0022: At most three audit rounds per PR

Date: 2026-10-28. Status: accepted. Changes one rule of ADR 0019: a commit pushed after an
audit no longer always needs a new audit. The rest of ADR 0019 stands.

**Context.** Under ADR 0019 every fix after an audit needed a new full audit. On PR #14 that
gave three rounds and a fourth started, each finding smaller points than the last, with no end
point and a token cost each time. The options were to keep re-auditing until a clean PASS, to
let the agent decide when to stop, or to set a fixed limit and a rule for which fixes need a new
audit.

**Decision.** The fixed limit, chosen by Greg on 2026-10-28. At most three audit rounds per PR;
after the third the agent stops and hands the PR to Greg with the open notes, and he decides. A
FAIL is fixed and audited again. After PASS WITH NOTES the agent fixes high and medium notes; a
small fix that touches only what the note named needs no new audit, and the PR says what
changed. Low and wording-only notes are listed in the PR, not fixed. A new full audit runs only
when a fix changes how something works. Details: `docs/workflow.md`, "Audit".
