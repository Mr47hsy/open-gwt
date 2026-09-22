# ADR 0006: Keys-only i18n, Unity Localization on the client

- Status: accepted, 2026-09-22
- Deciders: project owner
- Related: [ADR 0003](0003-card-effect-protocol-yaml.md), [ADR 0005](0005-client-ui-toolkit.md)

## Context

The project's documentation already exists in English, Simplified Chinese and Russian, and the
game is expected to be played by the same audience. Card names and texts are original content
written for this project (`.agent/context/04-legal.md`), so they must be translated as project
content, not scraped from anywhere. Display text that leaks into the rules core or the protocol
would have to be localised in three places.

## Decision

- **No display text in the core or in the protocol.** Cards, factions, errors and prompts are
  identified by keys; the server sends keys and codes, never sentences.
- **Source of truth for text** is `data/i18n/<locale>/*.yaml`, one flat map per file, with the
  locales `en`, `zh-CN` and `ru`. English is the base language, as for the documentation. Key
  conventions are part of the card protocol: `card.<id>.name`, `card.<id>.text`,
  `faction.<id>.name`, `ui.<screen>.<element>`, `error.<code>`.
- **Completeness is checked in CI** by the content compiler: every key present in `en` must
  exist in every other locale, and every card id must have its `name` and `text` keys. A missing
  key fails the build with the list of what is missing.
- **Client:** the official `com.unity.localization` package. An editor script imports the
  compiled pack's translations into String Tables; Smart Strings handle parameters and plurals.
  Fonts use a TextMeshPro fallback chain covering Latin, Cyrillic and CJK.
- **Server:** returns error codes and message keys. It has no localisation layer of its own.
- **Legal:** original names in every locale. A transliteration of an official name is still an
  official name.

## Consequences

- Adding a language is a new directory under `data/i18n/` plus a String Table; no code change.
- Translators work on YAML files with keys and text, and CI tells them what is missing.
- Rules tests never mention display text, so they do not break on wording changes.

## Alternatives considered

- **Text embedded in card files with per-locale fields.** Convenient for one language, becomes
  unreadable with three and mixes content with translation. Rejected.
- **gettext on the server.** The server has nothing to say to a human directly; the client is
  the only place text is rendered. Rejected.
