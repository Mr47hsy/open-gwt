---
name: ruleset-v2
description: Decided 2026-09-23 — the game targets the two-row standalone ruleset (ADR 0009), replacing the three-row shape, in phases A–F, one pull request each; A–E are done, F is next.
metadata:
  type: project
---

The owner chose the standalone online game's rules over the in-RPG version, and chose to
**replace**, not to keep both. ADR 0009 describes the target in the project's own words (two rows
of nine, provisions at deck-building, draws and redraws each round, base / boost / damage / armour,
statuses with timers, activated abilities that do not end the turn, leader charges, tied rounds
won by both) and the six phases: A protocols v2, B power and board, C triggers and activation,
D deck building, E server and client, F content. Every shape number lives in `Rules`, to be
confirmed against public descriptions when implemented.

**Why:** the standalone ruleset is the game people play today; the classic shape was the MVP's
quickest proof of the architecture, and the architecture (pure core, protocol, thin client)
carries over unchanged.

Phase A is done: `docs/protocol/cards.md` (`opengwt.cards/2`), `match.md` (protocol 2), their
schemas and examples, glossary rows.

Phase B is done. The owner asked for the vocabulary to follow the **standalone game strictly**
and to be complete in B — a superset of what C needs, so C adds behaviour and never changes a
card field or a word. B therefore revised the vocabulary against public sources (listed in
`cards.md` §16): bleeding and growing tick at their controller's turn end and cancel each other,
bleeding ignores armour, immunity only stops a player's choice, current power is one running
value with `heal` and `reset_power`, new statuses `status_proof`, `guarding`, `on_enemy_side`,
new actions `take_control`, `drain`, `duel`, `consume`, `discard`, `create`, conditions
`this`, `hand_at_most`, `units_at_least`, `starting_deck_without_neutral`, filters `boosted` /
`damaged`, `clear_row_effect.only`. Rules defaults confirmed by the owner: redraws `[3, 2, 2]`
plus one per draw a full hand prevents, round winner starts the next round, a tie is won by
both. The core loads every v2 word; the phase-C words are listed in `model.phase_c_words`, carried
and inert. The owner then decided (ADR 0011) that the **compensation for going first** belongs
to the game and to phase B: one more redraw in round one for the starter (`mulligans_per_round`
`[2, 2, 2]` plus `starter_extra_mulligans`) and a **stratagem** — a deck names one, only the
round-one starter gets it, on the board at the left end of its row where it **takes a place**
(the owner confirmed), nothing acts on it, it is banished if still unused when round one ends
(the owner confirmed), is used once through
`use_order` and is then banished. So `use_order`, `cancel_choice` and `order_used` exist since B,
ready for stratagems only.

Phase C is done (2026-09-24): one resolution queue for every trigger, activated abilities of
units, artifacts and leaders, `add_charges`, choices of kind `row`, `place` and `card`,
`play_from_deck` / `play_from_graveyard` / `create`. Decisions the owner took for it, from public
sources (`cards.md` §16): activated abilities are usable **before and after** the turn's card;
using one commits the turn to a card (no pass while a card can be played); after the card the
turn **waits for `end_turn`** and never ends by itself — the owner's own rule, only a timeout
ends it for the player; a player's units' `on_turn_start` abilities resolve **before** the row
effects on their rows, which act in the order they were set (`RowEffect.since`); a resolution
stops after 1000 queued steps; a first choice is cancellable only when it shows nothing hidden and
took no random draw. `data/`'s starter decks use every phase-C word; the owner will export a
card set of their own design later, to be imported in one go.

Phase D is done (2026-09-24): `check_deck` judges every deck-building rule of `cards.md` §12 and
reports all at once as `DeckProblem`s (key, card, numbers); the server judges decks by the one
`Rules` value it serves (`Content.rules`), shows `provisions {used, budget}` and `problems` on
every deck, and the pack's decks carry their provisions. Decisions the owner took for it: 25 to
40 cards, 13 units, bronze twice and gold once, 150 plus the leader's bonus, confirmed from
public sources and play; a leader belongs to the deck's own faction and is **never neutral**
when a match starts; **no card costs fewer than 4** provisions (fixed in the card schema, not in
`Rules`); no limit by rarity, colour count or neutral cards — bronze and gold are the only
colours. Legality is judged when a deck is saved and when a match starts; a saved deck the rules
now refuse is kept and shown with its problems; `replay` holds a record's decks only to what the
engine needs (`UNPLAYABLE_DECK_KEYS`), so tightening deck building breaks no record. The owner
also said that some cards change the leader's faction during a match — the vocabulary has no
word for it yet (see [[backlog]]).

Phase E is done (2026-09-24): the Unity client speaks protocol 2 end to end, and the protocol
is frozen — `match.md` got its last in-place corrections there (which row-side bounds a
position, `match_over` on connect to a finished match, no view for a waiting room, the full
list of illegal-intent reasons, both players' redraws in the view). Decisions the owner took:
display words for statuses and row effects are descriptive originals, except that the plain
English words ADR 0009 allows (Immune, Bleeding, Locked, Shielded, Poisoned) are used as they
are; a card is placed with a click on it and a click on a slot, not by dragging; graveyard and
banished piles open as read-only lists.

**How to apply:** do not add v1 content or vocabulary; read ADR 0009 and take the next unfinished
phase from [[backlog]]; vocabulary words describe behaviour and never reuse a distinctive official
keyword; regenerate goldens when a phase changes rules and say so in the pull request; rules
tests are replay scenarios under `server/tests/replays/scenarios/` where they can be. See
[[card-protocol-yaml]], [[project-status]].
