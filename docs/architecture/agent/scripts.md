# Core script rules

> **When to read:** when you touch `.github/scripts/` (version · changelog · build number · issue helper · initializer) or `.sh` files, or add a template-only file at the repo root
> Canonical text split out of `CLAUDE.md`. `CLAUDE.md` keeps only a summary and a link to this document.

## Core scripts

### version_manager (.py holds the logic, .sh is a delegating shim — #448)
```bash
.github/scripts/version_manager.sh get            # or: python .github/scripts/version_manager.py get
.github/scripts/version_manager.sh increment       # patch +1 (default)
.github/scripts/version_manager.sh increment --bump minor   # 4.2.45 → 4.3.0
.github/scripts/version_manager.sh increment --bump major   # 4.2.45 → 5.0.0
.github/scripts/version_manager.sh set 2.0.0
.github/scripts/version_manager.sh sync
.github/scripts/version_manager.sh get-code
.github/scripts/version_manager.sh increment-code
```
> Since v4.2 the logic lives in `version_manager.py` (stdlib only — no yq/jq needed) and `.sh` is a shim that delegates to Python. On Windows, run `python .github/scripts/version_manager.py get` directly. **The integrator copy list must contain both the `.sh` and the `.py` of each pair** (same for `truncate_release_notes.*`).

#### ⚠️ Automatic semver bump axis (#546 — agent must read)

The bump size on release is set by `metadata.template.options.semver_auto` in `version.yml`.

| Value | Behavior |
|---|---|
| **Key missing** (all previously integrated repos) | Always `patch +1` — the old behavior |
| `true` | Major/minor/patch decided from the commit subjects in the release range |
| `false` | Always `patch +1` |

- **When the key is missing, both new and existing repos are recorded as `true`.** (Old policy: existing repos were left at `false`, changed by owner decision.)
  To keep versions from jumping without notice, **the completion screen warns the first time an update turns it on**
  (`semverAutoNewlyOn`). A saved value is always respected, including an explicit `false`.
- **The wizard does not ask about this axis** (keeping the #485 direction of fewer questions). To turn it on, edit `version.yml` directly.
- For the decision rule and commit-type mapping, see the "Required commit conventions" section. `version_code` goes up by 1 on every release
  regardless of this option.
- **`PROJECT-COMMON-VERSION-CONTROL` (direct push to main) also follows `semver_auto` (#805, #815).** When it is on,
  major/minor/patch is decided from the commit subjects in the pushed range whether or not a development branch exists; only an explicit `false` means patch.
  (This path used to be fixed at patch, so the option was silently ignored. The earlier reason, "commit conventions cannot be trusted", was dropped by owner decision.)
- The VERSION-CONTROL guard detects a release merge by **a change to the `version:` value, not by the `version.yml` file name** (#806).
  A push that only changes settings is not a release, so the version is bumped.

### Build numbers and iOS upload decisions (#643, agent must read)

The app build number and the interpretation of Apple upload errors are **each decided in exactly one place**. Do not re-implement number calculation or grep for error text in workflow yaml.

| What | Where | Rule |
|---|---|---|
| Build number | `.github/scripts/build_number.py` | `max(seconds since 2024-01-01 UTC, latest ASC number + 1, number required by the rejection message + 1)`. Shared by iOS test, iOS release and Android test |
| Apple upload error interpretation | `.github/scripts/ios_release.py classify-error` (rules in `ios_release_rules.py`) | Classified as `duplicate` / `too_low` / `train_closed` / `other`, plus `is_upload_reported_ok` when altool said the upload succeeded. Whether to retry is decided from this classification too |

- `version_code` is **for Android releases only** (Play Store, Firebase CICD). Do not use it for iOS or test build numbers.
- **To handle a new Apple error code (ITMS-...)**, add a pattern to `classify_upload_error` based on the **actual error text**. Do not make up the text.
- An iOS release on a closed version fails without changing the version name. Only test builds move on to the next patch.

### changelog_manager.py
```bash
python3 .github/scripts/changelog_manager.py update-from-summary
python3 .github/scripts/changelog_manager.py generate-md
python3 .github/scripts/changelog_manager.py export --version 1.2.3 --output release_notes.txt
python3 .github/scripts/changelog_manager.py classify-bump --commits-file commits.txt  # major|minor|patch
```

### changelog_providers/ (release note generation ladder — all .py, #455 · #566)

The fallback-summary job of `RELEASE-CHANGELOG` calls `ladder.py`. **The wizard does not ask for a provider** (#566) — the user's goal is "good release notes", not picking a generator.

**Generation ladder** (tried from the top, falling down on failure)

| Order | Path | Condition | Cost |
|---|---|---|---|
| ① | Use the PR body as is if it already has one | Written by the deploy skill, CodeRabbit or a person | — |
| ② | `openai_compatible.py` | Only when an AI key is registered | Free tier possible |
| ③ | `commit.py` — commit analysis | When the above fails | **Free, unlimited** |
| (separate) | `copilot.py` — Copilot CLI | Only when `provider: copilot` is **set explicitly** | **Uses Premium Requests** |

> **⚠️ Never put a paid element on the default path (#569).** Copilot bills per request, so it was
> removed from the default ladder. This template is installed in other people's repos, so **it must never incur costs
> without the installer knowing.** The default is always "the one that costs nothing".

**Register AI keys under service-specific names** — with a single `MODEL_API_KEY`, neither people nor code
could tell which service it was for.

| Secret name | Service | Free |
|---|---|---|
| `GEMINI_API_KEY` | Google Gemini | ✅ 500 per day |
| `GROQ_API_KEY` | Groq | ✅ |
| `MISTRAL_API_KEY` | Mistral | ✅ |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | OpenAI / Anthropic | ❌ |
| `MODEL_API_KEY` | Old name — service guessed from the key prefix | Backward compatibility |

**④ depends on neither AI nor network, so it always completes.** Every path ends with `commit`, so "empty release notes" never happens.

| Saved provider value | Behavior |
|---|---|
| Unset | `coderabbit` if the repo root has `.coderabbit.yaml`, otherwise `commit`. Either way, if a key exists the ladder picks the external AI automatically (#821) |
| `copilot` | Copilot → (Gemini if a key exists) → commit |
| `openai`/`gemini`/`claude`/`groq`/`mistral`/`ollama` | That provider → commit (needs `MODEL_API_KEY`; ollama needs `changelog.base_url`) |
| `github-ai` | **Service shut down (2026-07-30)** — never called, silently absorbed, migrated to `commit` on update |
| `coderabbit` | Does not wait. A summary in the body is simply respected at ① |

> The unset decision (explicit value → `.coderabbit.yaml` → `commit`) must follow **the same rule in two places**: the workflow's "Read version info" step and `_read_release_branches` in `changelog_cli.py`.

> **⚠️ Never pin a version in a model name (#566).** `gemini-1.5-flash` had been dead with 404. The presets in `openai_compatible.py` use `-latest` aliases. The gemini default is **`gemini-flash-lite-latest`**, because on the free tier the higher Flash has an RPD of 20 while Lite has 500, so Lite is the only one usable for automation (measured).
>
> **⚠️ Never make an external service the default.** The default paths (①, ②, ④) need no external API key. This template is installed in other people's repos, so it must never demand a key or incur charges without the installer knowing.

**Generation notice** (`changelog_notice.py`): records which path produced the notes in the Job Summary every time, and comments on the PR with alternatives **only when no AI could be used at all**. The comment is updated through a marker, so the email notification goes out only the first time — a notification on every release becomes noise, and noise is something nobody reads.

The npx copy engine (`src/core/copy/simple.js`) copies the provider .py files into the user's project — **when you add a new provider, add it to the copy list too** (if it is missing, the import fails in user repos).

### issue_helper.py (issue branch/commit comment — brought in-house in #478)
`PROJECT-COMMON-SUH-ISSUE-HELPER.yaml` runs it when an issue is created or its title is edited. No external action dependency (stdlib only).
Settings: `version.yml` `metadata.template.options.issue_helper` (branch_prefix/commit_template/commit_type_map/timezone/show_guide, etc. — defaults when missing).
The branch core (`YYYYMMDD_#number_title`) and the `### 브랜치` code block in the comment are an immutable contract — the consumer list is in `docs/BRANCH-CONVENTION.md`.
The signature text is the `guide_signature` setting (default `Guide by ProjectOps`), and the old text `Guide by SUH-LAB` that older consumers look for is always kept as a hidden comment (#749).
Custom settings from the old MODULE workflow are migrated automatically (`rules/settings-extractors.js`).

### template_integrator.sh / .ps1 — removed (EOF #458 → deleted #800)
**Both scripts became notice-only shims in v4.3.0, and #800 deleted the files themselves.** The old `curl .../template_integrator.sh | bash` now returns 404. Do not write line numbers or function names of the deleted scripts (`equivalent to .sh L1234`) in `src/` comments — the file they point to does not exist. Write reasons in the present tense (#916).
Integration, updates and skill installation all go through one path: **`npx projectops`**. The npx wizard asks for every option (deploy/publish axes, secret backup, etc.), and the chosen values are saved identically in `metadata.template.options.*` of `version.yml`.

**Template-only files that are not copied on initialization/integration**:
```
CLAUDE.md, CONTRIBUTING.md, LICENSE
CHANGELOG.md, CHANGELOG.json
docs/, .github/scripts/test/
.claude-plugin/, .codex-plugin/, .agents/, .cursor/, skills/, scripts/
package.json, harness/         # pi package manifest + Persona Harness
plugins/                       # optional extras plugin (projectops-extras)
hooks/                         # Claude Code plugin hooks (return pro-launch devices at session end #953 · block raw device commands #954)
```

#### ⚠️ When adding a "marketplace/template-only" file or folder at the repo root (agent must read)

This repo has **two identities** at once — that is the key difference from an ordinary repo.

1. **Template repo**: when a new project is created with GitHub "Use this template", `.github/scripts/template_initializer.py` (.sh is a delegating shim) **deletes** the marketplace/template-only files.
2. **Wizard source**: when `npx projectops` (src/) integrates the template into an existing project, those files are **excluded from copying** (`src/core/exclusions.js`).

So if you add a new file/folder at the repo root that **only makes sense in this repo and must not flow into user projects** (plugin manifests, skills, pi package files, internal docs, etc.), **you must edit the two places below together (plus the third when needed)**. Fixing only one either pollutes new projects or makes the wizard copy unneeded files — a trap that is missed often in practice.

| # | File | Where to edit | Effect |
|---|------|------------|------|
| 1 | `.github/scripts/template_initializer.py` | Delete list `CLEANUP_TARGETS` (near the `CHANGELOG.json` entry) | Add a `("file name", "description")` entry (**delete**) |
| 2 | `src/core/exclusions.js` | Exclusion arrays such as `DOCS_TO_REMOVE` | Add the file/folder name (**excluded from copying**) |
| 3 | `.github/workflows/PROJECT-TEMPLATE-PLUGIN-VERSION-SYNC.yaml` | Version sync step + `git add` | For a manifest with a version field (`package.json`, etc.), add a sync step |

> (The `plugin_items_to_remove` array of the old `template_integrator.sh`/`.ps1` went away with the #458 EOF — npx `exclusions.js` is now the only copy-exclusion point.)
>
> **Check order**: add a new root file → ask "does the user's project need this too?" → **if not, edit both 1 and 2 above**. If it is a manifest whose version must match `version.yml`, add 3 too. Afterwards verify with `python -m py_compile .github/scripts/template_initializer.py` and `npm test` (watch checks).
>
> **Conversely**, if what you added is a shared asset that must go to user projects too (workflows, scripts, settings), do not add it to the lists above — excluding it means integrated projects never receive the feature.

#### ⚠️ macOS is bash 3.2 + BSD tools — never forget this when writing or verifying `.sh` (agent must read, measured)

> **Key point: something that runs fine on Windows (`.ps1`, Git Bash) can break on macOS.** The default macOS `/bin/bash` is **frozen at 3.2.57 (2007)** for licensing reasons, and the default grep/sed are **BSD flavored**. Always verify `.sh` with **`/bin/bash` (3.2) + BSD tools**. "Tested only on Windows" is the main reason real user (macOS) bugs were missed entirely. (Measured: issues #415 and #418 — fine on Windows, broken only on macOS.)

**Not available in bash 3.2 (4+ only → silently misbehaves on macOS)**
- **No associative arrays (`declare -A`).** bash 3.2 does not support them → every string key **collapses to index 0** and you get a "only one key left" bug (measured #418: 6 @wizard env keys, only 1 collected). For dynamic key-value data, use eval dynamic variables + a hex key-encoding helper (the old integrator's `_kv_*` pattern, works on 3.2 and 4).
- **No `declare -g`.** bash 3.2 reports `invalid option`. At the top level it is global anyway, so declare without `-g`.
- `mapfile`/`readarray`, `${var,,}`/`${var^^}` (case conversion) and `&>>` are 4+ only too → do not use them.

**BSD tool traps (macOS default grep/sed ≠ GNU)**
- **No `grep -P`/`-oP`/`\K`** (PCRE is GNU only). Match lines with `grep -E` and extract with `sed -E`. (Measured #415: version detection failed with `grep: invalid option -- P`.)
- **`grep` exits 1 on zero matches** → under `set -e`, a bare `var=$(grep ...)` assignment kills the script. Absorb it with `|| true` or end with a `| head`/`| sed` pipe (without pipefail only the last command's code counts). (Measured #415.)
- `sed -i` takes different arguments on BSD: `sed -i ''` / `sed -i.bak`. `readlink -f`, `date -d` and `xargs -r` are not supported on BSD either.

**`set -e` + exit code at the end of a function (applies to ordinary functions too, not only menus)**
- Generalization of the "var=$(menu_fn)" trap above: **if a function's last command is non-zero** and that function is the caller's last command, `set -e` kills the whole script. `[ -d x ] || return` (propagates 1 when the folder is missing), `[ cond ] && cmd` (1 when the condition is false), `command -v foo && ...` (1 when not installed) and `cp ... && ...` (1 on failure) are all risky. → Write `return 0` explicitly for early returns, and wrap a trailing `condition && command` as `{ ...; } || true`. (Measured #415: 5 places including the Nexus/Secret menu, interactive_mode, codex removal and config cp.)

**How to verify**: `bash -n` (syntax) alone is not enough. **Always actually run it with `/bin/bash` (3.2).** Pull out just the function, `source` it and call it with real input to confirm it **completes with exit code 0**. If `which bash` points to brew bash (`/opt/homebrew/bin/bash`, 4+), run `/bin/bash` explicitly to force 3.2.
