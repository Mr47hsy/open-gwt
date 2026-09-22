# Conventions

## Branches

Classic git-flow, two branches:

- `release` — publish branch, and the default branch on GitHub.
- `develop` — integration branch for day-to-day work.

There is no `main`; it was deleted as a duplicate of `release`. Do not recreate it.

Branch off `develop` for features and fixes, and open the pull request against `develop`. Only a
release merges `develop` into `release`; nobody pushes to `release` directly. `release` sitting
behind `develop` between releases is expected.

The policy is enforced, not just documented — see [`.github/BRANCH_POLICY.md`](../../.github/BRANCH_POLICY.md):

- `develop` takes no direct pushes. Every change arrives by pull request, approved by the owner
  (`.github/CODEOWNERS`).
- `release` accepts pull requests **from `develop` only**. GitHub cannot express that, so
  `.github/workflows/branch-policy.yml` checks the source branch and is wired up as a required
  status check.
- Release tags are `release-1.2.3` — three numeric components, no `v` prefix — created by the owner
  on `release`. A tag ruleset restricts who may create them; `.github/workflows/tag-policy.yml`
  verifies the tagged commit is actually contained in `release`, after the fact.

Do not work around any of this. If a workflow needs a new path (a hotfix branch, say), change the
policy in `.github/BRANCH_POLICY.md` and the workflow together, in a pull request.

## Commits

Conventional-commit prefixes, imperative subject, in English:

```
docs: add trilingual README, licenses and contribution guide
feat(core): add row-limit check to unit placement
fix(server): stop leaking opponent hand size on reconnect
test(core): cover pass-in-round-three tie handling
feat(data): add placeholder faction B
```

Common scopes: `core`, `data`, `bots`, `server`, `client`, `protocol`, `docs`, `assets`, `ci`.

Explain *why* in the body when the reason is not obvious from the diff. For a rules change, name the
public source or the observed behaviour you based it on — this is part of the clean-room record, see
`04-legal.md`.

## Decisions

Architecture decisions go in `docs/adr/` as numbered records that are not rewritten afterwards.
When a record changes a rule an agent relies on, update `.agent/context/` in the same pull request.

## Tests

A rules change ships with a test that fails before it and passes after it. Replay-based tests are
preferred: seed + decks + intents + expected end state, kept as data files.

Python tests use pytest. The import-linter contract for `opengwt.core` and the content compiler's
validation of `data/` are CI steps, not optional checks.

## Pull requests

One concern per pull request. A rules fix and a client refactor do not belong together. Build and
tests pass before review is requested.

## Trilingual documentation

`README` and `CONTRIBUTING` exist in English (`.md`), Simplified Chinese (`.zh-CN.md`) and Russian
(`.ru.md`). English is the source of truth; the others are translations that must not drift from it.

Every one of these files carries a language switcher as its first line under the title, with the
current language in bold and the other two as links.

When you change one of them, change all three in the same pull request, or say explicitly in the
pull request description which translations are outstanding. See `../skills/docs-i18n-sync/`.

`docs/adr/`, `docs/protocol/` and `.agent/` are English only.

## Code style

- Rules core (`opengwt.core`): Python 3.12+, standard library only, fully type-annotated and
  checked strictly, deterministic (see `02-architecture.md`). No I/O, no logging, no clock.
- Server: FastAPI, async throughout, ruff for formatting and linting. Routes call the core and the
  backends; they contain no rules.
- Card content: YAML under `data/`, valid against `docs/protocol/*.schema.json`. Ids are opaque
  and never displayed; text lives in `data/i18n/`.
- Unity code: `MonoBehaviour`s and UI Toolkit controllers render and collect input; they do not
  decide outcomes. UI is authored as UXML and USS text files.
- Names and comments in English. Do not put card flavour text in code comments.
