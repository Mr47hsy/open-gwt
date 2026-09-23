---
name: project-status
description: As of 2026-09-23 milestone M1 (rules core, data loader, bots, simulator) is implemented under server/ and data/; the FastAPI server (M2) and the Unity client (M3) do not exist yet.
metadata:
  type: project
---

As of 2026-09-23: `docs/adr/` (eight decisions) and `docs/protocol/` (card, match, i18n) are
written; `server/` holds `opengwt.core`, `opengwt.data`, `opengwt.bots` and `opengwt.sim` with 42
tests, and `data/` holds placeholder cards, two starter decks and three-locale texts. M1
acceptance was met on 2026-09-23: 10 000 random-bot matches without an exception, 100 replays
byte-identical, a new card is a `data/`-only change, import-linter keeps the layers, and the core
state round-trips canonically. `opengwt.server` (M2) and `client/` (M3) do **not exist yet**.

Both branches are pushed to the public repository at https://github.com/Mr47hsy/open-gwt.

Next milestone is M2 of ADR 0007: the FastAPI server with the match protocol over WebSocket, the
memory backends behind `MatchStore` / `EventBus`, and the i18n renderer with its conformance
suite.

**Why:** the architecture described in `../context/02-architecture.md` is now partly built, and
an agent that assumes either more or less than this will invent or miss module paths and APIs.

**How to apply:** check the filesystem before describing any module, path or API as existing.
Update this file when the next milestone is accepted. See [[mvp-order]] and
[[server-python-thin-client]].
