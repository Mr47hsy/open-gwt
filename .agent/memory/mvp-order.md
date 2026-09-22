---
name: mvp-order
description: MVP is built core → server → Unity client, each milestone with acceptance criteria that do not need the next one.
metadata:
  type: project
---

Decided 2026-09-22 (`docs/adr/0007`): M1 rules core + bots + simulator (ten thousand bot matches
without exceptions, one hundred byte-identical replays, new card = data-only change); M2 server
(scripted clients play over WebSocket, reconnect works, opponent hand never on the wire, runs on
SQLite and PostgreSQL); M3 Unity thin client (ten complete matches on macOS, iOS and Android smoke
builds, no rules code in the client).

**Why:** the risk is in the rules and the protocol, not in rendering; validating them without Unity
is faster and keeps the client honest about being thin.

**How to apply:** do not start client work before M2's acceptance passes; do not start server work
that needs a UI to test. Update [[project-status]] when a milestone is accepted.
