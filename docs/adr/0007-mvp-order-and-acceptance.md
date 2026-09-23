# ADR 0007: MVP order — core, then server, then client

- Status: accepted, 2026-09-22
- Deciders: project owner
- Related: all previous records

## Context

The fastest way to find out whether the architecture holds is not to open Unity first. The rules
core can be validated with bots and replays in minutes; a client validates presentation, which is
not where the risk is. The owner chose the order core → server → client.

## Decision

The MVP is built in three milestones, each with an acceptance test that does not depend on the
next milestone existing.

### M1 — rules core, bots, simulator

Scope: three rows, best of three rounds, pass, mulligan, the row effects and abilities in the
card protocol vocabulary (`docs/protocol/cards.md`), a placeholder card set of roughly thirty
cards with neutral ids and no display names, a random bot and a greedy bot, a command-line
simulator, and replay-based tests.

Accepted when:

- ten thousand bot-versus-bot matches run without an exception;
- one hundred of them, replayed from seed plus intents, reproduce the final state byte for byte;
- adding a new card is a change under `data/` only;
- the core state round-trips through canonical serialisation: serialise, deserialise, serialise
  again yields identical bytes (needed by replay storage and by ADR 0008);
- the import-linter contract for `opengwt.core` passes.

### M2 — server

Scope: FastAPI application with guest login, deck storage, "play against a bot" and "room code"
matches, the WebSocket match protocol (`docs/protocol/match.md`), the content pack endpoint,
SQLite and memory backends by default, replay storage.

Accepted when:

- a scripted client plays a full match against the server-hosted bot over WebSocket;
- two scripted clients play each other through a room code;
- a client that disconnects mid-match reconnects and receives the same view it would have had;
- the opponent's hand never appears in any message captured on the wire;
- every WebSocket message goes through `MatchService.apply` and the memory backends; no handler
  holds match state (ADR 0008);
- the i18n conformance suite passes in the Python renderer (ADR 0006);
- the same server starts with PostgreSQL by changing one URL, and its migrations pass on both.

Multi-worker operation over Redis is a milestone of its own, **M2b**, with its acceptance in
ADR 0008. It follows M2 and does not block M3.

### M3 — Unity client

Scope: thin client on UI Toolkit, flat placeholder card visuals, a match against the bot, a
match against another client through a room code, macOS first, then iOS and Android smoke builds.

Accepted when:

- ten complete matches are played on macOS against the server without a client-side error;
- iOS and Android builds start and reach the board;
- the i18n conformance suite passes in the C# renderer, and the client renders every string it
  shows from keys;
- the client contains no rules code: it never computes a score or checks legality.

## Consequences

- Nothing in M1 needs a network, a database or Unity.
- The server is proven with scripted clients before any UI exists, so M3 is a rendering task.
- Client-only features that need rules on the client (offline play, prediction) remain out of
  scope; see ADR 0001.

## Alternatives considered

- **Unity first.** Shows something on screen sooner and validates nothing about the rules or the
  protocol. Rejected.
- **Server and client together.** Doubles the surface under change while the protocol is still
  moving. Rejected.
