# ADR 0011: Compensate the player who goes first — an extra redraw and a stratagem

- Status: accepted, 2026-09-23. Corrected the same day from the owner's play experience: an
  unused stratagem does not stay — it is banished when round one's board is cleared
  (`docs/protocol/cards.md` §3, §11.5).
- Deciders: project owner
- Supersedes: in [ADR 0009](0009-two-row-standalone-ruleset.md), the sentence leaving
  stratagems and the coin-toss compensation out of scope.
- Related: [ADR 0009](0009-two-row-standalone-ruleset.md) phases B, C and D

## Context

The seeded PRNG decides who starts round one. In a game where both players take turns until
both have passed, starting is a handicap: the second player answers every play and has the last
word of the round. The standalone game offsets it for the player who goes first in two ways,
according to its public patch notes and guides: one more redraw in round one's mulligan, and a
**stratagem** — a card each deck chooses at deck-building time, which only the player who goes
first gets, on the board from the start, to use once as an activated ability.

ADR 0009 left both out of its first revision. Reviewing phase B against the standalone game, the
owner decided on 2026-09-23 that the compensation belongs to the game's shape and is to be built
in phase B.

## Decision

- **Redraws.** Round one's mulligan gives the player who starts it `Rules.starter_extra_mulligans`
  redraws more (default 1); the redraws of every round default to `Rules.mulligans_per_round =
  [2, 2, 2]`. Round one therefore gives the starter three redraws and the other player two.
- **Stratagems.** A new card kind, `stratagem`: no power, no provisions, never in a deck or a
  hand, only `on_activate` abilities — one use unless its `activation` says otherwise. A deck
  names exactly one (`opengwt.deck/2` field `stratagem`), of its faction or neutral. When
  `Rules.starter_stratagem` is on (the default), the round-one starter's stratagem starts on
  their side of the board, at the left end of the first row it allows, and **takes a place** on
  that row like any card. Nothing acts on it: no selector offers it, row effects and auras pass
  it by, and it is not cleared at round end. Its activated ability is ready from the first turn;
  once used it leaves the board for its owner's banished zone. The other player's stratagem never
  enters the match.
- **Phases.** This lands in phase B. Using a stratagem needs `use_order`, a cancellable first
  choice and `order_used` — the activated-ability machinery ADR 0009 puts in phase C — so phase B
  implements that machinery and makes it ready for stratagems only; phase C extends it to units,
  artifacts and leaders. The deck field and its legality keys land with it; the rest of deck
  building stays in phase D.
- Words stay descriptive (ADR 0009, *Naming*): `stratagem` is an ordinary English word, and the
  names and texts of stratagems are original like every other card's.

## Consequences

- `cards.md` gains the kind, the `Rules` fields and the placement and use rules; `match.md` the
  `stratagem_placed`, `order_used` and `choice_cancelled` events, `use_order` and
  `cancel_choice` as legal intents, and the stratagem in the view as a card on its row.
- Every deck must name a stratagem. Decks saved on a server before this (none outside
  development) are refused until they do; `decks.stratagem` is a new column (migration 0003).
- Phase C starts from a working `use_order` instead of none.
- The replay golden and the acceptance run of phase B include the compensation.

## Alternatives considered

- **Leave it out, as ADR 0009 did.** Simpler, but the first player plays at a disadvantage the
  standalone game corrects; the owner chose the game as it is played.
- **Only the extra redraw.** Keeps phase B free of activated abilities, but leaves out the half
  of the compensation that shapes deck building.
- **A stratagem in the hand, or in a slot beside the rows.** It would not cost a place on the
  board; the owner confirmed that in the standalone game it takes one.
- **Split it across phases B, C and D.** Keeps each phase's scope as ADR 0009 drew it; the owner
  preferred the compensation complete in one pull request.
