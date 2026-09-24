# ADR 0009: Adopt the two-row standalone ruleset as the game's shape

- Status: accepted, 2026-09-23; keeping the PRNG and the replay record as they are is
  superseded by [ADR 0010](0010-unpredictable-random-stream.md). Phase B confirmed the numbers
  and the vocabulary against public descriptions of the standalone game and corrected them in
  `docs/protocol/cards.md` (§4, §9, §11, §16): two redraws in rounds two and three, a redraw for
  each draw a full hand prevents, status timers at turn end. Leaving stratagems and the coin-toss
  compensation out is superseded by [ADR 0011](0011-first-player-compensation.md). Phase C
  (2026-09-24) corrected the turn against public descriptions of the standalone game, with the
  owner: activated abilities stay usable after the turn's card, using one commits the turn to a
  card, and the turn ends with the player's `end_turn`, never by itself — not with the card as
  *Turn* below says (`docs/protocol/cards.md` §11.4, `match.md` §6); and a player's units act at
  their turn start before the row effects on their rows, which act in the order they were set.
  Phase D (2026-09-24) confirmed the deck numbers of *Deck* below against public descriptions
  of the standalone game (at most forty cards as well) and added, with the owner, two rules it
  does not state: a leader belongs to the deck's own faction and is never neutral, and no card
  costs fewer than four provisions (`cards.md` §3, §12, §16). The owner's further limits the
  phase was to discuss came to these two: the standalone game has no limit by rarity or on
  neutral cards, and bronze and gold are its only colours.
- Deciders: project owner
- Supersedes: the game-shape parts of [ADR 0007](0007-mvp-order-and-acceptance.md) (M1 scope)
  and the vocabulary of [ADR 0003](0003-card-effect-protocol-yaml.md) v1; the protocol itself,
  the layering and the determinism contract stand.

## Context

The MVP implemented the rules of the card game as it appears *inside* the RPG: three fixed rows,
no draws between rounds, two lives, and eleven effect actions. The owner decided on 2026-09-23 to
target the ruleset of the **standalone online game** instead, which is the version people play
today: two rows with positional play, a provision budget at deck-building time, draws and
mulligans every round, a base-versus-current power model with armour and statuses, and abilities
a player activates during a turn. The owner chose to **replace** the current ruleset rather than
keep both.

Everything below is written from public rules descriptions and play experience, in this
project's own words (`.agent/context/04-legal.md`). Exact numbers have changed across the
official game's patches; the values here are defaults of the `Rules` configuration, to be
confirmed against current public descriptions when each phase is implemented.

## Decision

### The target ruleset, in our words

- **Board.** Each player has two rows, melee and ranged, each holding at most nine units. A unit
  is played to a row the player chooses unless its card restricts it. Artifacts sit on a row
  without power. Position matters: some effects target the units adjacent to a card.
- **Deck.** At least twenty-five cards. Every card has a provision cost; a deck's total must stay
  within a budget that the chosen leader ability sets (a base plus the leader's bonus). Bronze
  cards may appear twice, gold cards once. A minimum number of units is required.
- **Hand and draws.** Ten cards at the start of round one with up to three redraws; three more
  cards at the start of rounds two and three with one redraw each; the hand never holds more than
  ten — draws beyond that are lost.
- **Turn.** On their turn a player may use any number of ready *activated* abilities (a unit's
  order, or the leader ability) without ending the turn, then either plays one card, which ends
  the turn, or passes, which ends their participation in the round.
- **Power.** A unit has a base power and a current power. Boosts raise the current power, damage
  lowers it, armour absorbs damage first; a unit whose current power reaches zero is destroyed and
  goes to the graveyard (or is banished if it is doomed). Statuses — locked, shielded, immune,
  poisoned, bleeding, vitality, and the like — alter how these rules apply to a unit, some with
  timers that tick at the owner's turn start.
- **Triggers.** Effects fire on play, on activation (with charges, cooldowns, and "usable at
  once" as options), when destroyed, at turn start or end, at round end, when an ally is played,
  when boosted or damaged, and continuously. Row effects (weather-like) damage a unit on the row
  each turn start.
- **Leader.** Not a card on the board but an ability with a number of charges, usable on the
  owner's turn without ending it.
- **Rounds.** Higher total wins the round; a tied round counts as a win for both. First to two
  round wins takes the match; a match in which both reach two, or that ends tied, is a draw.
  Who starts round two and three is a `Rules` option (`next_round_starter`), default to be
  confirmed from public descriptions. Stratagems and the coin-toss compensation are out of scope
  for this revision.

### What changes in the code base

- **`Rules`** gains: `rows`, `row_capacity`, `deck_min_cards`, `deck_min_units`,
  `provision_base`, `copies_bronze`, `copies_gold`, `hand_limit`, `draws_per_round`,
  `mulligans_per_round`, `tie_rule`, `next_round_starter`. Nothing about the shape stays
  hard-coded.
- **`CardDef`** gains: `color` (bronze / gold), `provisions`, `armor`, `tags` (free-form,
  original words, used by synergies), `kind` extended with `artifact`; `rows` becomes optional
  (any row by default).
- **`CardInstance`** gains: `base_power`, `boost`, `damage`, `armor`, an ordered `statuses` list
  with timers, `charges`, `cooldown`; current power is derived, never stored twice.
- **Engine**: activated abilities as a new intent (`use_order {instance, target?}`), a generalised
  targeting step (a unit, a row, or an entry of a list, from a candidate set the server computes),
  per-turn and per-round phases with their triggers, row capacity, per-round draws and mulligans,
  the tie rule, leader charges. The resolution queue, deterministic PRNG, replay record and
  per-player views stay as they are.
- **Protocol**: `opengwt.cards/2` and `opengwt.deck/2` (new vocabulary, provisions, colours,
  tags, artifacts), match protocol v2 (`use_order`, targeting in `pending_choice`, two rows,
  armour / statuses / readiness in the view, new events for damage, boost, armour, status,
  banish, charges). Both protocols are documented before the code, as before.
- **Data**: the placeholder content is rewritten to v2; the classic v1 files are deleted, not
  migrated. The golden replay of v1 is deleted and a v2 golden takes its place — this is the
  breaking replay change ADR 0002 asks to call out.
- **Server**: deck validation over provisions and copies; the content pack carries the v2 fields.
- **Client**: two rows, a targeting mode for orders and deploy effects, armour and statuses on
  cards, an order button on ready units, provisions in the deck choice.

### Naming

Vocabulary words describe behaviour and never reuse a distinctive official keyword:
`on_activate` rather than the official name for orders, `on_destroyed` rather than its keyword,
`boost_when_stronger_ally_played` rather than its keyword. Single generic English game words —
lock, shield, poison, bleed, armour, boost, damage, banish — are ordinary rules vocabulary and
may be used. Card, faction and tag names are original in every language.

### Phases

Each phase is one pull request with its own tests; nothing later starts before the earlier one
merged. Replay goldens are regenerated where the phase changes rules, and the pull request says so.

| Phase | Delivers | Accepted when |
| --- | --- | --- |
| A — protocols | `docs/protocol/cards.md` v2 and schema, `match.md` v2, glossary rows | schemas validate the new examples; the vocabulary covers the placeholder set planned for phase F |
| B — power and board | two rows with capacity, base / boost / damage / armour, statuses with timers, per-round draws and mulligans, hand limit, tie rule, weather as per-turn damage; v1 actions dropped | 10 000 random-bot matches without an exception, 100 replays identical, canonical state round trip |
| C — triggers and activation | `use_order` with charges / cooldown / immediate, leader charges, on-destroyed, turn-start/end, ally-played, boosted/damaged, adjacency targeting, generalised choices | every trigger has a replay test; the greedy bot uses orders; the simulator shows no stalls |
| D — deck building | provisions, colours, copy limits, minimum units; server validation; content pack v2 | illegal decks are refused with the rule key; starter decks are legal under the budget |
| E — server and client | intents and views v2 end to end; targeting UI; statuses and armour on cards; order buttons | the PlayMode test plays a v2 match against the bot; the owner plays it |
| F — content | an original placeholder set that exercises every vocabulary word, two starter decks per faction | `opengwt-sim` balance report; every string in three languages |

## Consequences

- The project's pitch changes: the interesting decisions are provisions at deck-building time,
  positional play on two rows, and what to activate before committing a card — plus the tempo of
  passing, which both versions share. `01-project.md` and the READMEs say so.
- The v1 engine, data and goldens are replaced, not kept. They remain in git history and in the
  M1–M3 pull requests if anyone wants the classic shape back as a fork.
- The client changes least: one row fewer to draw, a targeting mode and a few badges more.
- The rules core grows to roughly twice its size; phases B and C are the largest rules work since
  M1 and carry the most risk of non-determinism (timers, random targets — always through the
  seeded PRNG, never `random`).

## Alternatives considered

- **Two rulesets side by side** (`classic` and the new one, selected per deck). Cleanest for
  history and comparison, but doubles the vocabulary to maintain and the content to write; the
  owner chose one game.
- **Stay with the three-row shape.** It is finished and playable, but it is not the game the
  owner wants to build.
