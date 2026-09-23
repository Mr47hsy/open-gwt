---
name: backlog
description: Open work after the MVP, by layer, with what each item depends on — the menu for parallel feature sessions.
metadata:
  type: project
---

Not ordered; the owner picks. One session per item, one pull request per concern.

**Client**
- Event-driven animation: cards flash today; playing, destroying, returning and row effects
  should move (USS transitions or a small tween on `VisualElement`). Presenter seam exists in
  `BoardView.OnEvent`; keep rendering from the view.
- Deck builder: the server has `GET/PUT/DELETE /decks` and validates legality; the client only
  offers starter decks.
- Replay viewer: `GET /matches/{id}/replay` exists; the client has no way to watch one.
- Lobby polish: list of a player's matches, rejoin a running match after a restart (the server
  supports reconnect; the client forgets `MatchId` on restart).
- Mobile: iOS / Android smoke builds (deferred by the owner); needs Hub modules and, for iOS, Xcode.
- WebGL: needs a JavaScript WebSocket bridge; out of the MVP by decision.

**Server**
- M2b: Redis `MatchStore` and `EventBus`, the timer loop over a shared sorted set, and the
  multi-worker acceptance of ADR 0008. The factories in `backends/factory.py` refuse non-memory
  URLs today.
- Turn timeout is implemented but off by default and has no automated test.
- Accounts beyond guest tokens are out of scope by decision; a display-name change exists.

**Content and rules**
- Real, original card set with names and texts in three languages (placeholders now); balance
  passes with `opengwt-sim`. Legal rules in `.agent/context/04-legal.md` apply to every name.
- Generated card text from ability templates (docs/protocol/i18n.md §10, deferred).
- Vocabulary gaps of v1 (docs/protocol/cards.md): specials cannot ask the player for a row;
  summoned or returned units go to their first row; choices only arise from `played` and
  `activated`; `removed` does not fire on round clean-up.

**Tooling**
- Client CI (needs a Unity licence secret); until then the headless checklist is the gate.

**How to apply:** when an item lands, delete it here and update [[project-status]]; when a new
one appears, add it with its dependency. See [[client-workflow]].
