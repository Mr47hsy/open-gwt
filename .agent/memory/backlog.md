---
name: backlog
description: Open work after the MVP, by layer, with what each item depends on — the menu for parallel feature sessions.
metadata:
  type: project
---

Not ordered except for the ruleset phases, which are strictly sequential. One session per item,
one pull request per concern.

**Ruleset v2 (ADR 0009) — in order, each blocks the next.** Phases A (protocol v2 documents),
B (power and board, ADR 0010's random streams) and C (triggers, activated abilities, generalised
choices) are done; the phases below implement `docs/protocol/cards.md` and `match.md` as written,
and change them in the same pull request where the code proves them wrong. The vocabulary is
complete since B: a later phase adds behaviour, not words.
- Phase D: provisions, colours, copy limits, minimum units (and the owner's further deck-building
  limits, to be discussed); server validation; pack v2 completed with deck provisions. Decks
  already name a stratagem (ADR 0011).
- Phase E: the client speaks protocol 2 (the server does since B); an end-turn button (the turn
  waits for `end_turn` once its card is played) and a pass that `legal_intents` may withhold;
  choice UIs for every kind — unit, row, place (the view names the card being placed) and card
  (a `create` offer has no instance); statuses and armour on cards; order buttons; stratagem
  choice in decks; the interface texts for statuses, row effects and every `choice.<action>`
  prompt (and `choice.place`) in three languages. Remove the client's protocol-1 leftovers with
  it (owner, 2026-09-23): the lives shown as hearts, the `ui.effect.*` row-effect texts (v2 uses
  `row-effect.<id>.name`), the mulligan modal that picks several cards at once (v2 redraws one at
  a time, then `end_mulligan`), and the leader's "used" label (v2 shows the order's charges and
  cooldown).
- Phase F: original placeholder set covering every vocabulary word; two starter decks per
  faction. The owner will export a card set of their own design to import instead (2026-09-24).

**Client**
- Motion still missing: row effects appearing and clearing, power changes (a flash today), the
  opponent's draws and passes. Playing, destroying, returning and specials move since the visual
  baseline (`BoardMotion`, driven by `BoardView`'s step queue); add the rest there, rendering from
  the view. `BoardMotion` diffs renders and takes only two notes from events (played by whom,
  destroyed), so phase E maps protocol 2's `card_destroyed` onto the latter and gets the rest —
  `card_summoned`, `card_moved`, `card_returned`, `card_banished`, `stratagem_placed` — from the
  diff.
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
  URLs today. A shared timer is per match and seat and keeps the wait it was set for (the
  mulligan's round, or the `seq`), as the memory one does, so a timer that a move overtook stays
  a no-op on whichever worker serves it; and like it, keeps its deadline through a `use_order`
  stopped on a cancellable choice and its `cancel_choice` (`_keeps_clock`, match.md §9).
- Accounts beyond guest tokens are out of scope by decision; a display-name change exists.

**Content and rules** (after phase F)
- Real, original card set with names and texts in three languages; balance passes with
  `opengwt-sim`. Legal rules in `.agent/context/04-legal.md` apply to every name.
- Generated card text from ability templates (docs/protocol/i18n.md §10, deferred).

**Tooling**
- Client CI (needs a Unity licence secret); until then the headless checklist is the gate.

**How to apply:** when an item lands, delete it here and update [[project-status]]; when a new
one appears, add it with its dependency. See [[client-workflow]].
