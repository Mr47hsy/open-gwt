---
name: project-status
description: open-gwt is documentation-only as of 2026-09-22; client/ and server/ are not created yet.
metadata:
  type: project
---

As of 2026-09-22 the repository contains documentation only: trilingual `README` and `CONTRIBUTING`,
`LICENSE` (MIT), `LICENSE-ASSETS` (CC BY 4.0), a Unity + .NET `.gitignore`, and `.agent/`. The
`client/` and `server/` directories do **not exist yet**.

History so far: `b60c049` (docs scaffold, on both branches) and `263e1f0` (`.agent/` context, memory
and skills, on `develop`). Both branches are pushed to the public repository at
https://github.com/Mr47hsy/open-gwt.

**Why:** the architecture described in `../context/02-architecture.md` is design intent, not
something that can be read out of the code, and an agent that assumes otherwise will invent module
paths and APIs that do not exist.

**How to apply:** check the filesystem before describing any module, path or API as existing. When
the first code lands, update this file with what actually exists. See [[branch-strategy]].
