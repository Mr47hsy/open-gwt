# ADR 0001: Python server, Unity thin client

- Status: accepted, 2026-09-22
- Deciders: project owner

## Context

The project is three layers: a rules core, an authoritative server, and a Unity client that
renders and decides nothing. The rules must exist exactly once; two implementations would drift
and break deterministic replay.

Unity runs C#. The owner's server experience and tooling are Python (FastAPI, SQLAlchemy, async
workers), and they want the server and the client to be separate applications in separate
languages from the first commit, so that neither can quietly grow a dependency on the other.

The MVP is validated by running the server and connecting a client to it. Bots are exercised by
importing the rules directly, without a network. Offline play is not an MVP goal.

## Decision

- The **server is a Python application**. The rules core is a Python package inside it
  (see [ADR 0002](0002-rules-core-pure-python-package.md)); bots and the match simulator import
  that package directly.
- The **client is a Unity C# application and runs no rules at all**. It receives per-player views
  and event streams from the server, renders them, and sends intents. It never computes an
  outcome, never checks legality, and never sees hidden information.
- The client therefore **always needs a running server**, local or remote, including for a
  match against a bot. The server hosts the bot as an in-process participant.

## Consequences

- One implementation of the rules, in the language the tests, bots and simulator are written in.
- Server-authoritative by construction: there is no code path in the client that could disagree
  with the server.
- The server sends the list of legal intents with every view, since the client cannot compute it.
- No offline single-player and no client-side rule prediction. Any "optimism" in the client is
  presentation only: it may start an animation before the server answers, but it must be able to
  roll it back when the server's events arrive.
- A replay is watched by streaming it from the server, not by re-simulating it on the client.
- The client keeps a passive C# model of card *static* data (power, rows, traits, text keys) for
  rendering. That model is generated from the content pack the server serves, never hand-written.
- Mobile builds are online-only.

## Alternatives considered

- **C# everywhere.** Shares the core with the client, so offline play and local prediction become
  possible. Rejected: the owner's server stack is Python, and offline play is not a goal.
- **Python platform service plus a C# match-engine service.** Keeps one rules implementation and
  reuses the Python stack for accounts and matchmaking. Rejected: two languages and two services
  for one concern, more moving parts than the MVP needs, and it still leaves the client thin.
- **Rules in both languages.** Rejected outright; see Context.
