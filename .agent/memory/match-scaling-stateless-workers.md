---
name: match-scaling-stateless-workers
description: Multi-worker scaling is stateless workers over a shared match store; one MatchService.apply path, MatchStore and EventBus with memory and Redis implementations, intent log durable, start-up check on worker count.
metadata:
  type: project
---

Decided 2026-09-22 (`docs/adr/0008`): every match mutation goes through `MatchService.apply`
(lock → load → core.apply → save with version → append intent → publish events and views).
`MatchStore` and `EventBus` have memory and Redis implementations chosen by URL; Redis uses
`SET NX PX` locks and Streams. The accepted-intent log is the durable thing; snapshots only speed
things up, and a live match can be rebuilt by replay. Bots move inside the lock; turn timers live
in a shared sorted set served by one timer loop. The server refuses to start with more than one
worker unless both backends are Redis. Prerequisites: M1 canonical state serialisation, M2 all
WebSocket handling through `MatchService`. Multi-worker acceptance is milestone M2b.

**Why:** the owner asked whether Redis lifts the single-worker limit. It does only if the code is
written so the store is the sole difference between the modes; retrofitting that is expensive,
designing it in is cheap.

**How to apply:** never let a WebSocket handler, bot or timer touch match state directly; add any
new backend with a memory implementation first; keep the single-worker check tied to the memory
backends, not blanket. See [[server-optional-backends]], [[mvp-order]].
