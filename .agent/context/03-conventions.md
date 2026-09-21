# Conventions

## Branches

Classic git-flow, two branches:

- `release` — publish branch, and the default branch on GitHub.
- `develop` — integration branch for day-to-day work.

There is no `main`; it was deleted as a duplicate of `release`. Do not recreate it.

Branch off `develop` for features and fixes, and open the pull request against `develop`. Only a
release merges `develop` into `release`; nobody pushes to `release` directly. `release` sitting
behind `develop` between releases is expected.

## Commits

Conventional-commit prefixes, imperative subject, in English:

```
docs: add trilingual README, licenses and contribution guide
feat(core): add row-limit check to unit placement
fix(server): stop leaking opponent hand size on reconnect
test(core): cover pass-in-round-three tie handling
```

Common scopes: `core`, `server`, `client`, `bots`, `docs`, `assets`, `ci`.

Explain *why* in the body when the reason is not obvious from the diff. For a rules change, name the
public source or the observed behaviour you based it on — this is part of the clean-room record, see
`04-legal.md`.

## Tests

A rules change ships with a test that fails before it and passes after it. Replay-based tests are
preferred: seed + action log + expected end state.

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

## Code style

- Rules core: plain C#, no engine types, no `UnityEngine` using-directives, deterministic (see
  `02-architecture.md`).
- Unity code: `MonoBehaviour`s render and collect input; they do not decide outcomes.
- Names and comments in English. Do not put card flavour text in code comments.
