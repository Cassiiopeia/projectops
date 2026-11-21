# Branch strategy and release

> When to read: installing projectops in a new repo, answering its branch questions, or promoting a release to deploy.

## Three tiers

```
issue branch  YYYYMMDD_#<n>_<title>        one issue, cut from develop
   | PR
develop       development branch           collects work, head of the release PR
   | release PR (pro-changelog-deploy)
main          default branch               version bump and changelog commits land here, nothing deploys
   | promote PR (merge commit)
deploy        deploy trigger branch        a push runs store uploads and server deploys
```

| Concept | Owner's value | Where projectops stores it |
|---|---|---|
| Default branch | `main` | `metadata.default_branch` |
| Development (release source) branch | `develop` | `metadata.development_branch` (old key `deploy_branch`, same value) |
| Deploy trigger branch | `deploy` | `metadata.template.options.deploy_trigger_branch` (`--deploy-trigger-branch`) |
| Issue branch | `YYYYMMDD_#<n>_<title>` | name comes from `pro-github create-branch-name` |

- **Branch names are the user's input.** Suggest `develop` and `deploy`; never create or force them. The deploy trigger
  branch may equal the default branch (small repos, libraries): then no promote step.
- Create the deploy branch on the remote only when the first deploy is wanted: pushing it runs every deploy workflow.
- Never commit directly to `main` or `deploy`.

## Why deploy is split from the default branch

CI/CD writes version and changelog commits to the default branch on every release. When the default branch was also
the deploy trigger, its history filled with bot commits and every merge risked a deploy, which made it hard to manage.
Splitting gives: `main` = released and versioned, `deploy` = what is live, and a deploy happens only by an explicit promote.

## Promote main to deploy by merging a PR

Open a PR `main` > `deploy` and merge it with a **merge commit**. Do not push `main` to `deploy` directly.

Reason: the tip of `main` is usually the release workflow's `[skip ci]` version commit. A direct push makes that commit
the head of the push event, and GitHub skips every push-triggered workflow for it, so nothing deploys. A merge commit
is a new head without `[skip ci]`, so the deploy workflows run.

## Release flow

1. `git fetch origin`, then `git log origin/develop..origin/main`. If main has commits develop lacks (version commits),
   `git merge origin/main` into develop first; otherwise the next release fails on a version file conflict.
2. `pro-changelog-deploy`: push develop, open the release PR to main with release notes, automerge.
3. Promote: PR `main` > `deploy`, merge commit. Server deploys run; app store workflows run too, so promote only with
   the user's explicit go-ahead when the repo ships apps.
4. Check the deploy workflows and the live health endpoint; then `pro-report` and close the issues.

## Commit types decide the version

With `semver_auto` on: `feat!` = major, `feat` = minor, everything else = patch. Add `!` only when compatibility breaks.
