# Output shape and global options (shared by every skill CLI)

The response is always one line of JSON, with **`ok` · `code` · `summary` · `next` first** (#940). `summary` is always a string (when empty, failures get `error` or `code`, and successes get `완료` — the literal string the CLI emits, meaning "done"). Do not guess keys and parse them with inline Python.

## Global options

| Option | Effect |
|---|---|
| `--field a.b.0` | Returns only that value of a success response, as text (`--field issue.title`, `--field runs.0.run_id`). For a path that does not exist, returns `field_not_found` with `did_you_mean` (nested path candidates, for example `issue.labels`) and `available_keys`. Not applied to error responses |
| `--fields a,b` | Another spelling of the same option as `--field`. With several paths, returns one JSON object `{path: value}` |
| `--brief` | Keeps `ok · code · summary · next · error · hint · usage · example · count · warning(s)`, and for list values keeps only each row's identifying keys (`number · id · run_id · job_id · title · name · state · status · conclusion`). Saves calling a list response again |

A `bad_args` response contains `usage` (how to use that subcommand) and `did_you_mean` (similar subcommands) — do not call `--help` separately.

## Keys to read in common responses

| Command | Keys to read |
|---|---|
| `github_cli get-issue` | Top-level `number` · `title` · `url` · `state` · `labels[]` · `assignees[]` · `body`, raw `issue.{…,created_at,updated_at,comments_count}`, alias `html_url` |
| `github_cli create-issue` | `number`, `url`, `title`, `branch`, `commit_template`, `next` (+ `body_file_renamed_to` · `rename_warning` · `label_warning` · `assignee_warning`) |
| `github_cli list-comments` | `comments[].{id,url,author,body,created_at}` — pass `id` to `edit-comment` / `delete-comment` |
| `github_cli list-labels` | `labels[]` (list of name strings) |
| `github_cli set-labels` | `labels[]` (after replacement), `removed[]` (labels removed), `warning` (non-status labels were removed) |
| `github_cli finish-issue` | `steps[].{step,ok}`, `failed_steps[]`, `warnings[]` (no report comment, and so on) |
| `github_cli create-branch-name` | `branch`, `issue_number` |
| `github_cli upload-image` | `markdown`, `tag` (the evidence release actually used), `images[].{name,url,asset_id,renderable,tag,file}` (`file` is the absolute path of the uploaded local file), top-level `url` when there is 1 |
| `github_cli list-prs` | `prs[].{number,title,url,state,head,base,merged_at}` |
| `github_cli create-pr` · `changelog_cli create-pr` | `number`, `url` (+ `notes_wrapped` · `body_guard`) |
| `github_cli explore repo-detail` | `repo.{name,default_branch,private,visibility,url,…}` |
| `github_cli api` | `data` (valid JSON), `truncated`, `truncated_items`, `saved_to` (`--out`) |
| `github_cli actions runs\|list-failed` | `runs[].{run_id,name,path,branch,event,status,conclusion,created_at,url}` (`list-failed {run_id}` gives that run's `jobs[]`) |
| `github_cli actions show-run` | Run summary + `jobs[].{job_id,name,conclusion,failed_steps[]}` + `failed_job_ids[]` |
| `github_cli actions joblog` | `lines[]`, `matched_count`, `mode` (`error_markers` · `grep`), `saved_to` |
| `github_cli actions wait` (several runs) | `runs[]`, `finished`, `pending_run_ids[]`, `failed_job_ids[]` |
| `github_cli add-comment` | `id`, `url` (+ `reconciled`) |
| `changelog_cli deploy-status` | `verdict`, `stuck_reason`, `pr.{number,state,merged,mergeable_state,age_seconds,head_sha,url}`, `workflow.{status,conclusion,run_url}` |

The table above was taken from the code. When you add a new subcommand, add one line here with the keys to read.
