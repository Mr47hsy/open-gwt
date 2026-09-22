# Card protocol — `opengwt.cards/1`

How cards, decks and their translations are written, validated and compiled. This is the
authoring contract behind [ADR 0003](../adr/0003-card-effect-protocol-yaml.md): the schema files
next to this document are normative, this document explains them and fixes the semantics the rules
core implements.

Everything here describes *mechanics*, which are not copyrightable. Names, ids and texts are
original to this project. Nothing in the vocabulary reuses an official ability name, and card ids
are never displayed — see `.agent/context/04-legal.md`.

## 1. Files

```
data/
  cards/<faction>.cards.yaml     one file per faction, plus neutral.cards.yaml
  decks/<deck-id>.deck.yaml      one file per deck
  i18n/<locale>/cards.yaml       card and faction texts, one flat map per locale
  i18n/<locale>/ui.yaml          client strings
  i18n/conformance.yaml          renderer conformance cases, run by server and client
```

Schemas: [`cards.schema.json`](cards.schema.json), [`decks.schema.json`](decks.schema.json).
Worked examples: [`examples/`](examples/).

## 2. Cards file

```yaml
schema: opengwt.cards/1
faction: placeholder-a          # faction id; `neutral` for cards any deck may use

cards:
  u-0001:                       # card id — stable, lower-case, never shown to players
    kind: unit
    rows: [melee]
    power: 5
```

| Key | Required | Meaning |
| --- | --- | --- |
| `schema` | yes | Exactly `opengwt.cards/1`. |
| `faction` | yes | Id of the faction every card in this file belongs to. |
| `cards` | yes | Map of card id → card. Ids match `^[a-z][a-z0-9-]{1,63}$` and are unique across **all** files. |

Ids are opaque. The convention `u-` (unit), `s-` (special), `l-` (leader) followed by a number is
recommended for placeholder content but not enforced. Ids never encode a name.

## 3. Card

| Key | Applies to | Required | Meaning |
| --- | --- | --- | --- |
| `kind` | all | yes | `unit`, `special` or `leader`. |
| `rows` | unit | yes | Rows the unit may be played on: one to three of `melee`, `ranged`, `siege`. More than one means the player chooses when playing. |
| `power` | unit | yes | Base power, integer ≥ 0. |
| `deploy` | unit | no | `self` (default) or `opponent`: which side of the board the unit is placed on when played. |
| `traits` | all | no | Set of traits; v1 has one, `immune`: the unit ignores row effects and cannot be destroyed, boosted or set by abilities. |
| `abilities` | all | no | Ordered list of abilities, resolved in order. |

A `special` is played and then goes to the discard pile after its abilities resolve, unless an
ability says otherwise (`swap_with_board_unit` leaves it on the board). A `leader` sits outside
the deck; its `activated` ability may be used once per match on the owner's turn.

## 4. Ability

```yaml
abilities:
  - when: played
    do: destroy
    target: { side: opponent, units: strongest, where: { row_total_at_least: 10 } }
  - when: played
    do: draw
    count: 2
```

Every ability has `when` and `do`. The other keys depend on `do` (section 5). `choose: player`
may be added to the actions marked *choosable*: instead of acting on every candidate, the engine
emits a pending choice, the owner picks exactly one candidate, and the match cannot continue until
they have. If there are no candidates the ability does nothing and no choice is asked.

### Triggers — `when`

| Value | Fires |
| --- | --- |
| `played` | once, when the card is played from hand. |
| `activated` | leader only: when the owner uses the leader ability. |
| `always` | not a trigger — a continuous modifier evaluated whenever power is resolved (section 6). Only the two passive actions may use it. |
| `round_end` | at the end of each round while the card is on the board. |
| `turn_start` | at the start of the owner's turn while the card is on the board. |
| `removed` | when the card leaves the board for any reason. |

### Target

```yaml
target:
  side: self | opponent | both      # default depends on the action
  rows: [melee, ranged]             # optional; default: all rows
  units: all | strongest | weakest | this   # default all; ties select every tied unit
  where:                            # all listed conditions must hold
    row_total_at_least: 10          # the unit's row-side total power is at least this
    traits_none: [immune]           # the unit has none of these traits
    traits_any: [immune]            # the unit has at least one of these traits
    same_id_as_this: true           # the unit has the same card id as the acting card
```

`strongest` and `weakest` are evaluated on **effective** power after filtering by `where`.

## 5. Actions — `do`

| Action | Parameters | Choosable | Effect |
| --- | --- | --- | --- |
| `destroy` | `target` | yes | Removes the targeted units to their owners' discard piles. Immune units are never candidates. |
| `draw` | `side` (default `self`), `count` (default 1) | no | The side draws from its deck; stops silently when the deck is empty. |
| `boost` | `target`, `amount` ≥ 1 | yes | Adds `amount` to the targets' current power. |
| `set_power` | `target`, `value` ≥ 0 | yes | Sets the targets' current power. |
| `apply_row_effect` | `effect`, `rows`, `sides` | no | Puts a row effect (section 6) on each listed row on each listed side, replacing any existing one. |
| `clear_row_effects` | `rows` (default all), `sides` (default `both`) | no | Removes row effects. |
| `summon_from_deck` | exactly one of `same_id: true` or `card: <id>`; `count` (default all) | no | Moves matching cards from the owner's deck onto the board and resolves their `played` abilities in deck order. |
| `return_from_discard` | `side` (default `self`), `where` | yes | Plays a unit from the discard pile as if from hand. Use `choose: player` for a player pick; without it, every candidate returns. |
| `swap_with_board_unit` | `where` | yes (required) | The owner picks one of their own non-immune board units; it returns to hand and the acting card takes its place on that row. |
| `multiply_power_by_copies` | — | no | Passive (`when: always`): the unit's power is multiplied by the number of units with its id on the same row-side, itself included. |
| `boost_row_others` | `amount` ≥ 1 | no | Passive (`when: always`): every *other* non-immune unit on the same row-side gains `amount`. |

"Current power" is the stored value that starts at `power` and is changed by `boost` and
`set_power`. Effective power is derived from it every time it is needed (section 6).

## 6. Row effects and effective power

Two row effects exist in v1. A row-side holds at most one; applying another replaces it.

| Effect | Meaning |
| --- | --- |
| `power_to_one` | Every non-immune unit on the row-side has power 1 before other modifiers. |
| `double_power` | Every non-immune unit on the row-side has its power doubled after other modifiers. |

Effective power of a unit is resolved in this order. Immune units stop after step 1.

1. start from current power;
2. if the row-side has `power_to_one`, the value becomes 1;
3. if the unit has `multiply_power_by_copies`, multiply by the number of units with the same id on this row-side;
4. add the `amount` of every `boost_row_others` on *other* units of this row-side;
5. if the row-side has `double_power`, double the value.

A row's total is the sum of its units' effective power; a side's score is the sum of its rows.

## 7. Decks

```yaml
schema: opengwt.deck/1
id: starter-a
faction: placeholder-a
leader: l-0001                # optional in v1
cards:
  - { id: u-0001, count: 3 }
  - { id: s-0002, count: 1 }
```

A deck may contain cards of its own faction and of `neutral`. Minimum size, unit/special limits
and copy limits are rules-core configuration, not schema: the compiler checks references, the core
checks legality.

## 8. Translations

Flat maps, one per locale, keys shared across locales. English is the base.

```yaml
# data/i18n/en/cards.yaml
card.u-0001.name: Placeholder unit one     # TODO: original name
card.u-0001.text: A plain unit.
faction.placeholder-a.name: Placeholder faction A
```

Required keys per card: `card.<id>.name`, `card.<id>.text`. Per faction: `faction.<id>.name`.
Every key in `en` must exist in every other locale; the compiler fails otherwise and lists the
missing keys. Names must be original in every locale, transliterations of official names included.

Message syntax, plural variants, `@` references, the fallback chain and the conformance suite are
defined in [`i18n.md`](i18n.md).

## 9. Compilation and the content pack

`opengwt.data` (the compiler) reads `data/`, validates each file against its schema, checks the
cross-file rules below, and writes one pack:

```json
{ "schema": "opengwt.pack/1", "hash": "sha256:…",
  "factions": [...], "cards": [...], "decks": [...], "i18n": { "en": {...}, "zh-CN": {...}, "ru": {...} } }
```

Cross-file rules: card ids unique; every id referenced by a deck exists; a deck's cards belong to
its faction or `neutral`; every required text key exists in every locale. Cards are sorted by id
so that the pack, and its hash, are reproducible.

The server loads the pack at start-up and serves it (`GET /content/pack`); the client renders from
it. No runtime component reads YAML.

## 10. Versioning

`schema` is the protocol version. Adding a word to any vocabulary above, or changing a rule in
section 6, is a rules-core change: it bumps the version, ships with tests, and names its public
source in the commit body. Files declaring an older version are rejected by the compiler until
migrated; the migration is part of the same pull request.
