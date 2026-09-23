---
name: backlog
description: Open work after the MVP, by layer, with what each item depends on — the menu for parallel feature sessions.
metadata:
  type: project
---

Not ordered except for the ruleset phases, which are strictly sequential. One session per item,
one pull request per concern.

**Ruleset v2 (ADR 0009) — in order, each blocks the next.** Phase A (protocol v2 documents,
schemas and examples) is done; the phases below implement `docs/protocol/cards.md` and
`match.md` as written, and change them in the same pull request where the code proves them
wrong.
- Phase B: two rows with capacity, base / boost / damage / armour, statuses with timers,
  per-round draws and mulligans, hand limit, tie rule, weather as per-turn damage; v1 actions
  dropped; data rewritten to v2; goldens regenerated. Also ADR 0010: SHA-256 random stream,
  256-bit hex seed (`opengwt.record/2`, `matches.seed` migration), opaque instance ids, bot
  on its own per-decision stream. Remove the strict `xfail` markers phase A put on
  `test_packaged_schemas_match_docs` and `test_protocol_examples_load` — they fail loudly once
  the packaged schemas are v2.
- Phase C: `use_order` with charges / cooldown / immediate, leader charges, on-destroyed,
  turn-start/end, ally-played, boosted/damaged, adjacency, generalised choices; bots use orders.
- Phase D: provisions, colours, copy limits, minimum units; server validation; pack v2.
- Phase E: intents and views v2 end to end in server and client; targeting UI; statuses and
  armour on cards; order buttons.
- Phase F: original placeholder set covering every vocabulary word; two starter decks per faction.

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

**Content and rules** (after phase F)
- Real, original card set with names and texts in three languages; balance passes with
  `opengwt-sim`. Legal rules in `.agent/context/04-legal.md` apply to every name.
- Generated card text from ability templates (docs/protocol/i18n.md §10, deferred).
- Stratagems and coin-toss compensation, left out of ADR 0009's first revision.

**Tooling**
- Client CI (needs a Unity licence secret); until then the headless checklist is the gate.

**How to apply:** when an item lands, delete it here and update [[project-status]]; when a new
one appears, add it with its dependency. See [[client-workflow]].
