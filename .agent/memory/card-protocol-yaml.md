---
name: card-protocol-yaml
description: Cards, decks and translations are YAML under data/ with a closed vocabulary; validated by JSON Schema and compiled to a content pack the server serves.
metadata:
  type: project
---

Decided 2026-09-22 (`docs/adr/0003`, spec `docs/protocol/cards.md`): card content is authored in
YAML with a closed vocabulary of triggers (`when`), conditions (`if`), actions (`do`), target
selectors, statuses and row effects — `opengwt.cards/2` since ADR 0009 phase A, which the code
implements from phase B on.
JSON Schemas in `docs/protocol/` are normative. `opengwt.data` validates and compiles everything
into one content pack; no runtime component parses YAML. Action names describe behaviour and never
reuse official ability names. Card ids are opaque and never displayed.

**Why:** the owner rejected JSON as the authoring format for readability; a closed vocabulary keeps
the core a rules engine instead of a pile of card-specific code, and keeps replays stable.

**How to apply:** a new card is a change under `data/` only. Behaviour the vocabulary cannot express
is a core change with a schema version bump and tests, not a special case. Validate any example
against the schemas before committing. See [[server-python-thin-client]].
