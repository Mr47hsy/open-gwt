---
name: project-status
description: As of 2026-09-23 M1 and M2 are implemented and merged; the M3 Unity thin client exists under client/ with EditMode and PlayMode tests, its human acceptance and mobile smoke builds still open; the Redis backends (M2b) do not exist yet.
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
CI. `opengwt.server` runs as one worker process.

M3 (2026-09-23): `client/` is a Unity 6000.6.2f1 project created by the editor itself and set up
by `OpenGwt.Editor.ProjectSetup.Run`; `Assets/OpenGwt/` holds the C# i18n renderer (passes the
shared conformance suite), `ServerApi`, `MatchSocket`, `MatchClient`, the UI Toolkit board, and
tests. Fonts: a Noto fallback chain built from subset static instances
(`server/scripts/fonts.py`, `FontSetup.Run`); every interface string is keyed and shipped in the
build; language and deck selection exist. Still open for M3 acceptance: the owner's ten complete
matches on macOS; the iOS / Android smoke builds are deferred by the owner until the application
is complete. Redis backends (M2b)
do **not exist yet**.

Both branches are pushed to the public repository at https://github.com/Mr47hsy/open-gwt.

Next: finish M3 acceptance (play-through, CJK font, mobile builds), then M2b, the Redis
`MatchStore` / `EventBus` with the multi-worker acceptance of ADR 0008.

**Why:** the architecture described in `../context/02-architecture.md` is now mostly built, and
an agent that assumes either more or less than this will invent or miss module paths and APIs.

**How to apply:** check the filesystem before describing any module, path or API as existing.
Update this file when the next milestone is accepted. See [[mvp-order]],
[[server-python-thin-client]] and [[match-scaling-stateless-workers]].
