# ADR 0003: Card effects as a YAML protocol with a closed vocabulary

- Status: accepted, 2026-09-22
- Deciders: project owner
- Related: [ADR 0002](0002-rules-core-pure-python-package.md), spec in
  [`docs/protocol/cards.md`](../protocol/cards.md)

## Context

Adding a card must not require touching the rules core, or the core turns into a pile of special
cases and every balance change becomes a code release. At the same time the effects must stay
deterministic, reviewable, and free of anything that resembles official ability names or data
files (`.agent/context/04-legal.md`).

The owner wants the authoring format to be readable in the way a compose file is readable, and
explicitly does not want raw JSON as the format people edit.

## Decision

- Cards, decks and translations are authored in **YAML** under `data/`. One cards file per
  faction; cards are a map keyed by a stable, never-displayed id.
- The format is a **protocol**, defined by three things that ship together:
  1. a versioned JSON Schema (`docs/protocol/cards.schema.json`, `decks.schema.json`);
  2. the vocabulary document (`docs/protocol/cards.md`): triggers, actions, targets, row effects,
     and the order in which effective power is resolved;
  3. the compiler in `opengwt.data`, which validates every file against the schema and the
     cross-file rules (unique ids, referenced ids exist, every text key exists in every locale)
     and emits one **content pack** (`cards.pack.json`) with cards sorted by id.
- The vocabulary is **closed**. A card may only combine the triggers, actions and selectors the
  core implements. Adding a word to the vocabulary is a core change, bumps the schema version,
  and ships with tests.
- Names in the vocabulary describe behaviour (`destroy`, `apply_row_effect`,
  `return_from_discard`). They deliberately do not reuse official ability names.
- The runtime never parses YAML. The server loads the compiled pack at start-up and serves it to
  clients; the client renders from the pack and never reads `data/`.

## Consequences

- A new card is a pull request touching `data/` only, validated in CI, with no core change.
- Balance data is reviewable as text diffs.
- The client can update card data without a rebuild, by fetching a new pack.
- Card behaviour that the vocabulary cannot express is a signal to extend the core deliberately,
  not to add an escape hatch.

## Alternatives considered

- **JSON as the authoring format.** Same model, worse to read and edit by hand. Rejected by the
  owner; JSON remains the *compiled* form.
- **One class per card in the core.** Simplest to start, but every card is a code change and the
  core stops being a rules engine. Rejected.
- **Embedded scripting (Lua or similar).** Flexible, but it introduces a second runtime, makes
  determinism a property of the scripts rather than of the core, and means the server executes
  contributed code. Rejected.
