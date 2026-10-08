# Flutter CI/CD overview

> A fully automated deployment pipeline for Flutter projects

---

## Contents

- [Overview](#overview)
- [System architecture](#system-architecture)
- [Wizard tools](#wizard-tools)
- [Workflow list](#workflow-list)
- [Quick start](#quick-start)
- [Full list of GitHub Secrets](#full-list-of-github-secrets)

---

## Overview

The projectops Flutter CI/CD system combines **wizard tools** with **GitHub Actions workflows**.

**Key features:**
- A web UI wizard generates the complicated deployment settings for you
- PR/issue comments trigger test builds
- Automatic deployment to iOS TestFlight, Android Play Store and Firebase App Distribution

---

## System architecture

### Overall flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        Initial setup                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  🧙 TestFlight wizard    🧙 Play Store wizard   🧙 Firebase wizard│
│  ├─ ExportOptions.plist  ├─ Fastfile            ├─ Deploy config │
│  ├─ Fastfile             ├─ Signing config      └─ Tester groups │
│  └─ Gemfile              └─ Signing key guide                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                  Verification and testing during development     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  develop push/PR → PROJECT-FLUTTER-CI.yaml (analysis + build check)│
│                                                                  │
│  Build command comment on a PR/issue (build app/apk build/ios build)│
│                     ↓                                            │
│  PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml (trigger)     │
│                     ↓  repository_dispatch                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ PROJECT-FLUTTER-ANDROID-TEST-APK.yaml  → APK artifact   │    │
│  │ PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml → TestFlight   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                     ↓                                            │
│  Build result comment is posted automatically                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                        Production deployment                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Push to main branch                                             │
│           ↓                                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml       → TestFlight  │    │
│  │ PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD.yaml → Play Store│    │
│  │ PROJECT-FLUTTER-ANDROID-FIREBASE-CICD.yaml  → Firebase  │    │
│  │ PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD.yaml → Own server│   │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

> All four production deployment workflows trigger on a `main` push. Delete or disable the ones your project does not need.

### Wizard-to-workflow relationship

```
.github/util/flutter/testflight-wizard/
    → Generates: ExportOptions.plist, Fastfile, Gemfile
    → Used by workflows:
        - PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml (production deployment)
        - PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml (test)

.github/util/flutter/playstore-wizard/
    → Generates: Fastfile, build.gradle.kts signing config
    → Used by workflows:
        - PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD.yaml (production deployment)
        - PROJECT-FLUTTER-ANDROID-TEST-APK.yaml (test)

.github/util/flutter/firebase-wizard/
    → Generates: Firebase App Distribution deploy config
    → Used by workflows:
        - PROJECT-FLUTTER-ANDROID-FIREBASE-CICD.yaml (production deployment)
        - PROJECT-FLUTTER-ANDROID-TEST-APK.yaml (Firebase upload option)
```

---

## Wizard tools

| Wizard | Purpose | Detailed guide |
|--------|---------|----------------|
| **TestFlight wizard** | Generates iOS deployment settings | [FLUTTER-TESTFLIGHT-WIZARD.md](../FLUTTER-TESTFLIGHT-WIZARD.md) |
| **Play Store wizard** | Generates Android Play Store deployment settings | [FLUTTER-PLAYSTORE-WIZARD.md](../FLUTTER-PLAYSTORE-WIZARD.md) |
| **Firebase wizard** | Generates Firebase App Distribution deployment settings | [FLUTTER-FIREBASE-WIZARD.md](../FLUTTER-FIREBASE-WIZARD.md) |

---

## Workflow list

### CI (code verification)

| Workflow | Purpose | Trigger |
|-----------|------|--------|
| `PROJECT-FLUTTER-CI.yaml` | Code analysis + build verification | develop push / PR targeting develop |

### Production deployment workflows

| Workflow | Purpose | Trigger |
|-----------|------|--------|
| `PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml` | iOS TestFlight deployment | main push |
| `PROJECT-FLUTTER-IOS-ASC-STATUS.yaml` | Looks up App Store Connect version status and the latest build number (read-only, Linux runner) | Manual run |
| `PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD.yaml` | Android Play Store internal testing deployment | main push |
| `PROJECT-FLUTTER-ANDROID-FIREBASE-CICD.yaml` | Firebase App Distribution deployment | main push |
| `PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD.yaml` | APK deployment to your own server (SMB) | main push |

> Self-hosted APK signing: by default it uses the debug key and logs a warning. It signs with the release key (`RELEASE_KEYSTORE_BASE64`, `RELEASE_KEYSTORE_PASSWORD`, `RELEASE_KEY_ALIAS`, `RELEASE_KEY_PASSWORD`) only when you register the repository variable `ANDROID_SELFHOSTED_RELEASE_SIGNING=true`, and in that case the build fails if any of those secrets is empty. If the signing key changes, the update may not install over an app that is already installed, so be careful. Set the upload subpath with the workflow `env.SMB_PATH_ANDROID` (default: empty).

### How far a deployment goes (`DEPLOY_MODE`)

**One value goes to different points on the two platforms.** The shared name makes this easy to confuse, so here is a table.

| `DEPLOY_MODE` | iOS | Android |
|---|---|---|
| `store_only` (default) | Up to the TestFlight upload | Up to the internal testing track |
| `store_prepare` | Attaches the build to the App Store version (does not submit) | Promotes to a production **draft** (a person presses "Start rollout" in the console; the console label is Korean in the original, `출시 시작`) |
| `store_submit` | **Submits to App Store review** | **Registers for production review automatically** |

> The old aliases (`testflight_only`, `appstore_prepare`, `appstore_submit`) are still accepted.
>
> **The default is `store_only`**, in the workflow and inside the Fastfile alike. Previously only the
> Android Fastfile defaulted to `store_submit`, so calling the lane directly without going through the
> workflow put the build into production review (fixed in #618).

### Store "What's New" text (`STORE_WHATS_NEW_OVERRIDE`)

This is the text that goes into the store "What's New" field (iOS "What's New in This Version",
Android "Release notes") on `store_prepare`/`store_submit`. **Reviewers read it as well as users.** Set it in the `env` of the workflow file
(the name is the same for iOS and Android, so change both places together).

| Value | Behavior |
|---|---|
| `""` (template default) | Uses the CHANGELOG entry for that version, same as before |
| Text | Uses that text every time, regardless of version |

- A value with only whitespace is treated as empty. The build log records the source (`CHANGELOG` / `STORE_WHATS_NEW_OVERRIDE 덮어쓰기` (STORE_WHATS_NEW_OVERRIDE override)).
- If you give the manual run input `whats_new_override` a value, it takes priority for **that run only**.
- The iOS TestFlight "What to Test" text (for internal testers) always uses the CHANGELOG, regardless of this value.
- The Android release notes are fixed at the internal testing upload and carry through to promotion, so they apply to every track.
- Why `env` and not a repository variable: the template cannot pre-create repository variables, and since this value rarely changes,
  it is better to have it visible in code with a git history. (The deploy mode stays a repository variable because you may need to switch it off right away in an emergency.)

**iOS review notes (Notes)**: if `ios/fastlane/review_notes.txt` exists, its content is used every time. If it is missing or empty,
the existing App Store Connect value is left as is. (It used to try to "reset" the notes with an empty file, but an empty value is not sent,
so the existing value stayed. Confirmed by measurement.) Apps that have no shared review account and keep login instructions only in the Notes can manage them alongside the code with this file.

### Android tracks: internal testing alone cannot reach production ⚠️

`DEPLOY_MODE` decides **only the production step**. Independent switches handle the intermediate tracks.

| Switch (repository variable / manual run input) | What it does | Default |
|---|---|---|
| `ANDROID_PROMOTE_TO_CLOSED_TESTING` | Also uploads to the closed testing track | `false` |
| `ANDROID_PROMOTE_TO_OPEN_TESTING` | Also uploads to the open testing track | `false` |
| `ANDROID_CLOSED_TESTING_TRACK` | Closed track name | `alpha` |
| `ANDROID_OPEN_TESTING_TRACK` | Open track name | `beta` |

| Track | Google review | Takes effect | Counts toward production access requirements |
|---|---|---|---|
| `internal` (internal) | **None** | A few minutes | ❌ |
| `alpha` (closed) | Yes | Tens of minutes to several days | ✅ |
| `beta` (open) | Yes | Same | ✅ |
| `production` | Yes | Same | n/a |

> A **personal developer account created after 2023-11-13** must complete **closed testing** with at least
> 12 testers participating for at least 14 days to get production access. Internal testing has no review,
> which is convenient, but it **does not count toward that requirement**. If you only run internal testing, the requirement never fills.
> (Accounts created before that date and organization accounts are not affected.)
>
> Track names can be changed in the console, so they are values. If hard-coded, a repository
> that uses custom names would silently fail to upload.

### Test build workflows

| Workflow | Purpose | Trigger |
|-----------|------|--------|
| `PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml` | Detects the build trigger | `@projectops build app` / `apk build` / `ios build` comment |
| `PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml` | iOS test build | repository_dispatch (`build-ios-app`) |
| `PROJECT-FLUTTER-ANDROID-TEST-APK.yaml` | Android APK test build | repository_dispatch (`build-android-app`) |

Detailed guide: [FLUTTER-TEST-BUILD-TRIGGER.md](../FLUTTER-TEST-BUILD-TRIGGER.md)

### iOS build number and version (#643)

| Item | Behavior |
|------|------|
| Build number | Seconds elapsed since 2024-01-01 UTC (about 87 million), decided right before the archive. The latest ASC number and the number Apple's rejection message asks for are used only as lower bounds. The rule lives in one place, `build_number.py` |
| Test build version | The `version.yml` version. If it has already been released and closed, it builds with the next patch and shows the reason in the progress comment |
| Release version | The `version.yml` version. If it is closed, it **fails before the build** (raise the `version.yml` version and run again) |
| Upload rejection | For a number that is too low, it retries up to 5 times with a new number at or above the required value (the Flutter build is not redone). For a closed-version rejection, only test builds retry with the next patch. A duplicate number means that number is already uploaded, so it fails without re-uploading, and running again uses a new number |
| Failure reason | A test build shows a `사유` (reason) line in the failure comment; a release shows it in the run summary and `::error::` |

`version_code` is not used for iOS or for test build numbers ([version-control.md](./version-control.md#managing-version_code)). For the detailed rules, see [FLUTTER-TEST-BUILD-TRIGGER.md](../FLUTTER-TEST-BUILD-TRIGGER.md#빌드-번호-규칙).

---

## Quick start

### Step 1: Generate the settings files with a wizard

```bash
# iOS TestFlight settings
open .github/util/flutter/testflight-wizard/testflight-wizard.html

# Android Play Store settings
open .github/util/flutter/playstore-wizard/playstore-wizard.html

# Firebase App Distribution settings
open .github/util/flutter/firebase-wizard/firebase-wizard.html
```

### Step 2: Set up GitHub Secrets

Register them using the [full list of GitHub Secrets](#full-list-of-github-secrets) below.

> ⚠️ **Secret names must match exactly what the workflows reference.** If even one name differs, the build fails at the certificate/keystore restore step.

### Step 3: Install the workflows

```bash
# Install the Flutter workflows with the npx wizard
npx projectops --mode workflows --type flutter
```

### Step 4: Run a test build

Write a comment on a PR or issue:
```
@projectops build app    # Build both Android and iOS
@projectops apk build    # Build Android only
@projectops ios build    # Build iOS only
```

---

## Full list of GitHub Secrets

### iOS (TestFlight, shared by production deployment and test builds)

| Secret | Description |
|--------|------|
| `APPLE_CERTIFICATE_BASE64` | Apple Distribution certificate `.p12` (base64 encoded) |
| `APPLE_CERTIFICATE_PASSWORD` | `.p12` certificate password |
| `APPLE_PROVISIONING_PROFILE_BASE64` | `.mobileprovision` file (base64 encoded) |
| `IOS_PROVISIONING_PROFILE_NAME` | Provisioning profile name |
| `APP_STORE_CONNECT_API_KEY_ID` | App Store Connect API Key ID (10 characters) |
| `APP_STORE_CONNECT_ISSUER_ID` | Issuer ID (UUID format) |
| `APP_STORE_CONNECT_API_KEY_BASE64` | `AuthKey_XXXXXX.p8` file (base64 encoded) |
| `IOS_BUNDLE_ID` (optional) | Bundle ID. Can also be given as a repository variable (`vars`) instead of a Secret |
| `ENV_FILE` (optional) | `.env` file contents |
| `SECRETS_XCCONFIG` (optional) | Contents of `ios/Flutter/Secrets.xcconfig` |

> **App Store Connect API key role**: **App Manager or higher is recommended.** The prepare step uses this key to read the app's version list and latest build number, and read access for the Developer role has **not been confirmed.** If the lookup fails, it only logs a warning and continues with the `version.yml` version, and the automatic recovery when an upload is rejected for a closed version works the same. No new Secret is required.

### Android: Play Store deployment

| Secret | Description |
|--------|------|
| `RELEASE_KEYSTORE_BASE64` | Signing keystore `.jks` (base64 encoded) |
| `RELEASE_KEYSTORE_PASSWORD` | Keystore password |
| `RELEASE_KEY_ALIAS` | Key alias |
| `RELEASE_KEY_PASSWORD` | Key password |
| `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64` | Play Console service account JSON (base64 encoded) |
| `GOOGLE_SERVICES_JSON` | Firebase `google-services.json` contents |
| `ENV_FILE` or `ENV` (optional) | `.env` file contents (`ENV_FILE` takes priority) |

### Android: Firebase App Distribution deployment

It uses the same `RELEASE_*` signing Secrets as Play Store; only the upload credentials differ.

| Secret | Description |
|--------|------|
| `RELEASE_KEYSTORE_BASE64` / `_PASSWORD` | Signing keystore and its password |
| `RELEASE_KEY_ALIAS` / `RELEASE_KEY_PASSWORD` | Key alias and its password |
| `FIREBASE_SERVICE_ACCOUNT_JSON_BASE64` | Firebase service account JSON (base64 encoded) |
| `GOOGLE_SERVICES_JSON` (optional) | Firebase `google-services.json` contents |
| `ENV_FILE` or `ENV` (optional) | `.env` file contents |

### Android: own server (SMB) deployment

| Secret | Description |
|--------|------|
| `RELEASE_KEYSTORE_BASE64` / `_PASSWORD` | Signing keystore and its password |
| `RELEASE_KEY_ALIAS` / `RELEASE_KEY_PASSWORD` | Key alias and its password |
| `SERVER_HOST` / `SERVER_USER` / `SERVER_PASSWORD` | SMB connection info |
| `GOOGLE_SERVICES_JSON` (optional) | Firebase `google-services.json` contents |
| `ENV_FILE` or `ENV` (optional) | `.env` file contents |

> The `🔑 필수 GitHub Secrets` (Required GitHub Secrets) comment at the top of each workflow file is always the most current reference. If it disagrees with this table, trust the workflow comment.

---

## File location summary

```
.github/
├── util/flutter/
│   ├── testflight-wizard/           # iOS wizard
│   │   ├── testflight-wizard.html
│   │   ├── testflight-wizard.js
│   │   ├── testflight-wizard.py
│   │   └── templates/
│   │       ├── ExportOptions.plist
│   │       ├── Fastfile.ios.template
│   │       └── Gemfile
│   │
│   ├── playstore-wizard/            # Android Play Store wizard
│   │   ├── playstore-wizard.html
│   │   ├── playstore-wizard.js
│   │   ├── playstore-wizard.py
│   │   └── templates/
│   │       ├── Fastfile.playstore.template
│   │       └── build.gradle.kts.signing.template
│   │
│   └── firebase-wizard/             # Firebase App Distribution wizard
│       ├── firebase-wizard.html
│       ├── firebase-wizard.js
│       └── firebase-wizard.py
│
└── workflows/project-types/flutter/
    ├── PROJECT-FLUTTER-CI.yaml
    ├── PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml
    ├── PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD.yaml
    ├── PROJECT-FLUTTER-ANDROID-FIREBASE-CICD.yaml
    ├── PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD.yaml
    ├── PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml
    ├── PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml
    └── PROJECT-FLUTTER-ANDROID-TEST-APK.yaml
```

---

## Related documents

- [iOS TestFlight wizard details](../FLUTTER-TESTFLIGHT-WIZARD.md)
- [Android Play Store wizard details](../FLUTTER-PLAYSTORE-WIZARD.md)
- [Firebase App Distribution wizard details](../FLUTTER-FIREBASE-WIZARD.md)
- [Test build trigger details](../FLUTTER-TEST-BUILD-TRIGGER.md)
