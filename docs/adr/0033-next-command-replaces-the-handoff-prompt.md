# ADR 0033: A `/next` command replaces the handoff prompt

Date: 2026-11-01. Status: accepted. Replaces cycle step 7 of `docs/workflow.md` (added with the
Phase 2 spec, pull request #23, without an ADR).

**Context.** Each worktree had to end with a short prompt for Greg to paste into the next
Conductor workspace. In practice Greg still typed "let's go on with the project" and the agent
worked out the next step from the spec and the git history; the last pull requests left no
prompt at all. The options were to enforce the handoff prompt, or to let the new agent find the
next step itself with a project command, so Greg types one word.

**Decision.** Greg chose the command on 2026-11-01. `.claude/commands/next.md` reads the project
documents, finds the first spec step that is neither merged nor in progress (open pull requests
and other worktrees), says which one in a line, and starts it under `docs/workflow.md`; `/next
<step>` picks a step by name, and an unclear choice is asked, not guessed. The handoff prompt and
its report section are removed. A note the next step needs that the spec does not contain yet
goes into the spec in the same pull request, so it survives without a message to paste. Codex does
not run Claude commands (see `AGENTS.md`); there the same text is read as instructions.
