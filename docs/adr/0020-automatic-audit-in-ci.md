# ADR 0020: Automatic audit in CI gates every merge

Date: 2026-10-28. Status: accepted. Adds to ADR 0019, which keeps the audit an agent starts
before a PR leaves draft.

**Context.** Under ADR 0019 the audit depends on an agent remembering to start it. Greg wants
it to run by itself and to block merges until it passes, without letting a PR change its own
audit and without exposing the API key once the repository is public. The options were the
`pull_request` trigger (the workflow file then comes from the PR, so a PR could rewrite its own
audit), `pull_request_target` with the PR's code checked out (the key would sit next to code
anyone can propose), and `pull_request_target` reading the PR only through the GitHub API.

**Decision.** The third, chosen by Greg on 2026-10-28. `.github/workflows/audit.yml` audits
every non-draft PR from this repository into `main`, with the workflow and the checklist
`.github/audit-prompt.md` as they are on `main`; fork PRs are skipped, so they never reach the
key. A step without the key saves the PR description, the diff of the audited commit and the
results of the secret-free `backend` and `frontend` jobs as files; the auditor has no commands
and reads only files of the `main` checkout, so it cannot reach the key and public comments never
reach it. A separate job without the key posts the report unedited and completes the "Audit
verdict" check, which turns "in progress" when an audit starts and which the `main` ruleset
requires. The key is a pay-per-use Anthropic API key with a monthly spending cap, not Greg's
subscription. Rule 6 now reads "test jobs have no secrets". Fork PRs and bot-started runs cannot
pass; an agent carries such changes into its own PR.
