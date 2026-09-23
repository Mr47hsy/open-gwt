---
name: project-status
description: As of 2026-09-23 the MVP (M1–M3) is merged and ADR 0009 phase B has replaced the v1 rules core — the server speaks protocol 2, the Unity client still speaks 1 and cannot play until phase E; mobile smoke builds deferred, Redis backends (M2b) not started.
metadata:
  type: project
---

As of 2026-09-23, `develop` holds the whole MVP (pull requests #1–#6 merged):

- `docs/adr/` 0001–0008 and `docs/protocol/` (card, match, i18n) — the design.
- `server/`: `opengwt.core` (rules), `opengwt.data` (YAML loading, `opengwt-data` tooling),
  `opengwt.i18n` (renderer), `opengwt.bots`, `opengwt.sim` (`opengwt-sim`), `opengwt.server`
  (`opengwt-server`: FastAPI, WebSocket match protocol, SQLite + memory backends, Alembic).
  Around 70 tests; CI on Python 3.10 and 3.14 with PostgreSQL migrations.
- `data/`: placeholder cards for three factions, two starter decks, en / zh-CN / ru texts for cards,
  interface and errors, the i18n conformance suite (YAML and its JSON twin).
- `client/`: Unity 6000.6.2f1 thin client on UI Toolkit — connect → lobby → match screens,
  language and deck selection, every string keyed and shipped in the build, Noto Sans / Serif
  with SC fallbacks, EditMode tests and a PlayMode test that plays a match against a live server.

Acceptance: M1 met (10 000 bot matches, 100 identical replays). M2 met (scripted clients over the
WebSocket, reconnect, hidden information never on the wire, migrations on SQLite and PostgreSQL).
M3: the owner played the client against the bot with the Chinese interface and confirmed the
text renders; the formal ten-match log of ADR 0007 was not kept. The iOS / Android smoke builds
are **deferred by the owner until the application is complete**. Redis backends (M2b) do **not
exist yet**.

On 2026-09-23 the owner decided to **replace the three-row ruleset with the two-row standalone
ruleset** (ADR 0009, [[ruleset-v2]]), in phases A–F. Phase A (the v2 protocols) and phase B are
done: the core implements two rows, positions and capacity, the standalone power model, statuses
with timers, draws and redraws each round, the hand limit and the tie rule, with the SHA-256
random streams, 256-bit seeds, `opengwt.record/2` and opaque instance ids of ADR 0010; `data/`
and the golden replay are v2 (a breaking replay change). Phase B acceptance: 10 000 random-bot
matches without an exception, 100 identical replays, canonical state round trips.

The server speaks protocol 2. **The Unity client still speaks protocol 1 and cannot play until
phase E** — the owner accepted that gap: upgrade phases do not keep the client compatible. Its
PlayMode test against a live server fails until then. Client polish and content work that depend
on the rules wait for the relevant phase; the rest of [[backlog]] is open to parallel sessions,
with the branch discipline in `AGENTS.md`.

**Why:** an agent that assumes either more or less than this will invent or miss module paths,
APIs and acceptance results.

**How to apply:** check the filesystem before describing any module, path or API as existing;
update this file when a milestone or a backlog item lands. See [[mvp-order]],
[[client-workflow]], [[backlog]].
