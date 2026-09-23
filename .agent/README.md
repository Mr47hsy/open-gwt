# `.agent/` — context for AI coding agents

Everything an AI agent (or a new human contributor) needs to work on open-gwt without guessing.
Nothing here is required to build or run the project; it is prompt and context material.

## Layout

```
.agent/
  context/   background an agent should read before touching the repo
  memory/    durable facts about the project — decisions, status, open questions
  skills/    task-specific procedures, loaded on demand
```

## How to load it

| Tool | What it picks up |
| --- | --- |
| Claude Code | `CLAUDE.md` at the repo root, which points here |
| Other agents (Cursor, Codex, Aider, …) | `AGENTS.md` at the repo root, same pointer |
| Anything else | read `context/` in order, then `memory/MEMORY.md` |

Read in this order:

1. `context/01-project.md` — what this is and why it exists
2. `context/04-legal.md` — **the two hard rules; read before writing any code or adding any asset**
3. `context/02-architecture.md` — intended layering and the determinism contract
4. `context/03-conventions.md` — branches, commits, tests, trilingual docs
5. `context/05-glossary.md` — shared vocabulary, incl. the zh/ru terms used in the docs
6. `memory/MEMORY.md` — current status, decisions made, questions still open

Load a file from `skills/` only when its task comes up:

- `skills/clean-room-review/` — review a contribution against the legal rules
- `skills/docs-i18n-sync/` — keep the English / 简体中文 / Русский docs in sync
- `skills/client-headless-check/` — verify a Unity client change without the editor GUI
- `skills/i18n-strings/` — add or change a player-facing string in all three languages

## Keeping it honest

These files describe intent as much as reality, and the repository is young. If something here
contradicts the code, **the code wins** — fix the document in the same pull request.

Language: written in English to match the repository's default language. The user-facing docs
(`README`, `CONTRIBUTING`) exist in three languages; these agent files do not need translations.
