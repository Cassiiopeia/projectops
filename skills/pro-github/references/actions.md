# GitHub Actions logs

> When to read: when diagnosing a build or workflow failure ("check the failed build", "show the Actions log", "why did this PR's build fail?", a run/job/PR URL, "did the main build pass?"; Korean: "빌드 실패 확인해줘", "Actions 로그 봐줘"). The input → subcommand routing table is in SKILL.md.

Commands have the form `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions <sub> ...` (SKILL.md "Find the scripts").

## Core principles

- All logic lives in the `actions` subcommand of `github_cli.py`. **Do not write inline Python.**
- **Interpreting the input is the agent's job.** Look at the URL, PR number, branch name or empty input and pick the subcommand and arguments from the routing table in SKILL.md.
- `github_cli` takes **only explicit arguments** (it does not parse URLs). There is **one** positional argument (`arg`), and the subcommand reads it as run_id · job_id · pr_number · branch (#622). Exception: `wait` takes several run ids.
- Put the action name right after `actions`. If the order is wrong, as in `actions {owner} {repo} show-run …`, `next` in the `bad_args` response gives the correct command.
- Output is **always JSON** with `ok`, data and `next` (a hint for the subcommand to call next). If `next` is not empty, run it as the next command to continue the chain (for example `next` of `show-run` → `joblog`).
- The PAT is loaded from config.json automatically, so `export GITHUB_PAT` can be omitted (an environment variable wins if set). `PYTHONIOENCODING=utf-8` is required (protects non-ASCII output).

## Typical diagnosis flow

1. No run_id in the input (PR / branch / empty) → find the failed run with `resolve-pr`, `resolve-branch` or `list-failed`
   If `resolve-pr` returns several runs, pick the **most recent** one whose `conclusion` is `failure`.
2. Run the failed run's `next` (= `show-run ...`) → find the failed job_id and failed step
3. Run `next` of `show-run` (= `joblog ...`) → read the actual error log lines
   By default (no `--grep`) you get the `##[error]` lines and the output lines before them (`mode: error_markers`). The `##[group]Run` script source sections are skipped, so the word `error` or branch names in the source do not match. If there is no `##[error]`, it searches `error|failed` instead.
   To widen, use `--grep "exception|exit code"` (regex, case-insensitive). `--grep "" --tail 80` gives the last 80 lines of the log.
   If you pass a run id where a job id belongs, you get `run_id_given` and `next: show-run`.
4. Read the log lines and present the diagnosis to the user

## Usage

```bash
# Run metadata + job list + failed steps
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions show-run {owner} {repo} {run_id}
# Failed job log (error line filter, Azure redirect handled automatically)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions joblog {owner} {repo} {job_id}
#   --grep "\.dart" : search with a regex (case-insensitive). Without it: ##[error] lines + preceding output (script source excluded)
#   --tail 30       : last N matching lines (default 30)
#   --out log.txt   : full log to a file
# Recent failed runs
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions list-failed {owner} {repo} --limit 10
# Only the failed jobs of one run (when given a run id)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions list-failed {owner} {repo} {run_id}
# PR → linked runs
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions resolve-pr {owner} {repo} {pr_number}
# Branch → recent runs
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions resolve-branch {owner} {repo} "{branch}" --limit 10
```

> **Windows note**: do not use temporary-file parsing, curl piped into Python or heredoc interpolation (they break in Windows Git Bash). Pass every argument on the command line or as an environment variable.

## Sample output

```json
{"run_id": 26554093214, "name": "Project build test", "conclusion": "failure",
 "jobs": [{"job_id": 78222159478, "name": "Project build test", "conclusion": "failure", "failed_steps": ["Run code analysis"]}],
 "failed_job_ids": [78222159478],
 "ok": true, "next": "actions joblog acme-org acme-app 78222159478"}
```


## Run · rerun · wait · list (#939)

Do not use curl to run a workflow or wait for it to finish. Reading the PAT from the config file for curl was the main reason it ended up in session logs.

```bash
# Run (workflow_dispatch). It does not return a run id, so find the new run with runs
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions dispatch {owner} {repo} build.yaml --ref develop --input env=test
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions runs {owner} {repo} build.yaml --on-branch develop --limit 3   # --branch works too
# Wait inside the tool until it finishes (up to 540 s; if not done, finished: false and the same command as next). Do not use sleep or polling loops
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions wait {owner} {repo} {run_id} --timeout 300
# Wait until several runs all finish (runs[] · pending_run_ids · failed_job_ids)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions wait {owner} {repo} {run_id} {run_id2} {run_id3}
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions rerun {owner} {repo} {run_id} --failed-only
# Cancel (only when the user asks). --force is a force cancel that also stops always() steps
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions cancel {owner} {repo} {run_id} [--force]
```

- `joblog --grep` is a regex (`'error|failed'`, case-insensitive). An invalid regex is searched as literal text. Check `regex` in the response to see how it was interpreted.
  If you need the full log, save it with `--out file` and read it yourself. Logs past the retention period return `log_expired`.
- `list-failed --workflow build.yaml` keeps only failed runs of that workflow.
- For REST calls the commands above do not cover, use `api`: `api GET {owner} {repo} releases/latest` (a relative path gets `/repos/{owner}/{repo}/` prepended; an absolute path `/repos/{owner}/{repo}/...` also works).
  It accepts only this repo's paths. The only exception outside the repo is the read-only `GET /rate_limit`. Add `--write` to state-changing methods (POST · PUT · PATCH · DELETE) only for work the user asked for.
  If the response exceeds 20,000 characters, trailing list items are dropped and you get **valid JSON** (`truncated: true`, `truncated_items`). If you need all of it, use `--out file` (`saved_to` in the response); otherwise shrink it with `?per_page=10`.
  With `--out`, a non-JSON response (artifact zip `actions/artifacts/{id}/zip`, `zipball/{ref}`) is saved as raw bytes and the reply says `binary: true` with `bytes` — use this instead of `gh api` or curl.
- For a multi-line secret value, pass it with `secrets set {owner} {repo} {name} --value-file file` (the `SECRET_VALUE` environment variable also works).
