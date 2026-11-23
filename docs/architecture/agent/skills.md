# Skill development rules

> **When to read:** when you touch `skills/`, `scripts/common/` or `plugins/`, or add a skill CLI subcommand, config or output path
> Canonical text split out of `CLAUDE.md`. `CLAUDE.md` keeps only a summary and a link to this document.

### ⚠️ Test code never ships to users (#591)

`skills/` is the install source for Cursor and GitHub Copilot, so **it is copied whole into `~/.cursor/skills/` and `~/.copilot/skills/`** (#200).
The `scripts/` (common, etc.) that skill CLIs import are copied alongside into `~/.cursor/scripts/` and `~/.copilot/scripts/` — without them the CLI dies on import.
So unless `skills/*/tests/`, `scripts/tests/` and `conftest.py` are filtered out, our tests pile up on other people's computers.
`SKIP_IN_COPY` and `TEST_PATH` in `src/core/ide/skills-copy.js`, shared by both adapters, block them.
Maintainer-only files at the top of `scripts/` (`README.md`, `build_troubleshooting.py`, `sync_extras.py`) are dropped by `SHARED_SCRIPTS_DEV_ONLY` (#988).
**When you add or rename a skill, update `SKILL_CLIS` and `RESOLVER_REVISION` (+1) in `scripts/projectops_cli.py` together (#1080 real incident: the number was not bumped, so existing users' fixed entry point rejected the new skill as `bad_args`).**
**When you add a new maintainer-only file at the top of `scripts/`, add it to this list.** Adding an item the runtime uses makes the installed CLI die on import.
**When you add a new helper file to a skill, ask yourself "does a person using this skill need it?"**

## Skill development guide

### Folder structure
```
skills/
├── {skill-name}/SKILL.md
├── config.json.example       # Full config structure example (includes every skill_id section)
└── references/
    ├── common-rules.md       # Absolute rules only (confirmation gate, issue status, push, sensitive data). Details live in per-topic docs (#1133)
    ├── script-invocation.md  # Canonical fixed entry point + fallback lookup block (do not copy the block into SKILL.md, #1133)
    ├── personas.md           # 5 expert personas + 6 mindsets (harness/PERSONA.md single source) — no skill loads it (harness copy)
    ├── approval-and-questions.md # Approval gate + pre-start key questions standard for the 8 output-producing skills (#526)
    ├── config-rules.md       # Config path, schema and read/write standard
    ├── mcp-subcommand-rules.md # MCP-style design standard for skill CLI (<scope>_cli.py) subcommands (JSON + next, code template)
    ├── doc-output-path.md
    ├── project-detection.md
    ├── code-style-detection.md
    ├── tech-flutter.md
    ├── tech-react.md
    └── tech-spring.md
```

### Core principles

1. **The agent handles config directly with the Read/Write tools** — do not call a `config-get` CLI
2. **Config path and schema: see `references/config-rules.md`** — do not describe them inside a skill
3. **Call the GitHub API through each skill's `<scope>_cli.py` subcommands** (via `scripts/common/gh_client`) — no `gh` CLI
4. **OS compatibility**: run Python with the `PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)` pattern
5. **Must read at skill start**: `references/common-rules.md`. Every other shared doc is linked **directly** from the `## Shared references` table in each SKILL.md, together with "when to read" (references are one level deep from SKILL.md, #1133)
5.5. **If the skill produces an output (md)**, follow `references/approval-and-questions.md` — key questions before starting, an approval gate before saving, a one-time automation offer on first run. Get the save path from each skill CLI's `get-output-path`; never assemble it yourself (#525 · #526)
6. **Python behavior logic lives in reusable script files + the MCP-style standard** — follow the "Python behavior script standard" section below. No long inline Python heredocs in SKILL.md.

### Python behavior script standard (required)

When a skill calls an external system (GitHub API, SSH, etc.) from Python, it must follow this pattern.
This standard has been verified in practice not to break on either Windows Git Bash or macOS.

> **Before adding a new subcommand to a skill CLI (`skills/pro-*/scripts/<scope>_cli.py`), read `skills/references/mcp-subcommand-rules.md` first.** It is the concrete implementation reference, with a code template and checklist for the input contract, JSON schema (`ok`/`verdict`/`summary`/`next`), separation of gh_client and command layers, and test patterns. Model examples: the `actions` and `deploy-status` subcommands.

> **The output options (`--brief`, `--field`, `--fields`) are implemented in three places — if you change the behavior, change all three together.** The single source of the rules is `skills/references/output-schemas.md`.
> `_extract_output_options` in `scripts/common/cli_parser.py` (shared `run_cli`) · `_pop_output_options` in `skills/pro-launch/scripts/pro_launch/cli.py` (its own runtime) · `_extract_output_options` in `skills/pro-image/scripts/image_cli.py` (standalone CLI that does not use shared code — preserves Korean paths on Windows non-UTF-8 consoles, #1102).
> Why they are not merged: each is about 40 lines with a different runtime, so a generated-copy scheme would cost more (7th review decision, 2026-11-14). `--fields` returns JSON even for a single path (#1187), and `--brief` keeps the read-result keys (#1188).

#### 1. Logic lives in reusable script files

- **Thin entry file, subcommands in a package, 450 lines per file.** The entry `<scope>_cli.py` holds only the parser and registration; subcommand implementations live in the sibling package (model: `skills/pro-launch/scripts/pro_launch/`).
- Store behavior logic as fixed files in `skills/{skill-name}/scripts/{name}.py`.
- SKILL.md describes **only how to call it** (subcommands, arguments, environment variables). Do not inline long Python code in SKILL.md.
- Why: SKILL.md is a document the LLM re-types every time. Inlining core logic like the redirect strip risks omissions and typos on re-entry.

#### 2. MCP-style subcommands — the agent interprets input, the .py executes

- The .py has a **clear input contract** through `argparse` subcommands (e.g. `show-run RUN_ID`, `joblog JOB_ID`, `resolve-pr PR_NUM`).
- The .py does **no interpretation** such as URL parsing or PR→run tracing. The agent interprets user input (URL/PR/branch/empty) and passes the exact subcommand and arguments.
- State the routing rules "this input → this subcommand" in SKILL.md so the agent decides correctly.
- Effect: the .py can run and be tested on its own (predictable, like an MCP tool), and the agent interprets input flexibly.

#### 3. Pass arguments through environment variables — no heredoc, /tmp or stdin pipe

- Pass sensitive values (PAT, etc.) and arguments through **environment variables**. Heredoc body interpolation, `/tmp` temp files and `curl | python` stdin pipes are all forbidden.
- Why (measured):
  - `/tmp` paths → break on Windows Git Bash.
  - `curl | python3` → exit code 49 on Windows.
  - heredoc `{variable}` interpolation → escaping of Korean and special characters breaks.

```bash
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
GH_PAT="..." GH_OWNER="..." GH_REPO="..." \
  PYTHONIOENCODING=utf-8 "$PYTHON" "$PROJECT_ROOT/skills/{skill}/scripts/{name}.py" show-run 12345
```

#### 4. Output is always JSON — with a `next` hint field inside

- Every subcommand **always prints JSON** to stdout (no plain-text mode, and no `--json` option either).
- The JSON holds `ok` (success), the data fields, and **`next`** (a hint for the next subcommand the agent should call).
- The agent parses a single JSON format → decides the next action precisely.

```json
{"ok": true, "run_id": 12345, "conclusion": "failure",
 "failed_jobs": [{"job_id": 678, "name": "build", "failed_steps": ["Flutter build"]}],
 "next": "joblog 678"}
```

#### 5. Standard library first — the real goal is working on both mac and Windows + closed networks

- "Zero dependencies" is not the goal. **The real goal is to never break on mac or Windows, and to run on internal (closed) networks where `pip install` is impossible.**
- So solve things with the standard library (`urllib.request`/`json`/`argparse`) when possible — it works right away on both OSes and on closed networks without extra installs.
- When the standard library cannot do the job, **of course use an external package**. But try installing it inside the script (`pip install ... -q`) and show manual install instructions on failure, so closed networks are handled gracefully. (Example: PyNaCl for secret encryption)

#### 6. Strip the Authorization header on redirect (required for security and correctness)

- Some endpoints, such as GitHub job logs, 302-redirect to Azure Blob (SAS URL).
- By default urllib forwards the `Authorization` header to the redirect target → Azure returns `403 AuthenticationFailed`.
- Always install a handler that removes the `Authorization` header on redirect:

```python
class StripAuthRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            new.headers.pop("Authorization", None)
            new.unredirected_hdrs.pop("Authorization", None)
        return new
opener = urllib.request.build_opener(StripAuthRedirect)
```

### Config structure

The config of every skill is managed in **one single file**, `~/.projectops/config/config.json`.
Each skill's settings are namespaced under its skill_id as the key.

| Skill | Config section key | Note |
|------|--------------|------|
| `commit`, `github`, `changelog-deploy`, `report` | `github` | Share PAT + repos (includes the `issue.*` keys for issue-creation approval and assignee settings) |
| `synology-expose` | `synology-expose` | NAS instance info |
| `ssh` | `ssh` | SSH server connection info |
| `presentation` | `presentation` | New-deck defaults (language, time limit, deck location, export format) + projects[] |
| any skill with a secret | `launch.credentials` (the credential store) | Secrets only here, referenced by name from the skill section, read through `scripts/common/credentials.py` (`config-rules.md` §9) |

### How to add config for a new skill

1. Add a section to `config.json` keyed by the `skill_id` (skill folder name)
2. Document the schema in `skills/references/config-rules.md` §7
3. Add an example to `skills/config.json.example`
4. Reference `references/config-rules.md §2~3` explicitly in SKILL.md

**Do not create a separate config file (`skill-name.config.json`, etc.).**

### Per-skill CLI commands (3-layer architecture)

Each skill has its own `scripts/<scope>_cli.py`. CLIs with many subcommands are split into **an entry file + a package in the same folder** — the entry file holds only the parser and registration, and subcommand implementations live in the package (`pro_github/`, `pro_agent_test/`, `pro_ui_design/`, `figma_tools/`, `oss_consult/`, `pro_launch/`; for worktrees, `scripts/git_worktree/`). Call pattern = fixed entry point `~/.projectops/bin/projectops_cli.py <skill>` + a fallback block when it is missing (`skills/references/script-invocation.md`, #1133).

| skill | CLI file | Main subcommands |
|---|---|---|
| github | `skills/pro-github/scripts/github_cli.py` | create-issue, get-issue, get-issues, list-issues, update-issue, close-issue, reopen-issue, search-issues, add-comment, list-comments, edit-comment, delete-comment, list-labels, add-labels, remove-label, set-labels, add-assignees, remove-assignees, create-pr, list-prs, update-pr, get-pr, add-pr-comment, close-pr, reopen-pr, merge-pr, normalize-title, create-branch-name, get-commit-template, explore, create-repo, update-repo, delete-repo, secrets, actions, upload-image, delete-image, get-output-path |
| commit | `skills/pro-commit/scripts/commit_cli.py` | get-issue-number, get-issue, normalize-title, sanitize-message, get-commit-template, resolve-style |
| report | `skills/pro-report/scripts/report_cli.py` | get-output-path, add-comment |
| review | `skills/pro-review/scripts/review_cli.py` | get-output-path |
| changelog-deploy | `skills/pro-changelog-deploy/scripts/changelog_cli.py` | actions, deploy-status, list-prs, update-pr, create-pr, detect-release-context (`release_language`: the notes language is `version.yml` `language` — same rule as the workflow, store languages, fixed text — #977) |
| testcase | `skills/pro-testcase/scripts/testcase_cli.py` | get-output-path (#525 · #623) |
| init-worktree | `skills/pro-init-worktree/scripts/worktree_cli.py` | recall, record (remembers the set of local files copied last time — #839) |
| figma | `skills/pro-figma/scripts/figma_cli.py` | get-output-path, coverage, assets, conform, diff, screens, fetch, ingest, check-fresh, token (link type detection and screen list · direct REST fetch with the saved token (no MCP needed, past versions via `--version`) · diff excludes mock-data areas with `--mask-data`/`--mask-node`, `--solids` (color fills present on one side only), `--rows` (text line height), conform position checks with automatic system-node exclusion, svg-check (SVG elements the renderer drops) · save MCP result files · check for design changes · register a Figma token — the token uses the `provider: figma` entry in `launch.credentials`, #1017), store-specs, store-check (canonical store image specs `figma_tools/store_specs.json` · per-language verdicts, #884), store-compose (app capture + copy > per-language store image HTML and render script, outputs only under run_dir/store from `get-output-path`, #1021), store-upload-plan, store-upload-mark, store-upload-status (console upload checklist · per-step record, the upload itself via pro-launch web, never submit for review, #1021), store-pages (per-language landing pages + hreflang + sitemap, run_dir/store/site, #1021) |
| agent-test | `skills/pro-agent-test/scripts/e2e_cli.py` | detect, scenario, note, api, other (run and capture commands are handed to pro-launch — #631) |
| launch | `skills/pro-launch/scripts/launch_cli.py` | doctor, detect, devices, device, app, web, desktop (windows on the PC screen, #985), render, http, access, db, logs, cred (incl. `check`, `migrate-github-pat`, `--secret-field`, #1266), ssh, local (sudo on this Mac, #784), shrink, mask, redact (cover images and mask text before upload, #1082), recall, learn, forget, kb (official troubleshooting search, show, list, propose, #889), journal, harness (per-site/per-task guide folders: list, show, match, new — shown automatically in responses for matching URLs, hosts, app identifiers and window names, #1023 · #1024), get-output-path |
| desktop-control | (no CLI of its own) `skills/pro-launch/scripts/launch_cli.py` | Uses the `desktop` group as is: doctor, setup, session, windows, tree, find, click, type, press, focus, wait, shot |
| ui-design | `skills/pro-ui-design/scripts/ui_design_cli.py` | start, status, stop, choices, tokens, check, capture, decide, decision (#1080), config (show, set, options), get-output-path, board, copy-lint, ascii, rewrite-images (replaces body image paths with upload results — #974) |
| code-consult | `skills/pro-code-consult/scripts/arch_cli.py` | detect, scan, assets, deps, cochange (files that change together, hidden coupling, #1109), copies (full survey of name, value and file copies, `--out` outside the repo only), diff, rule-docs, ledger (check, freeze, tighten), conventions (install, check), install-tests, get-output-path |
| image | `skills/pro-image/scripts/image_cli.py` | providers, harness, kind, run, check, remove-bg, fit, render-svg, board, record, history (#1102) |
| presentation | `skills/pro-presentation/scripts/presentation_cli.py` | start, status, stop, import, recording add, check, export (--pdf · --pptx, with review), get-output-path (#1097) |
| oss-consult | `skills/pro-oss-consult/scripts/oss_cli.py` | collect, local-facts, list-repos, get-output-path (**collects facts only — the agent judges**, #644), repo-update, label (the only path that changes a repo — `--dry-run` and a `before` record, **deletion and visibility changes are not implemented**, #660) |

Shared domain logic lives in `scripts/common/` (gh_client, config, credentials, paths, title, issue_number, gh_branch, manifest, emit, bootstrap).

> **⚠️ Never hard-code output paths in SKILL.md (#623 — agent must read).** The output root
> can be changed in settings (`output.root`). Assembling `docs/projectops/<skill>/...` directly **goes silently wrong**
> in teams that moved the root — in practice `testcase` wrote to the wrong place, and the reading skill searched an empty folder
> and concluded "no output". Always get output paths from the CLI's `get-output-path`.
> In docs, write the actual call line rather than a prose mention, and check that the subcommand really exists in the CLI.
>
> **Evidence (screenshots, dumps, renders) and documents (reports, plans) are different (#621).** Which one a skill produces
> is known solely by `EVIDENCE_SKILLS`/`DOCUMENT_SKILLS` in `common/paths.py`, and for an evidence skill
> `resolve_output_path` plants a `.gitignore` in the folder automatically (the root `.gitignore` is not touched).
> **Every new output skill must be added to one of the two sets** — otherwise the test blocks it.

> **⚠️ Do not line up several optional positional arguments (#622 — agent must read).** argparse fills values
> **from the left**, so if each subcommand's value (`run_id`/`job_id`/`pr_number`/`branch`) gets its own slot,
> **everything lands in the first slot**. `actions` in `github_cli.py` did this, and `joblog`, `resolve-pr` and `resolve-branch`
> **broke even when called exactly as documented** (only `show-run` and `list-failed` happened to work, so it went unnoticed for a long time). Keep **one**
> positional argument and let the subcommand interpret it (`changelog_cli.py` works that way from the start).

> Call the GitHub API through each skill's `<scope>_cli.py` subcommands first. If you need a new behavior, add a `common/gh_client` helper + a CLI subcommand + a test following `skills/references/mcp-subcommand-rules.md`. If a new skill needs a .py, copy the `skills/pro-skill-creator/templates/python_cli_script.py` skeleton.

### Evidence attachments in issue and completion comments (#1082)

Attach images, captures, E2E results and logs **without asking, and always look at them yourself before uploading.** The canonical rules are in `skills/references/evidence-attach.md`. The canonical masking rules are in `scripts/common/redact.py`, and the extras copy is generated by `scripts/sync_extras.py`.

### Agent notes

| Situation | Handling |
|------|------|
| No config | Collect interactively — no forced guessing |
| Repo owner/repo unclear | Extract with `git remote get-url origin` → on failure use config `github_repos` |
| GitHub API 401 | Tell the user the PAT expired + guide them to re-register via `/pro-github` (`references/config-rules.md §2~5`) |
| Attempting to use the `gh` CLI | Forbidden — use curl instead |
| Editing a shared workflow | Keep `project-types/common/` and the `.github/workflows/` root **identical in both places** |
| Markdown table in a GitHub comment | Use the `array.join('\n')` pattern (template literal indentation breaks the table) |

## Known skill behavior problems and fixes

### 1. `pro-github` skill fails to trigger automatically

**Problem**: even when the user asks "open a PR" or "leave a comment", the `pro-github` skill is not triggered automatically and another skill (brainstorming, etc.) runs first.

**Cause**: the `superpowers:using-superpowers` rule forces calling any skill with even a 1% chance first, and general skills like `brainstorming` have broader descriptions, so they match first. Even with trigger keywords ("make a PR", "leave a comment") in the `pro-github` description, it is handled at a lower priority than other skills.

**Fix (user side)**:
- Type the `/pro-github` slash command explicitly for GitHub work
- Or prefix the message with "github:" ("github: open a PR")

**Fix (skill development side)**:
- Add more specific trigger keywords to the description in `skills/pro-github/SKILL.md`
- Or register `pro-github` in the Skill routing table with a clearer pattern
- State in CLAUDE.md the principle that PR creation, issue comments and GitHub API work **always call `/pro-github` explicitly**

### 2. `pro-github` fails to detect the repo automatically (worktree environment)

**Problem**: the skill detects the repo of the current directory with `git remote get-url origin`, but when Claude Code runs in the **projectops** repo context it picks `Cassiiopeia/projectops` as origin instead of `TEAM-ROMROM/RomRom-BE`.

**Cause**: happens when the target repo (RomRom-BE) is in a separate worktree, or the current Claude Code session's primary working directory is another repo.

**Fix**:
- Name the target repo when calling the skill: `/pro-github TEAM-ROMROM/RomRom-BE create a PR for issue #653`
- Repos registered in the config `repos` list can be named directly: "open a PR for RomRom-BE"

### 3. Python `urllib` error on Windows (exit code 49)

**Problem**: the `curl ... | python3 -c "..."` pipeline fails with `Exit code 49`. Even with Python installed correctly, the bash pipe fails to resolve the python3 path.

**Cause**: on Windows Git Bash, the `python3` command points to the Windows Store python stub, or pipe stdin is handled differently.

**Fix (skill improvement needed)**:
- On Windows, parse GitHub API JSON with **PowerShell `Invoke-RestMethod`** instead of `curl | python3 -c`
- Or save the curl response to a file and parse it: `curl ... -o /tmp/out.json && python3 /tmp/out.json`
- Add a Windows PowerShell code block to `skills/pro-github/SKILL.md`

**Workaround**: Claude uses the PowerShell tool directly and calls the GitHub API with `Invoke-RestMethod`

### 4. PR head branch name 422 error (Korean branch names)

**Problem**: when the branch name contains Korean (`20260420_#653_FCM_푸시_페이로드에_라우팅용_데이터_포함_필요`), creating a PR through the GitHub API fails with `422 Validation Failed: head invalid`.

**Cause**: PowerShell `ConvertTo-Json` fails to encode strings containing Korean correctly, or the GitHub API treats URL-encoded branch names differently.

**Fix**:
- Before creating the PR, check that the remote branch really exists: `git ls-remote origin "<branch>"`
- Call the API only after confirming the branch has been pushed
- Use the `owner:branch` form for `head`: `"TEAM-ROMROM:<branch>"`
