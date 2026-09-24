# ADR 0012: Run the server's CI on the Python floor only

- Status: accepted, 2026-09-24
- Deciders: project owner
- Supersedes: in [ADR 0002](0002-rules-core-pure-python-package.md), running the test suite on
  the newest stable Python release as well as on 3.10.
- Related: [ADR 0002](0002-rules-core-pure-python-package.md) (the 3.10.15 floor, which stays)

## Context

ADR 0002 fixed the toolchain floor at Python 3.10.15 and had CI run every server check twice:
on 3.10 and on the newest stable release, 3.14 today. Of the steps in that job, ruff and mypy
target `py310` whatever the interpreter, so the second run repeats their result exactly. Only
pytest and the simulation can behave differently on 3.14.

The owner deploys on 3.10, and `server/.python-version` pins 3.10, so `uv run` works on 3.10 in
a contributor's checkout too unless they override it. The owner decided to drop the 3.14 job.

## Decision

- `.github/workflows/server.yml` runs the server checks on Python 3.10 only. The matrix stays,
  with one entry, so the version it tests is one line to change.
- The floor does not move: `requires-python` stays `>=3.10.15` with no upper bound, and ruff and
  mypy keep targeting `py310`. Newer interpreters stay allowed but are no longer tested.
- When the floor is raised (3.10 reaches end of life in October 2026), `requires-python`,
  `server/.python-version`, the ruff and mypy targets and the matrix entry move together.

## Consequences

- One CI job per push or pull request instead of two.
- Nothing checks that the server still runs on a newer Python. A standard-library removal, a
  changed deprecation or a dependency that resolves or behaves differently there shows up only
  when someone runs it there — typically when the floor is raised, possibly several releases
  later at once.
- The golden replays and state hashes run on one interpreter only, so CI no longer shows that a
  replay gives the same result on two CPython versions. What keeps replays independent of the
  interpreter is still the determinism contract of ADR 0002 (no `hash()` of strings, no
  `random`, integers only, ordered iteration), not the test matrix.

## Alternatives considered

- **Keep both versions (ADR 0002).** Catches problems on the newest release as they appear, at
  the cost of a second full job whose lint and type checks repeat the first's.
- **Keep 3.14 for pytest and the simulation only.** Drops the repeated lint and type checks and
  keeps the forward check, but keeps a second job on every push.
- **A scheduled run on the newest release** (weekly, say), off the pull-request path. Keeps an
  early warning without a second job per change; not taken for now.
