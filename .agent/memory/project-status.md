---
name: project-status
description: As of 2026-09-23 milestones M1 and M2 are implemented under server/ and data/ (core, data, i18n, bots, sim, FastAPI server with memory backends); the Redis backends (M2b) and the Unity client (M3) do not exist yet.
metadata:
  type: project
---

As of 2026-09-23: `docs/adr/` (eight decisions) and `docs/protocol/` (card, match, i18n) are
written. `server/` holds `opengwt.core`, `opengwt.data`, `opengwt.i18n`, `opengwt.bots`,
`opengwt.sim` and `opengwt.server`, with about seventy tests; `data/` holds placeholder cards, two
starter decks, three-locale card texts, error and UI strings, and the i18n conformance suite.

M1 acceptance was met on 2026-09-23 (10 000 random-bot matches without an exception, 100 replays
byte-identical, data-only new cards, layers kept, canonical state round trip). M2 acceptance was
met the same day: a scripted client plays a full match against the server-hosted bot over the
WebSocket, two scripted clients play through a room code, a reconnecting client receives the same
view and can `resync`, the opponent's hand never appears on the wire (asserted on every message),
every socket message goes through `MatchService.apply` with the memory backends, the i18n
conformance suite passes in Python, and the migrations run on SQLite locally and on PostgreSQL in
CI. `opengwt.server` runs as one worker process; Redis backends (M2b) and `client/` (M3) do
**not exist yet**.

Both branches are pushed to the public repository at https://github.com/Mr47hsy/open-gwt.

Next: M3, the Unity thin client on UI Toolkit, or M2b, the Redis `MatchStore` / `EventBus` with
the multi-worker acceptance of ADR 0008 — the owner chooses the order.

**Why:** the architecture described in `../context/02-architecture.md` is now mostly built, and
an agent that assumes either more or less than this will invent or miss module paths and APIs.

**How to apply:** check the filesystem before describing any module, path or API as existing.
Update this file when the next milestone is accepted. See [[mvp-order]],
[[server-python-thin-client]] and [[match-scaling-stateless-workers]].
