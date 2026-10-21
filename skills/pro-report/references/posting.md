# GitHub posting · image attachment details

> When to read: before posting the report as an issue comment (issue number, PAT and repo checks), and when posting screenshots with it.

## Issue number detection order

1. Extract the `YYYYMMDD_number_title` pattern from the current working directory (worktree folder name)
2. Extract it from the git branch name (`YYYYMMDD_#number_title` from `git branch --show-current`)
3. An issue number the user mentioned in the conversation (when the branch name has no number, such as direct work on develop)
4. If all of the above fail, ask the user for the issue number

## PAT · repo check

1. **PAT check**: do not read the PAT yourself (opening the config with Read leaves the PAT in the session log). Call `add-comment` directly; if it returns `missing_pat`, save locally only and stop. The CLI loads the repo's `pat`, then `global_pat`, automatically.

   > ⚠️ **Do not search for the config.** config.json lives only at the fixed path `{HOME}/.projectops/config/config.json`; read it directly with the Read tool. Do not use the `ls ~/.claude/plugins/cache/...` pattern (meant for finding `report_cli.py`) to find the config. The config is not in that cache.

2. **Repo check**: extract `owner`/`repo` from `git remote get-url origin`; if that fails, use the repo with `default: true` in the config's `repos`.

## How `add-comment` works

- Do not write inline Python. The report body goes in as the already saved `.md` file (`body_file`), so non-ASCII text, emoji, line breaks and mermaid blocks are preserved safely.
- **report_cli loads the PAT from config.json automatically, so `GITHUB_PAT=` can be omitted** (an environment variable wins if set).
- Output is JSON: `{"ok": true, "id": ..., "url": "https://github.com/.../issues/{number}#issuecomment-...", "summary": ..., "next": null}`. Use the `url` field in the completion message.
- **Windows + macOS/WSL compatible**: the self-contained 5-line pattern works regardless of cwd or environment variables.
- GitHub comments render mermaid blocks, so the flowchart shows as is.

## Screenshots · evidence images

> **Order**: the approval screen shows the "images to attach" list together with the body. After approval: `upload-image` → put the returned `markdown` into the body → `add-comment`. The approved body and the posted body differ only in the image links. On "view only", do not upload either.

**If the report needs screens, post images with it.** For test results, failure reproduction and UI changes, a screen is better evidence than text.

```bash
# Get the URLs from pro-github's upload-image first (before inserting them into the body)
PYTHONIOENCODING=utf-8 "{PYTHON}" "{pro-github/scripts}/github_cli.py" \
  upload-image {owner} {repo} {image files...} --prefix report{issue_number}
```

Paste the `markdown` field of the output JSON into the report `.md`, then post it with `add-comment`.
**Keep the order.** If you post the report first, the body goes up without images.

Detailed rules (format limits, private repo constraints, undo): `../../pro-github/references/images.md`.

> If there are no images, add none. Meaningless screenshots only make the report longer.
