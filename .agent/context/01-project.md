# What open-gwt is

An open-source, unofficial reimplementation of the Gwent rules. Official content development for
Gwent has ended; this project keeps the design alive as open source so it can be played, studied,
forked and extended.

## What makes the design worth reimplementing

- No mana curve — every card is playable on any turn, so the decision is *which* card, not *when can
  I afford it*.
- Three rows, which turn positioning into a real decision.
- Best-of-three rounds with a shared hand across rounds: cards spent now are cards you do not have
  later.
- The tempo game around **when to pass** — conceding a round to keep card advantage is the central
  skill of the game.

Anything that would flatten one of these is a design regression, not a simplification.

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

## Current state — 2026-09-22

The repository contains documentation only: trilingual `README` and `CONTRIBUTING`, `LICENSE` (MIT,
code) and `LICENSE-ASSETS` (CC BY 4.0, original art and audio), a `.gitignore` for Unity and .NET,
this `.agent/` directory, `docs/adr/` (decisions 0001–0007) and `docs/protocol/` (card and match
protocols with schemas and examples).

`client/`, `server/` and `data/` do **not exist yet**. Any description of them in
`02-architecture.md` is intended design, not something you can read out of the code. Do not tell
a user a module exists because it is mentioned here — check the filesystem.

## Legal position in one line

Unofficial fan work, not approved or endorsed by CD PROJEKT RED, containing none of their assets.
Every distribution surface (README, store pages, client splash) must say so.
