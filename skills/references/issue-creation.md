# Issue creation workflow (pro-github only)

When the user asks to **create a new GitHub issue** (for example "make an issue", "file a bug report", "feature request issue", or in Korean "이슈 만들어줘", "버그 리포트 올려줘", "기능 요청 이슈"), the `pro-github` skill follows this procedure. It takes a rough description, **writes a title and body that fit the issue template**, **saves them to a local file first**, **files the issue on GitHub** after user confirmation (or under the auto-approval setting), and **computes the branch name right away** so it can offer next-step choices.

> Work "other than creation" (reading, editing, comments, labels, assignees, PRs) follows `pro-github/SKILL.md`. This document is **for the creation workflow only**.

All commands take the form `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py <subcommand> ...`. Fill in `{PYTHON}`, `{SCRIPTS}`, and `{PROJECT_ROOT}` with the real paths you got by running "Finding the scripts" in `pro-github/SKILL.md` once (Bash resets its state on every call). The CLI loads the PAT automatically.

Talk to the user in the user's language (or the configured `language` preference). The message templates below are reference wording in English.

## Before starting

1. Apply the **absolute rules** in `common-rules.md` (no Git commits, protect sensitive information).
2. **Check config** — the procedure in `config-rules.md` §2~5. config.json lives in one fixed place only: `{HOME}/.projectops/config/config.json` (read it directly with the Read tool; do not search with `ls` or `find`).
   - If it exists → take `global_pat` and `repos`. **Choose the repo**: ① match `owner/repo` from `git remote get-url origin` against `repos` → ② if that fails, the repo with `default: true` → ③ if none or several, number them and let the user choose.
   - If it does not exist → collect `global_pat`, `default_assignee`, and the first repo (owner/repo/name), and save them (format in `config-rules.md`).
3. **Determine auto-approval mode** — `issue.auto_approve` (the key name stays `issue.*` for backward compatibility). Take the first value found:
   1. `issue.auto_approve` in the `github.repos[]` entry for the current OWNER/REPO
   2. `github.issue.auto_approve` (global)
   3. If neither, `false` (safe default — manual approval)

   Remember: `AUTO_APPROVE` (boolean), `CONFIG_HAS_KEY` (true if found in 1 or 2, otherwise this is the first run).
   > Even in automatic mode, the duplicate checks (2-1, 4-1) and the stop-on-matching-open-issue policy still apply. auto_approve skips only the "final filing approval" gate.
4. **Decide the assignee** — the "global + per-repo override + ask only on first run" pattern:
   1. `issue.assignee` in the `github.repos[]` entry for the current OWNER/REPO
   2. `github.default_assignee` (global)
   3. If neither, unset (first run — ask once at step 4, C-2)

   Remember: `ASSIGNEE`, `ASSIGNEE_HAS_KEY`. If it is set, apply it automatically without asking and show only "Assignee: {ASSIGNEE}" on the approval screen.

> Speak to the user in natural language only. Do not put key names or paths such as "auto_approve" or "config.json" in messages to the user.

## Allowed emoji + tag rules

> **The language follows the target repo's templates.** Read the target repo's `.github/ISSUE_TEMPLATE/` and use that template's language, section headings, and allowed tags as they are. With a Korean template, use the Korean section headings and tags (`❗[버그]`); with an English template, use English (`❗[Bug]`). If there is no template, write in English (the defaults below). Tags in both languages map to commit types.

**Main tags** (decide the type; exactly one):

| English (default) | Korean | Use |
|-------------|------|------|
| `❗[Bug]` | `❗[버그]` | Bug report |
| `🎨[Design]` | `🎨[디자인]` | Design/UI request |
| `🔧[Feature Request]` | `🔧[기능요청]` | Feature request |
| `⚙️[Feature]` | `⚙️[기능추가]` | New feature |
| `🚀[Improvement]` | `🚀[기능개선]` | Improvement to an existing feature |
| `🔍[QA]` | `🔍[시험요청]` | QA/test request |

**Modifier tags** (optional, before the main tag):

| English (default) | Korean | Condition |
|-------------|------|------|
| `🔥[Urgent]` | `🔥[긴급]` | Only when the user explicitly says it is urgent |
| `📄[Docs]` | `📄[문서]` | When it is about documentation |
| `⌛[~month/day]` | `⌛[~월/일]` | When there is a due date |

**Rules**: no space between the emoji and `[`. No emoji outside the list above.
The copy-paste example in template comments has a space, like `❗ [Bug][Category]`, but **write it without the space in the title**. Every filed issue title is written that way, and the issue helper and commit template strip the tag the same way either way, so keep a single spelling.

## Never

- Print the issue body only in chat and skip saving the file
- Code-level content (implementation approach, code examples)
- Emoji outside the allowed list, or a space between the emoji and `[`
- Add `🔥[Urgent]` / `🔥[긴급]` on your own (only when the user says so), or fill in the assignee on your own
- Add any status label other than the template default (`status: todo`) at creation, or close the issue. Later transitions — start (`status: in progress`), done (`status: done` then close), cancelled (`status: cancelled` then close) — follow `common-rules.md` §Issue state rules
- Skip the duplicate checks (2-1, 4-1) in automatic mode — always run them. Always stop if a matching open issue is found
- Expose config key names or file paths in messages to the user

## Process

### Step 1: Determine the issue type automatically

| Type | Keywords (English / Korean) | Template |
|------|--------|--------|
| **Bug** | doesn't work, error, broken, crash, outage / 안 됨, 에러, 깨짐, 오류, 크래시, 장애 | `bug_report` |
| **Feature** | add, need to build, new, implement, improve, change, request / 추가, 만들어야, 새로, 구현, 개선, 변경, 요청 | `feature_request` |
| **Design** | design, UI, UX, font, color, layout / 디자인, UI, UX, 폰트, 색상, 레이아웃 | `design_request` |
| **QA** | test, QA, trial, verify, check / 테스트, QA, 시험, 검증, 확인 | `qa_request` |

**Feature subtypes**: `🔧[Feature Request]`/`🔧[기능요청]` (request/review), `⚙️[Feature]`/`⚙️[기능추가]` (a completely new feature), `🚀[Improvement]`/`🚀[기능개선]` (improving an existing one).

### Step 2: Write the issue title

```
[emoji+tag][category] title (50 characters or fewer)
```

Example: `⚙️[Feature][Skills] Add issue edit subcommands to the github skill` (in a repo with Korean templates: `⚙️[기능추가][Skills] github 스킬 이슈 편집 서브커맨드 보강`)

**Title punctuation rules (mandatory)** — punctuation you cannot type directly on a keyboard looks "AI-made", so do not use it.

- **No em dash (`—`) or en dash (`–`).** Use a colon, comma, or parentheses instead. ❌ `Skill rebranding — neutralize` / ✅ `Skill rebranding: neutralize`
- **No middle dot (`·`).** Use a comma or slash instead. ❌ `Fix old names·workflow names` / ✅ `Fix old names, workflow names`
- Use a plain hyphen (`-`) only where the original spelling needs it, such as file names and versions (`v4.2.0`).

### Step 2-1: Search for duplicate issues (before saving the file)

Pull the key keywords from the title (remove emoji, `[...]` tags, special characters, and URLs → 2–3 key nouns). Pass the keywords as the last argument as is (spaces allowed; URL-encoded internally). No inline Python.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py search-issues {owner} {repo} "{2-3 key keywords}"
```

Output JSON `{"count":N,"items":[{number,title,url,state,labels}]}`. Exclude `closed` items from duplicates. If `[ERROR]` appears on stderr, skip the duplicate search, warn, and continue.

**Decision (open issues only):**
- **Effectively identical** → print the following and **stop**.
  ```
  🚫 An identical issue already exists.

  #{number} — {title}
  {html_url}

  Stopping new issue creation. Continue the work in the existing issue.
  ```
- **Similar but different** → warn and ask the user (1. Create a new one / 2. Cancel). Stop on 2.
- **Unrelated** / no results / API error → continue.

### Step 3: Explore the code and write the body

1. Read the matching template in `.github/ISSUE_TEMPLATE/` to learn its format
2. Explore the related code and include the relevant file paths
3. Write the body in the template's format (if the preferences have a `template`, append it as extra sections; use `examples` only as a style reference)
4. **Attach images (mandatory)** — if images, mockups, or screenshots related to this issue are in the conversation, upload them without missing any.
   Upload with `upload-image` and put the output's `markdown` into the matching section of the body as is (commands and cautions: `../pro-github/references/images.md`).
   ```bash
   PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py upload-image {owner} {repo} {image files...} --prefix issue
   ```
   - If you do not know the image's local file path (it was only pasted into the chat), ask the user for the path. Do not silently continue without the image
   - If `private_warning` comes back, tell the user the image will not render because the repo is private

### Step 4: Save the local file first

Follow the rules in `doc-output-path.md`. **Do not build the path yourself**; use the `path` returned by `get-output-path issue` as is (the artifact root can change through settings). It is computed for the current repo, so call it from the project root.

```bash
cd "{PROJECT_ROOT}" && PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py get-output-path issue --title "{issue title}"
```

- Example `path`: `<artifact root>/issue/YYYYMMDD_001_title.md`
- Because it runs before filing, it gets **the day's sequence number** (`001`, `002`…) instead of an issue number. Even on an issue branch, it does not borrow that branch's number. No `TMP` prefix (`common-rules.md` §Issue MD file name rule)
- The emoji and `[tags]` in the title are dropped from the file name automatically

**Right before saving**: review the whole body with the **self-review right before saving a file** protocol in `common-rules.md`. Mask any sensitive information found.

After saving, branch on `AUTO_APPROVE` / `CONFIG_HAS_KEY` from [Before starting §3].

#### A. Automatic mode (`AUTO_APPROVE == true`)

Show only the summary and file path, then go straight to 4-1 → step 5. Do not wait for a reply.

```
🤖 This repo is set to file without confirmation, so here is a summary before filing on GitHub.
   (If you want to confirm every time again, just say "ask me first".)

Issue file: {path returned by get-output-path}
Title: ⚙️[Feature][Skills] ...
Labels: status: todo
Assignee: {ASSIGNEE}

Filing on GitHub now.
```

> If the user says "ask me first", update the config before 4-1/step 5 (set priority 1 if it exists, otherwise priority 2, to `false`) and switch to branch B.

#### B. Manual mode (`AUTO_APPROVE == false`)

```
Created the issue file: {path returned by get-output-path}

Title: ⚙️[Feature][Skills] ...
Labels: status: todo
Assignee: {ASSIGNEE}

Please review the content. File it on GitHub?
1. Yes, file it
2. I want to change the title
3. I'll edit the content (edit the file, then ask again)
4. No, just keep it saved locally
```

**Never call the GitHub API before the user approves.**

- **1** → step 4-1. If `CONFIG_HAS_KEY == false` (first run), run [C] once right before 4-1
- **2** → take the title change, regenerate the body → back to the start of step 4
- **3** → the user edits the file and asks again → back to the start of step 4
- **4** → keep the local file only and stop

#### C. First-run automation offer (chose 1 in B + `CONFIG_HAS_KEY == false`, once only)

```
💡 How should I handle filing issues from now on?

By default I show you the issue content and ask for confirmation right before every filing.
If you like, I can skip this step and file on GitHub right away.
(Duplicate checks keep running in automatic mode too.)

1. File issues in this repo without confirmation from now on
2. File issues in all repos without confirmation from now on
3. Keep asking me to review the issue every time
```

Update `config.json` with Read/Write based on the reply: **1** → `issue.auto_approve: true` in the `github.repos[]` entry for the current OWNER/REPO / **2** → `github.issue.auto_approve: true` / **3** → `github.issue.auto_approve: false`.

> Updates follow `config-rules.md` §4: Read the whole file, change only that key, then Write. Never drop the PAT or other repos entries.

#### C-2. First assignee setup (`ASSIGNEE_HAS_KEY == false`, once only)

Ask once only, before 4-1 (skip if config already has an assignee).

```
🙋 Who should be the issue assignee? (It will be applied automatically from now on)
Tell me the GitHub username. (Say "none" to proceed without an assignee)
```

- A username → save it to `github.default_assignee` and use it as `ASSIGNEE` starting with this issue
- "none" → save `github.default_assignee` as an empty string

### Step 4-1: Final duplicate check (right before the API call)

Call the same `search-issues` as in 2-1 again.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py search-issues {owner} {repo} "{key keywords}"
```

**An effectively identical open issue** → stop immediately. **None/unrelated** → step 5. `closed` issues are not duplicates.

### Step 5: Create the GitHub issue (after approval)

**Do not put a title heading (`# ...`) or a labels/assignee meta block in the issue body.** Use only the template sections (📝 current problem, 🛠️ proposed solution, and so on). Pass the local `.md` file as `body_file`, and pass `ASSIGNEE` from [Before starting §4] to `--assignees` (omit it if unset).

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py create-issue {owner} {repo} "{title}" "{absolute path to issue body .md}" "{labels csv}" --assignees "{ASSIGNEE}" --rename-body-file
```

Output JSON: `number`, `url`, `title`, `assignees`, plus `body_file_renamed_to`, `branch`, `commit_template`, and `next`. Labels that do not exist are filtered out automatically, so no 422 occurs. If the assignee is not applied, `assignee_warning` comes back; the issue was created normally, so do not stop — just pass the warning on in natural language.

`--rename-body-file` replaces the sequence number in the local file name with the real number (for example `20260710_001_title.md` → `20260710_245_title.md`) and returns the new path as `body_file_renamed_to`. **Do not `mv` it by hand.**

### Step 6: Branch name

Use `branch` from the `create-issue` response as is. Only when it is missing (old versions), call `create-branch-name "{issue title}" {number}`. Format `YYYYMMDD_#{issue number}_{normalized title}` (for example `20260710_#235_Feature_github_skill_merge`).

### Step 7: Commit template

Use `commit_template` from the `create-issue` response **as is**. Do not build it yourself.
Only when it is missing (old versions), use the `template` from `get-commit-template "{issue title}" "{issue URL}" --repo-root "{PROJECT_ROOT}"`.
- The format follows team and personal settings (the team `version.yml` format if present, otherwise the personal preference — `preferences.md`). Do not assume a format here
- `{type}` is inferred from the title tag — `fix` for a bug, `feat` for a feature, `docs` for docs. Do not rewrite it as `feat` (in a `semver_auto` repo, a bug fix would then bump the minor version)

### Step 8: Offer next-step choices

```
Issue created: #{number} — {title}
Branch name: {branch name}
Issue URL: {url}

📝 Commit message template:
{commit_template from create-issue, as is}
(When the work is done, commit using the format above as a reference — the message format follows the user's and repo's rules)

Choose the next step:
1. Create a worktree now (/pro-init-worktree)
2. Create the branch only (work in the current directory)
3. Keep working on the current branch (no branch change)
4. Later, by hand (just copy the branch name)
```

- **1** → hand the branch name to the `/pro-init-worktree` skill. Do not call raw `git worktree add` yourself — that skill handles the location rules, `#` in paths, and copying local config files
- **2** → `git checkout -b {branch name}`. In a repo where several sessions share the same tree, switching branches also changes it for the other sessions, so recommend 1 in that case
- **3** / **4** → print only the branch name, run no git command, and stop. If the repo's default is working directly on the development branch (for example working on develop), present 3 as the default choice
