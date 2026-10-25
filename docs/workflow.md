# Agent workflow

How work gets done and approved. Greg does not read code. Approval rests on evidence: passing
tests, pasted output, an independent audit, and Greg using the running app. An agent's own
summary is never evidence.

## Hard limits for every agent

- Never commit, push, merge, open a PR as final, or approve anything without Greg's explicit
  go-ahead. Leave changes in the working tree or on a local branch and stop.
- One spec step per branch. If the step grows past its description, stop and report.
- Do only what the spec says (see `CLAUDE.md`). No "while we are here" changes.
- Frozen areas stay untouched unless the spec names them.

## Cycle for one spec step

1. **Tests first.** The implementing agent writes the tests named in the spec, runs them, and
   shows that they fail for the right reason.
2. **Implement** until the tests pass. Never delete, skip or weaken an existing test to get
   green. If a test is wrong, say so in the report and let Greg decide.
3. **Mechanical checks.** Backend `pytest -q` and frontend `npm run build` must pass. The
   repo-rules test (`backend/tests/test_repo_rules.py`) only checks the deleted render today;
   guards for frozen-area changes and for deleted or skipped tests are still to be added.
4. **Report.** The implementing agent writes the report below and stops.
5. **Audit.** A separate fresh agent (no part in the implementation) runs the audit prompt below
   against the diff and the spec, and writes a verdict.
6. **Greg decides.** Greg reads the report and the verdict, tries the "how to see it" steps in
   the running app, and says go or no-go. Only then does anything get committed.

One human gate per phase, plus the per-step go/no-go. Everything between runs without Greg.

## Implementing agent: report template

Write it as `report.md` next to the work (not committed). One page. Plain language, no jargon
that is not already in `docs/PLAN.md`.

```
# Report: <spec step>

## What I did
Five lines max, plain language.

## Why
Which spec item and which done criterion this satisfies.

## What I did NOT do
Anything in the step I skipped, deferred or only partly did.

## Decisions the spec did not cover
Each choice I made that the spec was silent on, with my reason. "None" only if true.

## Evidence
- Tests added (file::name) and what behavior each one proves.
- Pasted output of `pytest -q` and `npm run build` (the real last lines, not a description).
- Output showing the new tests failed before the change.

## Files changed
Count, plus the list. Flag any file outside the step's expected area.

## How Greg can see it working
One to three concrete steps in the running app (use the mock provider).

## Risks
What could be wrong that the tests would not catch.
```

## Audit agent: prompt

Give this to a fresh agent. It must not have seen the implementation conversation.

```
You are an independent auditor for Machine Forge (~/machine-forge). You did not write this code
and have no stake in it. Read CLAUDE.md, docs/engineering-rules.md, and the spec for the step
under review (docs/specs/phase-N.md). Then read the diff and the implementing agent's report.

Do not fix anything. Report only. Check:
1. Scope: anything changed or added that the spec does not ask for.
2. Completeness: every spec item for this step, done / partly / missing, with file evidence.
3. Frozen areas: any change under app/suppliers/, services/rfq.py, services/plc.py,
   services/sourcing.py, or supplier ratings that the spec does not name.
4. Engineering rules: go through each rule in docs/engineering-rules.md and name any breach,
   especially logic reading a display name or free text, the AI writing computed values, and
   non-deterministic or silently approximating engine code.
5. Tests: any test deleted, skipped, loosened or made vacuous. Do the new tests prove the
   behavior the report says they do? Run the suites yourself and paste the real output.
6. Report honesty: does each claim in the report match the diff? List mismatches.
7. Uncovered decisions: choices in the code that the report did not list.

Output one page: a verdict (PASS / PASS WITH NOTES / FAIL), then findings ordered by severity,
each with file and line. Say plainly what you could not verify.
```

## Extra scrutiny for the foundation

Model v2 (`models.py`) and the patch validator (`services/patch.py`) are trusted by every later
engine. For these steps, require in addition: the property tests from the spec, an audit by a
strong model at high effort, and a second look at the "Decisions the spec did not cover"
section by Greg.

## Suggested models

Spec writing, schema and patch validator, audits: Opus at high effort. Mechanical steps
(frontend types, provider fixtures, doc updates): Sonnet at medium.
