# Firebase App Distribution wizard

> A 5-step web wizard that generates the settings for deploying a Flutter Android app through Firebase App Distribution.

---

## Contents

- [Overview](#overview)
- [How to run it](#how-to-run-it)
- [The 5-step flow](#the-5-step-flow)
- [GitHub Secrets setup](#github-secrets-setup)
- [Workflow env settings](#workflow-env-settings)
- [CLI usage](#cli-usage)
- [Related workflows](#related-workflows)
- [Troubleshooting](#troubleshooting)

---

## Overview

Use it when you want to ship an APK straight to testers without Play Store review. It uses **the same signing Secrets** as the Play Store deployment; only the upload target changes to Firebase.

| Item | Value |
|------|-----|
| **Location** | `.github/util/flutter/firebase-wizard/` |
| **Contents** | `firebase-wizard.html` (web UI) / `firebase-wizard.js` / `firebase-wizard.py` (CLI) |
| **Shared assets** | `.github/util/flutter/_shared/` (CSS, JS and check scripts shared by all three wizards) |
| **Deployment target** | Firebase App Distribution |
| **Linked workflow** | `PROJECT-FLUTTER-ANDROID-FIREBASE-CICD.yaml` |

> All file conversions (base64 encoding, etc.) happen **only inside the browser** and nothing is sent to an external server.

---

## How to run it

```bash
open .github/util/flutter/firebase-wizard/firebase-wizard.html
```

On Windows, double-click `firebase-wizard.html` in File Explorer or drag it into a browser.

You can move freely between steps (click the step indicator at the top).

---

## The 5-step flow

| Step | Contents | Result |
|------|------|--------|
| **1. Firebase Console guide** | Create the project, register the Android app, **enable App Distribution**, create a tester group | Download `google-services.json`, get the app ID and group alias |
| **2. Issue a Service Account** | Issue the service account key GitHub Actions uses to upload to Firebase | Download the Service Account JSON |
| **3. Enter app info** | Enter the **app ID** and **tester group alias** from step 1 | A setup command that substitutes the workflow placeholders |
| **4. Upload files** | Upload the Service Account JSON (required) and `google-services.json` (optional) | Base64 encoded Secret values |
| **5. Register Secrets** | Review the GitHub Secrets to register and download the outputs | JSON / TXT / ZIP (includes the setup script) |

> ⚠️ **If you skip enabling App Distribution in step 1, deployment fails with `404 not found`.** Do not skip it.
>
> ⚠️ The tester group value for step 3 is **the "group alias", not the "display name"** shown on screen.

---

## GitHub Secrets setup

### Secrets the wizard generates

| Secret name | Description | Value format |
|------------|------|---------|
| `FIREBASE_SERVICE_ACCOUNT_JSON_BASE64` | Firebase service account JSON | Base64 encoded |
| `GOOGLE_SERVICES_JSON` (optional) | Contents of `google-services.json` | JSON string |

### Signing Secrets you register yourself

These use **the same names** as the Play Store deployment. If you already ran the Play Store wizard, there is nothing more to do.

| Secret name | Description | Value format |
|------------|------|---------|
| `RELEASE_KEYSTORE_BASE64` | Signing keystore (.jks) | Base64 encoded |
| `RELEASE_KEYSTORE_PASSWORD` | Keystore password | String |
| `RELEASE_KEY_ALIAS` | Key alias | String |
| `RELEASE_KEY_PASSWORD` | Key password | String |
| `ENV_FILE` or `ENV` (optional) | Contents of the `.env` file (`ENV_FILE` takes precedence) | String |

---

## Workflow env settings

In the env section of `PROJECT-FLUTTER-ANDROID-FIREBASE-CICD.yaml`, change these two values for your project. The setup command from wizard step 3 (or the CLI below) substitutes them for you.

```yaml
env:
  FIREBASE_APP_ID: "your-firebase-app-id"     # e.g. 1:905325245238:android:86db...
  FIREBASE_TESTER_GROUP: "testers"            # tester group alias
```

---

## CLI usage

To substitute the values without the web wizard, run `firebase-wizard.py` directly (stdlib only, works on macOS and Windows).

```bash
python3 .github/util/flutter/firebase-wizard/firebase-wizard.py setup \
  --project-path /path/to/project \
  --app-id "1:905325245238:android:86db..." \
  --tester-group "testers"
```

### Common options (same for all three wizards)

| Option | Description |
|------|------|
| `--dry-run` | Prints only what would change and leaves files untouched |
| `--non-interactive` | Proceeds without confirmation prompts (for CI) |
| `--no-backup` | Does not create a backup file (`.bak`) before editing |

> `--dry-run` takes **the same decision path** as a real run. It keeps what would have been written in memory and later steps read it, so there is no case where "the real run succeeds but only the dry run fails". You can rely on it to check before applying.

---

## Related workflows

### Production deployment
- **File:** `PROJECT-FLUTTER-ANDROID-FIREBASE-CICD.yaml`
- **Trigger:** push to the main branch (+ `workflow_dispatch`)
- **Purpose:** build the APK and upload it to Firebase App Distribution

### Test build
- **File:** `PROJECT-FLUTTER-ANDROID-TEST-APK.yaml`
- **Trigger:** an `@projectops build app` or `@projectops apk build` comment (repository_dispatch)
- **Purpose:** test APK builds from a PR or issue (includes an option to upload to Firebase)

---

## Troubleshooting

### 404 not found

```
❌ Error: Requested entity was not found
```

**Fix:**
1. Check that App Distribution is **enabled** in Firebase Console (wizard step 1, item 3)
2. Check that `FIREBASE_APP_ID` matches the actual app ID

### Not delivered to testers

**Check:**
1. Check that `FIREBASE_TESTER_GROUP` holds **the group alias, not the display name**
2. Check in Firebase Console that testers are registered in that group

### Authentication failure

```
❌ Error: Could not authenticate
```

**Fix:**
1. Check that `FIREBASE_SERVICE_ACCOUNT_JSON_BASE64` is a base64 encoded value (not the raw JSON)
2. Check that the service account has Firebase App Distribution permissions

### Signing errors

```
❌ Error: Keystore was tampered with, or password was incorrect
```

**Fix:** same as the signing items in the [Play Store wizard guide](./flutter-playstore-wizard.md#troubleshooting).

---

## Related docs

- [Flutter CI/CD overview](./flutter-cicd-overview.md)
- [Android Play Store wizard](./flutter-playstore-wizard.md)
- [Test build trigger](./flutter-test-build-trigger.md)
