# Config Rules

Every skill reads and writes its config file by the rules in this file.

---

## 1. Config file path

Config is kept in **one global file only**. Adding a skill never creates a new file.

```
{HOME}/.projectops/config/config.json
```

`{HOME}` differs by OS. Follow §2 below to find it.

---

## 2. Finding the home directory (per OS)

Before reading or writing config, check the home directory with `echo "$HOME"`. If it is empty, retry with `echo "$USERPROFILE"`.

| Returned form | OS |
|-----------|----|
| `/Users/username` | macOS |
| `/home/username` | Linux |
| `/c/Users/username` | Windows (Git Bash) |
| `C:\Users\username` | Windows (PowerShell — use `$env:USERPROFILE` instead of `$HOME`) |

---

## 3. Reading config

> ⚠️ **Never search for config.json.** The path is **fixed to one place**: `{HOME}/.projectops/config/config.json`. Read this path **directly** with the Read tool. Do not look for it with `ls`, `find`, or glob.
>
> **In particular, do not dig through harness install paths (`~/.claude/...`, `~/.codex/...`, `~/.gemini/...`, `~/.pi/...`).** Skills `find` in these paths to locate *scripts* (`*_cli.py`), but that is **for scripts only**; config.json is **not** there. Carrying that pattern over to finding config picks up the wrong file, or wrongly concludes "no config" and asks again for a PAT that is already registered (a real incident). **Scripts: `find` in install paths. Config: Read the fixed path in home. Never mix the two.**

If the file does not exist → continue with §5 interactive collection.

Each skill reads only the section for its own `skill_id`:

```
github skill    → config["github"]
synology-expose → config["synology-expose"]
ssh skill       → config["launch"]["credentials"]  (servers also live in the one pro-launch credential store — §7 `launch` section)
launch skill    → config["launch"]  (named credentials — §7 `launch` section)
```

**Automatic repo matching for the github skill (do right after reading):**

```bash
git remote get-url origin 2>/dev/null
```

Extract `owner/repo` from the result and compare it with the `repos` array:
- `https://github.com/owner/repo` → extract `owner`, `repo`
- `git@github.com:owner/repo.git` → extract `owner`, `repo`

**Repo selection order:**
1. git remote URL match → the `repos` entry where both `owner` and `repo` match
2. If no match → the entry with `default: true`
3. If neither exists → number the entries and let the user choose

If the repo is not in the config → ask the user whether to add it, and add it with the §4 procedure.

**PAT priority**: the repo entry's `pat` (non-null) → otherwise `global_pat` (§7 PAT resolution logic).

**Do not extract the PAT yourself (important).** In the past, agents pulled the PAT out with inline Python, left out the
`["github"]` namespace, and hit `KeyError`/`missing_pat` again and again. Use only one of the two paths below.

- **When calling a `<scope>_cli.py` subcommand** → do not worry about the PAT. The CLI **loads it automatically** from the
  `GITHUB_PAT` environment variable, then `config.json` (`scripts/common/config.py:get_github_pat`).
- **When calling curl directly (emergency only)** → use the `common.config.get_github_pat` function.

  ```bash
  PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
  PAT=$(PYTHONIOENCODING=utf-8 "$PYTHON" -c "import sys; sys.path.insert(0, '$PROJECT_ROOT/scripts'); from common.config import get_github_pat; print(get_github_pat('{owner}', '{repo}') or '')")
  # Empty PAT means no config → guide interactive registration with §2~5 of this document
  ```

---

## 4. Saving config (writing)

Save to `{HOME}/.projectops/config/config.json` with the Write tool. **Always Read the whole file first**, then change
only that `skill_id` section (or key) and overwrite. Never drop other sections or the PAT.

---

## 5. When there is no config — interactive collection

Collect only the sections the skill needs, **one at a time** (do not ask several at once), then save with the §4 procedure.

---

## 6. Agent judgment principles

- **When unclear, do not force a guess** — ask the user right away (one message = one question)
- **Do not ask again for information already given**
- **Always confirm before risky actions** — including overwriting config
- Apply `common-rules.md` §Masking rules to sensitive data such as PATs and tokens

---

## 7. Config schema per skill

All skill settings live in the single `config.json`, keyed by `skill_id`.
For a full example, see `skills/config.json.example`.

### `preferences` · `skills` sections (#864)

Personal expression settings shared by every skill. Merge order (later wins): `preferences` → `skills.<skill>` →
`github.repos[].preferences` → `github.repos[].skills.<skill>`. Key meanings and how they apply: `preferences.md`.
The only allowed keys are `language`, `tone`, `rules` (shared) and `template`, `preset`, `examples`, `sections` (per skill).
Safety settings such as `auto_approve` are never read from here.

```json
{
  "preferences": {
    "language": "ko",
    "tone": "concise, plain statements",
    "rules": ["prose over tables", "no emoji"]
  },
  "skills": {
    "pro-commit": { "template": "{type}({scope}): {description}", "examples": ["fix(auth): refresh token before expiry"] },
    "pro-report": { "sections": ["Summary", "Changes", "Verification"], "tone": "report style" },
    "pro-review": { "rules": ["security findings always on top"] }
  },
  "github": {
    "repos": [
      {
        "owner": "my-org", "repo": "my-repo",
        "preferences": { "language": "en" },
        "skills": { "pro-commit": { "preset": "conventional" } }
      }
    ]
  }
}
```

### `github` section

Shared by the `issue`, `commit`, `changelog-deploy`, `github`, and `report` skills.

```json
{
  "github": {
    "default_assignee": "github_username",
    "global_pat": "ghp_xxxxxxxxxxxxxxxxxxxx",
    "commit":            { "auto_approve": false },
    "issue":             { "auto_approve": false },
    "changelog_deploy":  { "auto_approve": false },
    "repos": [
      {
        "name": "Project name",
        "owner": "github_username_or_org",
        "repo": "repository_name",
        "pat": null,
        "default": true,
        "commit":            { "auto_approve": true },
        "issue":             { "auto_approve": true },
        "changelog_deploy":  { "auto_approve": true, "app_release": true }
      }
    ]
  }
}
```

| Field | Required | Description |
|------|------|------|
| `default_assignee` | ✅ | Default issue assignee GitHub username (global). `pro-github` applies it automatically when creating issues. An empty string creates issues without an assignee. If missing, ask once on the first issue and save it |
| `global_pat` | ✅ | Shared GitHub PAT for everything (repo + workflow scopes) |
| `commit.auto_approve` | — | Whether the commit skill auto-passes the commit message approval gate (global default). If `true`, show the proposed message and commit immediately. Missing → `false` (manual approval) |
| `issue.auto_approve` | — | Whether `pro-github` issue creation auto-passes the filing approval gate (global default). If `true`, show the title, labels, and local file path, then file on GitHub immediately. **Duplicate checks (steps 2-1 and 4-1) always run** — even in automatic mode, stop if a matching open issue is found. Missing → `false`. (The key name stays `issue.*` for backward compatibility — same key after the pro-issue merge) |
| `changelog_deploy.auto_approve` | — | Whether the changelog-deploy skill auto-passes the release notes approval gate (global default). If `true`, only show the body and create the PR immediately. Missing → `false` |
| `repos` | ✅ | List of repositories to use |
| `repos[].name` | ✅ | Project display name |
| `repos[].owner` | ✅ | GitHub username or organization |
| `repos[].repo` | ✅ | Repository name |
| `repos[].pat` | — | Per-repo PAT. `null` means use `global_pat` |
| `repos[].default` | — | The entry with `true` is the default repo |
| `repos[].{commit,issue,changelog_deploy}.auto_approve` | — | Auto-approval override for this repo only. Takes precedence over the global value |
| `repos[].issue.assignee` | — | A different issue assignee for this repo only. Takes precedence over `default_assignee` (global). Missing → use the global one. When the user says "the assignee for this repo is X", the agent saves it |
| `repos[].changelog_deploy.app_release` | — | Whether this repo's deploy leads straight to App Store / Play Store review (app review awareness). If `true`, the changelog-deploy skill shows a review warning banner at the release notes approval gate and applies stricter cleanup. Stored **per repo only** (no global default). If missing, the skill auto-detects it at step 1.5, confirms once, and saves. The agent updates it from natural-language replies; the user does not edit it directly |
| `repos[].changelog_deploy.{head_branch,base_branch,provider}` | — | Release branches and provider used **only in repos without version.yml**. The source of truth is version.yml (`development_branch` (old `deploy_branch`), `default_branch`, `options.changelog.provider`), decided by `changelog_cli.py detect-release-context`. If version.yml exists and these values differ, the CLI reports a `conflict` and follows version.yml (#842) |

> The global `github.changelog_deploy.{head_branch,base_branch,provider}` keys are **no longer read or written** (#842). They were a cache in which a value decided for one repo overwrote every other repo's version.yml. If they remain, they are ignored, and `detect-release-context` reports them in `config.ignored_global_keys`.

**PAT resolution logic:**
```
effective_pat = repo.pat if repo.pat else config["github"].global_pat
```

**Auto-approval resolution logic (shared by the 3 skills, in priority order):**
```
1. repos[i].{skill_id}.auto_approve   (result of matching the current owner/repo)
2. github.{skill_id}.auto_approve     (global default)
3. false                              (safe default — manual approval)
```

`{skill_id}` = `commit` / `issue` / `changelog_deploy`

> **Operating principle**: the `commit`, `issue`, and `changelog_deploy` options are designed to be updated automatically by each skill from natural-language replies (such as "proceed automatically from now on"), rather than edited by hand. A skill never shows key names or file paths to the user.

> **Migration — explicit break**: the old key `changelog_deploy.auto_approve_release_notes` is no longer recognized. If it remains in config it is ignored; to turn automatic mode back on, toggle once in conversation so that `changelog_deploy.auto_approve: true` is saved anew.

### `synology-expose` section

Used by the `synology-expose` skill.

```json
{
  "synology-expose": {
    "instances": [
      {
        "name": "NAS name (e.g. home NAS)",
        "ddns": "your-nas.synology.me",
        "domains": ["example.com"],
        "email": "your@email.com",
        "dns_provider": "cloudflare",
        "default": true
      }
    ]
  }
}
```

| Field | Required | Description |
|------|------|------|
| `name` | ✅ | NAS display name |
| `ddns` | ✅ | Synology DDNS address |
| `domains` | ✅ | Domains used for external exposure |
| `email` | ✅ | Email for SSL certificate issuance |
| `dns_provider` | ✅ | DNS provider (e.g. `cloudflare`, `route53`) |
| `default` | — | Whether this is the default among several instances |

### `ssh` section (retired — read only for compatibility)

Server connection details live in **one place: `launch.credentials` (`kind: "ssh"`)** (#841). The old `ssh` section
(`{"instances": [...]}` or a server list) is no longer used. If you have one, move it with `launch_cli.py cred import-ssh`
(`--dry-run` to preview, `--prune` to remove imported servers from the old section). The code only reads the old section's
`ssh_server` references and never writes new ones.

### `launch` section (pro-launch credentials)

Named credentials that let `pro-launch` connect to servers, registries, and organizations **without asking again**.
Servers (SSH) live here too — write host, port, user, and password (or `key_path`) directly; the password exists only in this one file.
`launch_cli.py cred set` saves them (it does not touch other sections; file mode 600), and lookups mask secret values.

```json
{
  "launch": {
    "credentials": {
      "synology": {
        "kind": "ssh",
        "host": "your-server.example.com",
        "port": 22,
        "user": "username",
        "password": "...",
        "scope": "test-only",
        "use_when": "only for server deploy QA",
        "notes": "production containers run here; only create and delete pops-qa- prefixed ones"
      },
      "dockerhub": { "kind": "dockerhub", "username": "...", "token": "...", "scope": "test-only", "use_when": "..." }
    }
  }
}
```

| Field | Description |
|------|------|
| `kind` | `ssh` · `dockerhub` · `db` · `http` · `github-org` · `other` |
| `ssh_server` | (retired, compatibility) Reference to a server `name` in the old `ssh` section. Do not write new ones — move the values with `import-ssh` |
| `use_when` · `scope` · `notes` | What the agent uses to decide **when it may use the credential**: rationale, allowed scope, cautions |
| `login_policy` | (`kind: login`) Policy for this account's intermediate login screens — table below. Takes precedence over the global default |
| Anything else | `host` · `port` · `user` · `username` · `password` · `token` · `db` … free-form |

**Intermediate login screen policy (#905)** — `launch.login_policy` (global default) and `launch.credentials.<name>.login_policy` (per account).
Each key resolves as account > global > `ask`. Save and change it only with `launch_cli.py cred policy set|unset`
(`cred set --json` merges shallowly and overwrites the whole object).

| Key | Screen type | Values |
|---|---|---|
| `trust_device` | Trust this device · don't ask again · remember this device | `ask` · `always` · `never` |
| `keep_signed_in` | Stay signed in | same |
| `skip_nags` | Prompts such as create a passkey or add contact info | same (`always` = skip) |

```json
{ "launch": { "login_policy": { "trust_device": "always", "skip_nags": "always" } } }
```

### `output` section (#525)

Shared by skills that save md artifacts (`report`, `review`, and so on).

```json
{
  "output": { "root": "docs/projectops" }
}
```

| Field | Required | Description |
|------|------|------|
| `root` | — | Artifact root. **If omitted, `docs/projectops`** (keeps the existing behavior). Relative paths are from the repository root; absolute paths also work |

`resolve_output_root()` in `scripts/common/paths.py` is the single place that resolves it.
Skills do not build path strings themselves; they go through each skill CLI's `get-output-path` — detail in `doc-output-path.md`.

### `design_brief` section (#634)

Used by `pro-design-brief`. **Do not put it under `github`** — repos that do not use GitHub also get design requests.

```json
{
  "design_brief": {
    "destination": "issue",
    "auto_approve": false,
    "projects": [
      { "match": "acme-org/myapp", "destination": "issue", "designer": "designer-id", "auto_approve": true },
      { "match": "/Users/me/work/landing", "destination": "html", "designer": "Jane Designer" }
    ]
  }
}
```

| Field | Required | Description |
|------|------|------|
| `destination` | — | `issue` (design issue) · `html` (one HTML page) · `markdown` (md + PNG folder). If missing, decided on the first run |
| `designer` | — | Designer's GitHub ID or name (issue assignee) |
| `auto_approve` | — | Skip confirmation before posting. **Default `false`** |
| `projects[].match` | ✅ | GitHub `owner/repo`, or the repo's **absolute path** (when not on GitHub) |

Resolution order: matching `projects[]` entry → section default → first-run decision. `design_brief_cli.py config show|set`
resolves and saves it — it reads the whole file and changes only that key.

---

## 8. Adding config for a new skill

When a new skill needs config:

1. Add a section to `config.json` keyed by `skill_id` (the skill folder name)
2. Document the schema in this file (§7)
3. Add an example to `skills/config.json.example`
4. In SKILL.md, point to `../references/config-rules.md` §2~3

**Never create a separate config file (such as `skill-name.config.json`).**
