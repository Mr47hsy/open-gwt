# Card set import — `opengwt.cardset/1`

How a card set designed outside the repository — in a spreadsheet, a database export or a YAML
file of its own — becomes `data/` content in one step. The importer writes the files the
[card protocol](cards.md) defines and validates the whole resulting tree exactly as the compiler
does (cards.md §14) **before** it writes anything: a set with a single problem changes nothing.

```bash
cd server
uv run opengwt-data import ../my-set.yaml --data ../data --dry-run     # validate and report
uv run opengwt-data import ../my-set.yaml --data ../data --preview zh-CN
uv run opengwt-data import ../cards.csv --set my-set --data ../data     # a CSV of cards alone
```

Worked example: [`examples/cardset.yaml`](examples/cardset.yaml) with its cards in
[`examples/cardset.csv`](examples/cardset.csv).

## 1. The set file

YAML (`.yaml`, `.yml`) or JSON (`.json`):

```yaml
schema: opengwt.cardset/1
set: my-set                          # id of the set: names its files and its manifest
factions:
  forest: { name: { en: …, zh-CN: …, ru: … } }
tags:
  beast: { name: { en: … } }
cards:                               # a list, or a map of key → card
  - key: wolf                        # the designer's handle; any string, unique in the set
    faction: forest
    kind: unit
    color: bronze
    provisions: 5
    power: 4
    tags: [beast]
    abilities:
      - { when: on_play, do: damage, amount: 2, target: { units: chosen, side: opponent } }
    name: { en: …, zh-CN: …, ru: … } # or a string: the base locale's
    text: { en: … }                  # optional: overrides the generated text in that locale
cards_csv: cards.csv                 # optional: more cards, from a CSV next to this file
decks:                               # optional: a list, or a map of deck id → deck
  forest-starter:
    faction: forest
    leader: grove-keeper             # a key of this set or any card id in data/
    stratagem: g-0001
    cards: { wolf: 2, grove-keeper: 1 }   # or a list of { card, count }
```

| Field | Required | Meaning |
| --- | --- | --- |
| `schema` | yes | Exactly `opengwt.cardset/1`. |
| `set` | yes | Set id, `^[a-z][a-z0-9-]{1,63}$`. `--set` overrides it. |
| `factions`, `tags` | no | Names of the set's factions and tags per locale. |
| `cards` | yes, unless `cards_csv` | The cards (section 2). |
| `cards_csv` | no | A CSV of further cards (section 3), relative to the set file. |
| `decks` | no | Decks, written to `data/decks/` (section 4). |

## 2. Cards

A card is a card of a cards file (cards.md §3) — same fields, same closed vocabulary — plus:

| Field | Meaning |
| --- | --- |
| `key` | The designer's handle for the card. Other cards and decks may name it instead of an id. Defaults to `id`. |
| `id` | Optional card id. Without one the card gets one (section 5). |
| `faction` | The faction id the card belongs to; `neutral` for cards any deck may use. |
| `name` | Its name per locale, or one string for the base locale. |
| `text` | Optional explicit text per locale. Without it, a locale's text is generated from the card's abilities ([`i18n.md`](i18n.md) §10). |

The card rules of cards.md apply as they are: a card in a deck costs at least 4 provisions, a
leader belongs to a faction and never to `neutral`, and a deck meets every rule of cards.md §12
(size, units, copies, budget). `place_new_card`'s `card` may name a key of the set. Every other field goes to the cards file as
written and is validated against [`cards.schema.json`](cards.schema.json); a problem names the
card's key.

## 3. CSV

One card per row, as a spreadsheet or a database exports it; the first row names the columns.
UTF-8, with or without a byte-order mark. Empty cells are absent fields; empty rows are skipped.

| Column | Cell |
| --- | --- |
| `key`, `id`, `faction`, `kind`, `color`, `side` | as in section 2 |
| `provisions`, `provision_bonus`, `power`, `armor` | an integer |
| `rows`, `statuses`, `tags` | items separated by commas, semicolons, spaces or `|` |
| `token` | `true` / `false` (also `yes`, `1`, `x`) |
| `activation`, `abilities` | YAML or JSON: `{charges: 2}`, `[{when: on_play, do: draw}]` |
| `name.<locale>`, `text.<locale>` (or `name_<locale>`), `name`, `text` | the texts; a column without a locale is the base locale's |

An unknown column is an error, so a typo never loses a field. A CSV holds cards only: import it
alone with `--set`, or name it from a set file's `cards_csv` to add factions, tags and decks.

## 4. Decks

A deck has `id`, `faction`, `leader`, `stratagem` and `cards`, as a deck file (cards.md §12);
each card and the leader and stratagem may be a key of the set or any card id in `data/`. Decks
are written to `data/decks/<id>.deck.yaml` and must be legal (cards.md §12).

## 5. Ids and the manifest

Card ids are opaque and never shown (cards.md §2). A card without an `id` gets
`<prefix>-<number>`: the prefix by kind — `u` unit, `s` special, `a` artifact, `l` leader, `g`
stratagem, `t` token — and the number counting up from `--id-start`, by default the first number
of the thousand after every numbered id in `data/` (3001 while the placeholder set tops out at
2021), skipping ids in use.

The importer remembers every key's id in the set's **manifest**, `data/import/<set>.yaml`, with
the list of files it wrote. Commit it: a re-import gives every key it knows the same id, a new
key a fresh one, and deletes the files the set no longer produces — a faction it dropped, say.

## 6. What is written

| File | Holds |
| --- | --- |
| `data/cards/<faction>.cards.yaml` | the set's cards of that faction, in the set's order |
| `data/i18n/<locale>/<set>.cards.yaml` | per locale: every card's name, the texts the set gives, the names of its factions and tags |
| `data/decks/<id>.deck.yaml` | each deck |
| `data/import/<set>.yaml` | the manifest |

Every file starts with a comment naming its source; edit the source and import again, since an
import overwrites these files. A file the set did not write before is never overwritten unless
`--replace` is passed — replacing `neutral.cards.yaml`, for instance, is a decision.

**Stubs.** A locale lacking a name gets the base locale's (or the first one the set has, or
`TODO <key>`), marked `# TODO(i18n): translate` on its line, so the tree compiles and the gap is
easy to find; the report counts them per locale. A faction or tag name another translation file
already holds stays where it is, and the set's own name for it is reported and not used.

**Texts.** Card texts are not stubbed: a locale without an explicit text gets one generated from
the card's abilities (`--preview <locale>` prints them). Write a `text` only where the generated
one will not do.

## 7. Validation

In order, stopping before anything is written at the first step that finds problems, and
listing every problem that step found:

1. the set file: structure, ids, duplicate keys, CSV cells;
2. each cards file and deck file against its schema;
3. the whole tree as it would be after the import, compiled by `load_data`: duplicate ids across
   files, `place_new_card` references, deck factions and legality, translation completeness and
   the templates generated texts need.

`--dry-run` stops after step 3 and writes nothing. Names must be original in every locale, and
never resemble official material ([`.agent/context/04-legal.md`](../../.agent/context/04-legal.md)):
no tool can check that, so review the set before importing it.

## 8. Drafting abilities from plain language

A designer who writes abilities in plain language — a spreadsheet column such as
`打出时：对一个敌方单位造成 3 点伤害。` — can have them drafted into the vocabulary by the Claude
Code workflow [`.claude/workflows/ability-to-vocabulary.js`](../../.claude/workflows/ability-to-vocabulary.js):

```text
Workflow({ scriptPath: ".claude/workflows/ability-to-vocabulary.js",
           args: { source: "my-designs.csv", set: "my-set", locale: "zh-CN", batch: 8 } })
```

1. **Guard.** The input must be the owner's original design (section 7's last paragraph). The
   workflow stops, writing nothing, on official card or character names, flavour text, official
   ids, a game version or card-database links. Otherwise it normalises the cards — any shape: CSV,
   YAML, JSON, a Markdown table — and splits them into batches.
2. **Translate.** One agent per batch writes an `opengwt.cardset/1` draft that says exactly what
   each design says. A phrase the vocabulary cannot express is left out — never approximated —
   and reported with the layer it would need and a proposed descriptive word.
3. **Verify.** Another agent checks each draft with `opengwt-data check-set`, which validates
   every card on its own against the schema and prints the text generated from it
   ([`i18n.md`](i18n.md) §10), compares that text with the design, and fixes misreadings.
4. **Assemble.** The drafts become one card set, dry-run through `opengwt-data import`, and a
   report lists the vocabulary gaps, most frequent first, and every card's verdict — faithful,
   fixed or lossy.

Everything lands in `.drafts/<set>/`, which git ignores: `batches/`, `drafts/`,
`<set>.cardset.yaml` and `gaps.md`. The card set is a proposal for the owner to review before a
real import; a gap becomes a vocabulary word only by the owner's decision, with a public source,
as any rules change (cards.md §15). [`examples/draft-abilities.csv`](examples/draft-abilities.csv)
is a small original sample with some phrases the vocabulary cannot express yet.

```bash
cd server
uv run opengwt-data check-set ../.drafts/my-set/drafts/01.yaml --locale zh-CN --data ../data
```
