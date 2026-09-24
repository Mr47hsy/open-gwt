# Card protocol — `opengwt.cards/2`

How cards, decks and their translations are written, validated and compiled, and what the rules
core does with them. This is the authoring contract behind
[ADR 0003](../adr/0003-card-effect-protocol-yaml.md), revised for the two-row ruleset of
[ADR 0009](../adr/0009-two-row-standalone-ruleset.md): the schema files next to this document are
normative, this document explains them and fixes the semantics the rules core implements.

> **Phases.** The rules core implements the whole vocabulary below. ADR 0009 phase B implemented
> the power and board words and the stratagem of [ADR 0011](../adr/0011-first-player-compensation.md);
> phase C the other triggers, activated abilities of units, artifacts and leaders, the
> resolution queue and the generalised choices, and corrected the turn (section 11.4) against
> the standalone game; phase D the deck-building rules (section 12) — the unit minimum, the copy
> limits, the provision budget, a leader of the deck's own faction and a card cost of at least
> 4 — and the decks' provisions in the content pack (section 14). `data/`'s placeholder decks
> use every word. The vocabulary was revised in phase B against public descriptions of the
> standalone game (section 16); `opengwt.cards/1` is gone.

Everything here describes *mechanics*, which are not copyrightable. Names, ids and texts are
original to this project. Vocabulary words describe behaviour and never reuse a distinctive
official keyword (ADR 0009, *Naming*). They are identifiers, never displayed: what a player reads
for a status or a row effect comes from the translation tables (section 13). Card ids are never
displayed either — see `.agent/context/04-legal.md`.

## 1. Files

```
data/
  cards/<faction>.cards.yaml     one file per faction, plus neutral.cards.yaml
  decks/<deck-id>.deck.yaml      one file per deck
  i18n/<locale>/cards.yaml       card, faction and tag texts, one flat map per locale
  i18n/<locale>/ui.yaml          client strings, including the names of statuses and row effects
  i18n/conformance.yaml          renderer conformance cases, run by server and client
```

Schemas: [`cards.schema.json`](cards.schema.json), [`decks.schema.json`](decks.schema.json).
Worked examples: [`examples/`](examples/). The two example card files together use every word
of the vocabulary; phase F's placeholder set grows from them.

## 2. Cards file

```yaml
schema: opengwt.cards/2
faction: placeholder-a          # faction id; `neutral` for cards any deck may use

cards:
  u-0001:                       # card id — stable, lower-case, never shown to players
    kind: unit
    color: bronze
    provisions: 4
    power: 5
```

| Key | Required | Meaning |
| --- | --- | --- |
| `schema` | yes | Exactly `opengwt.cards/2`. |
| `faction` | yes | Id of the faction every card in this file belongs to. |
| `cards` | yes | Map of card id → card. Ids match `^[a-z][a-z0-9-]{1,63}$` and are unique across **all** files. |

Ids are opaque. The convention `u-` (unit), `s-` (special), `a-` (artifact), `t-` (token),
`l-` (leader), `g-` (stratagem) followed by a number is recommended for placeholder content but
not enforced. Ids
never encode a name.

## 3. Card

| Key | Applies to | Required | Meaning |
| --- | --- | --- | --- |
| `kind` | all | yes | `unit`, `special`, `artifact`, `leader` or `stratagem`. |
| `color` | unit, special, artifact | yes, except tokens | `bronze` or `gold`; sets the copy limit in a deck (section 12). |
| `provisions` | unit, special, artifact | yes, except tokens | Provision cost, integer ≥ 4 — no card of the standalone game costs less — counted against the deck's budget (section 12). |
| `provision_bonus` | leader | yes | Added to `Rules.provision_base` to give the budget of a deck led by this leader. |
| `token` | unit, artifact | no | `true`: the card is never in a deck and only reaches the board through `place_new_card`; it is banished whenever it leaves the board, whatever its statuses. A token has no `color` and no `provisions`. |
| `power` | unit | yes | Base power, integer ≥ 1. |
| `armor` | unit | no | Armour the unit has whenever it enters the board, integer ≥ 1. |
| `rows` | unit, artifact, stratagem | no | Rows the card may be played on — for a stratagem, the row it starts on is the first of them: one or both of `melee`, `ranged`. Default: any row. |
| `side` | unit | no | `self` (default) or `opponent`: the side of the board the unit lands on when it is played or summoned (`place_new_card` sets the side itself). |
| `statuses` | unit, artifact | no | Statuses the card has whenever it enters the board: `shielded`, `immune`, `banish_on_leave`, `kept_at_round_end`, `status_proof`, `guarding` (artifacts: not `shielded` or `guarding`). |
| `tags` | unit, special, artifact | no | Free-form tag ids (`^[a-z][a-z0-9-]{1,31}$`), original words, used by `where` filters. |
| `activation` | unit, artifact, leader, stratagem | no | How the card's activated ability may be used (section 6.3). Only on a card with an `on_activate` ability. A stratagem without one has a single charge. |
| `abilities` | all | special, leader and stratagem: yes | Ordered list of abilities (section 6). |

What each kind is:

- A **unit** stands on a row of the board and has power.
- A **special** is played, its `on_play` abilities resolve, and it goes to its owner's graveyard.
  It only has `on_play` abilities and is never on the board.
- An **artifact** stands on a row like a unit and takes a place there, but has no power: power
  actions never affect it and it adds nothing to a score. It has every trigger except
  `on_boosted` and `on_damaged`.
- A **leader** is not in the deck and never on the board. It belongs to a faction, never to
  `neutral`, and leads decks of that faction only. It carries the deck's provision bonus
  and one activated ability — its `on_activate` abilities, the only kind it may have — usable
  from the first turn, with the charges its `activation` gives it for the whole match.
- A **stratagem** is the compensation for going first ([ADR 0011](../adr/0011-first-player-compensation.md)):
  a deck names one, and only the player who starts round one gets theirs. It starts on their
  side of the board, at the left end of the first row it allows, and takes a place there like
  any card; it has no power, only `on_activate` abilities, and nothing acts on it — no selector
  offers it, row effects and auras pass it by. Its activated ability is ready from the first
  turn; once used — or, unused, when round one's board is cleared — it leaves the board for its
  owner's banished zone. It is never in a deck, a hand or a graveyard.

## 4. Rules

`Rules` is the core's configuration: every number that shapes a match or a deck lives here, none
is hard-coded (ADR 0009). The server plays with one `Rules` value, publishes it in the content
pack (section 14) and stores it in every replay record, so a changed default never changes an
existing replay.

| Field | Default | Meaning |
| --- | --- | --- |
| `rows` | `[melee, ranged]` | Each side's rows, in board order. The row vocabulary of the schema is exactly these two. |
| `row_capacity` | `9` | Cards — units, artifacts and a stratagem — one row of one side holds. |
| `hand_limit` | `10` | Most cards a hand holds; a draw into a full hand does not happen (section 11.5). |
| `draws_per_round` | `[10, 3, 3]` | Cards each player draws at the start of round *n*: entry *n − 1*, the last entry for later rounds. |
| `mulligans_per_round` | `[2, 2, 2]` | Redraws each player may make in the mulligan of round *n*, indexed the same way. |
| `mulligans_per_skipped_draw` | `1` | Extra redraws in a round's mulligan for each of its draws that a full hand prevented; `0` for none. |
| `starter_extra_mulligans` | `1` | Extra redraws for the player who starts round one, in round one's mulligan (ADR 0011). |
| `starter_stratagem` | `true` | Whether the player who starts round one starts with their deck's stratagem on the board (ADR 0011). |
| `rounds_to_win` | `2` | Round wins that end the match. |
| `max_rounds` | `3` | Rounds after which the match ends in any case. |
| `tie_rule` | `both_win` | A tied round counts as won by both players (`both_win`) or by neither (`neither_wins`). |
| `next_round_starter` | `round_winner` | Who starts rounds after the first: `round_winner`, `round_loser` or `alternate`. When the rule names a winner or loser and the round was tied, the player who did not start the previous round starts. |
| `deck_min_cards` | `25` | Fewest cards in a deck, leader not counted. |
| `deck_max_cards` | `40` | Most cards in a deck. |
| `deck_min_units` | `13` | Fewest unit cards in a deck. |
| `provision_base` | `150` | Provision budget before the leader's `provision_bonus`. |
| `copies_bronze` | `2` | Most copies of one bronze card in a deck. |
| `copies_gold` | `1` | Most copies of one gold card in a deck. |

The defaults follow public descriptions of the standalone game (section 16), confirmed in phase
B: two rows of nine, ten cards and then three per round up to a hand of ten, a draw a full hand
prevents turned into a redraw, the round's winner starting the next round and a tied round won
by both, and the compensation for going first — a redraw more in round one and a stratagem
(ADR 0011). Who starts after a tied round is this project's choice; no public source was found.
The deck-building fields — 25 to 40 cards, 13 units, bronze twice and gold once, a budget of 150
plus the leader's bonus — were confirmed in phase D and are checked by the rules core (section
12). The floor of 4 on a card's provisions is the schema's (section 3), like the floor of 1 on
its power: it bounds what a card may cost, not what a deck may hold. `deck_max_cards`,
`rounds_to_win`, `max_rounds`, `mulligans_per_skipped_draw` and the two `starter_*` fields are
not in the ADR's list; they exist so that nothing about the shape is hard-coded.

## 5. Board, zones and card instances

Each player has a **deck** (ordered, top first), a **hand**, a **graveyard** (ordered by
arrival), a **banished** zone, and one **row-side** per row in `Rules.rows` — their half of the
board. A row-side is an ordered list of cards, left to right, holding at most `row_capacity`
cards, and at most one row effect (section 10). *Adjacent* cards are the ones immediately left
and right of a card on the same row-side.

- The **owner** of a card is the player whose deck (or ability, for a created card) it came
  from. A card that leaves the board always goes to its owner's zones.
- The **controller** of a card on the board is the player whose side it is on. Its
  `on_turn_start` and `on_turn_end` abilities, its statuses' timers and its activated ability
  follow its controller's turns. A card whose controller is not its owner carries the status
  `on_enemy_side` (section 9).
- **Board order**, used wherever several cards act one after another: the side of the current
  player first — the player whose turn it is, or who took the last turn — then the other side;
  within a side, rows in `Rules.rows` order; within a row, left to right.

A **card instance** is one physical card in a match, with an opaque id — shortened to forms such
as `c17` in the examples. Ids come from a counter in the match state rendered through the core's
id stream ([ADR 0010](../adr/0010-unpredictable-random-stream.md)), so an id reveals neither a
card's place in the deck list, nor its position after the shuffle, nor when it was drawn. Clients
treat ids as opaque strings.

**Randomness.** Every random draw in this document — the shuffles, the first starter, `random`
picks, offers, tie breaks, mulligan insertions — comes from the core's seeded engine stream,
called *the seeded PRNG* below. From phase B that is the SHA-256 counter-mode stream of ADR 0010,
seeded with 256 bits the server keeps secret until the match is over; instance ids and the
server's bots draw from streams of their own, so what a player sees of one says nothing about
another.

On the board an instance carries: `base` (printed power, raised by `raise_base_power`), its
current power (`base` moved up by boosts and down by damage), `armor`, an ordered list of
`statuses`, each with an optional timer in turns, and, for a card with an activated ability, its
remaining `charges` and its `cooldown`. Its power adds the auras around it (section 11.1). When a
card leaves the board, everything it carried there is reset to its definition; its instance id
stays. A leader's charges and cooldown last the whole match.

## 6. Abilities

```yaml
abilities:
  - when: on_play
    if: { on_row: melee }
    do: damage
    amount: 3
    target: { units: chosen, side: opponent }
  - when: on_play
    do: draw
    count: 1
```

Every ability has `when` and `do`, may have `if`, and carries the parameters its action needs
(section 8). A card's abilities with the same trigger fire in the order they are written, each
as its own step in the resolution queue (section 11.3).

The **acting player** of an ability — the one `self` and `opponent` are relative to, and the one
who makes its choices — is the player who played the card for `on_play`, the owner for a leader,
the player who used it for `on_activate`, the controller the card had when it was destroyed for
`on_destroyed`, and the card's controller when the ability resolves for everything else — a card
that changed sides while its ability waited in the queue acts for its new side.

### 6.1 Triggers — `when`

| Value | Fires |
| --- | --- |
| `on_play` | when the card is played: from hand by a player, or by `play_from_deck` / `play_from_graveyard` / `create`. Not when it is summoned, placed new, moved or returned. A unit or artifact fires it after it is placed. |
| `on_activate` | when its controller uses the card's activated ability (section 6.3). |
| `on_destroyed` | after the card was destroyed — by `destroy`, by its power reaching zero, or by a second poison — and has reached the graveyard or been banished. Not when it is banished by `banish`, returned, or cleared at round end. |
| `on_turn_start` | at each of its controller's turn starts while it is on the board (section 11.4). |
| `on_turn_end` | at each of its controller's turn ends while it is on the board. |
| `on_round_end` | when the round ends while it is on the board, before the scores are compared (section 11.5). |
| `on_ally_played` | when its controller plays another unit that lands on this card's side. The played unit is the *trigger unit*. |
| `on_boosted` | when this unit is boosted (`boost`, `drain`, `consume`, `growing`, `boost_random`). Not by a continuous effect and not by `raise_base_power`. |
| `on_damaged` | when damage reaches this unit's power — past shields and armour — and the unit survives it. |
| `while_on_board` | not a trigger: a continuous effect, in force while the card is on the board and not locked (section 11.1). Only `continuous_boost` uses it. |

A special has only `on_play` abilities and a leader only `on_activate`; an artifact has every
trigger except `on_boosted` and `on_damaged`; a unit has them all.

### 6.2 Conditions — `if`

| Key | Value | Holds when |
| --- | --- | --- |
| `on_row` | a row | the acting card is on that row — for `on_play`, the row it was played on; for `on_destroyed`, the row it was on when it was destroyed. |
| `trigger_unit` | a `where` filter | `on_ally_played` only: the played unit matches the filter. |
| `this` | a `where` filter | the acting card matches the filter — `boosted` or `damaged`, say. |
| `hand_at_most` | an integer | the acting player holds at most that many cards. |
| `units_at_least` | `{count, side, rows?, where?}` | at least `count` cards on the board, the acting card excluded, match the side, rows and filter — units unless `where.kind` says otherwise; immune ones count. |
| `starting_deck_without_neutral` | `true` | the acting player's deck held no neutral card when the match started. |

All listed conditions must hold. They are checked when the ability's turn in the queue comes;
an ability whose conditions fail is skipped without an event.

### 6.3 Activated abilities — `on_activate` and `activation`

All `on_activate` abilities of a card form its one **activated ability**, used with the
`use_order` intent ([`match.md`](match.md) §6); each use resolves them in the order written.
`activation` is set on the card, not on an ability:

| Key | Meaning |
| --- | --- |
| `charges` | Uses available. Each use spends one; at zero the ability cannot be used. Default: `1` without `cooldown`, unlimited with it. |
| `cooldown` | After each use, how many of its controller's turn starts must pass before it is ready again. |
| `ready_on_play` | `true`: usable on the turn the card enters the board. Otherwise a unit or artifact enters with a cooldown of 1. Not for leaders and stratagems, which are ready from the first turn. |

The activated ability is **ready** when all of these hold: it is its controller's turn; the
controller has not passed; no choice is pending; the card is on its controller's side of the
board and not locked, or is their leader; it has a charge left or unlimited charges; its
cooldown is zero; and, if its first ability asks a choice — `chosen`, `chosen_row`,
`cards.pick: chosen` or `create` — there is at least one candidate. Ready abilities may be used before and after the turn's card (section
11.4); once one is used, the turn needs its card.

Using it spends a charge and starts the cooldown when its first ability starts to act — after
that ability's choice, if it asks one. The cooldown drops by one at each of its controller's turn
starts and the ability is ready again at zero, so a cooldown of 1 allows one use a turn and 2
skips a turn. Until its first ability that acts has done so, that ability's choice may be
cancelled, which leaves
the match exactly as before the `use_order` — but only when the choice showed nothing hidden and
took no random draw: a unit, a row-side, or a card from a graveyard without an offer. A choice
among cards of a deck or a hand, or among an offer, cannot be cancelled. Once its abilities have
resolved, a stratagem leaves the board for its owner's banished zone. `add_charges` on an ability
with unlimited charges does nothing.

## 7. Targets

Three selectors, depending on what an action acts on.

### 7.1 Units on the board — `target`

```yaml
target:
  units: chosen          # how the targets are picked, below
  side: opponent         # self | opponent | both, relative to the acting player
  rows: [melee]          # optional; default every row
  count: 2               # `random` only; default 1
  where: { tags_any: [tag-a] }   # optional filter, section 7.4
```

For every value of `units` except `this`, targets are taken from the **candidates**: the cards on
the given side and rows that match `where`, excluding the acting card itself, and artifacts
unless `where.kind` lists `artifact`; a stratagem is never one. Power actions (`damage`, `boost`, `add_armor`, `heal`,
`reset_power`, `raise_base_power`, `drain`, `duel`, `consume`) never affect an artifact.

A player's **choice** — `chosen` — is narrower: it never offers an `immune` unit, and while a
unit with `guarding` stands on a row-side, the players other than its controller are not offered
any other card of that row-side except another guarding unit: with two guards on one row-side,
both are still offered. Every other selector, row effects included, reaches immune and guarded
units alike (section 9).

| `units` | Targets |
| --- | --- |
| `chosen` | one candidate the acting player picks (a pending choice of kind `unit`). |
| `chosen_row` | every candidate on one row-side the acting player picks (kind `row`; only row-sides holding a candidate are offered). |
| `all` | every candidate. |
| `random` | `count` distinct candidates drawn with the seeded PRNG, or all of them if there are fewer. |
| `strongest` | the candidate with the highest power; a tie is broken with the seeded PRNG. |
| `weakest` | the candidate with the lowest power; ties as above. |
| `this` | the acting card, if it is on the board. Immunity does not matter. |
| `adjacent` | the candidates adjacent to the acting card. |
| `trigger_unit` | the unit that fired `on_ally_played`, if it is a candidate. |
| `previous_targets` | the cards the ability before it — of the same card and the same trigger, in the same resolution — acted on with its unit selector, if they are still candidates; none if that ability was skipped or selects no units. |

`side` is required for the first six and not allowed for the rest, which are placed relative to
the acting card. `chosen` and `chosen_row` are only allowed in `on_play` and `on_activate`
abilities — the only moments a player is asked anything — and `trigger_unit` only in
`on_ally_played`; the schema enforces both. `chosen_row` picks a row-side, not a unit, so it
reaches immune units and the units a guard protects like any selector that asks nobody. An action acts on several targets one at a time, in
board order; a target that has left the board by its turn is skipped. With no candidates an
ability does nothing, and no choice is asked.

### 7.2 Rows — `row_target`

| `pick` | Row-sides |
| --- | --- |
| `chosen` | one row-side of `side` (and `rows`, default every row) the acting player picks (kind `row`). |
| `all` | every row-side of `side` and `rows`, in board order. |
| `this` | the row-side the acting card is on; `side` and `rows` are not allowed. |

### 7.3 Cards in a deck or graveyard — `cards`

The zone is given by the action (`play_from_deck`, `play_from_graveyard`, `summon_from_deck`,
and the hand for `discard`); `side` (`self` by default) says whose. Candidates are the cards in
that zone matching `where`. With no candidates the ability does nothing, and no choice is asked.

| `pick` | Cards |
| --- | --- |
| `chosen` | one card the acting player picks (kind `card`). With `offer: n`, only `n` candidates drawn with the seeded PRNG are offered, or all of them if there are fewer. |
| `random` | `count` (default 1) distinct candidates drawn with the seeded PRNG, or all of them if there are fewer. |
| `first` | the first `count` (default 1) candidates in zone order: from the top of a deck, from the earliest arrival in a graveyard, from the oldest card in a hand. |
| `all` | every candidate in zone order, at most `count` if given. |

Options from a deck or a hand are listed by card id, then instance id — never in zone order,
which would reveal the deck ([`match.md`](match.md) §11); a graveyard is public and keeps its
order. An offer is drawn from the candidates in zone order. A choice from the opponent's deck or
hand shows the chooser its candidates — the card reveals them by design.

### 7.4 Filters — `where`

| Key | Holds when |
| --- | --- |
| `kind` | the card is of one of the listed kinds (`unit`, `special`, `artifact`). Default: `[unit]` for `target`, any kind for `cards`. |
| `color` | the card is of this colour. |
| `tags_any` / `tags_none` | the card has at least one / none of the listed tags. |
| `statuses_any` / `statuses_none` | the card has at least one / none of the listed statuses. Cards off the board have none. |
| `same_id_as_this` | the card has the acting card's card id. |
| `power_at_least` / `power_at_most` | its power is at least / at most the value: its power on the board (section 11.1), its printed power elsewhere. |
| `stronger_than_this` | its power, read as for `power_at_least`, is greater than the acting card's power on the board; false when the acting card is not a unit on the board — the card of an `on_destroyed` ability, say. A trigger unit that has left the board by the time `if.trigger_unit` is checked is therefore compared by its printed power. |
| `boosted` / `damaged` | it is a unit on the board whose current power is above / below its base power (auras aside). |

All listed filters must hold.

## 8. Actions — `do`

| Action | Parameters | Effect |
| --- | --- | --- |
| `damage` | `target`, `amount` | Each target takes `amount` damage (section 11.2). |
| `boost` | `target`, `amount` | Each target's current power rises by `amount`; it fires `on_boosted`. |
| `add_armor` | `target`, `amount` | Each target's armour rises by `amount`. |
| `heal` | `target` | Each damaged target's current power returns to its base power. Boosts are kept: a unit at or above its base is not affected. |
| `reset_power` | `target` | Each target's current power returns to its base power, boosts and damage alike. |
| `raise_base_power` | `target`, `amount` | Each target's base power rises by `amount`, and its current power with it. |
| `destroy` | `target` | Each target is destroyed (section 11.2). |
| `banish` | `target` | Each target leaves the board for its owner's banished zone. `on_destroyed` does not fire. |
| `add_status` | `target`, `status`, `turns` | Each target gains the status (section 9). `turns` is required for `bleeding` and `growing`, optional for `locked`, `immune`, `status_proof` and `guarding`, not allowed otherwise. |
| `remove_statuses` | `target`, `statuses` | Each target loses the listed statuses, or all of them when `statuses` is absent. |
| `move_to_other_row` | `target` | Each target moves to the other row of its side, at the right end; nothing happens if that row is full. Row restrictions only govern playing a card. |
| `return_to_hand` | `target` | Each target goes to its owner's hand; it stays where it is if that hand is full. |
| `take_control` | `target` | Each target moves to the acting player's side, same row, at the right end; nothing happens if that row-side is full or the target is on that side already. It gains or loses `on_enemy_side` accordingly. |
| `drain` | `target`, `amount` | Each target takes `amount` damage; the acting unit, if it is on the board, is boosted by the damage that reached the target's power. |
| `duel` | `target` | The acting unit and each target damage each other in turn by their power, the acting unit first, until one of them has left the board — or until 64 strikes in all, 32 each, have been struck, when the duel ends with both still on the board. |
| `consume` | `target` | Each target is destroyed; the acting unit, if it is on the board, is boosted by the target's power at that moment. |
| `discard` | `cards` | Each selected card leaves its owner's hand for their graveyard without any of its abilities (`pick: chosen` is kind `card`). |
| `draw` | `side` (default `self`), `count` (default 1) | That player draws, one card at a time (section 11.5). |
| `play_from_deck` | `cards` | Each selected card is played as if from hand, one after another, before the next ability of the queue: the acting player places a unit or artifact (kind `place`, when more than one placement is legal; nothing happens if none is), then it fires `on_play` and `on_ally_played`. A special resolves and goes to its owner's graveyard once the queue is empty. A card taken from the opponent's zone stays theirs. It is not the turn's card (section 11.4). |
| `play_from_graveyard` | `cards` | As `play_from_deck`, from a graveyard. |
| `summon_from_deck` | `cards`, `row` | Each selected unit or artifact moves onto the board without being played — no `on_play`, no `on_ally_played` — on the side its `side` gives. Row: `row` if given, else the acting card's row (the row it was last on, if it has left the board), else the first row the card allows; a row the card does not allow is replaced by the first one it does. Position: right of the acting card on that row-side, else the right end; several cards keep their order, each right of the one placed before it. Nothing happens for a card whose row is full. Specials are never selected. |
| `place_new_card` | `card`, `count` (default 1), `side` (default `self`), `row` | `count` new instances of `card` — a unit or artifact, usually a token — are placed as `summon_from_deck` places, owned by the acting player. Each has `banish_on_leave`. They are not played. |
| `create` | `pool`, `offer` (default 3) | `offer` distinct card ids are drawn with the seeded PRNG from the cards of the acting player's faction and `neutral` that match the `pool` filter — never tokens, leaders or stratagems — and offered (kind `card`, in card id order); a new instance of the one picked, owned by the acting player, is played as `play_from_deck` plays. One that has nowhere to go never enters the match. |
| `add_charges` | `to` (`this` or `leader`), `amount` | The acting card's, or the acting player's leader's, activated ability gains `amount` charges. |
| `set_row_effect` | `effect`, `amount`, `count`, `row_target` | Each selected row-side gets the row effect (section 10), replacing the one it had. `count` is required for `damage_random` and `boost_random` and not allowed otherwise. |
| `clear_row_effect` | `row_target`, `only` | Each selected row-side loses its row effect — with `only`, just a `hazard` or just a `boon` (section 10). |
| `continuous_boost` | `amount`, `scope` (`row` or `adjacent`) | `while_on_board` only: the other units on the card's row-side (`row`) or adjacent to it (`adjacent`) have `amount` more power (section 11.1). |

`play_from_deck`, `play_from_graveyard` and `create` may only be used in `on_play` and
`on_activate` abilities, since placing a card is a choice. `place_new_card` must name a card of
kind `unit` or `artifact`; the compiler checks this (section 14).

## 9. Statuses

| Status | Timer | Effect |
| --- | --- | --- |
| `locked` | optional | The card's abilities do nothing: none of its triggers fire, its continuous effect stops, its activated ability is not ready, and queued abilities of the card are skipped. Its statuses still apply. |
| `shielded` | — | The next damage the unit would take is blocked entirely; the status is then removed. |
| `immune` | optional | Never offered by a player's choice (`chosen`). Everything that does not ask a player — `all`, `random`, `strongest`, a chosen row, row effects — still reaches the unit. |
| `poisoned` | — | Nothing on its own. A poisoned unit that is poisoned again is destroyed. |
| `bleeding` | required | At each of its controller's turn ends the unit takes 1 damage that armour does not absorb (a shield still blocks it). |
| `growing` | required | At each of its controller's turn ends the unit is boosted by 1. |
| `banish_on_leave` | — | Whenever the card leaves the board — destroyed, returned, or cleared at round end — it is banished instead of reaching any other zone. `on_destroyed` still fires when it was destroyed. |
| `kept_at_round_end` | — | When the board is cleared at the end of a round, the card stays, with everything it carries; the status is then removed. |
| `status_proof` | optional | No status can be added to the card: adding one does nothing and cancels nothing — bleeding added to it leaves its growing as it is, and the other way round. Its own statuses stay, and it can still be targeted. |
| `guarding` | optional | While the unit is on a row-side, the players other than its controller cannot choose any other card of that row-side except another guarding unit, so two guards on one row-side can both be chosen (section 7.1). It still applies while the unit is locked. |
| `on_enemy_side` | — | Carried by every card on the board whose controller is not its owner, and only by those: the board adds and removes it, no action does. |

A card's statuses are an ordered list, at most one entry per status, in order of arrival.

- **Adding** a status the card does not have appends it, with its timer if `turns` is given.
  Adding one it already has: `poisoned` destroys the unit; for a timed status the turns add up,
  and if either side has no timer the result has none; otherwise nothing changes. Nothing is
  added to a card with `status_proof`.
- **Bleeding and growing cancel** turn for turn: adding one to a unit that has the other first
  takes the smaller number of turns off both, removing a status whose turns run out; whatever is
  left of the new one is then added. On a card with `status_proof` nothing is added, so nothing
  is cancelled either.
- **Innate** statuses — the card's `statuses` — are added whenever the card enters the board,
  before anything else happens to it.
- **Timers** tick at the controller's turn end (section 11.4): `bleeding` and `growing` act,
  then every timer on the card decreases by one, and a status whose timer reaches zero is
  removed.
- An **artifact** is only affected by `locked`, `immune`, `banish_on_leave`,
  `kept_at_round_end`, `status_proof` and `on_enemy_side`; adding any other status to it does
  nothing.

## 10. Row effects

A row-side holds at most one row effect: `{effect, amount, count?}`. `set_row_effect` replaces
the current one; `clear_row_effect` and the end of the round remove it. Row effects do not
target, so immune units are affected. A player who has passed has no more turn starts in the
round, so the per-turn effects on their rows stop acting. When both of a player's row-sides have
a per-turn effect, the one set earlier acts first. A per-turn effect acts on the units of its
row-side only; with none there, it does nothing. `boost_random` is a **boon**; every other row
effect is a **hazard** (`clear_row_effect.only`).

| Effect | Acts |
| --- | --- |
| `damage_strongest` | at each turn start of the row-side's player: its strongest unit takes `amount` damage (a tie is broken with the seeded PRNG). |
| `damage_weakest` | the same, on its weakest unit. |
| `damage_random` | the same, on `count` distinct units drawn with the seeded PRNG, or all of them if there are fewer. |
| `boost_random` | at each turn start of the row-side's player: `count` distinct units drawn with the seeded PRNG, or all of them if there are fewer, are boosted by `amount`. |
| `damage_on_arrival` | whenever a unit enters the row-side — played, summoned, placed new, moved or taken over — it takes `amount` damage, after its innate statuses and before its `on_play`. |

## 11. Power and resolution order

### 11.1 Power

The power of a unit on the board is

```
power = current + aura
```

- `current` — the unit's current power: its `base` (the printed power, raised by
  `raise_base_power`), raised by every boost and lowered by every damage that got past shields
  and armour. Boosts and damage are one running value, so a boost of 2 after 2 damage leaves the
  unit neither damaged nor boosted; `heal` and `reset_power` bring it back to `base`;
- `aura` — the sum of the `continuous_boost` amounts of every *other* card on the same row-side
  that is on the board and not locked and whose scope covers this unit: the whole row-side for
  `row`, directly next to the source for `adjacent`. It is recomputed whenever power is read and
  never stored.

A unit is **boosted** when `current` is above `base` and **damaged** when it is below. Armour is
kept apart and is not part of power. Power is what row totals, scores, `strongest` and `weakest`,
the `power_*` and `stronger_than_this` filters and the view's `power` use. A side's score is the
sum of its units' power; artifacts add nothing.

### 11.2 Damage, boost and destruction

One instance of `n` damage to a unit resolves in this order:

1. if the unit is no longer on the board, nothing happens;
2. if the unit is `shielded`, the status is removed and the damage is blocked — stop;
3. armour absorbs as much as it can: `absorbed = min(armor, n)`, and armour drops by that much —
   except for `bleeding`, which armour does not absorb;
4. the rest, `n − absorbed`, is taken off `current`; if it is zero, stop;
5. the destruction check runs;
6. if the unit is still on the board, its `on_damaged` abilities are queued.

A boost of `n` adds `n` to `current` and queues the unit's `on_boosted` abilities.

The **destruction check** runs after every damage instance, after every card leaves the board and
after a card gains a status, since a leaving or locked card may take an aura with it: every unit
whose power is zero or less is destroyed, in board order, until none is left.

**Destroying** a card — by `destroy`, by the check, or by a second poison — moves it to its
owner's graveyard, or banishes it if it has `banish_on_leave`; its board state is reset; then,
unless it was locked at that moment, its `on_destroyed` abilities are queued.

### 11.3 The resolution queue

- Playing a card queues its `on_play` abilities, then the `on_ally_played` abilities of the
  cards it triggers, in board order. Using an activated ability queues the card's `on_activate`
  abilities.
- The queue runs first in, first out. Each queued ability resolves completely — its choice
  included, and the cards it plays (`play_from_deck`, `play_from_graveyard`, `create`), which
  go ahead of the next ability — before the next starts. Damage, boosts and destruction act at
  once; the abilities they trigger (`on_damaged`, `on_boosted`, `on_destroyed`, and a played
  card's `on_play` and `on_ally_played`) are appended in the order they were caused — damage a
  unit takes as it arrives on a row therefore queues its `on_damaged` ahead of its own
  `on_play`. Continuous effects are never queued.
- One resolution — everything a played card, an activated ability, a turn start, a turn end or a
  round end sets off, across its choices — resolves at most 1000 queued steps; content that
  keeps triggering itself stops there, the rest of the queue is dropped (a card created for it
  never enters the match), and the match goes on.
- A queued ability is skipped when its card is locked, when its conditions (section 6.2) fail,
  or when it belongs to a card that must be on the board to fire and no longer is. `on_destroyed`,
  a special's `on_play` and a leader's abilities do not need the board.
- A pending choice pauses the queue until the acting player chooses; nothing else happens in the
  match meanwhile.

### 11.4 A turn

1. The turn starts; the cooldowns of the player's cards on the board and of their leader drop
   by one.
2. The `on_turn_start` abilities of the player's cards on the board are queued in board order
   and resolve, with everything they cause.
3. The row effects on the player's row-sides act, the one set earlier first (section 10); the
   triggers they cause then resolve.
4. If the player's hand is empty and none of their activated abilities is ready, they pass
   automatically.
5. The player uses any number of ready activated abilities, before and after the turn's one
   card, and plays that card — or passes instead of playing one. Once an activated ability has
   been used the turn needs its card: a pass is refused while a card can be played. Once the
   card is played a pass is refused too, and the turn goes on — for more activated abilities —
   until the player ends it (`end_turn`, [`match.md`](match.md) §6); it never ends by itself. A
   pass ends the turn at once: steps 6 and 7 are skipped.
6. When the player ends the turn, the statuses of the player's cards act, in board order:
   `bleeding` and `growing`, then every timer drops by one and expired statuses are removed.
7. The `on_turn_end` abilities of the player's cards on the board resolve in board order, and
   the turn ends.
8. The opponent takes the next turn if they have not passed; otherwise the same player does; if
   both have passed the round ends.

Each of steps 2, 3, 6 and 7 resolves with everything it causes before the next starts.

### 11.5 Rounds, draws and the match

- **Match start.** Instances are allocated (section 5), each deck is shuffled with the seeded
  PRNG, and the PRNG decides who starts round one. With `starter_stratagem`, the starter's
  stratagem is then placed on their board (section 3).
- **Round start.** Each player, the starter first, draws `draws_per_round` cards. A draw into a
  hand already holding `hand_limit` cards does not happen and the card stays on top of the deck;
  a draw from an empty deck does nothing. ADR 0009 (*Hand and draws*) says such draws are lost;
  ADRs are not rewritten, so the difference is noted here: this document governs, as the rules
  core does, and the card stays on the deck.
- **Mulligan.** Both players redraw at the same time, each up to `mulligans_per_round` times plus
  `mulligans_per_skipped_draw` for every draw of this round start their full hand prevented —
  and in round one the starter `starter_extra_mulligans` more — and may stop early; a player with no redraws, an empty hand or an empty deck is done at once. A
  redraw returns one card from the hand to the deck and draws a replacement into its place: the
  first card from the top whose card id differs from every card that player has returned in
  this mulligan — the top card if there is none. The returned card is then inserted into the
  deck at a position drawn with the seeded PRNG. When both players are done, the starter's first
  turn begins.
- **Round end,** once both players have passed:
  1. the `on_round_end` abilities of every card on the board resolve, in board order;
  2. the scores are compared: the higher wins the round, and a tie follows `tie_rule`;
  3. the board is cleared: every card goes to its owner's graveyard, or is banished — except
     cards with `kept_at_round_end`, which stay as they are and lose that status; an unused
     stratagem is banished; row effects are removed and both players' passes are reset;
  4. the match ends once a player has `rounds_to_win` round wins or `max_rounds` rounds have
     been played: the player with more round wins wins the match, and equal wins are a draw;
  5. otherwise the next round starts, begun by the player `next_round_starter` names.
- **Between rounds** only the board and its row effects are cleared: each player's hand, deck,
  graveyard and banished zone are kept as they are into the next round, and a leader keeps its
  charges and cooldown (section 5).

## 12. Decks

```yaml
schema: opengwt.deck/2
id: starter-a
faction: placeholder-a
leader: l-0001
stratagem: g-0101
cards:
  - { id: u-0001, count: 2 }
  - { id: s-0001, count: 1 }
```

`leader` and `stratagem` are required in v2: the leader sets the deck's provision budget, the
stratagem is what the deck brings for going first (ADR 0011) and costs no provisions. The schema
checks the shape; the rules core (`check_deck`) checks legality against `Rules` and reports
**every** rule the deck breaks at once, in the order of the table, each as a problem: the rule's
key, the card it is about for the rules marked *card*, and the numbers its message shows.

| Rule | Problem key | About | Numbers |
| --- | --- | --- | --- |
| Every card id exists. | `error.deck.unknown-card` | card | |
| The leader is a `leader` card. | `error.deck.leader-not-leader` | card | |
| The stratagem is a `stratagem` card. | `error.deck.stratagem-not-stratagem` | card | |
| The leader belongs to the deck's own faction, which is never `neutral`; the stratagem and every card to the deck's faction or to `neutral`. | `error.deck.wrong-faction` | card | |
| No leader, stratagem or token among the cards. | `error.deck.leader-in-deck`, `error.deck.stratagem-in-deck`, `error.deck.token-in-deck` | card | |
| Between `deck_min_cards` and `deck_max_cards` cards. | `error.deck.too-few-cards`, `error.deck.too-many-cards` | | `count`, and `min` or `max` |
| At least `deck_min_units` units. | `error.deck.too-few-units` | | `count`, `min` |
| At most `copies_bronze` copies of a bronze card, `copies_gold` of a gold one. | `error.deck.too-many-copies` | card | `count`, `limit` |
| Total provisions at most `provision_base` plus the leader's `provision_bonus`. | `error.deck.over-budget` | | `used`, `budget` |

How the rules count:

- The leader and the stratagem are checked first, then each card in deck order, then the
  counts. The leader and the stratagem have one problem at most each — the first of *unknown*,
  *not a leader* / *not a stratagem*, *wrong faction* — since the next check means nothing once
  one fails. A card's problems are reported once, where it first appears.
- A *unit* is a card of kind `unit`; specials and artifacts are not units. The copies of a card
  are counted across the whole deck, however its entries are split.
- A deck's provisions are the sum of its cards' `provisions`; the leader and the stratagem cost
  nothing. Its budget is `provision_base` plus the leader's `provision_bonus` — or
  `provision_base` alone when the leader is not a leader card, in which case the budget is not
  judged. The server shows both as `provisions: {used, budget}` (section 14, `match.md` §2).
- Unknown cards, and leaders, stratagems and tokens among the cards, count toward the number of
  cards and nothing else.

A deck is judged when it is saved and when a match starts with it (`match.md` §2). A match's
record keeps its decks; replaying it holds them only to what the engine needs to set a match up
— every card known, the leader a leader, the stratagem a stratagem, nothing among the cards a
deck never holds — so a record stays replayable when deck building tightens. How a problem
travels to a client, and the parameters its message is rendered with, is `match.md` §10; the
messages are `error.deck.<rule>` in `errors.yaml`.

[`examples/starter-a.deck.yaml`](examples/starter-a.deck.yaml) is legal under the default `Rules`.

## 13. Translations

Flat maps, one per locale, keys shared across locales. English is the base.

```yaml
# data/i18n/en/cards.yaml
card.u-0001.name: Placeholder unit one     # TODO: original name
card.u-0001.text: A plain unit.
faction.placeholder-a.name: Placeholder faction A
tag.tag-a.name: Placeholder tag A
```

Required keys: per card, tokens and leaders included, `card.<id>.name` and `card.<id>.text`; per
faction, `faction.<id>.name`; per tag used by any card, `tag.<id>.name`. The interface names of
the vocabulary players see — `status.<status>.name` and `.text` for every status,
`row-effect.<effect>.name` and `.text` for every row effect, with the id's underscores written as
hyphens (`status.banish-on-leave.name`) — live in `ui.yaml`, and the words chosen there are
independent of the vocabulary ids. Every key in `en` must exist in every other
locale; the compiler fails otherwise and lists the missing keys. Names must be original in every
locale, transliterations of official names included.

Message syntax, plural variants, `@` references, the fallback chain and the conformance suite are
defined in [`i18n.md`](i18n.md).

## 14. Compilation and the content pack

`opengwt.data` (the compiler) reads `data/`, validates each file against its schema, checks the
cross-file rules below, and writes one pack:

```json
{ "schema": "opengwt.pack/2", "hash": "sha256:…", "rules": { "row_capacity": 9, … },
  "factions": [...], "cards": [...], "decks": [...], "i18n": { "en": {...}, "zh-CN": {...}, "ru": {...} } }
```

`rules` is the `Rules` value the server plays with (section 4) — the one it judges decks by and
starts matches with; the client reads row capacity, hand limit and the provision budget from it
and never assumes them. Each deck is the deck file's content with its provisions under those
rules (section 12):

```json
{ "id": "starter-a", "faction": "placeholder-a", "leader": "l-1001", "stratagem": "g-0002",
  "cards": [{ "id": "u-1001", "count": 1 }, …], "provisions": { "used": 163, "budget": 165 } }
```

Cross-file rules: card ids unique; every id a deck or a `place_new_card` references exists, and
the latter names a unit or artifact; a deck's cards belong to its faction or `neutral`; no leader
is `neutral`; every required text key exists in every locale. The decks under `data/decks/` must
also be legal under the pack's `rules` (section 12). Cards are sorted by id so that the pack, and
its hash, are reproducible.

The server loads the pack at start-up and serves it (`GET /content/pack`); the client renders from
it. No runtime component reads YAML.

## 15. Versioning

`schema` is the protocol version. Adding a word to any vocabulary above, or changing a rule in
sections 9–11, is a rules-core change: it bumps the version, ships with tests, and names its
public source in the commit body. Files declaring another version are rejected by the compiler.
The v1 files were deleted in phase B, not migrated (ADR 0009).

## 16. Public sources

Written from public descriptions of the standalone game and play experience, in this project's
own words (`.agent/context/04-legal.md`); never from a client, a data dump or datamined files.

- Round draws, redraws, the hand limit and redraws for draws a full hand prevents: the
  developer's *Mulligan Update* patch notes (January 2019) and beginner guides of the
  standalone game (KeenGamer, September 2020).
- Nine units per row: the developer's *Midwinter Update* patch notes (December 2017); two rows
  since the 2018 relaunch.
- The round's winner starting the next round and a tied round won by both: player guides of
  the standalone game; confirmed from the owner's play experience.
- Bleeding at its controller's turn end, not absorbed by armour, cancelling growing turn for
  turn: the developer's *Update 4.0* patch notes (September 2019).
- The compensation for going first — one more redraw in round one for the starter, a
  stratagem chosen at deck building, on the board from the start, used once: the Mulligan
  Update patch notes above, the developer's *Merchants of Ofir* announcement (December 2019),
  KeenGamer's guide above and the community wiki's description of stratagems; that a stratagem
  takes a place on its row and is gone when round one ends, from the owner's play experience.
- Growing, status-proof, guarding, the enemy-side marker, heal, reset, drain, duel, consume,
  discard, create, take control, immunity against choices only: community glossaries of the
  standalone game (the unofficial glossary on the developer's forums, July 2021) and
  gamepressure's glossary.
- The turn (section 11.4, phase C): activated abilities before and after the turn's card, and a
  card required once one is used — the developer's forums thread *Allow [END TURN] without
  playing a card* (October 2018, moderators' answers), a Steam community discussion (September
  2020), the community glossaries' definition of an order usable on the turn its card is placed,
  and BlueStacks' beginner's guide (February 2025); that the turn then waits for the player to
  end it, from the owner.
- Cooldowns counted in the controller's turns and an order unusable on the turn its card enters
  unless it says otherwise; charges as uses, which cards can add: the community glossaries above.
- The units' turn-start abilities before the row effects, and several row effects in the order
  they were set: the community rules page of the standalone game (NamuWiki, *Gwent: The Witcher
  Card Game/Rules*).
- Deck building (section 12, phase D): at least 25 cards and 13 units, bronze cards twice and
  gold cards once, and provisions within 150 plus what the leader ability adds — KeenGamer's
  guide above, the developer's forums guide *Deck Building Guides — Overview & Introduction*
  (May 2020), Team Leviathan's *Gwent Returning Player Guide* (April 2020) and the developer's
  *GWENT's Design 01: Provision* (February 2022); bronze cards limited to two copies since the
  2018 relaunch, and no card cheaper than 4 provisions: The Magic Rain's *Gwent Homecoming: It is
  time!* (November 2018) and the design article above. At most 40 cards: the developer's *6
  things you should know about playing GWENT*, confirmed by the owner from play experience.
- Leader abilities belong to one faction — seven per faction — and a leader is never neutral
  when a match starts: KeenGamer's guide and the forums guide above, confirmed by the owner; the
  bonus a leader ability adds varies from one to another (11 to 16 over the years): the
  developer's patch notes 6.1 (April 2020), 7.1 (August 2020), 9.6 (December 2021) and 10.1
  (January 2022). Stratagems — one per deck, neutral or of the deck's faction — are chosen apart
  from the cards and cost no provisions: Team Leviathan's guide and KeenGamer's guide above. No
  limit on neutral cards and none by rarity: the colours bronze and gold are the only ones since
  the relaunch (The Magic Rain above), confirmed by the owner.

Vocabulary ids describe behaviour and never reuse a distinctive official keyword (ADR 0009).
