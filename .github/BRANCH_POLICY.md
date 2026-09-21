# Branch policy

The rules this repository runs on, how each one is enforced, and how to apply the parts that live in
GitHub's settings rather than in the repository.

## The rules

1. **Only `develop` may be merged into `release`.**
2. **Merging into `develop` requires a pull request, approved by the owner.**
3. **`release-*.*.*` tags may only be created by the owner, on `release`.**

## How each rule is actually enforced

| Rule | Mechanism | Blocks the action? |
| --- | --- | --- |
| Pull request required on `develop` | `develop` ruleset | Yes |
| Owner review required on `develop` | `develop` ruleset + [`CODEOWNERS`](CODEOWNERS) | Yes |
| No direct pushes / force pushes / deletion of `develop` and `release` | branch rulesets | Yes |
| Pull requests into `release` come only from `develop` | [`workflows/branch-policy.yml`](workflows/branch-policy.yml) as a **required status check** | Yes, once the check is required |
| Only the owner creates `release-*` tags | `release tags` ruleset | Yes |
| `release-*.*.*` tags point at a commit on `release` | [`workflows/tag-policy.yml`](workflows/tag-policy.yml) | **No — reports after the fact** |

Two of these need explaining, because they are the places where GitHub cannot do what was asked:

**GitHub cannot restrict which branch a pull request comes from.** Branch protection and rulesets
only see the *target* branch. So "only `develop` merges into `release`" is a CI job that reads
`github.head_ref` and fails for anything that is not `develop`. Making that job a **required status
check** on the `release` ruleset is what turns it from a red X into an actual block — without that
step, the rule is advisory.

**GitHub cannot tie a tag to a branch.** A tag ruleset restricts *who* may create a tag matching
`release-*`, which covers the owner-only half of rule 3. Nothing in GitHub checks *which commit* the
tag points at, so `tag-policy.yml` verifies that the tagged commit is contained in `release` and
fails the run if it is not. The tag already exists at that point; the job tells you to delete it and
re-tag. This is detection, not prevention, and there is no configuration that makes it prevention.

## Applying the rulesets

The repository is public, so rulesets are available at no cost. Three rulesets, one per file in
[`rulesets/`](rulesets/). They are checked in so the configuration is reviewable and re-appliable.

### With the GitHub CLI

```bash
gh api --method POST /repos/Mr47hsy/open-gwt/rulesets --input .github/rulesets/develop.json
gh api --method POST /repos/Mr47hsy/open-gwt/rulesets --input .github/rulesets/release.json
gh api --method POST /repos/Mr47hsy/open-gwt/rulesets --input .github/rulesets/release-tags.json
```

To update one later, find its id with `gh api /repos/Mr47hsy/open-gwt/rulesets` and use
`--method PUT /repos/Mr47hsy/open-gwt/rulesets/<id>`.

### Through the web interface

*Settings → Rules → Rulesets → New ruleset.*

**`develop`** — target branch `develop`:
- Restrict deletions
- Block force pushes
- Require a pull request before merging → 1 approval, **Require review from Code Owners**, dismiss
  stale approvals on new pushes

**`release`** — target branch `release`:
- Restrict deletions
- Block force pushes
- Require a pull request before merging → 1 approval, Require review from Code Owners, merge commit only
- Require status checks to pass → add **`source-branch-must-be-develop`**

**`release tags`** — target tag pattern `release-*`:
- Restrict creations, updates and deletions

## Two things to check after applying

**The required status check has to exist before you can require it.** GitHub only offers a check in
the "require status checks" picker after it has reported at least once. Open one pull request into
`release` first, let `branch-policy.yml` run, then add `source-branch-must-be-develop` as required.

**Bypass actors: verify them in the UI.** Each ruleset JSON grants bypass to repository admin
(`"actor_type": "RepositoryRole", "actor_id": 5`). Open the ruleset after applying it and confirm
the bypass list reads *Repository admin* — role ids are an implementation detail and are worth a
look rather than a trust.

That bypass is deliberate, and it matters on a single-maintainer repository: **GitHub does not let
anyone approve their own pull request.** With required approvals and no bypass, the owner could not
merge their own work — the rule would lock the only maintainer out of the repository. With the
bypass, the rule binds contributors, which is what rules 2 and 3 are actually about, while the owner
can still merge. If a second maintainer joins, reconsider: remove the bypass and have the two review
each other.

## Working within the policy

```
feature branch ──PR──▶ develop ──PR──▶ release ──tag──▶ release-1.2.3
                (owner review)   (from develop only,    (owner, on release)
                                  owner review)
```

- Branch off `develop`, open the pull request against `develop`.
- A pull request into `release` *is* a release: it comes from `develop`, and nothing else.
- Tag on `release` after the merge, as `release-1.2.3` — three numeric components, no `v` prefix.
- Hotfixes are not exempt. There is no hotfix path today; if one is needed, add it to this document
  and to the workflow's allowed source branches rather than bypassing the rule quietly.
