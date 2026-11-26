---
type: issue-knowledge
id: "issue-1288"
title: "Installer copies every script a template workflow calls; iOS multi-target apps keep per-target profiles"
created: 2026-11-27
topics: ["installer", "workflows", "ios", "scripts"]
status: active
related: []
supersedes: []
source: "https://github.com/Cassiiopeia/projectops/issues/1288"
deploy_version: "4.120.2"
capture_mode: "issue-end"
captured_at: "2026-11-27T07:46:14+09:00"
captured_by: "pro-brain"
project: "projectops"
stacks: ["basic"]
app_version: "4.120.1"
build_number: 650
issue: 1288
issue_url: "https://github.com/Cassiiopeia/projectops/issues/1288"
pr: 1289
pr_url: "https://github.com/Cassiiopeia/projectops/pull/1289"
commit_base: "017d5cd1e64f7df46fdb3e29aaaa15bd0b6038c3"
commit_head: "e73a5706d82396734e2366bdf096e2c9b9421869"
commit_count: 1
merge_commit: "3fdf6a9bffa3788286c658a65c3966f25ea5caae"
changed_modules: [".github", "docs", "src"]
main_files: ["src/core/copy/script-references.js", ".github/scripts/ios_release_rules.py", ".github/workflows/project-types/flutter/PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml", ".github/workflows/project-types/flutter/PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml", "src/core/copy/simple.js", "docs/en/flutter-testflight-wizard.md", "docs/FLUTTER-TESTFLIGHT-WIZARD.md", "docs/architecture/agent/scripts.md"]
lines_added: 234
lines_deleted: 15
env_or_secret_names: ["APPLE_EXTENSION_PROVISIONING_PROFILE_BASE64"]
---

# Installer script guard, APP_ROOT steps, multi-target iOS signing, pycache

## Summary
A Flutter monorepo (`client/`) with an iOS widget extension hit four defects after updating from 4.6.0 to 4.119.0. All four are fixed in 4.120.2: missing scripts, Play Store steps run from `APP_ROOT`, one provisioning profile forced onto every iOS target, and `__pycache__` in release commits.

## Background
- `copyScripts()` copies a hand-kept list. `firebase_config_files.py` and `toolchain_versions.py` (in the template since 2026-10-22) were never added, so every updated Flutter repo stopped at the Firebase config step.
- Flutter jobs default to `working-directory: ${{ env.APP_ROOT }}`. Two PLAYSTORE steps called `.github/scripts/store_deploy_config.py` relatively, which only works when `APP_ROOT` is `.`.
- `xcodebuild archive PROVISIONING_PROFILE_SPECIFIER=X` applies X to every target, so an app extension got the app profile.

## Decisions
- **Guard in the installer, not a watch test.** The repo keeps five watch tests and new ones need the owner's sign-off. `collectReferencedScripts()` derives scripts from the `project-types/` workflows at install time (literal `.github/scripts/<path>` and `$SCRIPTS_DIR/<path>`, then local imports and sibling `*.py`/`*.sh` names), and the result is unioned with the documented list. The list stays so each script keeps a reason.
- **Omit the profile override instead of passing `$(inherited)`.** Omitted when the name is empty, `$(inherited)`, or `ios/ExportOptions.plist` lists more than one bundle id. Single-target apps keep the old behavior. Unreadable `ExportOptions.plist` keeps the override (export reports the file).
- **One optional extension profile secret** (`APPLE_EXTENSION_PROVISIONING_PROFILE_BASE64`), listed as optional in the install summary. Rejected: several profiles in one secret (Linux `base64` wraps lines, so splitting is ambiguous).
- **`.github/scripts/.gitignore` written by `copyScripts()`** (same pattern as `logs/`, `incoming/`; root `.gitignore` untouched, works in workflows mode) plus `PYTHONDONTWRITEBYTECODE=1` in the three workflows that stage the whole tree.

## Behavior change
- Installs and updates also ship `firebase_config_files.py`, `toolchain_versions.py` and a new `.github/scripts/.gitignore`.
- Workflows-mode help now says it updates the `version.yml` deploy block and branch keys (it always did, #670, #1248).

## Code pointers
- `src/core/copy/script-references.js > collectReferencedScripts()`; `src/core/copy/simple.js > copyScripts()`
- `.github/scripts/ios_release_rules.py > provisioning_profile_override()`; `.github/scripts/ios_release.py > _archive_and_export()`
- Flutter `IOS-TESTFLIGHT` / `IOS-TEST-TESTFLIGHT` > step `Install Provisioning Profile`

## Cautions
- The guard sees only literal paths in workflows. A script loaded through a runtime-built path must be in the list.
- A new Flutter step that reads repo-root files under an `APP_ROOT` default needs `working-directory: ${{ github.workspace }}` or `$GITHUB_WORKSPACE/...` (rule in `docs/architecture/agent/workflows.md`); it passes in single-app repos and fails only in monorepos.
- The install step takes one extension profile; more extensions need repo-local install lines, replaced on update.

## Verification
- `npm test` 43 pass, `pytest scripts/tests/ .github/scripts/test/` 111 passed, actionlint 361 > 359 findings, none new.
- Throwaway monorepo install before/after (non-ASCII path, `PYTHONUTF8` unset): scripts missing and exit 2 before; installed and exit 0 after.

## Follow-ups
- The issue's `client/pubspec.yaml` build number change was not reproduced; workflows mode never touches it.
