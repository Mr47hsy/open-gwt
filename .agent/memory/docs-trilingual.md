---
name: docs-trilingual
description: README and CONTRIBUTING exist in English, Simplified Chinese and Russian; English is the source of truth.
metadata:
  type: project
---

`README` and `CONTRIBUTING` exist as `.md` (English), `.zh-CN.md` (简体中文) and `.ru.md` (Русский).
English is the source of truth and the default `README.md` GitHub renders. Each file opens with a
language switcher listing all three, the current language in bold. Shared terminology is fixed in
`../context/05-glossary.md`.

**Why:** the project pitches itself to an international contributor base, and the owner drafted the
original copy in Chinese — so translations are first-class, not an afterthought, and they drift
immediately if one file is edited alone.

**How to apply:** edit all three in the same pull request, or state in the description which
translations are outstanding. The `docs-i18n-sync` skill in `../skills/` has the checklist. Adding a
fourth language means adding it to every switcher. See [[project-status]].
