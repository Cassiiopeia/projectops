# Projectops

A fully automated GitHub project management template

---

## ⚠️ Language (agent must read)

**Language: this is an open-source repository. Code comments, docstrings, commit messages, issues and rule documents are written in English (this overrides any personal convention of Korean comments). Korean stays only in localization catalogs, Korean docs-site pages and README translations, compatibility strings and historical records.**

---

## ⚠️ Working branch rules (agent must read)

**This project works directly on the `develop` branch by default. `main` is production (default) — never commit or push to it directly.**

- Unless told otherwise, do not create a feature branch; work, commit and push on `develop`.
- Before pushing `develop`, **always sync first with `git pull --rebase origin develop`** (releases add a version-finalization commit to develop, so local copies fall behind easily).
- Releases (deploys) go only through a develop→main PR (`/pro-changelog-deploy`). A direct push to main only has its version preserved by the safety net (VERSION-CONTROL guard); it is not a supported path.
- Run `git push` **only when the user explicitly asks for it**.
- Use a feature branch only when the user explicitly asks for branch work.
- **Commit with `/pro-commit`.** It extracts the issue number from the branch name to build a message that follows the conventions, and shows you the staging targets for confirmation.

### Several agents work at the same time (agent must read)

**Several Claude Code sessions work on the same `develop` at the same time.** No session knows about the others
or what they are doing. Act on the assumption that changes you did not make can appear in the working tree at any moment.

| Situation | Response |
|---|---|
| Before starting work | Get the latest state first with `git pull --rebase origin develop` |
| Before committing | Check `git status` for **changes you did not make** |
| Staging | Stage **only the paths you touched** explicitly, rather than `git add -A` |
| The branch has changed | Another session may have moved it. Do not switch back on your own; respect the current branch |
| Push rejected (non-fast-forward) | Do not force-push. Integrate with rebase, then push again |

**Forbidden**

- `git push --force` / `--force-with-lease` — other sessions' commits disappear
- `git checkout .` · `git reset --hard` — destroys other sessions' uncommitted work
- Committing files unrelated to your work — makes causes impossible to trace

If there are changes in the working tree whose intent you do not know, **leave them alone.** Committing only your changes and
leaving the rest for that session to handle is the safe choice.

### Three branch concepts (agents and wizard must read — #482)

Watch out for confusion: a project has **three branch concepts**, and the version.yml field names do not match intuition.

| Concept | Meaning | version.yml field | Standard value |
|------|-----|-----------------|--------|
| **Default (deploy) branch** | Repo default, production. Deployment runs when it is pushed | `default_branch` | `main` |
| **Development (release source) branch** | Collects development; the head of the release PR into the default branch | `development_branch` (formerly `deploy_branch`) | `develop` |
| Deploy trigger branch (optional) | Where a push runs the **deploy workflows**. Set only when splitting it from the default branch (develop > main > deploy). The wizard asks it right after the development branch (#1248) | `metadata.template.options.deploy_trigger_branch` | none = default branch |
| Issue branch | Unit of work (`YYYYMMDD_#number_title`) | — | — |

> ⚠️ **The canonical key name is `development_branch` (#915).** The old name `deploy_branch` was easily misread as "deploy branch", so it was demoted from canonical and remains only for backward compatibility.
> - **Reading**: every consumer reads `development_branch` → if missing, `deploy_branch` → if missing, `develop` (`readDevelopmentBranch` in `src/core/version-yml.js`, `_parse_release_branches` in `changelog_cli.py`).
> - **Writing**: generators write **both keys with the same value** — so older skill versions that read only the old key (the plugin updates separately from the repo) do not silently fall back to `develop`. An update (re-running the wizard) rewrites files that only have the old key with both keys.
> - Workflows do not read this key at runtime (the branch name is substituted at install time).
> - In user-facing text, do not call this branch the "deploy branch"; call it the "development (release source) branch". The CLI flag `--deploy-branch` and the internal variable name `deployBranch` stay as they are.

---

## ⚠️ Issue handling rules (agent must read)

**In this project, when an issue is complete, put the done label on it and close it.** (Changed by owner decision on 2026-10-10 — previously issues were not closed and only the label was changed.)

- When the work is done, change the issue's status label to **`status: done`** (`작업완료` in existing Korean-label repos) and **close the issue.**
  Use `finish-issue {owner} {repo} {number} [--outcome done|cancelled|in-progress]` — it changes only the status label (keeping other labels such as `type:` and `area:`) and closes the issue.
  `set-labels` **replaces all labels**, so passing only `set-labels ... "status: done"` wipes every other label. Using only `add-labels` leaves the previous status label, giving two statuses.
- **Respect the completion criteria** — close only issues whose implementation has landed on main (or the development branch) and whose verification and report (`/pro-report`) are done.
  If the user **explicitly asks to mark a specific issue complete**, do it without re-checking these criteria.
  If sub-tasks remain, do not close it; leave it at `status: in progress`. Cancelled work is closed with `status: cancelled`.
- Label changes and closing are done with `/pro-github` (`github_cli.py finish-issue`). If only some steps fail, redo just the steps in `failed_steps` with `set-labels` (the full existing label list with only the status changed) / `close-issue`.
- **The release workflow closes issues too (#771, `close_on_release`).** Among issues with the done label, it closes those referenced by URL from commits in the release range. No conflict if an agent closes them first (already-closed issues are skipped). It is on in this repo's `version.yml`.
- **An update does not bring back workflows the user deleted or excluded (#810).** Files that are in the baseline but missing, files listed in `options.excluded_workflows`, and files that run only on `develop` when the development branch does not exist on the remote are skipped, with a copy left in `incoming/`. If you add a new conditional install path, route it through the `skipNew` gate in `copy/workflows.js`.
- **Status labels exist in both the English standard (`status: todo`, etc.) and legacy Korean (`작업전`, etc.) (#776).** `label_style` decides the notation (new repos `en`, existing ones keep `ko`), and the shared skill label functions and Projects sync recognize either notation interchangeably.

---

## ⚠️ Documents to read before touching things (agent must read)

**Before editing anything in the table below, Read the matching document first.** This file holds only the rules that apply to all work; area-specific rules moved into the documents.
Each row's incidents really happened because someone edited without reading that document.

| What you touch | Read first | Incidents when edited without reading |
|---|---|---|
| Workflow YAML (`.github/workflows/`, `project-types/`), deploy/publish axes, comment triggers, issue/PR templates | [`docs/architecture/agent/workflows.md`](docs/architecture/agent/workflows.md) | Comment step failed due to missing `permissions:` (#595) · called a nonexistent fastlane lane (#601) · build flags applied in only one layer (#603) · the old workflow kept running after a rename (#470) · shared workflow original and copy out of sync · a local YAML parser error mistaken for a real breakage |
| Flutter wizards (`.github/util/flutter/`) | [`docs/architecture/agent/wizards.md`](docs/architecture/agent/wizards.md) | Redefining shared utilities disabled the canonical ones · load order reversed · `check-consistency.py` not run (#521) |
| `.github/scripts/` (version · changelog · build number · issue helper), `.sh`, template-only files at the repo root | [`docs/architecture/agent/scripts.md`](docs/architecture/agent/scripts.md) | A paid element on the default path (#569) · broke only on macOS bash 3.2 (#415 · #418) · template-only file registered in only one place · a version pinned in a model name gave 404 (#566) |
| `src/` CLI · wizard (options, run logs, breaking changes), doc/GIF language, Korean line budget | [`docs/architecture/agent/installer.md`](docs/architecture/agent/installer.md) | Canonical options and code out of sync (#851) · a `trace.emit` typo dropped the log entirely (#561) · the completion screen missing from the log |
| `skills/`, `scripts/common/`, `plugins/`, skill CLI · config · output paths | [`docs/architecture/agent/skills.md`](docs/architecture/agent/skills.md) | `SKILL_CLIS` · `RESOLVER_REVISION` not updated (#1080) · hard-coded output paths (#623) · several optional positional arguments (#622) · test files copied to user PCs (#591) |

- New area rules not in this table go into whichever document above fits, not into this file. Add only a one-line summary and a link here.
- The "Python behavior script standard" for editing skill CLIs is in `skills.md`, and the "adding template-only files" rule is in `scripts.md`.

---

## Project overview

### Supported project types
<!-- generated: project-types:types-table -->
| Type | Description | Version sync file |
|------|------|------|
| `flutter` | Flutter | `pubspec.yaml` |
| `spring` | Spring Boot | `build.gradle` |
| `python` | FastAPI/Django | `pyproject.toml` |
| `react` | React.js / Next.js | `package.json` |
| `react-native` | React Native CLI (no app workflows) | `Info.plist + build.gradle` |
| `react-native-expo` | Expo | `app.json` |
| `node` | Node.js | `package.json` |
| `basic` | General purpose | `version.yml only` |
<!-- /generated -->

> **Multi-type**: when several types coexist in one repo, pass them as csv with `--type spring,react,python`. They are saved in the `project_types` array in `version.yml`, and the first item is the primary type (the singular `project_type` key was removed in v4.1.0 — SSOT).
>
> **Monorepo paths**: when per-type projects live in subfolders (e.g. `app/`, `client/`, `ai/`), set them with the `project_paths` map in `version.yml` (type → path relative to the repo root). The integrator detects and confirms marker files (`pyproject.toml`, `package.json`, `pubspec.yaml`, `build.gradle`, etc.) automatically during integration, and without the key everything is root-relative (existing behavior kept 100%). Non-interactive: `--paths "flutter=app,react=client"` (`-Paths` for `.ps1`). `version_manager.sh` follows these paths to sync subfolder version files, so the `PROJECT-COMMON-VERSION-CONTROL` workflow covers monorepos without modification.

---

## Folder structure

```
projectops/
├── .github/
│   ├── workflows/
│   │   ├── PROJECT-TEMPLATE-INITIALIZER.yaml
│   │   ├── PROJECT-COMMON-*.yaml
│   │   └── project-types/
│   │       ├── common/          # Shared originals (+ secret-backup/ opt-in, deploy/vercel/ deploy target)
│   │       ├── flutter/         # Flutter only (store deploy workflows at the root)
│   │       ├── spring/          # Spring only (server-deploy/ + publish/{nexus,github-packages}/)
│   │       ├── python/          # Python only (CI at the root + server-deploy/)
│   │       ├── react/           # Shared by React/Next.js (the next type was absorbed in v4.1.0)
│   │       └── node/            # Node only (publish/npm/)
│   ├── scripts/
│   │   ├── version_manager.sh    # + version_manager.py (holds the logic, #448)
│   │   ├── changelog_manager.py
│   │   ├── truncate_release_notes.sh  # + .py (holds the logic, #448)
│   │   └── template_initializer.sh
│   ├── util/
│   │   ├── flutter/
│   │   │   ├── playstore-wizard/
│   │   │   ├── testflight-wizard/
│   │   │   ├── firebase-wizard/
│   │   │   └── oauth-wizard/          # Kakao and Google sign-in (#156)
│   │   └── common/
│   │       ├── projects-sync-wizard/
│   │       ├── github-projects-sync-worker/
│   │       └── github-secrets-converter/
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
├── .claude-plugin/              # Plugin manifest
├── skills/                      # Plugin skills (marketplace only)
├── scripts/                     # Plugin scripts (marketplace only)
├── .cursor/skills/
├── docs/                        # Detailed docs
├── version.yml
└── CHANGELOG.md / CHANGELOG.json
```

---

## Rules for all work

### ⚠️ Windows verification must cover cp949 and non-ASCII paths (agent must read)

**Passing with English paths and UTF-8 mode is not Windows verification.** A typical user environment has cp949 as the system code page and Korean characters and spaces in folder names.

| Trap | Symptom | How to avoid it |
|---|---|---|
| `fs.cpSync` + non-ASCII path (Node 22+) | Process exits without a message, temp folder left behind | `fsutil.copyPathSync`. Rule `no-fs-cpsync` |
| Using only `subprocess.run(text=True)` | `stdout` is `None` on Korean output, crash on the next line | git: `encoding="utf-8", errors="replace"`, otherwise `errors="replace"`. Rule `no-subprocess-text-without-errors` |
| `&&` in commands shown for Windows | PowerShell 5.1 parse error | Join with `;` |

- **On a development PC with `PYTHONUTF8=1` set, every defect above is hidden.** Reproduce with `unset PYTHONUTF8 PYTHONIOENCODING` when checking.
- The same goes for global git `core.longpaths`. Run with an empty `HOME`, like a new user.
- The smoke test (`matrix-smoke`) runs on 3 OSes with Node 20 and 24, including installation into a non-ASCII path with spaces.

### ⚠️ Keep only the 5 watch tests (agent must read)

The tests AI piled up task after task (about 250 files, 30k lines) were removed, and **only watch checks that confirm promises scattered across several files still agree** were kept.
They catch only what people miss by eye, and they are small and fast.

| File | What it guards |
|---|---|
| `test/rename-consistency.test.js` | Skill count and list are the same across folders ↔ manifests ↔ README and CLAUDE.md |
| `test/options-schema.test.js` | CLI flags and `version.yml` options match the canonical source (`src/core/options-schema.js`) |
| `scripts/tests/test_skill_docs.py` | Skill descriptions are short (300 characters) and in English |
| `scripts/tests/test_korean_line_budget.py` | Korean lines on English surfaces do not grow (section below) |
| `.github/scripts/test/test_workflow_permissions.py` | Every workflow declares `permissions:` |

- **Do not commit new test files.** Verify implementations with throwaway tests in a scratch folder or by running things directly, then delete them.
- Add another watch check only after discussing it with the user, and only when there was "a real incident where people missed promises across several files drifting apart".
- `PROJECT-TEMPLATE-CI`: on develop, one ubuntu runner runs the 5 above + wizard consistency (`check-consistency.py`) + CLI smoke; on main, CLI smoke runs on 3 OSes (macOS bash 3.2 and Windows `.cmd` differences, #415 · #418).

---

## Skills (Claude Code plugin)

**Plugin name**: `projectops`

```bash
claude plugin marketplace add Cassiiopeia/projectops
claude plugin install projectops@projectops-marketplace --scope user
```

> Design, planning and implementation are handled by `superpowers` (brainstorming → writing-plans → executing-plans), not by this plugin. The table below (core 18 + extras 6) has no analysis, planning or implementation skills.

| Command | Purpose |
|--------|------|
| `review` | Code review |
| `testcase` | QA test cases |
| `init-worktree` | Create a git worktree |
| `commit` | Issue-based commit automation |
| `github` | All GitHub work: create/read/edit issues, comments, labels, assignees, create/merge/read PRs, repo exploration, Actions logs, secret management, **image attachments** (issue body, comments, PRs) |
| `report` | Generate an implementation report |
| `changelog-deploy` | develop push → release PR (deploy PR) to main → version finalization + automerge / re-trigger when automerge fails |
| `synology-expose` | Guide for exposing Synology services externally (**optional extras plugin** `projectops-extras` — `plugins/projectops-extras/`, copies of shared docs are synced with `scripts/sync_extras.py`) |
| `code-consult` | **Managing AI-written code** (moved from extras to core in #1107) — audit against coding conventions, refactor one item at a time (before/after run comparison), check diffs (stale comments, duplicates), frozen violation lists (`docs/architecture/rules/`, lines can only be removed). The CLI `arch_cli.py` uses only the standard library and does not use `scripts/common` (#867) |
| `skill-bug` | **Report projectops skill bugs** (**extras**) — called from a session in any repo when a bug is suspected; it collects commands, results, flow, logs and screenshots from the session transcript, strips personal data, files an issue on `Cassiiopeia/projectops` without asking (or comments on an existing one), then returns to the task. It does not judge or fix (CLI `bug_cli.py`). In Claude Code, the extras hook (`plugins/projectops-extras/hooks/skill_bug_watch.py`, canonical rules in `skill_bug_rules.py`) catches, for every pro- CLI, workarounds after a failure (per-skill workaround table), a feature the tool says it lacks, the same usage error twice, the same failure three times and internal CLI exceptions, and has a background subagent report them automatically (3 per session, turn off with `skill-bug.auto_report: false`); `skill_bug_notice.ts` shows a toast (#997). The automatic report body is filled with the facts `bug_cli.py alarm`, `excerpt --tool-use-id` and `context` collect (raw response, surrounding flow, environment), so an agent given only the issue can reproduce and fix it (#1000) |
| `remote-link` | **One link to open a desktop agent app from outside** (**extras**, macOS, Windows, Linux; renamed from `pro-orca-tunnel` in #1218) — answers "give me the Orca / Paseo link" with a single link. `remote_link_cli.py` (standard library) has one adapter per app under `scripts/remote_apps/` (`CONNECTION` tunnel or relay) and an `apps` command for what is running and reachable. Orca (tunnel): reuses, opens fresh and cleans up cloudflared quick tunnels and replaces the tunnel address inside the saved pairing link without knowing its format. Paseo (relay): runs the Paseo CLI from the home folder (`daemon pair --json`) for a fresh `app.paseo.sh/#offer=` link, returns `relay_off` instead of enabling the relay silently, warns when no daemon password is set, never restarts the daemon. App facts live in `harness/<app>.md`; the local copy `~/.projectops/remote-link/harness/<app>.md` takes priority. New app = one harness + one adapter (#1126, #1218) |
| `disk-cleanup` | **Disk space cleanup** (**extras**, macOS, Windows, Linux, stack-agnostic — a table of known locations + `largest`, which finds big folders under home by size) — read-only `scan` first, split into safe, decide and keep tiers; only safe is cleaned after one confirmation, and decide (open-issue worktrees, DerivedData, Gradle cache, emulators) only when the user names it. Worktree removal: confirm closed on GitHub > refuse if in use or recently active > back up (patches, including ignored .env) > `git worktree remove`, keeping the branch. Every deletion goes through the `disk_cli.py` gate, and without `--yes` it only plans (#1091) |
| `project-blueprint` | **The owner's project house standard** (**extras**, docs only, no CLI) — repo layout (stack folders, `brand/`, `docs/`, root `CLAUDE.md` index), issue > develop > main > deploy branches (promote by merged PR because main's `[skip ci]` version tip skips push-triggered deploys), public-repo secrets (workflow secrets one value each, runtime secrets one whole file per platform, server copy, NAS backup), NAS Docker deploy (Traefik Blue-Green, sha tags, rollback). Reusable infra values live in the `project-blueprint` config section; the skill holds placeholders only (#1249) |
| `brain` | **Knowledge notes for a team brain** (**extras**) — keeps the decision, the reason and cautions for the next person as notes in the repo's knowledge folder, committed with the work; trivial work is skipped with one line. Capture modes in the repo switch `version.yml` `metadata.template.options.knowledge.capture`: `issue-end` (after `pro-report`, default), `session-end` and `merge` (change-set notes keyed by commit range, branch and PR, grouped by topic), `manual`. First run (`setup`) asks at most three questions with recommended answers: the mode (recommended from repo history), consent to add a marked rule block (`pro-brain:begin/end`) to the project CLAUDE.md telling agents when to capture (and, only with a team brain, to search it first; a no is stored as `claude_md: declined`), and how the repo's knowledge is used (repo only default, own local GBrain, own remote GBrain, team brain server, install guide; personal + team can combine; re-running shows the current state). Only the team brain is shared, as non-secret `team_brain: { mcp_name, mcp_url, contact }` in the switch (or `"none"`); a personal GBrain is detected per machine and the registry `mcp_server_name` is only a setup hint. A gitignored CLAUDE.md gets a tracked `.claude/rules/pro-brain.md` instead (Claude Code loads it at launch) or the pro-init-worktree copy set. `brain_cli.py` (standard library) has `status`, `collect` (flat frontmatter: commit range, merge commit, modules, line totals, contract names: API endpoints, migrations, config keys, env or secret names, feature flags; plus suggested id, topics and related notes), `setup` (plan, `--apply --yes` writes), `connect` (own local GBrain: plan, then `--apply --yes` adds one source `<project>-knowledge` and syncs with `--no-pull`; refuses a taken id or an already-read folder, never `--force`, never hooks, mounts, other sources or MCP settings; a remote brain gets host commands) and `gaps` (merged work with no note, git only, for brain sync scripts). `connect --team` (team brain: reads `team_brain` + the member's token from the credential store, then after a yes registers one user-scope MCP entry with `claude mcp add`, `--rotate` after a new token, optional `.mcp.json` with `${GBRAIN_<PROJECT>_TOKEN}`; the URL is probed when saved, so a mistyped brain key shows as `unknown_brain`), `install` (guided GBrain install and init: one question, exact commands, prerequisites, verification; never runs them). A repo's own vault rules win. A team brain token lives only in the user's credential store (`config-rules.md` §9), never in the repo, notes, `version.yml` or output (#1259, #1261, #1263, #1265) |
| `ssh` | Connect to remote servers over SSH and run commands (AWS EC2, Synology NAS, Linux servers, etc.) |
| `skill-creator` | Create/review/improve skills (CREATE, REVIEW, IMPROVE modes) |
| `agent-test` | **Actually runs and walks through the app, web or server** (E2E, evidence) — unlike `testcase`, which only writes documents |
| `figma` | **Design → code → comparison** in one bundle. Counts the dumped items as a worklist and compares pixels after porting (#619 merged porting and comparison into `figma-verify`, and #854 renamed it back to `figma`) |
| `launch` | **Capability skill** — launches, drives and captures apps, web and servers. Other skills call `launch_cli.py` as a script (#629) |
| `desktop-control` | **Driving programs on this computer's screen** (installer wizards, OS dialogs and desktop apps rather than web pages or emulators). Reads elements, presses without moving the mouse, asks before installing, and hands security confirmation windows to the user. A procedure skill on top of `launch`'s `desktop` command group, so it has no CLI of its own. Windows only for now (macOS is #985) |
| `ui-design` | **Show mockups on a local URL to compare and pick** (#1080) — reflects repo tokens and fonts, compares animations, multi-screen linked prototypes, shares PNG/GIF to issues, and falls back to a designer request (#634). The agent judges and builds the mockups; `ui_design_cli.py` only runs the server, collects facts and captures. Settings in the `ui-design` section + options table (`pro_ui_design/options.py`), project knowledge in the repo-scoped harness `ui-design`, skill handoff through `decision.json` |
| `image` | **Generate image assets in the project's style** (#1102) — the agent turns requests into a brief and an English prompt using the repo harness (`docs/image-harness/`: STYLE, characters, per-kind guides, references, records), and the image tool is chosen by priority (default codex subscription > antigravity > claude-vector SVG; add more with `image.priority` and `image.providers`). `image_cli.py` only runs tools, collects results, converts to PNG, removes backgrounds (fake checkerboards, key colors), fits sizes, builds comparison boards and records; standard library only (uses Pillow if present). Codex is allowed only with a ChatGPT subscription login (API key environment variables are removed) |
| `presentation` | **Build a presentation deck as HTML and rehearse it aloud** (#1097) — a deck folder (slide.html, script.md, notes.md, takes.md per slide, no build), a per-slide speaking coaching harness (`references/coaching.md`; user directions in the deck's `memory.md` + `~/.projectops/presentation/memory.md`), an auto-reloading rehearsal screen, per-slide timing comparison from recording captions, PDF and text PPT export with review. The agent does coaching and section judgment; `presentation_cli.py` only does the server, import, captions, checks and export |
| `oss-consult` | **Open-source consulting** — determines the repo's nature, scores it strictly on 6 axes (first impression, proof of value, community, code extensibility, legal safety, long-term operation), points out the maturity stage and prerequisites, and fixes what is approved. Single repo or all at once (#644) |

---

## Skill routing

Skill call rules available in this project:

| Request type | Skill to call |
|----------|----------|
| **Make an issue, register an issue, bug report, create a PR, open a PR, merge a PR, issue comment, add/edit/delete a comment, check an issue, close an issue, add/remove labels, add an assignee, look up a PR, GitHub API** | **`pro-github` ← top-priority trigger** |
| Something does not work, bug, outage, finding the cause | `superpowers:systematic-debugging` |
| Code review | `pro-review` |
| QA test cases | `pro-testcase` |
| Writing / creating an issue | `pro-github` (absorbs the issue creation workflow) |
| Commit | `pro-commit` |
| Deploy / re-trigger after automerge failure | `pro-changelog-deploy` |
| Report | `pro-report` |
| Knowledge note for the team brain, save this decision to the brain, which merged work has no note | `pro-brain` (extras) |
| SSH into a remote server, check logs/status | `pro-ssh` |
| **Test it for real, check in the emulator/simulator/browser, E2E, walk it to the end** | `pro-agent-test` |
| **Launch the emulator and capture, simulator screenshot, browser capture, capture at mobile width / empty list / 500 screen** | `pro-launch` |
| **Show me some mockups, compare animation mockups, let me click through this flow, post the mockups to the issue, request a design, make something to send to the designer, ask them to draw the empty and error screens too** | `pro-ui-design` |
| **Look at the whole thing, the code seems messy, clean up AI-written code, refactor, check comments and names before committing, install my coding conventions** | `pro-code-consult` |
| **Make an image, draw a picture, make a background/character/icon, which art style fits** | `pro-image` |
| **Let's rehearse the talk, make presentation slides, review my script, I uploaded a recording, export to PPT** | `pro-presentation` |
| **Open-source audit, repo consulting, to get on trending, make it more open-source-like, audit all my repos, are the README, labels and license OK?** | `pro-oss-consult` |
| **Implement a Figma design, build it to the mockup, check it matches the mockup, did it come out as designed, are any shadows missing** | `pro-figma` |
| **Design and planning (what and why)** | **`superpowers:brainstorming`** |
| **Implementation plan (how)** | **`superpowers:writing-plans`** |
| **Executing the plan** | **`superpowers:executing-plans`** |

> The design, planning and implementation flow is handled by the three superpowers skills above. (The three old analysis, planning and implementation skills were deleted in #849 and moved to superpowers.)

## Required commit conventions

**Never put emoji or tags (`🚀[기능개선]`, `⚙️[기능추가]`, etc.) at the start of a commit message.**
Use only the plain content of the issue title with the emoji and tags removed.

- Correct: `Protect the RELEASE-CHANGELOG PR body from being reset : feat : ... https://...`
- Wrong: `🚀[기능개선][ChangeLog] RELEASE-CHANGELOG : feat : ...` (legacy Korean issue-title tags must be stripped)

Commits are made by `pro-commit`. `pro-report` never runs a commit itself (forbidden in its SKILL.md) — skills that suggest commit messages follow this rule too.

### The commit type decides the release version (#546 — agent must read)

In repos with `semver_auto` on (including this one), **the bump size is decided by the commit subjects in the release range.**
Picking any commit type at random ships the wrong version.

| Commit type | Release result |
|---|---|
| `title : feat! : content` (or `feat!:`) | **major** — 4.2.45 → 5.0.0 |
| `title : feat : content` | **minor** — 4.2.45 → 4.3.0 |
| `fix` / `docs` / `chore` / `refactor` / `test` | patch — 4.2.45 → 4.2.46 |

- **Add `!` only when compatibility breaks** — changes after which existing users' settings, API or CLI arguments
  no longer work. If you are not sure, do not add it; ask the user.
- When mixed in one release range, the highest wins (major > minor > patch).
- Commits containing `[skip ci]` and commits starting with `Merge` are excluded from the decision.
- Decision logic: `classify_bump_level()` in `.github/scripts/changelog_manager.py`.

## Feature implementation workflow

Order for implementing a new feature:

1. `superpowers:brainstorming` — design and settle the spec
2. `superpowers:writing-plans` — detailed implementation plan
3. `superpowers:executing-plans` — the actual implementation
4. `superpowers:requesting-code-review` — request a code review

<!-- pro-brain:begin (managed by /pro-brain; settings live in version.yml) -->
## Project knowledge (pro-brain)

Durable project knowledge (decisions, reasons, cautions) is kept as notes in `knowledge/`.

- **When to capture**: after `/pro-report` posts the issue report and before the issue is closed, run `/pro-brain` (one note per issue).
- **Before answering why or what-did-we-decide questions**: read `knowledge/` first (search it by topic, file or issue number).
- Skip trivial changes with a one-line reason. Never put secrets, personal data or chat content in a note.
- Settings: `version.yml` > `metadata.template.options.knowledge`.
<!-- pro-brain:end -->
