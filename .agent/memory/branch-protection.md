---
name: branch-protection
description: How the branch policy is enforced, and the two rules GitHub cannot express natively.
metadata:
  type: project
---

Policy: only `develop` merges into `release`; merging into `develop` needs a pull request approved by
the owner; `release-*.*.*` tags are created by the owner on `release`. Configuration lives in
`.github/` — rulesets as JSON in `.github/rulesets/`, `CODEOWNERS`, and two workflows. Full write-up
in `.github/BRANCH_POLICY.md`.

**Why:** two of the three rules are not expressible in GitHub branch protection, and pretending
otherwise leaves a rule that looks enforced but is not. GitHub sees only a pull request's *target*
branch, never its source, so "only `develop` merges into `release`" is `branch-policy.yml` wired up
as a required status check. And nothing in GitHub ties a tag to a branch, so `tag-policy.yml` checks
that a `release-*` tag's commit is contained in `release` — after the push, which makes it detection
rather than prevention.

**How to apply:** do not describe these as native branch protection. The required status check only
blocks once it is listed on the `release` ruleset. Apply the rulesets by importing
`.github/rulesets/*.json` (*Settings → Rules → Rulesets → New ruleset → Import a ruleset*), which
carries that check name through — the web form's picker would only offer a check that had already
reported once. The rulesets grant bypass to repository admin on purpose: GitHub forbids self-approval,
so without it the sole maintainer could not merge their own work. Adding a hotfix path means editing
the policy document and the workflow together, never bypassing quietly. See [[branch-strategy]].
