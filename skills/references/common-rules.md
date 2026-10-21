# Common rules

The absolute rules every skill reads when it starts. Details for specific situations live in the documents linked
from each section — read them only when needed.
When writing or editing skill docs (the `../references/` path rule and so on), see `skill-authoring.md`.
When building or changing a feature that stores and recalls "knowledge for next time", see `memory-principles.md`.

## Absolute rules

1. **Never run a Git commit without issue context and user approval** — for issue-based work, commit only after the issue number is confirmed. Hotfixes and config changes unrelated to an issue may use a free format. Give subagents the same instruction. Get the number from the branch name (`YYYYMMDD_#number_title`) or from the user; if you cannot confirm it, **stop immediately** and offer choices (`commit-convention.md` §Issue-based commit principle).
2. **Follow the code style 100%** — detect the existing project patterns and follow them exactly. Do not propose a new "better" way on your own.
3. **Project type detection is mandatory** — always detect the project type automatically before starting work.
4. **Protect sensitive information** — never put real secret values in artifacts or comments (see §Protecting sensitive information below).
5. If the repo's `CLAUDE.md` or `AGENTS.md` sets different rules, those win.

## Enforced AI behavior

These principles **take precedence over skill content**.

### Never do these without confirmation

| Action | Why |
|------|------|
| Running a commit | Must go: propose the message → user approval → run |
| Creating a GitHub issue/PR | Must go: confirm content → user approval → create |
| **Changing issue state or labels** | **Pipeline steps** in §Issue state rules below may be done without confirmation (work start → `status: in progress`, work done → swap to `status: done` then close, both via `finish-issue`). Any other change (closing someone else's issue, changing unrelated labels) only when the user asks |
| Deleting files | Always get the user's permission before deleting |
| push | State the target and content, then get user approval |
| **Runs that change external accounts, certificates, or Secrets** | Reissuing certificates, renewing provisioning profiles, rotating Actions Secrets, pushing to external repos. Say what changes, get approval, then run (lookups and read-only checks need no approval) |
| **Installs that change the user's environment** | Installing a package, runtime, browser, or CLI: **say what, why, and how big, ask, then run**. "The skill needs it to work" is a reason, not approval |

### Issue state rules

Status labels exist in both an English standard and a Korean form (#776). The skill CLIs treat the two forms as
equivalent and substitute whichever one the repo has. Docs and examples write the English one first and the
Korean one next to it.

| When | Action | Command |
|------|------|------|
| Work starts | Swap the status label to `status: in progress` (`작업중`) | `github_cli.py finish-issue {owner} {repo} {number} --outcome in-progress` |
| Work done | Swap the status label to `status: done` (`작업완료`), then close | `github_cli.py finish-issue {owner} {repo} {number}` (default `--outcome done`) |
| Work remains | Do not close; keep `status: in progress` | — |
| Work cancelled | Swap the status label to `status: cancelled` (`취소`), then close | `github_cli.py finish-issue {owner} {repo} {number} --outcome cancelled` |

- **Change state with `finish-issue`** — it swaps only the status label and leaves other labels such as `type:`, `area:`, and `priority:` alone.
  `set-labels` **replaces all labels** with the list you pass, so passing only `set-labels ... "status: done"` deletes every other label.
  `add-labels` only adds, so `status: todo` stays and the issue ends up with two states.
- If `finish-issue` fails only some steps, redo only the steps listed in `failed_steps` (use `set-labels` only when you pass the full list read with `get-issue`, with just the status label swapped).
- The completion recipe is in `pro-github/SKILL.md` §"Completing an issue". `pro-report` follows it after posting the report.
- The release workflow (`close_on_release`) also closes issues with the done label, but it skips issues that are already closed, so closing first does not conflict.
- **`close_on_release` does not close cancelled issues** (it only targets the done label). So the agent closes cancelled issues itself with `finish-issue --outcome cancelled`.

### When something you need is missing

If a tool is missing: ① say what is needed, why, and how big the download is, ② ask, ③ once approved, **the skill installs it itself**
(do not stop after printing a command). Install idempotently into an isolated path.
**Before you say it cannot be done**, **look up** whether the repo's CLIs, automation, or saved credentials (`launch_cli.py cred list`) can do it.
Look things up right away; run changes only after approval. Propose the blocked point and the part you can do separately. Detail: `agent-conduct.md`.

### Route through the dedicated skill (no bypassing)

Handling things directly with `curl` or the GitHub API skips the procedures a skill guarantees: template format, duplicate checks, local saving, and so on.

| Task | Skill you must go through |
|------|------------------|
| **Creating** a GitHub issue | `pro-github` (the `issue-creation.md` workflow) |
| Creating a GitHub PR; reading, editing, commenting on, labeling, closing issues; Actions Secrets | `pro-github` |
| Writing an implementation report, PR comment | `pro-report` |

Even when asked to do several things at once, call each step's dedicated skill in order. **Exceptions**: **correcting** the title or body of an already created issue, and calls a skill explicitly delegates.

### Issue writing convention (mandatory)

Title format `[emoji+tag][category] title`. Only the tags below are allowed. Follow the language of the target
repo's templates; if there are no templates, use English. Tags in both languages map to the same commit type
(case-insensitive).

| English (default) | Korean | Use |
|-------------|------|------|
| `❗[Bug]` | `❗[버그]` | Bug report |
| `🎨[Design]` | `🎨[디자인]` | Design/UI request |
| `🔧[Feature Request]` | `🔧[기능요청]` | Feature request |
| `⚙️[Feature]` | `⚙️[기능추가]` | New feature |
| `🚀[Improvement]` | `🚀[기능개선]` | Improvement to an existing feature |
| `🔍[QA]` | `🔍[시험요청]` | QA/test request |
| `📄[Docs]` | `📄[문서]` | Documentation |
| `🔥[Urgent]` | `🔥[긴급]` | Urgent (only when the user says so) |

- No space between the emoji and `[`: `⚙️[Feature]` (O), `⚙️ [Feature]` (X). Even if the copy-paste example in a template comment (`❗ [Bug]`) has a space, **write it without the space in the title** — every issue title actually filed is written that way
- Do not use separator emoji such as `·` or any emoji outside the allowed list. Save the issue file to the `path` returned by `github_cli.py get-output-path issue --title "{title}"` (do not build it yourself; do not use an `.issue/` folder)

### Issue MD file name rule

Before filing: `YYYYMMDD_001_title.md` (`get-output-path issue` builds it from the day's sequence number and the title without tags) → after filing, rename to the real number,
`YYYYMMDD_245_title.md` (`create-issue --rename-body-file` renames it; do not `mv` it by hand). No emoji or `TMP` prefix in file names. Filing order: `work-start-protocol.md` §Issue filing order.

## Work start protocol

Every code-related skill starts in this order.

1. Detect the project type with `project-detection.md`
2. Detect the code style with `code-style-detection.md` (sample 3–5 existing files)
3. Tech guide: Spring Boot → `tech-spring.md` · React / React Native / Expo / Next.js → `tech-react.md` · Flutter → `tech-flutter.md` · Node.js / Python → no guide; analyze the codebase directly
4. **Check the Git context** (when the work changes code) — §Git context check protocol below
5. **Load personal preferences** — a skill that writes artifacts (messages, reports, issues, comments) reads personal preferences at start with the locate snippet in `preferences.md` (`prefs_cli.py resolve --skill <id>`) and applies them by the rules in `preferences.md`
6. Do the skill's own work

The design → plan → implement flow is `superpowers:brainstorming` → `writing-plans` → `executing-plans` → `/pro-review`.

## Git context check protocol

Do this before changing code. Question wording and handling of each choice: `work-start-protocol.md`.

- **main** (production) → stop immediately and confirm with the user. main is updated only through release PRs.
- **Development branch** (`version.yml` `metadata.development_branch` (old name `deploy_branch`), or `develop` if absent) → if the repo's `CLAUDE.md` or `AGENTS.md` declares direct work on it, pass; otherwise ask whether to link an issue.
- **Feature branch** → take the number from `YYYYMMDD_#number_title` and look up the issue; if there is none, ask. If a new branch is needed, ask whether to use a worktree (`/pro-init-worktree`).

## Distributed per-skill Python calls

Each skill owns `skills/<skill>/scripts/<scope>_cli.py` (argparse subcommands), and shared logic lives in `scripts/common/`.
SKILL.md calls Python with the standard block below (the self-contained 5-line principle — it works no matter which block you start from).
Config is handled by the agent with Read/Write, not by the CLI (`config-rules.md`).

Examples: `pro-github/scripts/github_cli.py` · `pro-report/scripts/report_cli.py` ·
`pro-review/scripts/review_cli.py` · `pro-changelog-deploy/scripts/changelog_cli.py` (other skills follow the same rule).
3-layer structure, JSON output (`ok`/`code`/`summary`/`next`), GitHub API error handling, OS compatibility: `script-invocation.md`.

**GitHub work** goes only through these subcommands too. No `gh` CLI; do not put curl recipes, Python heredocs, or temporary Python files in skill docs.
The CLI loads the PAT automatically.

### Standard call pattern

**The Bash tool resets its state on every call.** Find the scripts **once** per skill run, then write the printed
real paths into later blocks as values — `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/<scope>_cli.py <subcommand> [args]` (model: `pro-launch/SKILL.md`).
To call another skill's script, change only the `SKILL=` value to that skill.

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=<skill>; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
echo "PYTHON=$PYTHON SCRIPTS=$SCRIPTS PROJECT_ROOT=$PROJECT_ROOT"
```

To find and call in one block (self-contained), put
`PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPTS/<scope>_cli.py" <subcommand> [args]` in place of the `echo` line.
**Do not `cd` into the scripts folder** — once you leave the project folder, the git root and issue number can no longer be found (#943). When calling from outside the project, pass `--root <project>` or `$PROJECT_ROOT`.

### Finding the scripts

**Fixed entry point first** (#942): `~/.projectops/bin/projectops_cli.py <skill> <subcommand> ...` finds the newest installed script and passes the arguments through
(skill: github · commit · report · review · testcase · changelog-deploy · init-worktree · figma · agent-test · design-brief · oss-consult · launch).
The lookup block above is the fallback when this file does not exist yet (first run) or on `scripts_not_found`. `newer_installed` in the response means an old version is running.

**In zsh, do not store a command in a variable** — with `P="python3 …/projectops_cli.py github"; $P get-issue …`, zsh treats the variable as one word and fails with `exit 127` (command not found).
To shorten it, wrap it in a function:

```bash
G(){ PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py github "$@"; }
G get-issue {owner} {repo} {number}
```

The block above finds the plugin root in this order: **local (`skills/` in the projectops repo) → harness install paths (Claude Code, Codex, Gemini, pi)**.
**Do not change its shape** — running `find` for each harness in a `for` loop (to avoid zsh `no matches found`, #542) and the final `[ -d "$SCRIPTS" ]`
guard both came from real incidents. Rationale: `script-invocation.md` §Finding the scripts.

### Setting the PYTHON variable (required for cross-platform)

Use the `PYTHON=` line from the block above as is. Do not call `python3 -c` directly (Windows Store stub → `Exit code 49`); calls that carry Korean or other non-ASCII text
must set `PYTHONIOENCODING=utf-8`. Rationale: `script-invocation.md` §Setting the PYTHON variable.

### Windows corporate network

curl `exit 35` (SSL) → add `--ssl-no-revoke` and retry. Detail: `script-invocation.md` §Windows corporate network.

## Output paths

Use the `path` returned by each skill CLI's `get-output-path` as the artifact location. Do not build paths yourself
(the artifact root changes with the `output.root` setting). Detail: `doc-output-path.md`.

## Rules when running git push

1. **Do not push to main (the default/deploy branch)** — main is updated only through release PRs (`/pro-changelog-deploy`)
2. Order: **commit → `git fetch origin` → `git pull --rebase origin {current branch}` → push** (on release, a version-finalizing commit is also added to the development branch, so local easily falls behind).
   Sync before push **after** committing your changes — if your uncommitted changes remain, rebase refuses to run
3. If `pull --rebase` is refused because of another session's uncommitted changes, use `git merge --ff-only origin/{current branch}` instead
   (the same approach as `pro-changelog-deploy/SKILL.md` §Step 1-1). If fast-forward is not possible (history has diverged), stop and ask the user. Do not clear things away with stash or reset
4. **Chain the steps with `&&`** — with `;`, push runs even if the sync fails:
   `git fetch origin && git pull --rebase origin {branch} && git push origin {branch}`
5. On non-fast-forward, integrate again with steps 2–3 (no force push). Tell the user only the result

## Commit message convention

The format follows team and personal settings (team `version.yml` format > personal preference — `preferences.md`). The issue title is the plain content without emoji or tags,
and the type (`feat`/`fix`/`refactor`/`docs`/`chore`/`style`/`test`) is decided by **what this commit changes**. Use the `template` from
`github_cli.py get-commit-template ... --repo-root "{PROJECT_ROOT}"` as is. In a `semver_auto` repo, the type decides the release version
(`feat!` major · `feat` minor · everything else patch — `!` only when compatibility breaks). Commits unrelated to an issue may use a free format.
Detail and examples: `commit-convention.md`.

## Protecting sensitive information

Artifacts under `docs/projectops/` are committed publicly to Git. Do not include real values of PATs, API keys, Secrets, tokens, or passwords; server IPs, internal domains, or SSH details;
personal data; or `.env` and DB connection details.

### Masking rules

Use named placeholders (`{PAT}`, `{API_KEY}`, `{PASSWORD}`, `{DB_USERNAME}`, `{SERVER_HOST}`, `{EMAIL}`, and so on) instead of real values.
Anonymous asterisks like `***` are not allowed. Table: `sensitive-info.md` §Masking rules.

### Self-review right before saving a file

**Right before** saving an artifact, review its entire content, replace risky values with placeholders, and if you replaced anything, tell the user after saving.
Checklist, criteria, and notice format: `sensitive-info.md` §Self-review right before saving a file.
