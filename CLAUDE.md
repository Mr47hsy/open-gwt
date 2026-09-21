# CLAUDE.md

Agent instructions for this repository are in [AGENTS.md](AGENTS.md) — read it first.

Deeper context, project memory and task skills live in [`.agent/`](.agent/README.md):

- [`.agent/context/`](.agent/context/) — project, architecture, conventions, legal rules, glossary
- [`.agent/memory/`](.agent/memory/MEMORY.md) — decisions taken, current status, open questions
- [`.agent/skills/`](.agent/skills/) — load `clean-room-review/SKILL.md` when reviewing a
  contribution, `docs-i18n-sync/SKILL.md` when touching the trilingual docs

Non-negotiable, repeated here because it gates everything: **no CD PROJEKT RED assets, and
clean-room implementations only.** See [`.agent/context/04-legal.md`](.agent/context/04-legal.md).
