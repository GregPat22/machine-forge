# Contributing

Machine Forge is developed in phases. Read, in this order:

1. `docs/PLAN.md`: product, decisions, phases.
2. `docs/engineering-rules.md`: what every PR is checked against.
3. `docs/specs/phase-N.md`: the current phase. Work outside the current phase is parked, not merged,
   except small fixes the maintainer agreed to in `docs/parking-lot.md`.

## Workflow

- Branch from `main`, one concern per branch, small commits.
- Tests first for numeric behaviour (engines, migrations, layout). Tests never need network or keys.
- Run `cd backend && pytest -q` and `cd frontend && npm run build` before opening a PR.
- A PR links the phase spec it implements (or, for a small agreed fix, its entry in
  `docs/parking-lot.md`), updates docs and ADRs in the same PR, and touches no frozen module
  (`app/suppliers/`, `services/rfq.py`, `services/plc.py`) unless the spec says so.
- New dependencies: AGPL-compatible license (MIT, BSD, Apache 2.0; not "GPL v2 only", SSPL or
  BSL), exact version, listed in the PR description (see `docs/workflow.md`).
- Engineering constants (speeds, accelerations, index times, formulas) cite a public source.
  No data from employers, customers or NDAs, ever.

## License and contributor agreement

The project is licensed under the GNU Affero General Public License v3.0 (`LICENSE`). By
contributing you agree to `CLA.md`, which includes a Developer Certificate of Origin sign-off
(`git commit -s`) and grants the maintainer the right to relicense your contribution.
