---
name: branch-strategy
description: git-flow — release is the default publish branch, develop is the integration branch; main was deleted.
metadata:
  type: project
---

Decided 2026-09-22: classic git-flow with two branches.

- `release` — publish branch, and the default branch on GitHub.
- `develop` — integration branch; all day-to-day work branches off it and merges back into it.
- `main` — **deleted.** It duplicated `release` and no longer exists locally or on the remote.

Both branches are pushed to `origin` (https://github.com/Mr47hsy/open-gwt.git, public). GitHub picked
`release` as the default branch on its own, because it was the first branch pushed to the empty
repository — no repository setting was changed by hand.

`release` may lag behind `develop` between releases; that is the intended shape, not drift to fix.

**Why:** the owner asked for a dedicated `release` branch in a repository that already had `main`,
and chose to drop `main` rather than keep two branches meaning the same thing.

**How to apply:** branch off `develop`, open pull requests against `develop`, and merge into
`release` only when publishing. Do not recreate `main` or push to `release` directly. See
[[project-status]].
