# Before you start — PAT · auto approval · app review · branch/provider resolution and config records

> When to read: when you first resolve the values in [Before you start] §2~§5; when you must ask the user about branches (only for repos without version.yml) or app review and record the answer in the config; when `detect-release-context` reports a `conflict`; when the user asks to reconfigure ("change the deploy branch" / "change how release notes are made" / "ask me first" — Korean: "배포 브랜치 바꿔줘" / "릴리스 노트 방식 바꿔줘" / "확인받게 해줘").

**Config file location**: `~/.projectops/config/config.json` (one global file). Path rules in detail: `../../references/config-rules.md §2~3`.

**To update the config, always** follow `../../references/config-rules.md §4`: Read the whole file first, keep the other sections, add or change only the target key, and Write it back. Never drop the PAT, other repos entries, or existing `auto_approve`/`app_release`/branch values. If an entry has no `changelog_deploy` object, create one.

**Talk to the user in plain language only, in the user's language.** Never put key names or file paths such as "auto_approve", "config.json" or "the changelog_deploy section" in a user message. The user states intent in plain words such as "go ahead automatically" / "ask me every time", and the agent updates the config itself.

## §2 PAT extraction — the agent reads it directly with the `Read` tool (no bash Python extraction)

> In Windows Git Bash, `$HOME` is `/c/Users/...` (a POSIX path), so native Windows Python `open()` cannot open the file → PAT extraction fails (NO_PAT). This is a verified bug. So **the agent reads the config file directly with the `Read` tool** to get the PAT; this works regardless of OS or shell interpolation.

1. Read the config file with the `Read` tool. **Look only at this one fixed path. Do not search with `ls` or glob, and do not dig through the plugin cache (`~/.claude/plugins/cache/...`, scripts only). The config is not in the cache.**
   - Windows: `C:\Users\<user>\.projectops\config\config.json`
   - macOS/Linux: `~/.projectops/config/config.json`
   - If the file does not exist → tell the user "❌ No PAT. Register the config (PAT) with `/pro-github` first." and stop.
2. Pick the PAT from the `github` section:
   - the entry in `repos[]` with `repo == REPO` and a non-null `pat`
   - otherwise `global_pat`
   - if neither exists → same message as above, and stop.
3. **Remember** the PAT value. (A PAT is `ghp_` + alphanumerics, so no quote escaping is needed.)

## §3 Auto approval mode — `changelog_deploy.auto_approve`

Decide from the same content read in §2. Take the first value found:

1. `changelog_deploy.auto_approve` of the `github.repos[]` entry with `owner == OWNER && repo == REPO`
2. `github.changelog_deploy.auto_approve` (global default)
3. If neither exists, `false` (safe default — manual approval)

> **The old key `auto_approve_release_notes` is an explicit break.** It is no longer recognized and is ignored even if it remains in the config. To get auto mode, store a new `auto_approve: true` through a one-time toggle request.

Values to remember: `AUTO_APPROVE` (boolean), `CONFIG_HAS_KEY` (`true` if the key was found in 1 or 2, otherwise `false` for a first run). `CONFIG_HAS_KEY=false` triggers the **first-run automation offer (C)** in deploy step 5.5 / fix step 4.5.

**Handling toggle requests**
- If a user who saw the auto-mode notice says "ask me first", "switch to manual", "ask me next time" (Korean: "확인받게 해줘", "수동으로 바꿔줘", "다음부턴 확인받아줘"), update the config **before** creating the PR: if the key existed at priority 1 (per repo), set that value to `false`; otherwise set priority 2 (global) to `false`. After the update, keep the body as is and get the user's approval again (switch to the manual branch).
- Answer to the first-run automation offer (C): **1** → `changelog_deploy.auto_approve: true` on the current OWNER/REPO entry in `github.repos[]` / **2** → `github.changelog_deploy.auto_approve: true` (create the object if missing) / **3** → `github.changelog_deploy.auto_approve: false` (keep the key itself so the next run does not ask).

## §4 App review awareness — `changelog_deploy.app_release`

Decide the value for the current OWNER/REPO entry from the same content read in §2:

1. `changelog_deploy.app_release` of the `github.repos[]` entry with `owner == OWNER && repo == REPO`
2. If it does not exist anywhere, **no key** (first run — detect in step 1.5 and confirm once)

Value to remember: `APP_RELEASE` — `true` / `false` / `unset`. Used in step 1.5 and by the review warning banner in step 5.5.

> There is no global default (`github.changelog_deploy.app_release`). Whether a repo goes to app review differs per repo, so it is remembered **per repo only**.

Answer to the step 1.5 confirmation: **1 (yes, app review)** → `app_release: true` in `changelog_deploy` of the current OWNER/REPO entry, and the review warning banner applies from this deploy on / **2 (regular deploy)** → `app_release: false`, continue without a warning and do not ask again.

## §5 Release branch · provider resolution

**The source of truth is `detect-release-context` (version.yml) (#842).** The workflow (RELEASE-CHANGELOG) also reads version.yml, so the skill must look at the same place or the decisions diverge. The config is only a per-repo record for repos **without** version.yml.

**Priority:**

| Rank | Source | When | `branches_source` |
|---|---|---|---|
| 1 | version.yml (`development_branch` (old `deploy_branch`), `default_branch`, `changelog.provider`, with fallbacks) | **always** when version.yml exists | `version.yml` |
| 2 | `changelog_deploy.{head_branch, base_branch, provider}` of the current OWNER/REPO entry in `github.repos[]` | **only without** version.yml | `config` |
| 3 | Fallback `develop` → `main`, provider three-step rule | when neither 1 nor 2 exists → record in 2 after the first-time resolution | `fallback` |

> **The global `github.changelog_deploy.{head_branch, base_branch, provider}` is not read.** Keeping repo knowledge machine-wide overrides other repos' version.yml (#842, a real incident — a global `develop/main/commit` ignored settings that differed per repo). If those keys remain, the CLI only reports them in `config.ignored_global_keys` and does not use the values. **Do not write them either.** `auto_approve` in the same object still works as the global default (§3).

The CLI does the resolution. The agent does not read the branch keys from the config separately and recompute the priority. The CLI **only reads** the config, the same way it auto-loads the PAT (`../../references/config-rules.md §3`).

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/changelog_cli.py detect-release-context --project-root "{PROJECT_ROOT}"
# owner/repo come from the origin URL and the config from its fixed path. Override with --owner · --repo · --config if needed.
```

Values to remember from the output:

- `HEAD_BRANCH` = `branches.head`, `BASE_BRANCH` = `branches.base`, `PROVIDER` = `branches.provider`
  (`commit`|`copilot`|`openai`|`gemini`|`claude`|`groq`|`mistral`|`ollama`|`coderabbit`. The CLI returns `github-ai` as `commit`)
- `BRANCH_SOURCE` = `branches_source` (`version.yml` | `config` | `fallback`)
- `conflict` — the list of keys where version.yml and the per-repo config differ (`key`·`version_yml`·`config`·`version_yml_explicit`)

### When `conflict` is not empty

**Go with the version.yml value.** The per-repo config value is a stale record from before version.yml existed or changed. Tell the user in one plain-language line (no keys or paths):

```
ℹ️ The release setup I remembered before ({config value}) differs from the repository settings ({version.yml value}), so I am following the repository settings.
```

- If `version_yml_explicit == false`, version.yml does not contain that key and the comparison was against the fallback value. In that case add at the end of the message: "Writing the value into the repository settings avoids this confusion."
- Do not fix the config automatically. If the user wants it cleaned up, delete only that key in that repo entry (the config update rules in §4).

### First-time resolution (only when `BRANCH_SOURCE == fallback` and there is no version.yml)

If version.yml exists (even with fallback values), you never get here. There is a source of truth, so do not ask and do not record.

**Resolve the branches:**
- If `develop` exists on the remote and the default is `main` → settle on the standard layout silently.
- Otherwise (no develop, default is not main, or anything unclear) → ask in plain language and resolve head/base from the answer:
  ```
  Which branch does this repository release from, and into which branch?
  (e.g. from the development branch into the deploy branch)
  1. develop → main (standard)
  2. Tell me directly (e.g. "from the release branch into the production branch")
  ```

**Resolve the provider (do not ask):**
- Use `branches.provider` as is. The CLI already applied the three-step rule: ① explicit `changelog.provider` in version.yml → that value ② unset + `.coderabbit.yaml` at the repo root → `coderabbit` (keeps the existing behavior of repos that use CodeRabbit) ③ neither → `commit`.
- The workflow uses the same rule, so the skill and the workflow never disagree. If you change the rule, change both places together (`changelog_cli.py` `_normalize_provider`, and the workflow step "버전 정보 확인" (version info check)).

**Record in the config:** Write the resolved `head_branch`/`base_branch`/`provider` into `changelog_deploy` of the current OWNER/REPO entry in `github.repos[]`. If there is no entry, create one (`owner`·`repo`·`name`, `pat: null`). **Do not write to the global `github.changelog_deploy`.**

After recording, tell the user in plain language only (no keys or paths):
```
✅ I will remember how this repository releases ({HEAD_BRANCH} → {BASE_BRANCH}, {provider in plain words}).
   To change it, say "change the deploy branch" or "change how release notes are made".
```
(Provider in plain words: commit → "commit analysis (AI if an AI key exists)", copilot → "generated by Copilot", openai/gemini/claude/groq/mistral/ollama → "generated by AI", coderabbit → "respects the CodeRabbit summary, otherwise commit analysis")

> **Handling reconfigure requests**: when the user says "change the deploy branch" / "change how release notes are made" (Korean: "배포 브랜치 바꿔줘" / "릴리스 노트 방식 바꿔줘"):
> - Repo with version.yml → do not write to the config. Explain in plain language that the repository settings (version.yml `development_branch`·`default_branch`·`changelog.provider`) must change so the workflow changes with them, and edit that file if the user wants.
> - Repo without version.yml → ask the question above again and update that key in the per-repo config.

### Provider values for reference

- Values: `commit` (default) / `copilot` / `openai`·`gemini`·`claude`·`groq`·`mistral`·`ollama` / `coderabbit`.
- `github-ai` is **shut down (2026-07-30)**. Even if a stored value remains, the CLI returns `commit` (an update migrates it to `commit`).
- Workflow ladder: ① if the PR body has release notes, use them as is → ② the configured provider (or AI if an AI key exists) → ③ commit (always completes). `coderabbit` is not waited on; it is only respected at ①.
