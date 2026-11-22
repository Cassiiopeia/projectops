---
name: pro-project-blueprint
description: "Start, align or look up a project the owner's way without re-asking: a private registry of each project's repos, deploy and database, monorepo layout, develop > main > deploy branches, public-repo secrets as whole files, NAS Docker deploy. Use for 'new project', 'which server is this on'."
---

# Project Blueprint

## When to use

- "Start a new project", "set up this repo like my other ones", "bootstrap the monorepo", "make it a public repo"
- "Where do the secrets go?", "add a new secret key", "how should this deploy?", "split deploy from main"
- "Which server, container, domain or database is this project on?", "register this project", "update the project map"
- Before the first commit of a new repo, or when an existing repo drifts from the owner's usual setup.
- Not this skill: installing workflows is `npx projectops` (this skill decides the answers to its questions);
  exposing a domain on the NAS is `pro-synology-expose`; running commands on the server is `pro-ssh`.

This is the owner's house standard for how a project is started, laid out, released and kept safe in public.
**Apply it without asking about anything it already decides.** Ask only for what is genuinely new per project
(product name, short prefix, which stacks). Reply in the user's language.

**First, look the current repo up in the project registry** (`references/project-registry.md`): match the git remote,
then the local path, against `project-blueprint.projects`. A match answers stacks, branches, container, domains,
database and secret names; do not ask the user for anything the entry already holds.

## What you want → reference

| Topic | Decides | Details |
|---|---|---|
| Repo layout | Stack folders, `brand/`, `docs/`, root and per-stack `CLAUDE.md`, `version.yml`, `.gitignore` | `references/repo-layout.md` |
| Branches and release | Issue branch > `develop` > `main` > `deploy`, why deploy is split, promote by PR merge | `references/branch-strategy.md` |
| Secrets in a public repo | Workflow secrets vs one-file runtime secrets, server copy, NAS backup, jar check | `references/public-repo-secrets.md` |
| Server deploy | Docker Hub image tags, Traefik Blue-Green on the NAS, reverse proxy, DNS, shared PostgreSQL, rollback | `references/server-deploy.md` |
| Stack defaults and conventions | React Native (Expo) and Spring choices, coding rules in short | `references/stack-defaults.md` |
| Project registry | What each existing project is: repos, stacks, branches, deploy, database, secret names, store ids; lookup and write rules | `references/project-registry.md` |
| Reusable infra values | Registry user, servers, DNS, Traefik, shared databases (referenced by name from projects) | `config.sample.json` + below |

## Infra values: private config only

The owner reuses the same infra values in every project. They live in the private projectops config, never in a repo,
an issue, a report or this skill (reason: every repo is public, and these values identify the owner's machines).

1. Read `{HOME}/.projectops/config/config.json` directly with the Read tool and take the `project-blueprint` section
   (schema: `../references/config-rules.md` §7). Do not search for the file elsewhere.
2. Missing section → copy the shape of `config.sample.json`, ask for each value one at a time, save it there.
   A section without `schema_version` is version 1: read it, and convert it when you next write
   (`references/project-registry.md` migration table). Keep every key you do not change.
3. Passwords and tokens are not duplicated here. Server and account entries name a launch credential
   (`credential`, resolved by `pro-ssh`/`pro-launch`). Registry tokens and keys go straight into GitHub Secrets.
4. Use the values to fill workflow `env:` blocks and GitHub Secrets. In committed files write only what is already
   public by design (the service domain in a workflow, the Docker Hub image name), never hosts, users or ports of the server.

## New project checklist

Work through it in order. Each step names the skill that does the work.

1. **Design** - settle product name, prefix (`<PFX>`, 2-4 capitals, e.g. module names `<PFX>-Web`) and stacks with
   `superpowers:brainstorming`; save the spec under `docs/superpowers/specs/`.
2. **Create the repo** - public, with `main` as default (`pro-github create-repo`).
3. **Lay out folders** - `references/repo-layout.md`: stack folders, `brand/`, `docs/`, root `CLAUDE.md` index, per-stack
   `CLAUDE.md`, `.gitignore` that blocks every secret file before the first commit.
4. **Install projectops** - `npx projectops` with the answers from `references/branch-strategy.md` and
   `references/server-deploy.md` (types and `--paths`, `--deploy docker-ssh` for servers, development branch,
   deploy trigger branch). Branch names are the user's input: take them from `defaults` in the private config
   (saved once by the user), otherwise suggest `develop` and `deploy` and ask; never force them.
5. **Secrets** - write `application-prod.yml` / `.env` files locally, register them whole as GitHub Secrets
   (`pro-github secrets set`), add the workflow secrets (`references/public-repo-secrets.md`).
6. **Server** - a database on the shared PostgreSQL (owned by the shared account unless the project wants its own),
   volume folder, domain and reverse proxy (`pro-synology-expose`), then the first deploy (`references/server-deploy.md`).
7. **Verify** - build each stack locally, then check the deployed health endpoint (`pro-ssh` for logs).
8. **Register** - write the project's entry into `project-blueprint.projects` (`references/project-registry.md`).

## Daily work pipeline

```
design > issue (pro-github) > worktree (pro-init-worktree) > implement > verify > commit (pro-commit)
> push (only when asked) > release PR develop > main (pro-changelog-deploy) > promote main > deploy (PR merge)
> report (pro-report) > knowledge note when the repo turns it on (pro-brain) > label done and close (pro-github finish-issue)
```

- Stage only the paths you touched; other agent sessions may be working in the same tree.
- Push only when the user asks. Never force-push; integrate with rebase.
- App store deploys run only when the user explicitly asks for that deploy (store review follows).
- Before a release, merge `origin/main` into `develop` if main has commits develop lacks (version commits land on main).

## Decision rules

- An existing repo that already differs (single `main`, Flutter instead of Expo) is not migrated silently: list the
  differences and let the user pick what to align.
- A new secret key means editing the one secret file and replacing the whole GitHub Secret, never a new secret per key.
- If a value would have to be written into a committed file to make something work, stop and route it through a
  secret file or the private config instead.
- When the deploy branch equals the default branch (small repos), skip the promote step; everything else stays.

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-project-blueprint`.
Keys for this skill: the common `language`, `tone`, `rules` only.
Preferences change presentation only; secret protection and approval gates stay in force.
