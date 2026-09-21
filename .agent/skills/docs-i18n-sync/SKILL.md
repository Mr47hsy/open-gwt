---
name: docs-i18n-sync
description: Keep open-gwt's trilingual documentation in sync — English, Simplified Chinese and Russian versions of README and CONTRIBUTING. Use when editing any of those files, adding a documentation page that needs translating, or adding a new language.
---

# Trilingual docs sync

English is the source of truth. `zh-CN` and `ru` are translations and must not drift from it.

## The file set

| Document | English | 简体中文 | Русский |
| --- | --- | --- | --- |
| Readme | `README.md` | `README.zh-CN.md` | `README.ru.md` |
| Contributing | `CONTRIBUTING.md` | `CONTRIBUTING.zh-CN.md` | `CONTRIBUTING.ru.md` |

`LICENSE-ASSETS` is a single file with all three languages inside it, not three files.

## Editing an existing document

1. Make the change in the English file first.
2. Apply the same change to the `.zh-CN.md` and `.ru.md` files in the **same** pull request.
3. Keep the structure identical across the three: same headings in the same order, same lists, same
   code blocks, same links. A reader switching languages should land in the same place.
4. Use the terminology in `.agent/context/05-glossary.md`. If you need a term that is not there, add
   a row rather than inventing a one-off translation.
5. Leave the CDPR disclaimer intact in every language. In the zh and ru files it appears in English
   *and* in the local language — that is deliberate; do not "deduplicate" it.
6. If you genuinely cannot do a translation, say which ones are outstanding in the pull request
   description instead of letting them silently rot.

## Language switcher

Every translated file opens with a switcher directly under the `# open-gwt` title: the three
languages separated by ` · `, the current one in **bold** and the other two as links.

```markdown
[English](README.md) · **简体中文** · [Русский](README.ru.md)
```

## Checks before finishing

- Same heading count and order in all three files.
- Every relative link resolves — the translations link to `LICENSE`, `LICENSE-ASSETS` and
  `CONTRIBUTING.md` at the repository root, not to a translated path that does not exist.
- Badges, code blocks and the repository-layout tree are identical across languages; only prose and
  the comments inside the tree get translated.
- Switcher present and correct, with the current language bolded rather than linked to itself.

## Adding a language

Copy the English file, translate, add the new entry to the switcher in **all** existing files, add
the language column to the glossary, and say in the pull request who can review it. Do not add a
language nobody on the project can proofread.
