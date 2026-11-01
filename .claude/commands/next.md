---
description: Find the next spec step that is not merged yet, say which one, and start it
argument-hint: "[step, for example: step 7a]"
---

Start the next piece of work on Machine Forge (ADR 0033).

1. Read what `CLAUDE.md` lists under "Read first, every session".
2. Find the current phase: the newest `docs/specs/phase-N.md` whose done criteria are not all
   met. Do not trust the README status line alone; it can lag behind.
3. Find what is already done or in progress: `git fetch origin`, `git log --oneline origin/main`,
   `gh pr list --state open` and `git worktree list`. A step counts as in progress when an open PR
   or another worktree's branch is working on it.
4. Pick the step:
   - If Greg named one here, take it: $ARGUMENTS
   - Otherwise take the first step in the spec's "Order of work" whose prerequisites are merged
     and that is neither merged nor in progress.
   - Stop and ask Greg when the choice is not clear: several steps are free and could run in
     parallel, the phase is done and the next spec does not exist, or the spec and the merged code
     disagree.
5. Tell Greg in one or two lines: the step, its spec section, the model and effort the spec
   suggests, and whether the step needs his approval of a plan first (schema, prompts or viewer).
6. Then do the step as `docs/workflow.md` says. If it needs plan approval, present the plan and
   wait.
