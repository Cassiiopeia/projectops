# projectops — Agent Instructions

projectops is three things in one repository:

1. A **GitHub project automation template**: versioning, release notes, CI/CD, issue automation (`.github/`).
2. An **installer CLI**: `npx projectops` copies the template into an existing repo (`src/`, `bin/`).
3. An **agent skill package**: `skills/pro-*` (Claude Code, Codex, Gemini CLI, Cursor, pi).

## If you are an AI agent using projectops in a repo

Do not read documentation to find options. Ask the CLI:

```bash
npx projectops --mode options --json   # every flag and every version.yml key, with values and defaults
npx projectops --mode doctor           # read-only diagnosis of an existing install
```

Rules for running it non-interactively:

- Always pass an explicit `--mode` and `--force`. Without them the CLI asks questions and blocks.
- `--mode doctor` and `--mode options` never change files. Run them first.
- Settings live in `version.yml` under `metadata.template.options`. The option table above says which keys are safe to edit by hand.
- Do not edit files under `.github/.projectops/` (run logs, baseline, incoming copies). They are diagnostics.

## If you are an AI agent working on this repository

Read `CONTRIBUTING.md` first. The detailed maintainer rules are in `CLAUDE.md` (Korean); the ones that bite most:

- Work on `develop`. `main` deploys; never commit to it directly.
- Several agents may work in the same tree. Stage only your own paths, never use `git add -A`, and never use `git reset --hard`, `git checkout .`, `git stash` (whole tree) or force push.
- Commit through the `pro-commit` skill. The commit type decides the release version (`feat:` = minor, `feat!:` = major).
- Common workflows exist twice: `.github/workflows/` and `.github/workflows/project-types/common/`. Keep them identical.
- A new CLI flag or `version.yml` option must also be added to `src/core/options-schema.js`; `test/options-schema.test.js` fails otherwise.
- Run `npm test` and `python3 -m pytest .github/scripts/test/` before you say it works.

## Skills

Skill bodies live at `skills/{name}/SKILL.md`. If one applies, read it and follow it before you act.
No slash-command UI is needed; read the file directly.

| Intent | Skill |
|--------|-------|
| Commit with the issue number filled in | `pro-commit` |
| Create or manage GitHub issues, PRs, comments, labels, secrets, Actions logs | `pro-github` |
| Open the release PR from develop to main, retrigger automerge | `pro-changelog-deploy` |
| Write the implementation report for an issue or PR | `pro-report` |
| Review code | `pro-review` |
| Something is broken, or you learned something worth recording | `pro-note` |
| Run the app / server / browser and look for bugs end to end | `pro-agent-test` |
| Launch an emulator, simulator, browser or server and capture it | `pro-launch` |
| Compare an implementation with a Figma design | `pro-figma-verify` |
| Hand an already-built screen to a designer | `pro-design-brief` |
| Diagnose a repository as an open source project | `pro-oss-consult` |
| Generate QA test cases | `pro-testcase` |
| Build or package the project | `pro-build` |
| Create a git worktree for an issue | `pro-init-worktree` |
| Run commands on a remote server over SSH | `pro-ssh` |
| Expose a Synology service on a domain | `pro-synology-expose` |
| Create, review or improve a skill | `pro-skill-creator` |
| Plan / analyze / implement (explicit call only) | `pro-plan`, `pro-analyze`, `pro-implement` |

## Installing the skills

Claude Code:

```bash
claude plugin marketplace add Cassiiopeia/projectops
claude plugin install projectops@projectops-marketplace --scope user
```

Codex: `codex plugin marketplace add Cassiiopeia/projectops`, then open `/plugins` and check the `projectops` entry.
Fallback without the marketplace:

```bash
git clone https://github.com/Cassiiopeia/projectops.git ~/.codex/projectops
mkdir -p ~/.agents/skills && ln -s ~/.codex/projectops/skills ~/.agents/skills/projectops
```

Other IDEs: `npx projectops --mode skills`.

## Repository safety

This repository is also the source that initializes other projects. Agent package files belong here
but must not reach generated projects: `AGENTS.md`, `GEMINI.md`, `llms.txt`, `gemini-extension.json`,
`.agents/`, `.claude-plugin/`, `.codex-plugin/`, `.cursor/`, `skills/`.
They are removed by `.github/scripts/template_initializer.py` and skipped by `src/core/exclusions.js`.
Be careful when editing those two files and `.github/workflows/`.
Do not push unless the user explicitly asks for it.
