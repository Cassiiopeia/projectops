# Config Rules

Every skill reads and writes its config file by the rules in this file.

## Contents

- [1. Config file path](#1-config-file-path)
- [2. Finding the home directory (per OS)](#2-finding-the-home-directory-per-os)
- [3. Reading config](#3-reading-config)
- [4. Saving config (writing)](#4-saving-config-writing)
- [5. When there is no config — interactive collection](#5-when-there-is-no-config--interactive-collection)
- [6. Agent judgment principles](#6-agent-judgment-principles)
- [7. Config schema per skill](#7-config-schema-per-skill)
- [8. Adding config for a new skill](#8-adding-config-for-a-new-skill)
- [9. Secrets: the credential store](#9-secrets-the-credential-store)

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
any secret      → config["launch"]["credentials"][name], read only through scripts/common/credentials.py (§9)
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

**PAT priority**: the repo entry's `pat` (non-null) → otherwise `global_pat` → otherwise the credential named by `global_pat_cred` (§7 PAT resolution logic, §9).

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
- Apply `sensitive-info.md` §Masking rules to sensitive data such as PATs and tokens

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
| `global_pat_cred` | — | Name of a credential store entry (field `token`) holding the shared PAT, written by `launch_cli.py cred migrate-github-pat --yes` instead of `global_pat` (§9). Read only when `global_pat` is empty |
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
                or credential_store[config["github"].global_pat_cred].token
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

### `disk-cleanup` section (#1091)

Read by the extras skill `pro-disk-cleanup` (`disk_cli.py`). Every field is optional.

```json
{
  "disk-cleanup": {
    "roots": ["~/projects", "~/work"],
    "idle_hours": 2,
    "backup_dir": "~/.projectops/backups/disk-cleanup"
  }
}
```

| Field | Required | Description |
|------|------|------|
| `roots` | | Folders searched (two levels deep) for repositories and their worktrees. Default: the folder that holds the current repository. `--roots` overrides |
| `idle_hours` | | Anything touched within this many hours is kept. Default `2` |
| `backup_dir` | | Where worktree backups go before removal (one dated folder per day). Default `~/.projectops/backups/disk-cleanup` |

### `project-blueprint` section (#1249, registry #1250, knowledge #1259)

Read by the extras skills `pro-project-blueprint` and `pro-brain`. Holds the infra values the owner reuses in every project and a
registry of the owner's projects, so a repo is set up or worked on without asking again. One section, not a sibling:
config keys are owned by skill_id (§8), and the registry's references point into this section's `infra`.
Placeholders below; the annotated shape ships as the skill's `config.sample.json`, and the lookup and write rules as
its `project-registry.md` reference.
**References and non-secret metadata only.** A `credential` field names a `launch` credential (§7 `launch`), never a
password; `secrets` lists GitHub Secret names, never values. Keep keys you do not recognize when writing.

```json
{
  "project-blueprint": {
    "schema_version": 3,
    "infra": {
      "registry": { "provider": "dockerhub", "username": "<docker-username>" },
      "dns": { "provider": "cloudflare", "root_domain": "<root-domain>", "api_host_pattern": "api.{project}.{root_domain}" },
      "traefik": { "server": "<server-name>", "internal_port": "<traefik-port>", "network": "<traefik-network>", "entrypoint": "web" },
      "servers": {
        "<server-name>": { "kind": "synology", "credential": "<launch credential name>", "host": "<server-host>",
                           "ssh_port": "<ssh-port>", "user": "<server-user>", "volume_base_path": "<volume-base>", "timezone": "<timezone>" }
      },
      "databases": {
        "<db-instance>": { "engine": "postgresql", "server": "<server-name>", "container": "<container>", "host": "<db-host>",
                           "port": "<db-port>", "default_account": "<account>",
                           "accounts": { "<account>": { "role": "<db-role>", "superuser": true, "credential": "<launch credential name>" } } }
      },
      "brains": {
        "<brain-name>": { "engine": "gbrain", "kind": "team", "mcp_url": "<mcp endpoint, optional>", "mcp_server_name": "gbrain-<project>", "server": "<server-name>",
                          "database": "<database>", "sync_script": "<path>", "notes": "<free-form>" }
      }
    },
    "defaults": { "default_branch": "main", "development_branch": "develop", "deploy_trigger_branch": "deploy", "secret_backup": true },
    "projects": {
      "<project>": {
        "status": "active",
        "repos": [{ "github": "<owner>/<repo>", "local_path": "<path>", "worktree_path": "<path>",
                    "stacks": [{ "type": "spring", "path": "server" }],
                    "branches": { "default": "main", "development": "develop", "deploy_trigger": "deploy" },
                    "secrets": { "workflow": ["DOCKERHUB_TOKEN"], "runtime_files": { "APPLICATION_PROD_YML": "server/.../application-prod.yml" } },
                    "store": { "ios_bundle_id": "<id>", "android_package": "<id>" } }],
        "deploy": { "server": "<server-name>", "services": [{ "role": "backend", "image": "<image>", "container": "<container>",
                    "blue_green": true, "volume_path": "<path>", "runtime_config": "config/application-prod.yml",
                    "health_path": "/actuator/health", "domains": [{ "host": "<domain>", "backend_port": "<port>" }] }] },
        "database": { "instance": "<db-instance>", "name": "<project>" },
        "knowledge": { "brain": "<brain-name>", "source_id": "<project>-knowledge", "sync": "repo-commit", "enabled": true, "path": "knowledge/" },
        "gbrain_entity": "<slug>",
        "notes": "<free-form>"
      }
    }
  }
}
```

| Field | Required | Description |
|------|------|------|
| `schema_version` | | `3` (version 2 = the same without the optional knowledge keys, read as is). Missing = version 1 (flat `infra` keys: `docker_username`, `ssh_server_name`, `server_host`, `postgres.*` ...); read it and convert on the next write |
| `infra.registry` / `infra.dns` / `infra.traefik` | | Shared values filled into workflow `env:` blocks and GitHub Secrets of a new repo. Asked once, one at a time, when missing |
| `infra.servers.<name>` | | One entry per server; `credential` names the launch credential `pro-ssh` uses, so connection secrets are not duplicated |
| `infra.databases.<instance>` | | One entry per database instance. `default_account` is the account projects use when they name none (default practice: one shared owner account, one database per project) |
| `defaults.*` | | Branch names and options the user picked once; used as the answers to the projectops install questions |
| `projects.<key>` | | Registry entry per project. Agents match the current repo by git remote (`repos[].github`) or path (`local_path`, `worktree_path`) before asking anything, and write the entry when a project is set up. Every field is optional; absent = unknown |
| `projects.<key>.deploy.server`, `.database.instance`, `.database.account` | | Names of `infra.servers` / `infra.databases` / `accounts` entries, never copies of their values |
| `projects.<key>.status` | | `active` or `archived` |
| `infra.brains.<name>` | | One entry per brain: `engine` (`gbrain`), `kind` (`team` or `personal`), `mcp_url` (endpoint only, omitted when none; never a token), `mcp_server_name` (hint for pro-brain's team-brain answer, e.g. `gbrain-<project>`; the repo switch `team_brain` is the shared truth), `token_cred` (name of the credential store entry holding the brain token, §9), `server`, `database_instance`, `database`, `sync_script`, `notes`. References only |
| `projects.<key>.knowledge` | | `brain` (an `infra.brains` name), `source_id` (default `<key>-knowledge`), `sync` (`repo-commit`), `enabled`/`path` (owner intent only). The on/off switch itself is the repo's `version.yml` `metadata.template.options.knowledge`; `pro-brain` never connects to a brain |

### `image` section

Read by `pro-image` (`image_cli.py`). Every field is optional. Without `priority`, the skill asks the user once and saves it.

```json
{
  "image": {
    "priority": ["codex", "antigravity", "claude-vector"],
    "require_subscription": true,
    "harness_dir": "docs/image-harness",
    "providers": {
      "codex": { "args": ["exec", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check", "--enable", "image_generation"], "timeout_seconds": 900 },
      "my-tool": {
        "kind": "command",
        "command": "my-image-cli",
        "args": ["--prompt-file", "{prompt_file}", "--out", "{out_file}", "{refs}"],
        "supports_alpha": false,
        "attaches_references": true
      }
    }
  }
}
```

| Field | Required | Description |
|------|------|------|
| `priority` | | Image tools in the order to try. Built in: `codex` (ChatGPT subscription), `antigravity` (`agy`, free or Pro Google account), `claude-vector` (the agent draws SVG) |
| `require_subscription` | | `true` (default) refuses Codex when it is signed in with an API key, and strips API key variables when running it. Built-in tools run without approval prompts (Codex `--dangerously-bypass-approvals-and-sandbox`, Antigravity `--dangerously-skip-permissions`) in a scratch run folder outside the repo; override `providers.<name>.args` to restrict them |
| `harness_dir` | | The repo's art harness folder, relative to the repo root. Default `docs/image-harness` |
| `providers.<name>` | | Overrides a built-in tool or adds one. `kind`: `codex` · `command` · `agent`. Placeholders: `{prompt_file}` `{prompt_text}` `{run_dir}` `{out_dir}` `{out_file}` `{size}` `{timeout_seconds}`, a lone `"{refs}"` = every reference path. `harvest_globs` collects files a tool saves elsewhere |

### `skill-bug` section (#997)

Read by the extras watch hook (`plugins/projectops-extras/hooks/skill_bug_watch.py`). Without the section, automatic reports are on.

```json
{
  "skill-bug": {
    "auto_report": false
  }
}
```

| Field | Required | Description |
|------|------|------|
| `auto_report` | | `false` stops the hook from asking the agent to file suspected projectops bugs. Default `true` |

### `ssh` section (retired — read only for compatibility)

Server connection details live in **one place: `launch.credentials` (`kind: "ssh"`)** (#841). The old `ssh` section
(`{"instances": [...]}` or a server list) is no longer used. If you have one, move it with `launch_cli.py cred import-ssh`
(`--dry-run` to preview, `--prune` to remove imported servers from the old section). The code only reads the old section's
`ssh_server` references and never writes new ones.

### `launch` section (pro-launch credentials = the credential store)

This is the **credential store** every skill uses for secrets (§9); the key stays `launch.credentials` for compatibility.
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
| `kind` | `ssh` · `dockerhub` · `db` · `http` · `github-org` · `token` (an API or MCP token for one service: `provider` + `token`) · `login` · `local` · `other` |
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

### `ui-design` section (#634, #1080)

Used by `pro-ui-design`. **Do not put it under `github`** — repos that do not use GitHub also get mockups and design requests.
Style (language, tone, rules) stays in `preferences` · `skills.pro-ui-design`; project knowledge (token files, fonts) stays in the repo-scoped harness `ui-design`.

```json
{
  "ui-design": {
    "destination": "issue",
    "auto_approve": false,
    "devices": ["phone", "tablet"],
    "projects": [
      { "match": "acme-org/myapp", "designer": "designer-id", "devices": ["phone"] },
      { "match": "/Users/me/work/landing", "destination": "html", "devices": ["desktop"] }
    ]
  }
}
```

The option table (names, types, allowed values, defaults) has one source: `ui_design_cli.py config options`. Do not copy it here. Adding an option is one row in `pro_ui_design/options.py`.

| Field | Required | Description |
|------|------|------|
| any option from `config options` | — | Section default, or per project inside `projects[]` |
| `projects[].match` | ✅ | GitHub `owner/repo`, or the repo's **absolute path** (when not on GitHub) |

Resolution order: matching `projects[]` entry → section default → the old `design_brief` section (read only) → the table's default. `destination` and `designer` have no default and are asked on first use.
`config show` reports each value's source, invalid stored values (`invalid`, falls back) and unknown keys (`ignored`, kept in the file). `config set` reads the whole file, changes only that key, and writes only to `ui-design`.

### `presentation` section (#1097)

Used by `pro-presentation`. Style (language, tone, rules) stays in `preferences`; how the user likes to speak lives in
`~/.projectops/presentation/memory.md` (copied into each new deck's `memory.md`), not in config.

```json
{
  "presentation": {
    "language": "ko",
    "time_limit_seconds": 600,
    "export_formats": ["pdf", "pptx"],
    "projects": [
      { "match": "acme-org/pitch", "deck_root": "docs/talks", "time_limit_seconds": 300 }
    ]
  }
}
```

The option table has one source: `presentation_cli.py config options` (`pro_presentation/options.py`). Do not copy it here.
Resolution order: matching `projects[]` entry → section default → the table's default. `config set <name> <value> [--project P]`
reads the whole file, changes only that key, and writes only to `presentation`.

---

## 8. Adding config for a new skill

When a new skill needs config:

1. Add a section to `config.json` keyed by `skill_id` (the skill folder name)
2. Document the schema in this file (§7)
3. Add an example to `skills/config.json.example`
4. In SKILL.md, point to `../references/config-rules.md` §2~3

**Never create a separate config file (such as `skill-name.config.json`).**

---

## 9. Secrets: the credential store

Every secret (password, token, API key, PAT) has **one home**: a named entry in the credential store,
`config["launch"]["credentials"][<name>]` in this same file (mode 600). Skills do not invent new secret fields or files.

| Rule | How |
|---|---|
| Store | One named entry per secret: `kind`, the value field (`token`, `password`, `api_key` ...) and non-secret `provider`, `use_when`, `scope`, `notes`. Names: letters, digits, `._-`, e.g. `gbrain-<project>` |
| Reference | Another section names the entry, never holds the value: `"credential": "<name>"`, or a key ending `_cred` / `_credential` (`"token_cred": "gbrain-secbrief"`, `github.global_pat_cred`). Non-secret facts (URLs, server names) stay in the skill's own section |
| Read | Code reads only through `scripts/common/credentials.py` (`read_secret(name, field)`); extras skills use the copy generated by `scripts/sync_extras.py`. The value goes to the next program through an environment variable or stdin, never into argv, stdout, logs, notes, commits, `version.yml` or the repo |
| Save | The user types the value, not the chat: `launch_cli.py cred set --name <name> --secret-field token --prompt` (hidden input in a terminal) or `--from-env <VAR>`. `--json` is for non-secret fields |
| Rotate | Save the new value under the same name (`cred set ... --secret-field token --prompt`); every reference follows. Re-run whatever registers the value elsewhere (e.g. `brain_cli.py connect --team --rotate`) |
| New machine | Copy `config.json` (mode 600) or re-enter each name the check reports missing |
| Check | `launch_cli.py cred check` (read only): references whose entry is missing, entries nothing references (names and paths only). Unreferenced is not unused: pro-launch commands take names directly (`--cred`) |
| Migrate the GitHub PAT | Optional, only after the user says yes: `launch_cli.py cred migrate-github-pat` plans, `--yes` moves `github.global_pat` into the entry `github-global-pat` and writes `github.global_pat_cred`. The read path is unchanged (`get_github_pat` still reads `global_pat` first); releases before this one read only `global_pat` |

Existing fields stay readable: `github.global_pat`, `github.repos[].pat` and the Figma `provider: figma` entry keep working as they are.
A new skill that needs a secret follows this section instead of adding a field (ARCHITECTURE.md "How to add a skill" #9).
