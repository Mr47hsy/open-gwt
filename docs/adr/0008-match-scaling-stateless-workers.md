# ADR 0008: Match scaling — stateless workers over a shared match store

- Status: accepted, 2026-09-22
- Deciders: project owner
- Related: [ADR 0002](0002-rules-core-pure-python-package.md),
  [ADR 0004](0004-server-config-and-optional-backends.md), [`docs/protocol/match.md`](../protocol/match.md)

## Context

ADR 0004 keeps live matches in the memory of the process that hosts them, which forces a single
worker process. The owner asked whether Redis-backed state lifts that limit. It does, provided the
match-handling code is written so that the *store* is the only thing that changes between the
single-worker and the multi-worker deployment.

There are two ways to run many workers. **Stateless workers** load, mutate and save match state
through a shared store on every intent; any worker can serve any match. **Sticky ownership** gives
each match one owning worker and routes connections to it; the store holds only snapshots.

## Decision

Stateless workers over a shared store, built into the server from the first commit through
backend interfaces with a memory implementation and a Redis implementation.

1. **One mutation path.** `MatchService.apply(match_id, seat, intent)` is the only code that
   changes a match: acquire the match lock → load state and version → `core.apply` → save with a
   version check → append the accepted intent to the durable record → publish the events and both
   players' views → release the lock. WebSocket handlers, bots and timers all call it; none of
   them hold match state.
2. **`MatchStore`** — `load(match_id) → (state, version)`, `save(match_id, state, version)` with
   optimistic concurrency, `lock(match_id)` as an async context. Memory: a dict and an
   `asyncio.Lock` per match. Redis: `SET NX PX` lock, a version key, the state as a canonical
   snapshot.
3. **`EventBus`** — `publish(match_id, seq, payload)` and `subscribe(match_id, since_seq)` as an
   async iterator. Memory: per-match queues over a ring buffer. Redis: Streams, `XADD` with
   `MAXLEN`, `XREAD` for live delivery, `XRANGE` from a `seq` for the protocol's `resync`.
4. **The intent log is the durable thing; snapshots are an optimisation.** Every accepted intent
   is appended synchronously — to the database, or to a Redis Stream with append-only persistence
   — before its events are published. Because the core is deterministic (ADR 0002), any worker can
   rebuild a live match from `replay(seed, decks, intents)` if the snapshot is missing.
5. **Bots move inside the lock.** When a human intent leaves the turn with a server-hosted bot,
   the same worker computes and applies the bot's intents before releasing the lock. Turn-based
   play makes this cheap, and it keeps a bot's move in the same ordered record as everything else.
6. **Timers are shared.** Turn deadlines live in a sorted set (memory: a heap; Redis: `ZSET`).
   One timer loop — a dedicated process, or a worker holding a leader lock — pops due deadlines
   and calls `apply` with a pass. Per-process timers are never used in multi-worker mode.
7. **Idempotent intents.** The last few `intent_id`s per match are kept with the state; a
   duplicate returns the earlier outcome instead of applying twice.
8. **Start-up check replaces the blanket rule.** With a memory match store *or* a memory event
   bus the server refuses to start with more than one worker. With Redis for both, any number of
   workers may run behind one port.

### Prerequisites pulled into earlier milestones

- **M1:** the core state round-trips through canonical serialisation — serialise, deserialise,
  serialise again yields identical bytes. Replay storage needs it too.
- **M2:** all WebSocket handling goes through `MatchService` and the memory backends; no handler
  holds match state. Multi-worker mode then differs from single-worker mode only by two URLs.

### Acceptance — milestone M2b, after M2

With Redis backends and two worker processes behind one port:

- two scripted clients connected to *different* workers finish a match;
- a worker is killed mid-match and the match continues after the affected client reconnects;
- one hundred concurrent bot matches spread across the workers and all finish;
- `resync` from any `seq` returns the same events a single-worker run produced;
- every finished match replays from its stored record to its stored final state.

## Consequences

- Scaling live matches is adding workers, not redesigning the server.
- A worker crash loses nothing that was accepted.
- The memory and Redis backends share one code path, so single-worker development exercises the
  same logic that runs in production.
- Redis becomes required for multi-worker deployment; the default single-worker install still
  needs nothing.
- Every intent serialises a state of a few kilobytes and takes a lock for about a millisecond.
  For a turn-based game this is invisible.
- If the intent log lives only in Redis, Redis persistence configuration becomes part of the
  deployment notes.

## Alternatives considered

- **Sticky ownership (one worker per match).** No per-intent serialisation, but it needs
  consistent-hash routing at the load balancer, fail-over on worker death and rebalancing. More
  operations for no benefit at this scale. Rejected.
- **A separate match-worker service.** Isolates match handling from HTTP, at the cost of a
  second deployable. Unnecessary while stateless workers scale the same process; can be revisited.
- **Redis as the only durability.** Simpler, but a lost Redis loses every live match and every
  unfinished record. Rejected; the database keeps the intent log.
