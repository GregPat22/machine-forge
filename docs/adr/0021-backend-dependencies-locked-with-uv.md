# ADR 0021: Backend dependencies locked with uv

Date: 2026-10-28. Status: accepted.

**Context.** The backend declared minimum versions in `pyproject.toml` and had no lock file, so
CI, agents' workspaces and contributors could each install different versions of the same
libraries, and ADR 0019's rule on exact versions could only pin the direct package. The
options were pip-tools (one requirements file per platform and Python version), Poetry (a
rewrite of `pyproject.toml` into its own format) and uv.

**Decision.** uv, chosen by Greg on 2026-10-28. `backend/uv.lock` records the exact version and
checksums of every package, for every platform and Python version the project supports, from
the unchanged `pyproject.toml`. CI, the Conductor setup script and the README install with
`uv sync --locked`, which fails if the lock is out of date; new libraries are added with
`uv add`. uv is MIT or Apache 2.0, and CI pins its version. `pip install -e .` still works but
ignores the lock.
