---
name: server-python-thin-client
description: The server is Python with the rules core inside it; the Unity client is a thin client that runs no rules and always needs a server.
metadata:
  type: project
---

Decided 2026-09-22 (`docs/adr/0001`, `0002`): the server is a Python application; the rules core
is the zero-dependency package `opengwt.core` inside it, guarded by an import-linter contract. The
Unity client renders per-player views and events and sends intents. It contains no rules, computes
no scores, checks no legality, and needs a running server even for a match against a bot. There
is no offline play.

**Why:** the rules must exist exactly once, and the owner's server stack and experience are Python.
Unity cannot host Python, so the client cannot run the rules; the owner accepted always-online in
exchange for one implementation and a clean language split.

**How to apply:** never write a rule in C#, never add a client-side legality check — the server
sends `legal_intents`. Bots and tests import `opengwt.core` directly. If someone asks for offline
play, point at ADR 0001 rather than adding rules to the client. See [[card-protocol-yaml]],
[[server-optional-backends]].
