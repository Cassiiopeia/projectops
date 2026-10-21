# Artifact path rules

The `report`, `review`, and `issue` (pro-github) skills must follow this reference when saving md artifacts.

## Computing the path before saving

Before saving an md artifact, always call the `get-output-path` subcommand of that skill's `_cli.py` and use the path it returns.
For the standard, see `common-rules.md` §"Distributed per-skill Python calls".

Where each skill calls it — **every artifact skill has its own CLI** (#525):

| skill_id | Call cwd | CLI file |
|---|---|---|
| review | `skills/pro-review/scripts/` | `review_cli.py` |
| report | `skills/pro-report/scripts/` | `report_cli.py` |
| issue | `skills/pro-github/scripts/` | `github_cli.py get-output-path issue --title "{title}"` (call from the project root. Because it runs before filing, it gets the day's sequence number instead of an issue number, and it does not borrow the number even on an issue branch — #822) |
| agent-test | `skills/pro-launch/scripts/` | `launch_cli.py get-output-path --skill agent-test` (returns **a run folder, not an md file** — see below. Since running and capturing moved to pro-launch, pro-launch also opens the slot, #631) |
| launch | `skills/pro-launch/scripts/` | `launch_cli.py get-output-path` (run folder — other evidence skills pass `--skill <id>`) |

> **Only agent-test's artifact is not an md file (#611).** It produces evidence of the walk-through
> (screenshots, recordings), so `get-output-path` creates and returns a **run folder**
> (`<umbrella>/agent-test/{date}_{number}_{title}/`) instead of a file, with `screenshots/` and the harness
> `env.sh` inside. The file name rule itself uses the same `common/paths.py`, so locations do not diverge.
>
> **This folder is not tracked.** The source of truth for evidence is the images uploaded to the GitHub issue;
> the local copy is an intermediate product, so there is no reason to pile up several MB in the repo (the same
> reasoning as the run logs in #561). The folder **carries its own** `<umbrella>/agent-test/.gitignore`
> (`*` + `!.gitignore`) so the root `.gitignore` is not touched — the skill is installed into other people's
> repositories, and editing a shared file would conflict with the user's changes.

> **The agent does not compute paths itself.** In the past some skills had no CLI and were told to "compute it yourself or borrow another skill's", so file name rules split between skills and no one noticed. Now the rule lives in **one place only**, `resolve_output_path()` in `scripts/common/paths.py`, and every CLI calls it.

Example (review):

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-review; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
# 홈 복사 설치본: npx projectops 의 GitHub Copilot·Cursor (#200)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.copilot ~/.cursor; do [ -d "$B/skills/$SKILL/scripts" ] && { ROOT="$B"; break; }; done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPTS/review_cli.py" get-output-path review --title "{title}"
# Outside the project: --root <project path>; to pass the issue number directly: --issue N
```

Take the `path` field from the output JSON and use it.

Example return values:
- `docs/projectops/report/20260418_427_dropdown_design_change.md`
- `docs/projectops/review/20260418_001_initial_review.md`

## The artifact path umbrella (default `docs/projectops/`)

All artifacts live under one umbrella. The harness (`harness/WORKFLOW.md` §"Single rule for artifact paths") and the skills share the same location.

| Kind | Path | Notes |
|------|------|------|
| Final skill artifacts | `<umbrella>/<skill>/` | report, review, issue, and so on |
| Work-in-progress knowledge graph | `<umbrella>/hypercortex/` | Harness SDLC TODO, REQUIREMENT, DESIGN, QUALITY, and so on |
| Isolated code work | `<umbrella>/workspace/` | Isolates harness Phase 4 code output |

### Users can move the umbrella (#525)

The default is `docs/projectops/`, and it **stays that way unless the setting is changed**.
If team conventions require another location, or you do not want docs left in the repository, change it in config.

```json
{
  "output": { "root": "docs/dev" }
}
```

| Value | Result |
|---|---|
| Not set | `<repo>/docs/projectops/` — same as before |
| Relative path (`docs/dev`) | `<repo>/docs/dev/` |
| Absolute path (`/Users/me/notes`) | That path as is (to collect outside the repository) |

`resolve_output_root()` in `scripts/common/paths.py` resolves it.
**Skills do not build path strings themselves** — always go through `get-output-path`.
When telling the user, do not expose setting key names or file paths; speak in natural language only.

## Handling failures

| Situation | Response |
|------|------|
| `[WARN] title_not_found` (exit 0) | The AI makes a title from the work context and calls again with `--title "title"` |
| `[WARN] issue_number_not_found` (exit 0) | Use the fallback path as is and tell the user "no issue number, so a sequence number is used" |
| `[WARN] issue_number_mismatch` (exit 0) | Use the fallback path as is and tell the user about the mismatch |
| `[ERROR] git_not_found` (exit 1) | Tell the user "this is not a git repository" and stop |

## Creating the directory automatically

After getting the path, create the directory before writing the file:

**Mac/Linux:**
```bash
mkdir -p "$(dirname "<returned path>")"
```

**Windows (PowerShell):**
```powershell
New-Item -ItemType Directory -Force -Path (Split-Path "<returned path>")
```
