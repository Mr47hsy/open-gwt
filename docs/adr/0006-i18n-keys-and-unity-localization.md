# ADR 0006: Keys-only i18n with one message format rendered on both sides

- Status: accepted, 2026-09-22 (revised before merge: the server side was missing)
- Deciders: project owner
- Related: [ADR 0003](0003-card-effect-protocol-yaml.md), [ADR 0005](0005-client-ui-toolkit.md),
  spec in [`docs/protocol/i18n.md`](../protocol/i18n.md)

## Context

The project's documentation already exists in English, Simplified Chinese and Russian, and the
game is expected to be played by the same audience. Card names and texts are original content
written for this project (`.agent/context/04-legal.md`), so they are translated as project content.

The first draft of this record said the server has no localisation layer. That was too strong.
The server is not where text is *rendered* for players, but it is where the translations are
*distributed*, where the player's locale is *negotiated*, and the only party that can put a
human-readable fallback into an error a client does not understand yet. Once both sides render
text, the real risk is two renderers that drift apart: same key, same parameters, different
sentence.

## Decision

- **No display text in the core or in the protocol.** Cards, factions, errors and prompts are
  identified by keys; events and views carry ids and keys, never sentences.
- **Source of truth** is `data/i18n/<locale>/<domain>.yaml`, flat maps, with the locales `en`,
  `zh-CN` and `ru`. English is the base language.
- **One message format, `opengwt.i18n/1`**, deliberately small: `{name}` placeholders, plural
  variants chosen by key suffix from the CLDR category of a `count` parameter, `@key` references
  to other messages, and a fixed fallback chain. The full definition is
  [`docs/protocol/i18n.md`](../protocol/i18n.md).
- **Two renderers, one conformance suite.** The server renders with `opengwt.i18n` (Python), the
  client with its own `I18n` class (C#). Both run `data/i18n/conformance.yaml` in CI. A change to
  either renderer that breaks a case fails that side's build.
- **Server responsibilities:** serve the translation tables per locale from the content pack with
  the pack hash as `ETag`; negotiate the locale as player profile → `Accept-Language` → `en`;
  put `code`, `message_key`, `params` **and** a server-rendered `message` into every error;
  keep logs, metrics and stored data as keys and parameters, never rendered sentences.
- **Client responsibilities:** pick the locale (system default, user override written to the
  profile); fetch and cache the tables by pack hash; render everything it shows with its own
  renderer; use the server's `message` only when it does not know the key; provide a font
  fallback chain for Latin, Cyrillic and CJK; leave room for text expansion in layouts.
- **The Unity Localization package is not required.** It may be adopted later for per-locale
  assets such as images; it is not the string renderer, because its Smart String syntax would be
  a second message format.
- **Completeness is checked in CI** by the content compiler: every key in `en` exists in every
  other locale, every card has its `name` and `text` keys, every plural variant set includes
  `other`, and the conformance suite passes.
- **Generated card text** is allowed for later: the compiler may generate `card.<id>.text` from
  per-action templates in an `abilities` domain, with an explicit key overriding. The key layout
  is designed for it; the feature itself is deferred.
- **Legal:** original names in every locale. A transliteration of an official name is still an
  official name.

## Consequences

- Adding a language is a new directory under `data/i18n/`, plural rules for it in both renderers,
  and conformance cases; no other code change.
- A player using `curl`, an admin tool or a future web client gets readable errors without
  implementing a renderer; the game client never waits for the server to render anything.
- Version skew is survivable: a new error key on the server reaches an old client as a rendered
  sentence.
- Rules tests never mention display text, so they do not break on wording changes.
- The renderers are small (about a hundred lines each) and must stay small; anything the format
  cannot express is a reason to move to Fluent, not to extend the format ad hoc.

## Alternatives considered

- **Unity Localization Smart Strings on the client, `str.format` on the server.** Two syntaxes,
  guaranteed drift. Rejected.
- **ICU MessageFormat.** Precise and standard, but there is no lightweight implementation for
  Unity and the Python one drags in ICU. Rejected for v1.
- **Fluent** (`fluent.runtime` for Python, Linguini for .NET, both MIT). More expressive than
  needed today; kept as the upgrade path if `opengwt.i18n/1` runs out of room.
- **Server renders everything.** Makes the client ignorant of text, but forces a round-trip for
  every string and bakes a locale into cached views. Rejected.
- **Text embedded in card files with per-locale fields.** Unreadable with three languages and
  mixes content with translation. Rejected.
