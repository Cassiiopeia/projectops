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

Read `CONTRIBUTING.md` and `ARCHITECTURE.md` (code map and "how to add a flag / option / provider / language / skill") first. The maintainer rules are in `CLAUDE.md` (Korean), which also lists the per-area rule document under `docs/architecture/agent/` to read before touching workflows, wizards, scripts, the installer or skills. The ones that bite most:

- Work on `develop`. `main` deploys; never commit to it directly.
- Several agents may work in the same tree. Stage only your own paths, never use `git add -A`, and never use `git reset --hard`, `git checkout .`, `git stash` (whole tree) or force push.
- Commit through the `pro-commit` skill. The commit type decides the release version (`feat:` = minor, `feat!:` = major).
- Common workflows exist twice: `.github/workflows/` and `.github/workflows/project-types/common/`. Keep them identical.
- A new CLI flag or `version.yml` option must also be added to `src/core/options-schema.js`; `test/options-schema.test.js` fails otherwise.
- Run `npm test` and `python3 -m pytest scripts/tests/ .github/scripts/test/` (the guard checks) and run the change itself before you say it works. Do not commit new tests.

### Read before you touch (English summary of the per-area rules)

The full rules are in Korean in `CLAUDE.md` and `docs/architecture/agent/`. This table gives the rule and the incident it prevents, so you know what to read and why.

| You are changing | Read first | What went wrong when people skipped it |
|---|---|---|
| Workflow YAML (`.github/workflows/`, `project-types/`), deploy or publish axes, comment triggers, issue and PR templates | `docs/architecture/agent/workflows.md` | A missing `permissions:` block broke a comment step (#595). A workflow called a fastlane lane that did not exist (#601). A build flag was applied to one layer only (#603). After a rename the old workflow kept running (#470). The common original and its copy drifted apart |
| Flutter wizards (`.github/util/flutter/`) | `docs/architecture/agent/wizards.md` | A shared utility was redefined and the original silently stopped working. The load order flipped. `check-consistency.py` was not run (#521) |
| `.github/scripts/` (version, changelog, build number, issue helper), `.sh` files, template-only files at the repo root | `docs/architecture/agent/scripts.md` | A default path started costing money (#569). Scripts broke only on macOS bash 3.2 (#415, #418). A template-only file was registered in one of its two places. A model name with a pinned version returned 404 (#566) |
| `src/` CLI and wizard (options, run log, breaking changes), docs and GIF language, the Korean line budget | `docs/architecture/agent/installer.md` | The options source of truth and the code disagreed (#851). A `trace.emit` typo dropped the whole run log (#561). The finish screen went missing from the log |
| `skills/`, `scripts/common/`, `plugins/`, skill CLIs, config, output paths | `docs/architecture/agent/skills.md` | `SKILL_CLIS` and `RESOLVER_REVISION` were not updated (#1080). An output path was hard-coded (#623). A CLI took several optional positional arguments (#622). Test files were copied to users' computers (#591) |

Rules that apply everywhere:

- **Windows is verified only with code page 949 and a non-ASCII path.** Use `fsutil.copyPathSync`, never `fs.cpSync` (silent exit on non-ASCII paths in Node 22+). Give `subprocess.run(text=True)` an `encoding` or `errors="replace"` (Korean output turns `stdout` into `None`). Join commands in Windows instructions with `;`, not `&&` (PowerShell 5.1). Reproduce with `unset PYTHONUTF8 PYTHONIOENCODING`; `PYTHONUTF8=1` hides all of these.
- **Only five guard checks are kept** (`test/rename-consistency.test.js`, `test/options-schema.test.js`, `scripts/tests/test_skill_docs.py`, `scripts/tests/test_korean_line_budget.py`, `.github/scripts/test/test_workflow_permissions.py`). Verify your change with a scratch test or by running it, then delete the scratch test.
- **Branches have three meanings.** The default (deploy) branch is `default_branch` (`main`). The development (release source) branch is `development_branch` (`develop`; the old key `deploy_branch` is read for compatibility and written alongside). The optional deploy trigger branch is `metadata.template.options.deploy_trigger_branch`. Do not call the development branch "the deploy branch".
- **Closing issues:** when work is done, set the status label to `status: done` and close the issue with `github_cli.py finish-issue`. `set-labels` replaces every label on the issue.

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
| Run the app / server / browser and look for bugs end to end | `pro-agent-test` |
| Launch an emulator, simulator, browser or server and capture it | `pro-launch` |
| Drive an installer wizard, OS dialog or desktop app on this computer's screen (not a web page or emulator) | `pro-desktop-control` |
| Compare an implementation with a Figma design | `pro-figma` |
| Show UI mockups to compare and pick, or request a design | `pro-ui-design` |
| Make an image asset (background, character, icon, illustration, item) in the project's own style, or compare styles | `pro-image` |
| Prepare a talk: build or import the deck as HTML, rehearse it slide by slide, export PDF and editable PPT | `pro-presentation` |
| Diagnose a repository as an open source project | `pro-oss-consult` |
| Generate QA test cases | `pro-testcase` |
| Create a git worktree for an issue | `pro-init-worktree` |
| Run commands on a remote server over SSH | `pro-ssh` |
| Expose a Synology service on a domain | `pro-synology-expose` (optional `projectops-extras` plugin) |
| Audit or refactor AI-written code, check a diff for stale comments, install coding conventions | `pro-code-consult` |
| Create, review or improve a skill | `pro-skill-creator` |

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
but must not reach generated projects: `AGENTS.md`, `GEMINI.md`, `llms.txt`, `CODE_OF_CONDUCT.md`, `gemini-extension.json`,
`.agents/`, `.claude-plugin/`, `.codex-plugin/`, `.cursor/`, `skills/`.
They are removed by `.github/scripts/template_initializer.py` and skipped by `src/core/exclusions.js`.
Be careful when editing those two files and `.github/workflows/`.
Do not push unless the user explicitly asks for it.
