---
name: ruleset-v2
description: Decided 2026-09-23 — the game targets the two-row standalone ruleset (ADR 0009), replacing the three-row shape, in phases A–F, one pull request each; A and B are done, C is next.
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
(the owner confirmed), nothing acts on it, it survives round ends, is used once through
`use_order` and is then banished. So `use_order`, `cancel_choice` and `order_used` exist since B,
ready for stratagems only. `data/` uses only phase-B words, except every leader's activated ability. Still open
for C: whether activated abilities stay usable after the turn's card is played — ADR 0009 and
protocol 2 say playing a card ends the turn.

**How to apply:** do not add v1 content or vocabulary; read ADR 0009 and take the next unfinished
phase from [[backlog]]; vocabulary words describe behaviour and never reuse a distinctive official
keyword; regenerate goldens when a phase changes rules and say so in the pull request. See
[[card-protocol-yaml]], [[project-status]].
