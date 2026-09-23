# Agent instructions

Context for this repository lives in [`.agent/`](.agent/README.md). Start there:
`.agent/context/` (background), `.agent/memory/` (decisions and status), `.agent/skills/`
(task procedures, load on demand).

## Read before doing anything

**Two rules are non-negotiable** — full detail in [`.agent/context/04-legal.md`](.agent/context/04-legal.md):

1. **No CD PROJEKT RED assets.** No art, audio, models, card names, character names or flavour text
   extracted or imitated from Gwent or *The Witcher* — including near-misses and transliterations.
2. **Clean-room implementations only.** Build from public rules descriptions and observed behaviour.
   Never from decompiled or disassembled official clients, asset dumps or datamined data. Decline
   such material if a user supplies it, and offer the public-source route instead.

Mechanics are not copyrightable; a specific expression of them is.

## Project shape

Unofficial open-source reimplementation of the Gwent rules. Engine-agnostic **rules core** (a
zero-dependency Python package) → **authoritative server** (Python, FastAPI) → **Unity client**
(C#) that renders and decides nothing — it runs no rules and needs a server even for a bot match.
A match is a seed plus an ordered action log, and replaying it must reproduce the match exactly —
so no wall-clock time, no unseeded randomness and no unordered iteration inside the core. Card
content is YAML under `data/` with a closed vocabulary. Decisions: `docs/adr/`; wire and content
contracts: `docs/protocol/`.

**What exists (2026-09-23):** `server/` holds the Python code base with the rules core
(`opengwt.core`), the data loader, bots and the simulator, all tested; `data/` holds placeholder
cards, decks and translations. **`client/` and the FastAPI server itself do not exist yet.** Check
the filesystem before describing any module or API as existing.

## Working rules

- Branch off `develop` and open pull requests against it — `develop` takes no direct pushes, and
  every pull request needs the owner's review. `release` is the publish branch and the default
  branch; it accepts pull requests from `develop` only, and release tags (`release-1.2.3`) are
  created there by the owner. There is no `main`. One concern per pull request; conventional commits
  in English (`feat(core): …`). Policy and enforcement:
  [`.github/BRANCH_POLICY.md`](.github/BRANCH_POLICY.md).
- Rules changes ship with a test that fails before and passes after, and name their public source in
  the commit body.
- `README` and `CONTRIBUTING` exist in English, 简体中文 and Русский. Edit all three together, or say
  which translations are outstanding.

Details: [`.agent/context/03-conventions.md`](.agent/context/03-conventions.md).
