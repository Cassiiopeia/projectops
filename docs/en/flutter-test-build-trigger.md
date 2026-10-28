# Flutter test build trigger guide

> Start Android APK and iOS TestFlight builds automatically with a comment on a PR or issue

---

## Contents

- [Overview](#overview)
- [Usage](#usage)
- [Who can trigger a build](#who-can-trigger-a-build)
- [Build number rules](#build-number-rules)
- [Workflow flow](#workflow-flow)
- [Build result comments](#build-result-comments)
- [Required setup](#required-setup)
- [Troubleshooting](#troubleshooting)

---

## Overview

The test build trigger runs an Android APK build and an iOS TestFlight build automatically when you write a build command as a comment on a PR or issue.

**Key features:**
- Works on both PRs and issues
- **3 build options**: full build / Android only / iOS only
- Build numbers are time-based, so builds from several issues at once never collide
- A test build on a version that was already released and closed switches to the same next patch version on both Android and iOS automatically
- Build results are posted as a comment automatically

---

## Usage

### Trigger a build from a PR

Write one of these comments on the PR:

| Command | Builds |
|--------|----------|
| `@projectops build app` | Android + iOS |
| `@projectops apk build` | Android only |
| `@projectops ios build` | iOS only |

```
@projectops build app    # build both
@projectops apk build    # build Android only
@projectops ios build    # build iOS only
```

### Trigger a build from an issue

To build from an issue, the issue must already have a **"Guide by ProjectOps"** comment.

1. The issue has a comment in the "Guide by ProjectOps" format
2. That comment contains the branch information

```markdown
### 브랜치
```
feature/20240101_#123_기능명
```
```

The `### 브랜치` ("Branch") heading is a fixed literal that the workflow parses, so it stays in Korean.

3. Write the build command comment on an issue that meets the conditions above

### Supported keywords

A comment triggers a build when it contains one of these patterns:

| Pattern | Required keywords | Builds |
|------|--------------|----------|
| Full build | `@projectops` + `build` + `app` | Android + iOS |
| APK only | `@projectops` + `apk` + `build` | Android |
| iOS only | `@projectops` + `ios` + `build` | iOS |

**Examples:**
```
@projectops build app                      # Android + iOS build
@projectops apk build                      # Android only
@projectops ios build                      # iOS only
@projectops please build the app and test  # Android + iOS build
```

---

## Who can trigger a build

A build uses signing keys and store secrets, so the workflow checks the comment author's permission on the repository.

- Allowed by default: `OWNER`, `MEMBER`, `COLLABORATOR`
- Private repositories are not checked. Anyone who can comment there is already a collaborator.
- If a team member is blocked in a public repository, override the allow list by putting a JSON array in the repository variable `PROJECTOPS_TRIGGER_ASSOCIATIONS`.
  Example: `["OWNER","MEMBER","COLLABORATOR","CONTRIBUTOR"]`
  If the value is not valid JSON, the workflow fails. Delete the variable to go back to the default.
- Comments from authors who are not allowed are ignored silently (the workflow does not run).

## Build number rules

The build number does not depend on the issue number or the comment count. It is **time-based**. The rule lives in one place: `.github/scripts/build_number.py`.

```
build number = max( seconds since 2024-01-01 00:00:00 UTC,
                    latest App Store Connect build number + 1,      (only when it can be read)
                    number required by the Apple rejection + 1 )    (only on a retry)
```

- Example: 2026-09-30 05:04:00 UTC is `86677440`. In 2026 it is about 87 million.
- Time never goes backwards, so **a number taken later is always larger.** Numbers keep rising even when several issues build at the same time or builds finish out of order.
- The second and third values are lower bounds. If the first value is already larger, they are not used. If an app used date-style numbers before (for example `2026093001`), the second value lifts the number above them.
- If two builds take the same number in the same second, Apple rejects one as a duplicate. For when a retry moves on to a new number, see "Automatic retry when the number is rejected (iOS)" below.

### Scope

| Build | Number |
|------|------|
| iOS test (TestFlight) | The rule above, decided right before the archive |
| iOS release (TestFlight, review submission) | The rule above |
| Android test (APK, Firebase) | The rule above (no App Store Connect lower bound and no retry) |
| Android release (Play Store, Firebase CICD, own server) | Not covered by this rule ([version-control.md](./version-control.md#managing-version_code)) |

The number is not written back to `version.yml`. The trigger workflow still sends a `build_number` built the old way (PR/issue number + comment count) in the payload. The new build workflows do not read it and decide the number themselves. The wizard does not overwrite workflows you edited, so a repository can end up with a new trigger and an old, edited builder, and the old builder uses this value as the build number as is. The field will be removed once old builders are gone.

> **Once an iOS number goes up, you cannot go back to the old scheme.** This is not a problem as long as you keep using the time-based rule.

### App version format
```
2.1.3(86677440)
```
- Version: the version from `version.yml` (not a fixed test version).
- Build number: the value decided by the rule above.

### Automatic version switch after release (Android and iOS test)

If the `version.yml` version was already released on the App Store and is closed, TestFlight rejects the upload. The test build checks this in advance and builds the **next patch after the highest closed version**. So that one commit gets the same app version on Android and iOS, both platforms run the same decision script (`ios_release.py precheck-version`).

- The prepare step reads the App Store Connect version list to decide. If the version changed, a `ℹ️ Version adjusted: ...` line gives the reason, and it stays on the progress, success and failure comments (including the issue comment).
- If the list cannot be read (no key, missing permission, network, no iOS bundle ID), the build only logs a warning and continues with the `version.yml` version. The same applies to Android-only repos. On iOS, if the upload is still rejected because the version is closed, it reads the closed version from the rejection message and archives again with the next patch.
- The lookup uses the same secrets as iOS: `APP_STORE_CONNECT_API_KEY_ID`, `APP_STORE_CONNECT_ISSUER_ID`, `APP_STORE_CONNECT_API_KEY_BASE64` and `IOS_BUNDLE_ID` (secret or variable).
- `version.yml` is not modified.
- An iOS release never changes the version behind your back. If the version is closed, it fails before the build, so bump the `version.yml` version and run it again.

### Stale branch warning

If the branch's `version.yml` version is lower than the default branch's, the comments get a `⚠️ This branch is behind the default branch ...` warning. A stale branch is the most common reason for the version switch above, and merging the default branch usually clears it. It is only a warning and never blocks the build.

> Repos that copied the older approach (the `asc_released_version.py` family, which fails the build on a closed version) are treated as modified workflows by the template update, so they are skipped instead of overwritten. The new version is saved in `.github/.projectops/incoming/`, so compare it and move the changes over.

### Automatic retry when the number is rejected (iOS)

When an upload is rejected, the workflow classifies the cause and retries. It tries up to 5 times and restarts from the archive without running the Flutter build again.

| Rejection cause | Behavior |
|-----------|------|
| Duplicate number | Apple answered "this number already exists". If that number is visible in App Store Connect, the build fails without re-uploading (for example when a parallel build took the same number in the same second). Running it again uses a new number. It retries with a new number only when the lookup does not show the number |
| Number too low | Retries with at least the number the message requires + 1 |
| Version closed (test) | Retries with the next patch version |
| Version closed (release) | Fails without retry |
| Anything else | Fails without retry |

A build that was already uploaded is not uploaded again. Before a retry, the workflow checks whether this number exists in App Store Connect (3 times, 20 seconds apart, to allow for propagation delay). If it does, the build fails without re-uploading. That happens when a step after the upload failed or when a parallel build took the same number, and running it again uses a new number. If this check cannot be done, the build fails without retrying, to avoid a duplicate upload.

---

## Workflow flow

```
1. Write a build command comment on a PR/issue
   (@projectops build app / apk build / ios build)
       ↓
2. BUILD-TRIGGER workflow runs
   - Add 👀 reaction to the comment
   - Detect build type (app/apk/ios)
   - Read PR/issue information
       ↓
3. repository_dispatch event fires (by build type)
   - build app: triggers Android + iOS
   - apk build: triggers Android only
   - ios build: triggers iOS only
       ↓
4. Selected workflows run
   ┌──────────────────────────────────┐
   │ ANDROID-TEST-APK                 │
   │ - Decide the build number (time) │
   │ - Flutter build                  │
   │ - create APK                     │
   │ - upload artifact                │
   │ - post result comment            │
   └──────────────────────────────────┘
   ┌──────────────────────────────────┐
   │ IOS-TEST-TESTFLIGHT              │
   │ - version pre-check (closed)     │
   │ - Flutter build                  │
   │ - decide number, create IPA      │
   │ - Upload to TestFlight (retries) │
   │ - post result comment            │
   └──────────────────────────────────┘
       ↓
5. Build result comment is posted automatically
```

---

## Build result comments

Comments follow the repository language (`language` in `version.yml`). The examples below are the English (`en`) text; Korean repositories get the same comments in Korean.

### Build progress

After a build is triggered, a **progress comment** is created for each platform and updated in real time.

**Android progress comment example:**
```markdown
## 🤖 Building Android APK...

| Step | Status | Duration |
|------|------|----------|
| 🔧 Prepare | ✅ Done | 1m 23s |
| 🔨 APK build | ⏳ In progress... | - |
| 📤 Upload | ⏸️ Waiting | - |

📋 **[View live log](link)**
```

**iOS progress comment example:**
```markdown
## 🍎 Building iOS TestFlight...

| Step | Status | Duration |
|------|------|----------|
| 🔧 Prepare | ✅ Done | 2m 15s |
| 🔨 IPA build | ⏳ In progress... | - |
| 📤 TestFlight deploy | ⏸️ Waiting | - |

📋 **[View live log](link)**
```

When the build finishes, the comment is updated with the final result.

If the build is canceled (a new build started on the same branch, or someone canceled it by hand), the progress comment changes to `⏸️ Cancelled`.

### Android build success comment

```markdown
✅ **Android test APK build complete**

| Item | Value |
|------|------|
| 📦 Version | `2.1.3(86677440)` |
| 🌿 Branch | `feature/20240101_#123_기능명` |
| 📝 Commit | `abc1234` |
| ⏱️ Duration | 5m 32s |

**📥 Download**
[Download the APK from the GitHub Actions artifacts](link)
```

### iOS build success comment

```markdown
✅ **iOS TestFlight build complete**

| Item | Value |
|------|------|
| 📦 Version | `2.1.3(86677440)` |
| 🌿 Branch | `feature/20240101_#123_기능명` |
| 📝 Commit | `abc1234` |
| ⏱️ Duration | 12m 15s |

**📱 Install from TestFlight**
Check the latest build in the TestFlight app.
```

### Build failure comment

```markdown
❌ **Android test APK build failed**

| Item | Value |
|------|------|
| 📦 Version | `2.1.3(86677440)` |
| 🌿 Branch | `feature/20240101_#123_기능명` |
| ⏱️ Duration | 2m 15s |

**🔗 Check the log**
[GitHub Actions workflow log](link)
```

When an iOS build fails, the comment also shows a `**Reason**: ...` line (for example: rejected because the version is closed, retry limit exceeded, bundle number mismatch).

---

## Required setup

### Workflow files

These 3 workflow files are required:

| File | Purpose |
|------|------|
| `PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml` | Detects comments and triggers builds |
| `PROJECT-FLUTTER-ANDROID-TEST-APK.yaml` | Android APK build |
| `PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml` | iOS TestFlight build |

### GitHub Secrets

**For Android builds:**
- `RELEASE_KEYSTORE_BASE64`
- `RELEASE_KEYSTORE_PASSWORD`
- `RELEASE_KEY_ALIAS`
- `RELEASE_KEY_PASSWORD`
- `GOOGLE_SERVICES_JSON` (optional): Firebase `google-services.json`
- `FIREBASE_SERVICE_ACCOUNT_JSON_BASE64` (optional): when you also use the Firebase upload
- `ENV_FILE` or `ENV` (optional)

**For iOS builds:**
- `APPLE_CERTIFICATE_BASE64`
- `APPLE_CERTIFICATE_PASSWORD`
- `APPLE_PROVISIONING_PROFILE_BASE64`
- `IOS_PROVISIONING_PROFILE_NAME`
- `APP_STORE_CONNECT_API_KEY_ID`
- `APP_STORE_CONNECT_ISSUER_ID`
- `APP_STORE_CONNECT_API_KEY_BASE64`
- `SECRETS_XCCONFIG` (optional): contents of `ios/Flutter/Secrets.xcconfig`
- `ENV_FILE` or `ENV` (optional)

> ⚠️ If even one secret name is different, the build fails at the certificate or keystore restore step. For the full list, see the [Flutter CI/CD overview](./flutter-cicd-overview.md#full-list-of-github-secrets).

### Repository permissions

The workflows need these permissions:

```yaml
permissions:
  contents: write
  pull-requests: write
  issues: write
```

---

## Troubleshooting

### Cannot find the "Guide by ProjectOps" comment

```
❌ 이슈에서 "Guide by ProjectOps" 댓글을 찾을 수 없습니다.
```

(The issue has no "Guide by ProjectOps" comment.)

**Fix:**
- The issue needs a comment in the "Guide by ProjectOps" format
- Or trigger the build from a PR

### Cannot parse the branch information

```
❌ "Guide by ProjectOps" 댓글에서 브랜치 정보를 파싱할 수 없습니다.
```

(The branch information in the "Guide by ProjectOps" comment cannot be parsed.)

**Fix:**
- The "Guide by ProjectOps" comment needs a `### 브랜치` section
- The branch name must be wrapped in a code block (```)

### Build workflow does not run

**Check:**
1. A workflow file that receives the `repository_dispatch` event exists
2. The workflow file is on the default branch
3. The workflow is enabled in the Actions tab

### Build fails

**Android:**
- Check that `flutter build apk` succeeds locally
- Check that the required secrets are set

**iOS:**
- Check that the certificate and provisioning profile are valid
- Check the App Store Connect API key permissions
- Check the ExportOptions.plist settings

---

## File structure

```
.github/workflows/project-types/flutter/
├── PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml  # build trigger
├── PROJECT-FLUTTER-ANDROID-TEST-APK.yaml           # Android test build
└── PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml        # iOS test build
```

---

## Environment variables

Environment variables you can set in each workflow:

```yaml
env:
  FLUTTER_VERSION: "3.24.5"      # Flutter version
  XCODE_VERSION: "16.4"          # Xcode version (iOS only)
  ENV_FILE_PATH: ".env"          # env file path
```

---

## Related docs

- [Flutter CI/CD overview](./flutter-cicd-overview.md)
- [iOS TestFlight wizard](./flutter-testflight-wizard.md)
- [Android Play Store wizard](./flutter-playstore-wizard.md)
