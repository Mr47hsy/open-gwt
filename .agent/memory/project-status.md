---
name: project-status
description: open-gwt is documentation-only as of 2026-09-22; decisions and protocols are written, client/, server/ and data/ are not created yet.
metadata:
  type: project
---

As of 2026-09-22 the repository contains documentation only: trilingual `README` and `CONTRIBUTING`,
`LICENSE` (MIT), `LICENSE-ASSETS` (CC BY 4.0), a Unity + .NET `.gitignore`, `.agent/`, `docs/adr/`
(eight accepted decisions) and `docs/protocol/` (card protocol with JSON Schemas and worked
examples, match protocol, i18n protocol with a conformance suite). The `client/`, `server/` and `data/` directories do **not exist yet**.

Both branches are pushed to the public repository at https://github.com/Mr47hsy/open-gwt.

Next milestone is M1 of ADR 0007: the rules core, bots and simulator in Python, with no server
and no Unity involved.

**Why:** the architecture described in `../context/02-architecture.md` is decided but not built,
and an agent that assumes otherwise will invent module paths and APIs that do not exist.

**How to apply:** check the filesystem before describing any module, path or API as existing. When
the first code lands, update this file with what actually exists. See [[mvp-order]] and
[[server-python-thin-client]].
