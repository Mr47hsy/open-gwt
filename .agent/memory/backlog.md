---
name: backlog
description: Open work after the MVP, by layer, with what each item depends on — the menu for parallel feature sessions.
metadata:
  type: project
---

Not ordered except for the ruleset phases, which are strictly sequential. One session per item,
one pull request per concern.

**Ruleset v2 (ADR 0009) — in order, each blocks the next.** Phases A (protocol v2 documents),
B (power and board, ADR 0010's random streams), C (triggers, activated abilities, generalised
choices), D (deck building) and E (the client on protocol 2, end to end) are done; the protocol
is frozen since E — a change now bumps the version. The vocabulary is complete since B: a later
phase adds behaviour, not words.
- Phase F: original placeholder set covering every vocabulary word; two starter decks per
  faction. The owner will export a card set of their own design to import instead (2026-09-24),
  with `opengwt-data import` (docs/protocol/import.md): YAML, JSON or a spreadsheet's CSV, ids
  kept stable by `data/import/<set>.yaml`, names stubbed `TODO(i18n)`, texts generated.
- Vocabulary gap found in phase D (owner, 2026-09-24): some cards of the standalone game change
  the leader's faction during a match; no word expresses it. A leader is never neutral when a
  match starts (`check_deck`), which stays true. Decide with the owner — with its public
  source — before the card set that needs it is imported.

**Client**
- Motion still missing: row effects appearing and clearing, power, armour and status changes (a
  flash today), the opponent's draws and passes, a used ability. Playing, moving between rows
  and sides, destroying, banishing, returning and specials move since phase E (`BoardMotion`,
  driven by `BoardView`'s step queue, diffing renders and taking three notes from events: played
  by whom, destroyed, banished); add the rest there, rendering from the view.
- Deck builder: the server has `GET/PUT/DELETE /decks`, validates legality and returns each
  deck's `provisions` and `problems` (keys with parameters, texts in `errors.yaml`); the client
  only offers the pack's starter decks, showing each one's leader, stratagem, provisions and
  problems in the lobby.
- Drag and drop as a second way to place a card (ADR 0005 allows a `PointerManipulator`); phase
  E places with a click on the card and a click on a slot, which works the same on touch.
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
- Vocabulary gaps the ability-drafting skill found in its sample
  (`docs/protocol/examples/draft-abilities.csv`, 2026-09-24), each a word only with a public
  source and the owner's go (cards.md §15): a trigger when a unit's power first reaches a
  threshold — **once per match** (owner), checked after every change to its power, auras
  included, not only at the destruction check; **transforming** a unit into another card in
  place — the new card **belongs to the acting player** (owner); moving a chosen card from hand
  to the bottom of the deck, optionally **revealing** it first.
- Real, original card set with names and texts in three languages; balance passes with
  `opengwt-sim`. Legal rules in `.agent/context/04-legal.md` apply to every name.

**Tooling**
- Client CI (needs a Unity licence secret); until then the headless checklist is the gate.

**How to apply:** when an item lands, delete it here and update [[project-status]]; when a new
one appears, add it with its dependency. See [[client-workflow]].
