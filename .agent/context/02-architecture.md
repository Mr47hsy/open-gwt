# Architecture

> **Status: decided, not yet built.** The decisions are recorded in `docs/adr/` (0001–0008,
> 2026-09-22) and the wire contracts in `docs/protocol/`. No code exists yet. When code lands and
> disagrees with this file, the code wins — update this file in the same pull request.

## Three layers, two languages

```
rules core   opengwt.core — pure Python package, standard library only, no I/O, no clock
    ↑
server       Python (FastAPI): owns matches, hosts bots, filters hidden information, serves content
    ↑
client       Unity (C#): renders views and events, collects input, sends intents. Runs no rules.
```

The client is **thin** (ADR 0001). It never computes a score, never checks legality and never sees
hidden information. The server sends `legal_intents` with every view; the client enables controls
from that list. Anything "optimistic" in the client is presentation only and must be able to roll
back when the server's events arrive. There is no offline mode: a bot match is a match against a
bot the server hosts in-process.

Inside the server code base the layering is enforced by an import-linter contract:
`core` ← `data` ← `bots` ← `sim` ← `server` (arrows point at what may be imported).

## The determinism contract

A match is **a seed plus an ordered list of accepted intents**. Replaying that record through the
same core version must reproduce the match exactly — same board, same hands, same events.

This is what makes tests, bug reports and bots practical, so the core must avoid everything that
breaks it (ADR 0002):

- no wall-clock time, no timers, no environment or locale reads inside rules evaluation;
- no `random` module — the core carries its own PCG32 over Python integers, seeded from the record;
- no `set` iteration and no `dict` iteration where order affects the result; ordered lists and
  explicit `sorted(..., key=...)`; nothing depends on `hash()` of a string;
- integers only for power, scores and counters; no floats;
- entity ids come from a counter in the state, never from `id()` or allocation order.

A rules change that breaks replay of existing records is a breaking change and must be called out
in the pull request.

## Hidden information

Hands, decks and upcoming draws exist only in the core state held by the server. Views are produced
by the core's `view(state, player)` with hidden information removed *before* serialisation; nothing
else serialises state for a client. "The client filters it out before rendering" is not acceptable
— a modified client would then see everything.

## Content pipeline

Cards, decks and translations are YAML under `data/`, defined by the card protocol
(`docs/protocol/cards.md`, ADR 0003) with a closed vocabulary of triggers, actions and targets.
`opengwt.data` validates them against the JSON Schemas and the cross-file rules and compiles one
content pack. The server loads the pack at start-up and serves it; the client renders from it.
No runtime component reads YAML. A new card is a change under `data/` only; a new vocabulary word
is a core change with a schema version bump.

## Server shape

- Configuration in three layers: code defaults, optional YAML file, environment variables. No
  configuration service (ADR 0004).
- Backends selected by URL with a zero-dependency default: SQLite, in-memory cache, inline tasks,
  in-memory match store. PostgreSQL, MySQL and Redis are packaging extras.
- Live matches live in the match store behind two small interfaces, `MatchStore` and
  `EventBus`, each with a memory and a Redis implementation. Every mutation goes through one
  path, `MatchService.apply`; handlers, bots and timers hold no state. With the memory backends
  the server **refuses to start with more than one worker**; with Redis for both, any number of
  workers may run (ADR 0008). The accepted-intent log is what is durable; snapshots are an
  optimisation, and a live match can be rebuilt by replay.
- Text: the server serves the translation tables per locale, negotiates the player's locale, and
  renders a fallback `message` into every error. Everything else it emits is ids and keys
  (ADR 0006).
- Wire contract: small HTTP API plus one WebSocket per player per match (`docs/protocol/match.md`).

## Client shape

- UI Toolkit for all UI (ADR 0005): UXML and USS text files, `PointerManipulator` for drag and
  drop, no third-party UI dependency in the MVP.
- A presenter consumes the server's event stream sequentially and drives the UI; nothing in the
  UI reads match state directly.
- Localisation: an in-house renderer of the `opengwt.i18n/1` message format
  (`docs/protocol/i18n.md`), fed from the tables the server serves and verified against the same
  conformance suite as the server's renderer (ADR 0006). The Unity Localization package is not
  required.

## Where things belong

| Concern | Layer |
| --- | --- |
| What a card does | card protocol data, interpreted by the rules core |
| Which words the card protocol has | rules core |
| Whether a play is legal | rules core; the server relays `legal_intents` |
| Round/pass/tempo logic | rules core |
| Bots | `opengwt.bots`, run in-process by the server or by the simulator |
| Accounts, decks, rooms, reconnect, replay storage | server |
| Hidden-information filtering | rules core `view()`, invoked only by the server |
| Animation, layout, input, audio | client |
| Rendering text for players | client, with its own renderer; the server renders only the fallback `message` in errors |
| Card art | client assets; card text comes from the pack |

If you find yourself writing a rule inside a `MonoBehaviour`, or inside a FastAPI route, stop: it
belongs in the core.
