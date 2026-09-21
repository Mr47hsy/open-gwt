---
name: branch-strategy
description: Three branches exist (main, release, develop); the main-vs-release overlap is an open question the owner has not decided.
metadata:
  type: project
---

Created 2026-09-22, all pointing at the initial commit `b60c049`: `main` (current default),
`release` (intended publish branch), `develop` (intended integration branch). Day-to-day work
branches off `develop`.

**Open question — do not decide this unilaterally:** `main` and `release` currently mean the same
thing. The three options put to the project owner were (1) drop `main` and make `release` the default
branch, classic git-flow; (2) keep `main` as default and use `release` as a pre-release staging
branch cut from `develop`; (3) leave all three and decide later. No answer yet. Also unanswered:
whether to push the branches to `origin`.

**Why:** the owner asked for `release` and `develop` specifically, in a repository that already had
`main`; resolving the redundancy by deleting or renaming a branch is their call, not an agent's
cleanup task.

**How to apply:** when branch layout comes up, state that the question is open and ask, rather than
assuming a workflow. Update this file once the decision is made. See [[project-status]].
