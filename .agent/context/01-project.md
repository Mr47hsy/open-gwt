# What open-gwt is

An open-source, unofficial reimplementation of the Gwent rules — the ruleset of the standalone
online game, decided in ADR 0009 on 2026-09-23. Official content development for Gwent has
ended; this project keeps the design alive as open source so it can be played, studied, forked
and extended.

## What makes the design worth reimplementing

- No mana curve in play — every card in hand is playable on any turn; the resource decision is
  the provision budget at deck-building time.
- Two rows with positional play: adjacency, row effects and row limits make *where* a real choice.
- Activated abilities within a turn: what to trigger before committing the one card that ends it.
- Best-of-three rounds with draws and redraws each round, so card advantage is earned and spent.
- The tempo game around **when to pass** — conceding a round to keep card advantage is the central
  skill of the game.

Anything that would flatten one of these is a design regression, not a simplification.

**Transition (2026-09-23):** phase B of ADR 0009 has landed: the core plays two rows with
capacity and positions, the standalone power model, statuses with timers, draws and redraws each
round and the tie rule, and the server speaks protocol 2. It loads the whole v2 vocabulary but
the phase-C words (other triggers, activated abilities, generalised choices) do nothing yet; deck
building is phase D and the Unity client speaks protocol 1 until phase E, so it cannot play in
between. The v1 shape is gone; read the ADR and `docs/protocol/cards.md` before touching the
core.

## Scope

In scope: the rules core, an authoritative server, a Unity client, bots, documentation, and
original art and audio.

Shape, decided 2026-09-22 (`docs/adr/`): the **server is Python** and contains the rules core as a
zero-dependency package; the **client is a Unity thin client** that runs no rules and needs a
server even for a match against a bot. Card content is authored in YAML under `data/`.

Out of scope: shipping anything from CD PROJEKT RED, monetisation, account systems beyond what
multiplayer needs, offline play (see ADR 0001), and "improvements" that quietly change the game's
shape.

## Platforms

Windows · macOS · iOS · Android, on Unity 6.6 (6000.6.2f1). Online-only.

## Current state — 2026-09-23

Milestones M1 and M2 of ADR 0007 are implemented. `server/` is a uv project (Python ≥ 3.10.15)
with `opengwt.core` (the v2 rules engine of ADR 0009 phase B, SHA-256 random streams, views,
canonical serialisation, replay), `opengwt.data`
(YAML loading against the protocol schemas), `opengwt.i18n` (the shared message-format renderer),
`opengwt.bots` (random, greedy), `opengwt.sim` (`opengwt-sim`) and `opengwt.server`
(`opengwt-server`: FastAPI, guest tokens, decks, bot and room matches, the WebSocket match
protocol, SQLite plus memory `MatchStore` / `EventBus` / `Cache`, Alembic migrations). `data/`
holds v2 placeholder cards for two factions and neutral, two starter decks and en / zh-CN / ru
texts. CI runs
ruff, mypy, import-linter, pytest (with the migrations on SQLite and PostgreSQL) and a simulation
on Python 3.10 and 3.14.

`client/` is the Unity 6.6 project of milestone M3: `Assets/OpenGwt/` with the C# twin of the
i18n renderer, `ServerApi` and `MatchSocket`, `MatchClient`, the UI Toolkit `BoardView`
(connect → lobby → match, language and deck selection, every string keyed and shipped in the
build), a Noto Sans / Serif font chain with SC fallbacks, editor setup, font and build scripts,
EditMode tests and a PlayMode test that plays a match against a running server. The owner has
play-tested it against the bot in Chinese. The iOS / Android smoke builds are deferred until the
application is complete; open work is listed in `../memory/backlog.md`. The Redis backends
(M2b) do **not exist yet**. Do not tell a user a module exists because it is mentioned here — check the filesystem.

## Legal position in one line

Unofficial fan work, not approved or endorsed by CD PROJEKT RED, containing none of their assets.
Every distribution surface (README, store pages, client splash) must say so.
