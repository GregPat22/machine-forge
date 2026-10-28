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
key. The auditor reads the PR description and diff, not public comments; it can read files only
inside the `main` checkout and cannot run code, so its test evidence is the secret-free
`backend` and `frontend` jobs. A separate job without the key posts the report unedited and sets
the "Audit verdict" check, which the `main` ruleset requires. The key is a pay-per-use Anthropic
API key with a monthly spending cap, not Greg's subscription. Rule 6 now reads "test jobs have
no secrets". Fork and bot PRs cannot merge as they are; an agent carries them into its own PR.
