---
name: i18n-shared-message-format
description: Text is keys everywhere; one small message format (opengwt.i18n/1) is rendered by a Python renderer on the server and a C# renderer on the client, kept equal by a shared conformance suite; Unity Localization is not required.
metadata:
  type: project
---

Decided 2026-09-22 (`docs/adr/0006` as revised, spec `docs/protocol/i18n.md`): `{name}`
placeholders, plural variants by key suffix from the CLDR category of `count`, `@key` references,
locale-major fallback to `en` then the key itself. Tables live in `data/i18n/<locale>/`, are
served per locale by the server with the pack hash as ETag, and are rendered on the client by its
own `I18n` class. The server negotiates the locale (profile → `Accept-Language` → `en`) and puts
a rendered `message` next to `message_key` and `params` in every error, as a fallback for clients
that do not know the key. `data/i18n/conformance.yaml` runs in both CI pipelines.

**Why:** the owner wanted the server side thought through, not waved away; the risk once two
sides render text is drift, and a shared conformance suite is the only mechanism that catches it.

Card texts are the one place the compiler composes messages: it renders phrase keys first and
passes them as literal parameters to sentence templates (i18n.md §10), so the format itself
stayed as it was. A grammatical case a locale needs is a twin key (`ability.target-to.…`), not
syntax.

**How to apply:** never put a sentence in an event, view, log or stored record; never extend the
message syntax ad hoc — a new need means Fluent, not a bigger regex; add plural rules and cases
for any new locale on both sides. See [[card-protocol-yaml]], [[client-ui-toolkit]].
