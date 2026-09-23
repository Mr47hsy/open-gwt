# ADR 0002: Rules core as a zero-dependency Python package

- Status: accepted, 2026-09-22; the PRNG clause is superseded by
  [ADR 0010](0010-unpredictable-random-stream.md) from ruleset phase B on
- Deciders: project owner
- Related: [ADR 0001](0001-python-server-unity-thin-client.md)

## Context

The rules core is the only place that knows what the rules are. It must be testable without a
server, usable by bots without a network, and replayable bit-for-bit from a seed plus an action
log. It lives in the Python server code base (ADR 0001), which makes it easy to accidentally
couple it to web, database or configuration code.

## Decision

- The core is the package `opengwt.core`. It imports **only the Python standard library**. An
  import-linter contract enforces this in CI; a pull request that makes `opengwt.core` import
  anything else fails.
- Layering inside the server code base, enforced by the same contract:
  `core` ← `data` (YAML loading, validation, pack compilation) ← `bots` ← `sim` ← `server`.
  Arrows point at what may be imported.
- The core exposes pure functions over an explicit state value:
  - `apply(state, intent) -> (state, events)` — the only way to change a match;
  - `legal_intents(state, player)` — what a player may do now;
  - `view(state, player)` — the per-player projection with hidden information removed;
  - `replay(record)` — seed plus decks plus ordered intents, back to a final state.
- Determinism is implemented, not hoped for:
  - the core carries its **own PRNG** (PCG32 on Python integers), seeded from the match record;
    the `random` module is not used anywhere in the core;
  - no `set` iteration and no `dict` iteration where order affects the result; ordered lists and
    explicit `sorted(..., key=...)` only; nothing depends on `hash()` of a string;
  - integers only for power, scores and counters; no floats;
  - no wall-clock time, no environment or locale reads;
  - entity ids are assigned from a counter in the state, never from `id()` or allocation order.
- **Toolchain floors: Python `>=3.10.15` and uv `>=0.12.5`**, declared in `pyproject.toml` as
  `requires-python` and `[tool.uv] required-version`. The floor is enforced by tooling, not by
  discipline: ruff and mypy target `py310`, and CI runs the test suite on 3.10 and on the newest
  stable release. Syntax and library features newer than 3.10 are therefore off the table in every
  package, not only the core: no `type` statements, `typing.Self`, `typing.override`, `tomllib`,
  `StrEnum`, `ExceptionGroup` or `itertools.batched`.
- The core is type-annotated and checked strictly.

## Consequences

- Tests, bots and the simulator run the real rules in-process with no fixtures beyond a record.
- A rules change is a change in `opengwt.core` and comes with a replay-based test.
- Performance is not a concern at this scale: a match is a few hundred state transitions, and
  ten thousand bot matches in the simulator are a matter of minutes, not hours.
- The core can be published or vendored on its own later, because nothing else leaks into it.
- Python 3.10 reaches end of life in October 2026. The floor is the owner's deployment
  environment, and raising it later is a one-line change plus a CI matrix edit; lowering it later
  would not be, which is why it is set at the floor now.

## Alternatives considered

- **Split packages in a workspace** (`opengwt-core`, `opengwt-server`, …). Cleaner boundary,
  more packaging overhead. Deferred: the import contract gives the same guarantee today, and a
  split is mechanical once the boundary has held for a while.
- **Use `random.Random(seed)`.** Its algorithms are stable in practice, but the guarantee is
  weaker than owning twenty lines of PCG32, and it would tie replays to CPython behaviour.
