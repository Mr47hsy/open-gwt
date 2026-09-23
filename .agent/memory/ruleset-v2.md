---
name: ruleset-v2
description: Decided 2026-09-23 — the game targets the two-row standalone ruleset (ADR 0009), replacing the three-row shape; the core on develop stays v1 until phases A–F land, one pull request each.
metadata:
  type: project
---

The owner chose the standalone online game's rules over the in-RPG version, and chose to
**replace**, not to keep both. ADR 0009 describes the target in the project's own words (two rows
of nine, provisions at deck-building, draws and redraws each round, base / boost / damage / armour,
statuses with timers, activated abilities that do not end the turn, leader charges, tied rounds
won by both) and the six phases: A protocols v2, B power and board, C triggers and activation,
D deck building, E server and client, F content. Every shape number lives in `Rules`, to be
confirmed against public descriptions when implemented.

**Why:** the standalone ruleset is the game people play today; the classic shape was the MVP's
quickest proof of the architecture, and the architecture (pure core, protocol, thin client)
carries over unchanged.

**How to apply:** do not add v1 content or vocabulary; read ADR 0009 and take the next unfinished
phase from [[backlog]]; vocabulary words describe behaviour and never reuse a distinctive official
keyword; regenerate goldens when a phase changes rules and say so in the pull request. See
[[card-protocol-yaml]], [[project-status]].
