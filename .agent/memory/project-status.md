---
name: project-status
description: open-gwt is documentation-only as of 2026-09-22; client/ and server/ are not created yet.
metadata:
  type: project
---

As of 2026-09-22 the repository contains documentation only: trilingual `README` and `CONTRIBUTING`,
`LICENSE` (MIT), `LICENSE-ASSETS` (CC BY 4.0), a Unity + .NET `.gitignore`, and `.agent/`. The
initial commit is `b60c049`. The `client/` and `server/` directories do not exist yet, and nothing
has been pushed to `origin` (https://github.com/Mr47hsy/open-gwt.git) — the remote is still empty.

**Why:** the architecture described in `../context/02-architecture.md` is design intent, not
something that can be read out of the code, and an agent that assumes otherwise will invent module
paths and APIs that do not exist.

**How to apply:** check the filesystem before describing any module, path or API as existing. When
the first code lands, update this file with what actually exists. See [[branch-strategy]].
