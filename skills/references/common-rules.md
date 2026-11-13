# Common rules

The absolute rules every skill reads when it starts. Situation details live in the shared documents each SKILL.md
links directly, with a "read when" line — read them only when that situation comes up.
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

## Work start protocol

Every code-related skill starts in this order. Steps 1–4 are detailed in the documents named, which each SKILL.md links.

1. Detect the project type (`project-detection.md`)
2. Detect the code style from 3–5 existing files (`code-style-detection.md`)
3. Tech guide: Spring Boot → `tech-spring.md` · React / React Native / Expo / Next.js → `tech-react.md` · Flutter → `tech-flutter.md` · Node.js / Python → analyze the codebase directly
4. **Check the Git context** before changing code: on main, stop and confirm; on the development branch or a feature branch, follow `work-start-protocol.md`
5. **Load personal preferences** — a skill that writes artifacts reads them at start (`prefs_cli.py resolve --skill <id>`, snippet and rules in `preferences.md`)
6. Do the skill's own work

The design → plan → implement flow is `superpowers:brainstorming` → `writing-plans` → `executing-plans` → `/pro-review`.

## Calling skill scripts

Call each skill's CLI through the fixed entry point `python3 ~/.projectops/bin/projectops_cli.py <skill> <subcommand> [args]`
with `PYTHONIOENCODING=utf-8`. If it is missing or answers `scripts_not_found`, use the fallback block in `script-invocation.md`.
GitHub work goes only through skill CLI subcommands: no `gh` CLI, no curl recipes, Python heredocs or temporary Python files in skill docs.
Artifact paths come only from each CLI's `get-output-path` (`doc-output-path.md`).

### Windows corporate network

curl `exit 35` (SSL) → add `--ssl-no-revoke` and retry. Detail: `script-invocation.md` §Windows corporate network.

## Rules when running git push

1. **Do not push to main (the default/deploy branch)** — main is updated only through release PRs (`/pro-changelog-deploy`)
2. Order: **commit → `git fetch origin` → `git pull --rebase origin {current branch}` → push** (on release, a version-finalizing commit is also added to the development branch, so local easily falls behind).
   Sync before push **after** committing your changes — if your uncommitted changes remain, rebase refuses to run
3. If `pull --rebase` is refused because of another session's uncommitted changes, use `git merge --ff-only origin/{current branch}` instead
   (the same approach as `pro-changelog-deploy/SKILL.md` §Step 1-1). If fast-forward is not possible (history has diverged), stop and ask the user. Do not clear things away with stash or reset
4. **Chain the steps with `&&`** — with `;`, push runs even if the sync fails:
   `git fetch origin && git pull --rebase origin {branch} && git push origin {branch}`
5. On non-fast-forward, integrate again with steps 2–3 (no force push). Tell the user only the result

## Protecting sensitive information

Artifacts under `docs/projectops/` are committed publicly to Git. Never put real values of PATs, API keys, Secrets, tokens, passwords,
server IPs, internal domains, SSH details, personal data, `.env` or DB connection details in artifacts or comments.
Use named placeholders (`{PAT}`, `{API_KEY}`, `{SERVER_HOST}`, …), never `***`. **Right before saving** an artifact, review all of it,
replace risky values, and tell the user if you replaced anything (`sensitive-info.md` has the table and checklist).
