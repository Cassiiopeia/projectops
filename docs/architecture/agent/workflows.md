# Workflow rules

> **When to read:** when you add, edit or rename workflows in `.github/workflows/` or `project-types/`, or touch the deploy/publish axes, comment triggers or issue templates
> Canonical text split out of `CLAUDE.md`. `CLAUDE.md` keeps only a summary and a link to this document.

## Naming conventions

### Workflow files
```
PROJECT-[TYPE]-[FEATURE]-[DETAIL].yaml

TYPE: TEMPLATE | COMMON | FLUTTER | SPRING | REACT | PYTHON | NODE | REACT-NATIVE-EXPO
```

### Script files
```
snake_case.sh / snake_case.py
```

## Core workflows

### Common workflows

| File | Trigger | Function |
|--------|--------|------|
| `PROJECT-TEMPLATE-INITIALIZER` | Repo creation | Template initialization (one-time) |
| `PROJECT-TEMPLATE-PLUGIN-VERSION-SYNC` | Push to main | Plugin manifest version sync (**this repo only**) |
| `PROJECT-TEMPLATE-CI` | Push/PR on develop and main | Tests — fast lane / wide lane (**this repo only**, see the section below) |
| `PROJECT-TEMPLATE-NPM-PUBLISH` | Push to main | Publishes the `projectops` npm package after every CI job on the same commit passes (**this repo only**) |
| `PROJECT-TEMPLATE-ISSUE-ASSIGNMENT` | Issue comment · daily · manual | Claim comments such as `/assign` on `good first issue` / `help wanted` issues > assign, and release after 7 days without a linked PR (**this repo only**, #1155) |
| `PROJECT-COMMON-VERSION-CONTROL` | Direct push to main (safety net) | Patch bump on pushes other than release merges |
| `PROJECT-COMMON-RELEASE-CHANGELOG` | PR to main (develop→main) | Version finalization (semver bump — #546) + AI changelog + automerge |
| `PROJECT-COMMON-README-VERSION-UPDATE` | Push to main | README version sync |
| `PROJECT-COMMON-SUH-ISSUE-HELPER` | Issue creation | Branch name/commit suggestion (internal py — `issue_helper.py`, brought in-house in #478) |
| `PROJECT-COMMON-QA-ISSUE-CREATION-BOT` | @projectops mention | Automatic QA issue creation |
| `PROJECT-COMMON-SYNC-ISSUE-LABELS` | Label file change | GitHub label sync |
| `PROJECT-COMMON-TEMPLATE-UTIL-VERSION-SYNC` | version.json change | Util HTML version sync (copied only to repos with util modules — #491) |
| `PROJECT-COMMON-PROJECTS-SYNC-MANAGER` | Issue label change | Issue Label → Projects Status sync (optional — `common/projects-sync/`, `--projects-sync`, #716) |
| `PROJECT-COMMON-AI-PR-SUMMARY` | Work PR opened/updated | Change summary comment (optional — `common/pr-summary/`, #566) |

### ⚠️ Fastlane lanes called by workflows must exist (#601 — agent must read)

**The wizard overwrites the Fastfile.** A lane added by hand disappears on reinstall,
so **match the workflow to the lanes that exist.** Never the other way around.

| Template | Lanes defined |
|---|---|
| `testflight-wizard/templates/Fastfile.ios.template` | `deploy` |
| `playstore-wizard/templates/Fastfile.playstore.template` | `build_aab` · `deploy_internal` · `promote_internal_to_production` · `validate` |

Real incident: the iOS test build called a nonexistent `upload_testflight`, so **it never once reached
TestFlight.** The IPA was built fine and it died **only at the final upload step**, so it went unnoticed for a long time.
The deploy path called the right lane and was fine; **only the test path** was wrong, and nobody had walked
that path to the end. Searching for the same kind of bug found two more on the Android side (`fastlane build`).

To use a lane that exists only in a hand-made Fastfile, **check that it exists before calling it.**

```bash
if [ -f "android/fastlane/Fastfile" ] \
   && grep -qE '^[[:space:]]*lane[[:space:]]*:build([[:space:]]|$)' android/fastlane/Fastfile; then
  ( cd android && bundle exec fastlane build --verbose )   # subshell — a leaked cd tangles what follows
else
  flutter build apk --release
fi
```

> **🔴 Test builds must pin `DEPLOY_MODE`.** Depending on this value, the iOS `deploy` lane goes
> **as far as automatic review submission (`submit_for_review`)**. If you rely on the default, the moment the Fastfile default
> changes, test builds get submitted for app review — an irreversible kind of incident.
> Test paths set `export DEPLOY_MODE="store_only"` explicitly.

### ⚠️ Both layers of build flags must move together (#603 — agent must read)

App development switches live in **two layers**, and **the build passes even when only one layer is right.**

| Layer | Where | Forgeable |
|---|---|:-:|
| Runtime | `.env` (dotenv) | Yes (secret injection) |
| Compile time | `--dart-define` | **No** (baked into the binary) |

Real incident: the development flag was written to `.env` and the log printed `✅ 적용 완료` ("applied"), but **after installing,
the debugging tools were missing.** It was a release build, so the compile-time gate was closed, and there was not a single
`dart-define` anywhere in the repo — that is, **it had never been on.** You cannot tell from the log alone.

**`.github/scripts/apply_build_profile.py` decides both layers in one place.**

```yaml
- name: Apply build profile (test)
  id: build_profile
  run: python3 .github/scripts/apply_build_profile.py test .env

- name: Build
  # 🔴 Do not write dart-define here directly. The moment you do, there are two places again.
  run: flutter build apk --release ${{ steps.build_profile.outputs.build_flags }}
```

- **Without the settings file (`.github/config/build-profile.json`) it does nothing.**
  This template is installed in other people's repos, so that is the default. See the `.example` file for a sample.
- The profile named `release` **is validated** — if a release build would ship with development keys on, a QA token
  left in, or test-only dart-defines mixed in, **the build is stopped.**
- **If `.env` generation and the build are in different jobs**, pass the profile result through `outputs.build_flags`
  (as `IOS-TEST-TESTFLIGHT` and `IOS-TESTFLIGHT` do). In the same job, read it through `steps.`.
- **Paths that build through a fastlane lane have no place to pass flags.** If flags exist and
  the build takes that path, **the build is stopped** — silently dropping them would bring back the very incident this step fixes.
- Use a neutral flavor name without the app name, such as **`APP_FLAVOR`**.
  Flutter's standard `FLUTTER_APP_FLAVOR` is reserved and cannot be passed with `--dart-define`
  (it is for `--flavor` only, which requires Gradle productFlavors and Xcode schemes).

Applied workflows: `ANDROID-TEST-APK` · `IOS-TEST-TESTFLIGHT` (test) ·
`ANDROID-PLAYSTORE-CICD` · `ANDROID-FIREBASE-CICD` · `ANDROID-SELFHOSTED-CICD` · `IOS-TESTFLIGHT` (release)

### ⚠️ Workflows must declare `permissions:` (#595 — agent must read)

**Without a declaration, the repo default applies, and that default differs per repo and changes later.**

| Default | Without a declaration |
|---|---|
| `read` (default for new GitHub repos) | Workflows that post comments **die at that step** |
| `write` | Deploy workflows that only need to read get **excessive permissions** |

Real incident: the `@projectops apk build` test build always failed. The trigger workflow had the block,
so **it succeeded up to the trigger**, and then the build itself was blocked the moment it posted a progress comment.
From the outside it looked like "the build runs but there is no result", so finding the cause took a long time.

```
RequestError [HttpError]: Resource not accessible by integration
```

| What it does | What to declare |
|---|---|
| Comments/labels on issues and PRs | `contents: read` + `issues: write` + `pull-requests: write` |
| Comments on PRs only | `contents: read` + `pull-requests: write` |
| Checkout, build, deploy only | `contents: read` |
| Pushes commits | `contents: write` |
| Calls the API only with a separate PAT | `contents: read` (GITHUB_TOKEN is not used) |

Place it **right after** the top-level `on:` block (per-job declarations are fine too).
Regression guard: `.github/scripts/test/test_workflow_permissions.py` checks **every** workflow.

> **⚠️ Do not scan only `.yaml`.** This repo also has 5 workflows with the `.yml` extension
> (`NEXUS-*` · `GITHUB-PACKAGES-PUBLISH` · `TEMPLATE-UTIL-VERSION-SYNC`).
> The first audit, which looked only at `*.yaml`, really did miss one, and the test caught it.

> **⚠️ `repository_dispatch` runs with the workflow definition on the default branch.** If you edit a workflow that uses this trigger
> (`ANDROID-TEST-APK` · `IOS-TEST-TESTFLIGHT` · `APP-BUILD-TRIGGER`) on develop
> and re-run the test build, **the old definition still runs.** The fix looks as if it did not take effect
> and you end up looking for the cause in the wrong place, so always verify after it has landed on the default branch.

### Per-type workflows

#### Flutter
| File | Purpose | Location |
|--------|------|------|
| `PROJECT-FLUTTER-CI` | Code analysis + build check | Base |
| `PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD` | Play Store deploy | Base |
| `PROJECT-FLUTTER-ANDROID-FIREBASE-CICD` | Firebase App Distribution | Base |
| `PROJECT-FLUTTER-ANDROID-TEST-APK` | Test APK build | Base |
| `PROJECT-FLUTTER-IOS-TESTFLIGHT` | TestFlight deploy | Base |
| `PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT` | Test build | Base |
| `PROJECT-FLUTTER-IOS-ASC-STATUS` | App Store Connect version status and latest build number lookup (manual run, read-only, #651) | Base |
| `PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER` | Comment-triggered build | Base |
| `PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD` | APK deploy to a self-hosted server (SMB) | Base |

#### React Native Expo (#1240)
| File | Purpose | Location |
|--------|------|------|
| `PROJECT-REACT-NATIVE-EXPO-CI` | Type check, lint, tests (each only when present) | Base |
| `PROJECT-REACT-NATIVE-EXPO-ANDROID-TEST-APK` | Test APK (manual, `build-android-app` dispatch) | Base |
| `PROJECT-REACT-NATIVE-EXPO-IOS-TESTFLIGHT` | TestFlight: release on push, test on `build-ios-app` dispatch or manual | Base |
| `PROJECT-REACT-NATIVE-EXPO-ANDROID-PLAYSTORE-CICD` | Play Store internal > closed testing | Base |
| `PROJECT-REACT-NATIVE-EXPO-PROJECTOPS-APP-BUILD-TRIGGER` | Comment-triggered build | Base |

- **No EAS and no committed native files.** `expo prebuild` regenerates `android/` and `ios/` on every run, so nothing the
  workflows need may live there: Android signing goes through `-Pandroid.injected.signing.*`, and the iOS ExportOptions,
  Fastfile (`deploy` lane) and Gemfile are written on the runner by `.github/scripts/expo_app.py ios-signing`.
  Committed native folders (no prebuild) are built as they are.
- **Shared logic lives in `expo_app.py`** (package manager, resolved app config, version into app.json, iOS workspace and
  Info.plist build variables). Do not re-implement these steps in YAML. The iOS archive, number and upload rules stay in
  `ios_release.py`, shared with Flutter.
- **The trigger has the same body as the Flutter trigger** (it only reads the comment and dispatches `build-android-app` /
  `build-ios-app`). Change both files together; only the header, `name:` and the triggered workflow list differ.
- The test builds comment on the payload's `pr_number` (issue or PR) with the existing `test_apk.*` / `test_testflight.*` messages.

#### ⚠️ Deploy/publish target axes (#439, v4.2.0 — agent must read)

Deployment is expressed on **two independent axes**. The wizard asks right after the type is settled (except for `basic` alone — see below).

| Axis | Meaning | Multiplicity | Values | version.yml key |
|----|------|--------|-----|---------------|
| **deploy** | Where the runnable (server/app) goes | **Pick one** | `docker-ssh` (default) · `vercel` · `none` | `options.deploy` |
| **publish** | Which registry a library/package is released to | **0..n together** | `nexus` · `npm` · `github-packages` | `options.publish` array |

##### 🧭 Intent (project nature) first (#485, v4.2.14 — agent must read)

Asking the two axes one by one burdened users with "does this even apply to me?". Now **the project nature (intent) is asked once first, and the answer derives the two axes**.

| intent | deploy question | publish question | version.yml key |
|--------|------------|-------------|---------------|
| `app` | Asked | **Skipped** (`publish=[]`) | `options.intent` |
| `library` | **Skipped** (`deploy=none`) | Asked | |
| `both` | Asked | Asked | |
| `none` | **Skipped** (`none`) | **Skipped** (`[]`) | |
| `manual` | Asked | Asked (the old sequential questions as is — the escape hatch) | |

- Saved in `metadata.template.options.intent`. An old version.yml (no intent) is **inferred backwards** from the `deploy`/`publish` values (`inferIntent`, `src/core/version-yml.js`) for backward compatibility. deploy≠none & publish=[] → app, deploy=none & publish≠[] → library, both → both, neither → none.
- Non-interactive: `--intent app|library|both|none|manual`. When unspecified, inferred from `--deploy`/`--publish` (existing CLI works unchanged). With an explicit intent and no flag for an axis, the intent derives that axis (library → deploy=none, etc., `src/index.js`).
- The edit menu has a "project nature" item (#485) alongside the individual axis items (#483). Changing the nature re-derives the axes, and the individual axis items fine-tune only that axis (`scope`).
- **`basic` alone also skips the intent question** — settled as `none`.

##### 🧩 Axis applicability per type (#498 — agent must read)

The deploy/publish axes **may not apply at all, depending on the type.** The `axes` of each entry in the type registry (`src/core/project-types.json`, read as `TYPE_DEPLOY_TARGETS`/`TYPE_PUBLISH_TARGETS` in `src/core/options-ask.js`) define the applicable targets per type, and `applicableTargets(types)` computes the union over the chosen types.

- **Mobile app types (flutter/react-native/react-native-expo) have empty arrays on both axes** — store deployment (Play Store/TestFlight/Firebase, etc.) is always included in the type workflows, so it has nothing to do with the server deploy axis, and there is no registry publish concept. Like basic, **the intent question is skipped entirely** and settled silently as `none`/`[]` (no notice either — there is no reason to show one).
- **Inapplicable saved/CLI values are cleaned up without a warning** — a repo where an old version saved `deploy: docker-ssh` for flutter alone is quietly cleaned up to `none`/the intersection on update (same copy result — SSOT). Non-interactive (`src/index.js`) follows the same rule.
- The edit menu (`editMenu`) also hides inapplicable axis items ("project nature", "deploy method", "publish target"). After changing the type, they show again on the next entry.
- Server types (spring/react/node/python) keep all current choices (behavior unchanged — finer per-type division is follow-up work). Question choices are filtered through `applicable.*`, so narrowing the declarations later updates the choices automatically.
- **When you add a new type, set its `axes` in the registry** — keep them in line with the `project-types` folders (`server-deploy/`, `publish/<target>/`). See "How to add a new project type" in `ARCHITECTURE.md`.

- **`basic` alone skips the deploy/publish questions** — it is a general type with no server or library concept, so asking confuses users. It is settled silently as `deploy=none` / `publish=[]` and shown only on the analysis card. If the type changes (edit menu → project type), the questions appear then. (The old js `isBasicOnly` special case was absorbed into #498's general empty-axes check `noAxes` — `.sh`/`.ps1` hit EOF in #458)
- Real-type questions get a one-line "**why we ask**" context in front (pick if you plan to deploy a server, otherwise skip).
- Non-interactive: `--deploy docker-ssh|vercel|none` + `--publish nexus,npm` (csv). `.ps1` uses `-Deploy`/`-Publish`.
- **The old flags `--nexus`/`--npm-publish` are deprecated** (kept for 1 minor) — interpreted as `--publish nexus`/`--publish npm` with a warning. `--nexus` additionally implies `--deploy none` (preserving the old behavior).
- The old version.yml keys (`nexus`/`npm_publish`) are **converted to the new axes and written automatically** on integration/update (SSOT — no double notation).

#### Spring
| File | Purpose | Location |
|--------|------|------|
| `PROJECT-SPRING-SIMPLE-CICD` | SSH+Docker deploy (default, single container) | spring/server-deploy/ |
| `PROJECT-SPRING-NONSTOP-TRAEFIK-CICD` | Zero-downtime deploy (Traefik Blue-Green) | spring/server-deploy/ |
| `PROJECT-SPRING-NONSTOP-NGINX-CICD` | Zero-downtime deploy (Nginx Blue-Green) | spring/server-deploy/ |
| `PROJECT-SPRING-PR-PREVIEW` | PR preview deploy | spring/server-deploy/ |
| `PROJECT-SPRING-NEXUS-CI` / `-NEXUS-PUBLISH` | Nexus library publish | spring/publish/nexus/ |
| `PROJECT-SPRING-GITHUB-PACKAGES-PUBLISH` | GitHub Packages library publish | spring/publish/github-packages/ |

> **When you add a new deploy workflow, add its file name to the type's `deploy_trigger_workflows` in `src/core/project-types.json` (#1114, #1244; `DEPLOY_TRIGGER_WORKFLOWS` in `src/core/branch-sub.js` is built from it, plus the type-independent Vercel workflow). The options schema test fails if a listed file does not exist.** This covers only workflows that deploy on push (store, server, package publish, Vercel).
> In repos using `deploy_trigger_branch`, a file missing from this table deploys from the default branch, so deployment runs in the wrong place even though the deploy branch was split off. Do not add common workflows such as version bump, README version, release notes or issue closing (they follow the default branch).
>
> **The CI minutes saver option (`ci_minutes_saver`, #1114) rewrites workflows through the file-name table in `src/core/ci-minutes-sub.js`.** When you add a new CI workflow, decide whether it goes in the table. A rewrite applies only when the pattern matches exactly, so if you change the shape of the `on:` block or the `ENABLE_IOS` line of a workflow in the table, update the table's rewrite too (otherwise the option silently does nothing).
>
> Server deploy workflows (SIMPLE/NONSTOP-*/PR-PREVIEW) are grouped in `server-deploy/` and **included only when `deploy=docker-ssh`** (the whole folder is excluded for `vercel`/`none`). Publish workflows live in `<type>/publish/<target>/`, and copying is decided by **the set of selected publish targets** (the type is only the file location, not a gate).
>
> **Extension rule (agent must read)**: put a new "server deploy" workflow file only into **that type's `<type>/server-deploy/`** (excluded automatically when deploy≠docker-ssh). Currently two types have `server-deploy/`: `spring` and `python`. **Never put it directly under the type folder, because then it is copied even with `--deploy none`** (python really fell into this trap and was corrected in #521). Put a new publish target in `<type>/publish/<target>/` and add the value to the wizard's question list. Type-independent deploy targets (Vercel, etc.) go in `common/deploy/<target>/`.
>
> **⚠️ When renaming/deleting a workflow (agent must read, #470)**: you must add the old name to `src/core/migrations/registry.js` — it is the only path by which a wizard update automatically neutralizes (.bak) the old file in existing integrated repos (all legacy migrations are managed in this single registry). Choose the tier by real harm: `safe` (pure rename — real harm from duplicate runs when both exist) / `confirm` (may be a deploy pipeline — notice only, no automatic action). Putting a name from the current deploy set into the registry neutralizes a live workflow, so before adding, check that the current templates have no file with the same name. If the old file may hold user custom settings, give the registry entry a `settingsExtractor` so they are migrated to version.yml automatically right before neutralizing (`rules/settings-extractors.js`; the #478 issue helper is the model example).
> Note: **orphan workflows left behind by deselecting a type** are detected dynamically by `src/core/orphan-workflows.js`, not the registry (#487) — the registry is for renames and retirements only, and orphan cleanup compares against the template inventory (exact file-name match). Interactive mode neutralizes to .bak after confirmation; non-interactive mode only prints a notice.
>
> **⚠️ When creating a new conditional folder under `common/` (agent must read, #567 · #851)**: add one line to `commonOptionalGroups` in `src/core/workflow-groups.js`. The copy gate (`copy/workflows.js`) and orphan detection (`orphan-workflows.js`) read **the same table**. The two places used to be edited separately, and when only the turn-on side was built, **files stayed and kept running even after the option was turned off** — this really happened with `secret-backup` and `deploy/<target>`.
>
> **The same applies when renaming/retiring files inside `.github/util/` modules (#500)**: register the old file in the registry with `category: "util-file"` (tier safe, exact path) — util copying (`src/core/copy/util.js`) is an overlay that does not delete old files, so the registry is the only cleanup path. Do not register a path that a current template file uses.
>
> **⚠️ When adding a workflow that depends on the branch convention (`YYYYMMDD_#number_title`) (agent must read, #478)**:
> add (file name, notice text) to `GUIDE_LINES` in `.github/scripts/issue_helper.py`,
> and put a "⚠️ 브랜치 규칙 의존" (depends on the branch convention) comment block in the workflow header. Details: `docs/BRANCH-CONVENTION.md`

#### Common — deploy targets / secret backup
| File | Function | Location | Condition |
|--------|------|------|------|
| `PROJECT-COMMON-VERCEL-DEPLOY` | Vercel production deploy (React/Next, etc.) | common/deploy/vercel/ | `--deploy vercel` |
| `PROJECT-COMMON-SECRET-FILE-UPLOAD` | GitHub Secret → server (SSH) upload | common/secret-backup/ | `--secret-backup` |
| `PROJECT-COMMON-AI-PR-SUMMARY` | Change summary comment on work PRs | common/pr-summary/ | Chosen in the PR comment question |

> Vercel needs the `VERCEL_TOKEN`, `VERCEL_ORG_ID` and `VERCEL_PROJECT_ID` secrets.

#### Python (FastAPI/Django)
| File | Purpose | Location |
|--------|------|------|
| `PROJECT-PYTHON-CI` | Build/check | Base |
| `PROJECT-PYTHON-SIMPLE-CICD` | SSH+Docker deploy (single container) | python/server-deploy/ |
| `PROJECT-PYTHON-PR-PREVIEW` | PR preview deploy | python/server-deploy/ |

> Uses the same SSH+Docker engine as Spring. The two deploy workflows live in `server-deploy/`, so they are included only when `deploy=docker-ssh` (moved from the type root to `server-deploy/` in #521; before that, a bug copied them even with `--deploy none`).

#### React (including Next.js)
| File | Purpose |
|--------|------|
| `PROJECT-REACT-CI` | Build check (includes .next/cache caching) |
| `PROJECT-REACT-CICD` | Docker build and deploy (includes the Next.js SSR option) |

> The `next` type was absorbed into `react` in v4.1.0 (PROJECT-NEXT-* workflows deleted).

#### Node — npm publish (opt-in)
| File | Purpose | Location |
|--------|------|------|
| `PROJECT-NODE-NPM-PUBLISH` | On push to main, publishes to public npmjs with the version.yml version (idempotent, NPM_TOKEN secret) | node/publish/npm/ |

> Included with `--publish npm` (the old `--npm-publish` is a deprecated alias). The chosen values are saved in the `metadata.template.options.publish` array of `version.yml`.

## ⚠️ Workflow YAML validation — do not mistake a local parser for GitHub's real behavior (agent must read)

> **Core principle: a red result from a local YAML validator (`actionlint`, Ruby `psych`, Python `pyyaml`) does not mean the workflow actually breaks on GitHub.** What a tool cannot read and what GitHub cannot run are **different things.** Do not "fix" a working workflow on your own because "the validator said it was an error" — this is a trap confirmed in practice.

### Why this happens (measured case)

The typical pattern is a heredoc with a **zero-indent body** inside a `run: |` block:
```yaml
        run: |
          cat > android/key.properties << EOF
storeFile=keystore/key.jks      # ← zero indentation
EOF
```
- `actionlint`, `psych` and `pyyaml` treat this as a **parse failure** with `could not find expected ':'` (strict go-yaml/libyaml-family parsers that decide block scalar boundaries by indentation alone).
- But **GitHub Actions' real YAML parser handles this heredoc fine and the workflow succeeds.** In other words, it is a tool limitation, not a real bug.

### The right order to check whether it is really broken (no guessing, measurements only)

1. **Look at the GitHub run history first (the strongest evidence).** If there is a run of the same file/pattern that actually `success`ed → **confirmed working code.** Never touch it.
   ```bash
   PAT=$(python3 -c "import json;print(json.load(open('$HOME/.projectops/config/config.json'))['github']['global_pat'])")
   curl -s -H "Authorization: token $PAT" \
     "https://api.github.com/repos/<owner>/<repo>/actions/workflows/<file>.yaml/runs?per_page=20" \
     | python3 -c "import json,sys;from collections import Counter;d=json.load(sys.stdin);print(Counter(r['conclusion'] for r in d.get('workflow_runs',[])))"
   ```
2. **Compare with "a reference repo that works well".** This template's reference repos are **`TEAM-ROMROM/RomRom-FE` (Flutter) and `TEAM-ROMROM/RomRom-BE` (Spring)** — they are in production and their builds succeed. `passQL` is **an experimental project for testing this template** (its Flutter init is not even finished), so **it is not a trusted reference.** Do not conclude the template is broken based on a passQL failure.
3. **Check whether YAML parsing itself broke with run annotations.** When GitHub fails to parse, it leaves a `syntax error` annotation. If there is no annotation and the job failed at a build step mid-way → **the YAML is fine; the cause is build logic (missing secret, etc.).**
   ```bash
   curl -s -H "Authorization: token $PAT" "https://api.github.com/repos/<owner>/<repo>/check-runs/<job_id>/annotations"
   ```

### How to treat validation tools

- `actionlint`/`psych`/`pyyaml` are **advisory signals**. A red light means "go check", not "go fix".
- Especially for **workflows already in production** (with success history on GitHub), **leaving them alone is the default**, whatever the tool says.
- If you really must change one, first fetch "how the working RomRom writes the same spot" and compare. (Example: RomRom-FE writes key.properties with `echo "k=v" >> file` and succeeds — it does not use a zero-indent heredoc.)
- When your work **only changes env values** (tokenization, substitution), self-check with `git diff` that **not a single line of execution logic** (`run:`/`uses:`/`with:`/`steps:` etc.) was touched:
  ```bash
  git diff <files> | grep "^+" | grep -v "^+++" | grep -vE "your_intended_change_pattern"   # empty output = execution logic intact
  ```

## Trigger keywords

### Comment-based
| Keyword | Workflow | Function |
|--------|-----------|------|
| `@projectops create qa` | QA-ISSUE-CREATION-BOT | Automatic QA issue creation |
| `@projectops build app` | PROJECTOPS-APP-BUILD-TRIGGER (Flutter, React Native Expo) | Android + iOS build |
| `@projectops apk build` | PROJECTOPS-APP-BUILD-TRIGGER | Android-only build |
| `@projectops ios build` | PROJECTOPS-APP-BUILD-TRIGGER | iOS-only build |

### Branch-based
| Branch | Trigger | Workflow |
|--------|--------|-----------|
| `develop` | push | CI (no version bump) |
| `main` | PR (develop→main) | CHANGELOG-CONTROL (version finalization + automerge) |
| `main` | push (release merge) | README-UPDATE, PLUGIN-SYNC, NPM-PUBLISH, CICD |
| `main` | push (direct) | VERSION-CONTROL safety net (+CICD — not a recommended path) |

## Issue/PR templates

**Issue templates**: `bug_report.md` / `feature_request.md` / `design_request.md` / `qa_request.md`

**Issue labels**: English standard `priority: urgent, documentation, status: todo, status: in progress, status: needs review, status: feedback, status: done, status: on hold, status: cancelled` (legacy Korean: `긴급, 문서, 작업전, 작업중, 담당자확인, 피드백, 작업완료, 보류, 취소`)

## Contribution guideline essentials

> Details: `CONTRIBUTING.md`, `docs/WORKFLOW-COMMENT-GUIDELINES.md`

### When adding a workflow
- Common workflows: keep `project-types/common/` (original) and the `.github/workflows/` root (copy) **identical**
- Per-type workflows: `project-types/[type]/` only
- Required elements: `workflow_dispatch`, `concurrency`, `[skip ci]`
