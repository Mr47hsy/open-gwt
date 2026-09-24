---
name: i18n-strings
description: Add or change a player-facing string — interface, error, prompt or card text — in all three languages, with plural variants where a count is shown, and keep the client's embedded export and the conformance suite in step. Use whenever code would otherwise contain a sentence.
---

# Adding or changing a string

No sentence lives in code, events, views, logs or stored records (ADR 0006). Everything shown to a
player is a key in `data/i18n/<locale>/*.yaml`, rendered by `opengwt.i18n` (Python) or
`MessageRenderer` (C#). The format is `docs/protocol/i18n.md`.

## 1. Pick the key

| Prefix | For | File |
| --- | --- | --- |
| `ui.<screen>.<element>` | interface text | `ui.yaml` |
| `error.<code-with-hyphens>` | server error codes (`AppError`) | `errors.yaml` |
| `choice.<action>` | prompts the core emits for a pending choice | `ui.yaml` |
| `card.<id>.name`, `card.<id>.text`, `faction.<id>.name` | content | `cards.yaml` |
| `ability.…` | templates card texts are generated from (`docs/protocol/i18n.md` §10) | `abilities.yaml` |

Lower-case, hyphens inside segments, dots between them. A string with a number takes a `count`
parameter and plural variants: `key.one` / `key.other` in `en`, `.one` / `.few` / `.many` /
`.other` in `ru`, `.other` alone in `zh-CN`. A locale with variants must have `.other`.

## 2. Write all three languages

English first (`en` is the base), then `zh-CN` and `ru` in the same change. Use the glossary in
`.agent/context/05-glossary.md` for game terms; keep **pass** in Latin script in Chinese. Never a
name that resembles official material (`.agent/context/04-legal.md`).

Parameters are `{name}`; a parameter value starting with `@` is another key to render in place,
which is how event lines get card names: `"{who}: played {card}"` with `who = "@ui.who.you"`,
`card = "@card.u-0001.name"`.

## 3. Regenerate and test

```bash
cd server
uv run opengwt-data client-i18n --out ../client/Assets/OpenGwt/Resources/i18n   # ui / choice / error keys shipped in the client
uv run pytest -q tests/test_i18n.py tests/test_data.py                          # completeness across locales, export freshness
```

`load_data` fails the build when a key in `en` is missing elsewhere (plural variants compare by
base key), a card lacks `name`, or a card text needs an `ability.…` template no table has. A card
without `text` in a locale gets one generated from its abilities; `uv run opengwt-data card-text
--data ../data` shows every card's text and where it comes from. Write a `card.<id>.text` only to
override the generated one.

## 4. If the renderer itself changes

Add cases to `data/i18n/conformance.yaml` (self-contained tables), regenerate the JSON twin with
`uv run opengwt-data conformance-json`, change **both** renderers, and run the Python tests and
the client EditMode tests (`.agent/skills/client-headless-check/`).

## 5. Use it

Python: `renderer.render(locale, key, params)`. C#: `client.Text(key)` or
`client.Text(key, MatchClient.P("count", n))`; static labels are set in `BoardView.ApplyStaticTexts`
so a language switch re-renders them.
