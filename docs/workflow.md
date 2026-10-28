# Agent workflow

How work gets done and approved. Greg does not read code. Approval rests on evidence: passing
tests, pasted output, an independent audit, screenshots and Greg using the running app. An
agent's own summary is never evidence.

Greg's attention is the scarce resource, not agent time. The checks stay; what Greg has to read
and decide shrinks to the merge, the questions only he can answer, and a short summary
(ADR 0019).

## Git and GitHub limits

Agents may:

- Commit and push to their own branch, and open a **draft** PR when the work is ready for a look.
- Mark a PR ready for review, only after an audit with a verdict of PASS or PASS WITH NOTES, and
  with no change after it beyond the small fixes "Audit" allows.

Agents never:

- Push or force-push to `main`, or merge anything. Merging is Greg's job and his approval point.

Agents ask Greg first before they:

- Rewrite history on a branch that is already pushed (rebase, amend, force-push).
- Delete a branch, local or remote.
- Change CI or GitHub workflow files (`.github/`).
- Edit `CLAUDE.md` or any agent-rule file: `docs/workflow.md`, `docs/engineering-rules.md`,
  `.claude/`, `.conductor/settings.toml`.

Silence is never approval, here and for level A questions: if Greg has not clearly said yes, do
not proceed.

Scope:

- One task per PR: one spec step, one agreed parking-lot fix, or one direct request from Greg
  (quoted in the PR as the task). If the task grows past its description, stop and report.
- Do only what the spec says (see `CLAUDE.md`). No "while we are here" changes.
- Frozen areas stay untouched unless the spec names them.

## Who decides what

| Level | Who decides | What Greg sees |
|---|---|---|
| **A. Ask Greg** | Greg, before the work | A question with a recommendation |
| **B. Decide and log** | The agent | One line each in the PR details, which Greg may skip |
| **C. Decide silently** | The agent | Nothing |

- **A:** a new behaviour or way of using the app; a bigger visual change (a new screen, layout
  or style, see "Visual changes"); what the AI may write (rule 3); the stored schema shape and
  migrations; prompts; frozen modules; how untrusted files are parsed; new paid services or token
  cost; anything public; phase scope; engineering constants (they need a cited public source); a
  license that is not clearly AGPL-compatible.
  Changes to `models.py`, the prompts or the viewer get an implementation plan that Greg
  approves before files change.
- **B:** small visual tweaks (shown with screenshots), default limits and timeouts, error message
  wording, internal API shapes, how the task is split into commits, new libraries (see "New
  libraries").
- **C:** names of new fields, labels, files, tests and enum values; code structure inside the
  touched files; formatting. Renaming a stored or AI-facing field or enum value is a schema
  change (level A).

## Cycle for one task

1. **Tests first.** Write the tests named in the spec, run them, and show that they fail for the
   right reason.
2. **Implement** until the tests pass. Never delete, skip or weaken an existing test to get
   green. If a test is wrong, say so in the PR and let Greg decide.
3. **Mechanical checks.** Backend `pytest -q` and frontend `npm run build` must pass. The
   repo-rules test (`backend/tests/test_repo_rules.py`) checks the deleted render and names;
   guards for frozen-area changes and for deleted or skipped tests are still to be added.
4. **See it working.** Run the "how to see it" steps in the app with the mock provider and take
   screenshots (see "App checks").
5. **Draft PR.** Commit, push, open a draft PR with the description below.
6. **Audit.** Start a fresh auditor. Fix and audit again as "Audit" says, at most three rounds.
7. **Ready.** Mark the PR ready and send Greg the summary block from the PR description, the
   audit verdict line and the screenshots.
8. **Greg decides.** He reads the summary, looks at the screenshots or the app, and merges or
   says what to change. New libraries are approved as part of the merge.

## Audit

- The auditor is a separate agent with fresh context: a new subagent (never a fork) given only
  the audit prompt below, the PR number and the task (spec step, parking-lot entry or Greg's
  quoted request). The agent that wrote the code never audits its own work.
- An audit runs before every move from draft to ready. No skipping. A FAIL keeps the PR in
  draft: fix it, and a new full audit follows.
- PASS WITH NOTES: fix the high and medium notes. If a fix is small and touches only what the
  note named, no new audit; the PR says what changed for each note. Low notes and wording-only
  notes are listed in the PR, not fixed, and need no new audit.
- A new full audit only when a fix changes how something works, not just how it is worded.
- At most three audit rounds per PR. After the third, stop and hand the PR to Greg with the open
  notes listed. He decides.
- The auditor posts its report as a PR comment itself. The comment is the record: nobody edits
  it. The implementing agent may answer in a separate comment.

## App checks

- Parallel steps of one batch (for example Phase 1 steps 3 to 6) share one app check. Each step
  still has its own automated tests and PR. The last PR of the batch to be ready carries the
  screenshots of the whole batch, run on all its branches merged locally; Greg checks once, then
  merges the batch.
- A step that changes what Greg sees on screen or how someone uses the app gets its own check.
- The agent runs the "how to see it" steps itself wherever it can and attaches screenshots, so
  Greg's check is a quick look. Screenshots are saved under `.context/` (not committed).

## Visual changes

- Bigger changes (a new screen, a new layout, a style change): show a rough version or two or
  three quick options first. Greg picks one; then polish it.
- Small tweaks: screenshots with the PR are enough.

## New libraries

An agent may add a library on its own branch when:

- The license works with AGPL v3: MIT, BSD and Apache 2.0 are fine. Not allowed: "GPL v2 only"
  and source-available licenses such as SSPL or BSL. If unsure, ask Greg (level A).
- The exact version is locked: frontend with `npm install --save-exact` (exact in
  `package.json` and in `package-lock.json`), backend with an `==` pin in
  `backend/pyproject.toml` (the backend has no lock file yet).
- The PR summary lists it with its license, last release date, roughly how widely it is used
  (weekly downloads or dependent projects) and how many other packages it pulls in.

It is logged at level B. Greg approves it with the merge, not separately.

## Small agreed fixes

A parking-lot item can go in as its own small branch, without a new spec, when:

- The entry in `docs/parking-lot.md` says Greg agreed to the fix, and the PR links to it.
- The change is small, does only that one thing, and touches no frozen module or shared
  contract (stored schema, patch operations, prompts, API shapes).
- Before starting, the agent checks what else depends on the thing it changes: other code, the
  mock machines, saved revisions, fixtures. For example, before the hot-melt unit becomes
  category `pump`, check where `dosing` and `pump` are read and whether the category is stored
  in saved designs.

If it turns out bigger, stop and ask Greg for a spec. The fix removes its parking-lot entry in
the same PR. The usual cycle (tests, audit, summary) applies.

## PR description template

The summary is short and in plain language: Greg reads it. The details are for the auditor.
Wherever a spec or the plan asks for a step's "report", this PR description is that report.

```
## Summary
- What changed: three lines max, as the user sees it.
- Why: the spec step or parking-lot entry (link).
- Unsure about: each uncertainty, or "Nothing".
- Needs your decision: level A items, or "None".
- New libraries: name, license, last release, how widely used, packages pulled in; or "None".
- How to see it: screenshots, or one to three steps in the app.

## Details
- Not done: anything in the task skipped, deferred or only partly done.
- Decisions log (level B): one line each, with the reason.
- Evidence: tests added (file::name) and what each proves; output showing they failed first;
  the commands `pytest -q` and `npm run build` with their real last lines and exit codes.
- Files changed: count and list; flag any file outside the task's expected area.
- Risks: what could be wrong that the tests would not catch.
```

## Audit agent: prompt

Give this to a fresh agent. It must not have seen the implementation conversation.

```
You are an independent auditor for Machine Forge. You did not write this code and have no stake
in it. Read CLAUDE.md, docs/engineering-rules.md, docs/workflow.md and the spec for the task
under review (docs/specs/phase-N.md, the linked docs/parking-lot.md entry, or Greg's request
quoted in the PR). Then read the PR
description and the diff (gh pr view <N>, gh pr diff <N>).

Do not fix anything. Report only. Check:
1. Scope: anything changed or added that the task does not ask for.
2. Completeness: every item of the task, done / partly / missing, with file evidence.
3. Frozen areas: any change under app/suppliers/, services/rfq.py, services/plc.py,
   services/sourcing.py, or supplier ratings that the spec does not name.
4. Engineering rules: go through each rule in docs/engineering-rules.md and name any breach,
   especially logic reading a display name or free text, the AI writing computed values, and
   non-deterministic or silently approximating engine code.
5. Tests: any test deleted, skipped, loosened or made vacuous. Do the new tests prove the
   behavior the PR says they do? Run the suites yourself and paste the real output.
6. PR honesty: does each claim in the PR description match the diff? List mismatches.
7. Uncovered decisions: choices in the code that the decisions log does not list, and any that
   belong to level A in docs/workflow.md.
8. Limits: CI, workflow or agent-rule files changed without Greg's request; new libraries without
   an allowed license, an exact version, or a line in the summary.

Output one page: a first line "Verdict: PASS / PASS WITH NOTES / FAIL (commit <sha>)", then
findings ordered by severity, each with file and line. Say plainly what you could not verify.
Post it as a PR comment yourself (gh pr comment <N> --body-file <file>), exactly as written.
```

## Extra scrutiny for the foundation

Model v2 (`models.py`) and the patch validator (`services/patch.py`) are trusted by every later
engine. For these steps, require in addition: the property tests from the spec, an audit by a
strong model at high effort, and a second look at the decisions log by Greg.

## Suggested models

Spec writing, schema and patch validator, audits: Opus at high effort. Mechanical steps
(frontend types, provider fixtures, doc updates): Sonnet at medium.
