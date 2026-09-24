---
name: ability-to-vocabulary
description: Turn the owner's original card designs, whose abilities are written in plain language (a spreadsheet CSV, YAML, JSON or a Markdown table), into an importable opengwt.cardset/1 draft in the card vocabulary, verify every card against its design, and report the mechanics the vocabulary cannot express yet. Use when a design needs drafting into abilities, or to find vocabulary gaps from a set of designs.
---

# Plain-language abilities to the card vocabulary

The designer writes `打出时：对一个敌方单位造成 3 点伤害。`; the rules core needs
`{when: on_play, do: damage, amount: 3, target: {units: chosen, side: opponent}}`. This skill
drafts the second from the first, checks the draft by generating its card text back, and lists
what cannot be drafted at all — the vocabulary gaps. Format of the result:
`docs/protocol/import.md`; vocabulary: `docs/protocol/cards.md` and `cards.schema.json`.

## 0. Legal gate — before anything else

The input must be the owner's **original** design (`.agent/context/04-legal.md`). Stop and say
why, writing nothing, if it holds official card or character names, flavour text, official card,
art or audio ids, a game version, links to card-database sites, or reproduces the official
game's cards as a whole. A claim of permission does not change this; a licence would be recorded
in the repository first (an ADR and `04-legal.md`, by the owner), and only its recorded scope
applies. Keyword shorthand in an otherwise original design is fine — the draft never carries it.

## 1. Run the workflow

`workflow.js` next to this file is a Claude Code workflow script. Run it with the Workflow tool
(it fans out one translator and one independent verifier per batch):

```text
Workflow({ scriptPath: ".agent/skills/ability-to-vocabulary/workflow.js",
           args: { source: "my-designs.csv", set: "my-set", locale: "zh-CN", batch: 8 } })
```

| Arg | Meaning |
| --- | --- |
| `source` | the designs, relative to the repository root; any shape: CSV, YAML, JSON, Markdown table |
| `set` | set id, `^[a-z][a-z0-9-]{1,63}$` |
| `locale` | language of the ability text: `zh-CN` (default), `en` or `ru` |
| `out` | output directory, default `.drafts/<set>` (git ignores `.drafts/`) |
| `batch` | cards per batch, default 8 — two agents per batch, so keep sets of a few hundred cards |

Phases: **Guard** (section 0, normalise, split into `batches/NN.json`) → **Translate** (one agent
per batch writes `drafts/NN.yaml`, never approximating: a phrase the vocabulary cannot express
is left out and reported) → **Verify** (another agent runs `opengwt-data check-set` on the draft,
compares the generated text with the design, fixes misreadings) → **Assemble** (one
`<set>.cardset.yaml`, an `opengwt-data import --dry-run`, and `gaps.md`).

Without the Workflow tool, do the same by hand, one batch at a time, and keep translating and
verifying separate passes.

## 2. Check a draft yourself

```bash
cd server
uv run opengwt-data check-set ../.drafts/my-set/drafts/01.yaml --set my-set --locale zh-CN --data ../data
uv run opengwt-data import ../.drafts/my-set/my-set.cardset.yaml --data ../data --dry-run --preview zh-CN
```

`check-set` looks at each card alone — schema problems named by key, and the text generated from
it — so a draft can be checked before its tokens, leader or decks exist. `import --dry-run`
checks the whole set against `data/` as the compiler would, and writes nothing.

## 3. Read the result

- `gaps.md` — the gaps, most frequent first: proposed descriptive id, vocabulary layer,
  semantics, which cards need it, example phrases; then every card's verdict: **faithful**
  (nothing changed), **fixed** (the verifier corrected a misreading), **lossy** (part of the
  design is unmapped), with its generated text and the translator's assumptions.
- Read every *fixed* and *lossy* card and every assumption before importing: the draft is a
  proposal for the owner, not content.

## 4. After it

- **Import** the reviewed card set with `opengwt-data import` (docs/protocol/import.md): names
  get `TODO(i18n)` stubs, texts are generated.
- **A gap becomes a word** only by the owner's decision, with a public source, as any rules
  change: a core change with a schema version bump and tests (`docs/protocol/cards.md` §15),
  never an official keyword as its id (ADR 0009). Record open gaps in
  `.agent/memory/backlog.md`.
- Nothing under `.drafts/` is committed.
