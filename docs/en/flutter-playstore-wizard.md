# Android Play Store wizard guide

> A setup wizard for deploying a Flutter Android app to the Play Store

---

## Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Using the wizard](#using-the-wizard)
- [Generated files](#generated-files)
- [GitHub Secrets setup](#github-secrets-setup)
- [Related workflows](#related-workflows)
- [Troubleshooting](#troubleshooting)

---

## Overview

The Play Store wizard is a web UI tool that generates the settings files needed for Android deployment.

**Location:** `.github/util/flutter/playstore-wizard/`

**Version:** 1.5.0 (for the exact value, see the version badge in the wizard header or `version.json`)

**Compatibility:**
- Flutter >= 3.0.0
- Android SDK >= 33
- Fastlane >= 2.220.0

---

## Prerequisites

Before running the wizard, prepare the following:

### 1. Register with Google Play Console
- Register a developer account at [play.google.com/console](https://play.google.com/console)
- One-time registration fee of $25

> ⚠️ **With a personal account, closed testing is effectively required.**
> **Personal developer accounts created after 2023-11-13** must complete a **closed test**
> with at least 12 testers taking part for at least 14 days before they get production access.
> This template's default deployment goes as far as the **internal testing track**, and internal
> testing **does not count** toward that requirement.
>
> So with a personal account, **turn on promotion to closed testing** in the deployment settings.
> If you do not, deployments keep going out but the production access requirement is never met,
> and you end up pushing the closed track by hand, so the versions on the two tracks drift apart.
>
> For how to turn it on and what each track is for, see the "Android tracks" section of
> [flutter-cicd-overview.md](./flutter-cicd-overview.md). (Accounts created before that date and organization accounts are not affected.)

### 2. Create a signing key
- You need a Keystore file for release signing
- If you lose the key you cannot update the app, so keep it safe

```bash
# create a Keystore
keytool -genkey -v -keystore release-key.jks \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -alias release-key
```

### 3. Create a Google Play service account
- Create a service account in Google Cloud Console
- Link it to Play Console
- Download the JSON key file

---

## Using the wizard

### How to run it

```bash
# open the wizard in a browser
open .github/util/flutter/playstore-wizard/playstore-wizard.html

# or run the setup script
# macOS/Linux
python3 .github/util/flutter/playstore-wizard/playstore-wizard.py setup

# Windows
python .github\util\flutter\playstore-wizard\playstore-wizard.py setup
```

### Wizard steps

| Step | Contents | Input |
|------|------|-----------|
| 1 | Start | Wizard introduction |
| 2 | Keystore | Signing key creation guide |
| 3 | Service account | Google Play service account creation guide |
| 4 | App info | Enter the Application ID |
| 5 | Fastlane | Download the generated settings files |
| 6 | Done | Confirm the setup is complete |

### What you need to enter

```yaml
# Application ID (package name)
Application ID: "com.company.appname"

# Keystore info
Keystore Path: "android/app/release-key.jks"
Keystore Password: "your-keystore-password"
Key Alias: "release-key"
Key Password: "your-key-password"
```

### Running the local script directly (CLI)

```bash
python3 .github/util/flutter/playstore-wizard/playstore-wizard.py setup \
  --project-path . \
  --application-id com.example.app \
  --key-alias my-release-key \
  --store-password MyPass123 --key-password MyPass123 \
  --validity-days 99999 \
  --cert-cn "My Name" --cert-o "My Company" --cert-l "Seoul" --cert-c "KR"
```

| Option | Description |
|------|------|
| `--project-path` | Root path of the Flutter project |
| `--application-id` | Android Application ID |
| `--key-alias` | Keystore alias |
| `--store-password` / `--key-password` | Keystore / key password |
| `--validity-days` | Certificate validity (days) |
| `--cert-cn` / `--cert-o` / `--cert-l` / `--cert-c` | Certificate details |

#### Common options (same for all three wizards)

| Option | Description |
|------|------|
| `--dry-run` | Prints only what would change. Does not actually create the keystore either |
| `--no-backup` | Does not create backups (`.bak`) of existing files |
| `--non-interactive` | Proceeds without confirmation prompts (for CI) |

> ⚠️ The old positional form (10 arguments) still works, but **the passwords are in positions 4 and 5, so getting the order off by one stores the wrong values.** Named flags are recommended.

---

## Generated files

### 1. Fastfile.playstore

The Play Store deployment automation script.

**Location:** `android/fastlane/Fastfile.playstore`

**Lanes provided:**
- `build_aab` - build the AAB
- `deploy_internal` - upload to Internal Testing + promote according to `DEPLOY_MODE` (closed/open testing, production)
- `promote_internal_to_closed_testing` / `promote_internal_to_open_testing` - promote to an intermediate track
- `promote_internal_to_production` - promote to production (`PRODUCTION_ROLLOUT`, default 1.0 = full release)
- `validate` - validate the service account

**Manage the deployment mode as code:** put `android.deploy_mode` and `android.production_rollout` in `.github/config/store-deploy.json` (example in `store-deploy.json.example`) so the choice is kept in git and can be reviewed. The order of precedence is **manual run input > settings file > repository variable (`ANDROID_DEPLOY_MODE`) > `store_only`**, and without the file it works exactly as before with the repository variable. The template does not ship this file, so updates never overwrite it, and an invalid value is not silently ignored; it fails before deployment. iOS (TestFlight) reads `ios.deploy_mode` from the same file the same way.

You do not have to write the file by hand. Add `--deploy-mode store_prepare --production-rollout 0.1` at the end of `playstore-wizard.py setup` and the wizard writes them to the `android` section (optional flags; if you leave them out, nothing is written). It does not remove an existing `ios` section or keys you wrote, it fails before creating the keystore if a value is invalid, and it does not create the file under `--dry-run`.

**Production rollout fraction:** set it with the repository variable `ANDROID_PRODUCTION_ROLLOUT` (greater than 0, at most 1.0, default 1.0). 1.0 goes out to all users as soon as review passes and cannot be undone. Below 1.0 (for example 0.1), only that fraction is rolled out in stages, and **raising the fraction is not automated**; a person raises it in Play Console under Production > Release management. If something goes wrong, halt the release on the same screen.

**The first release is manual:** an app that has never been released to production cannot be promoted to production through the API. You have to release it once from the console. A build already on closed testing can be attached without rebuilding via Production > New release > "Add from library".

**If you edited the Fastfile yourself:** values the workflow passes (`DEPLOY_MODE`, `PROMOTE_*`, `PRODUCTION_ROLLOUT`) are silently ignored if the Fastfile does not read them. The workflow detects this and leaves a warning in the CI log, but does not block. Running the wizard again rewrites this file from the template, so your manual edits are lost. Check with a diff before running it.

**Required environment variables:**
- `AAB_PATH` - path to the AAB file
- `GOOGLE_PLAY_JSON_KEY` - path to the service account JSON file

### 2. build.gradle.kts signing config

The app signing configuration code.

**Location:** `android/app/build.gradle.kts` (must be added by hand)

Signing values are read from the **`android/key.properties` file**, not from environment variables. In CI, the workflow restores this file and the keystore from Secrets.

```kotlin
// load key.properties
val keystorePropertiesFile = rootProject.file("key.properties")
val keystoreProperties = Properties()
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(FileInputStream(keystorePropertiesFile))
}

android {
    signingConfigs {
        create("release") {
            keyAlias = keystoreProperties["keyAlias"] as String? ?: ""
            keyPassword = keystoreProperties["keyPassword"] as String? ?: ""
            storeFile = keystoreProperties["storeFile"]?.let { rootProject.file(it) }
            storePassword = keystoreProperties["storePassword"] as String? ?: ""
        }
    }
    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release")
        }
    }
}
```

`android/key.properties` format (for local builds; always add it to `.gitignore`):

```properties
storeFile=keystore/key.jks
storePassword=store_password
keyAlias=key_alias
keyPassword=key_password
```

For the full template, see `.github/util/flutter/playstore-wizard/templates/build.gradle.kts.signing.template`.

---

## GitHub Secrets setup

Set the following Secrets so the workflows can run:

| Secret name | Description | Value format |
|------------|------|---------|
| `RELEASE_KEYSTORE_BASE64` | Release Keystore (.jks) | Base64 encoded |
| `RELEASE_KEYSTORE_PASSWORD` | Keystore password | String |
| `RELEASE_KEY_ALIAS` | Key alias | String |
| `RELEASE_KEY_PASSWORD` | Key password | String |
| `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64` | Play Console service account JSON | Base64 encoded |
| `GOOGLE_SERVICES_JSON` | Contents of Firebase `google-services.json` | JSON string |
| `ENV_FILE` or `ENV` (optional) | Contents of the `.env` file (`ENV_FILE` takes precedence) | String |

> ⚠️ Secret names must match the names the workflows reference **exactly**. Signing key secrets use the `RELEASE_` prefix, and the Play Console service account is the **base64 encoded value** (`..._BASE64`), not the raw JSON.

### How to Base64 encode

```bash
# encode the Keystore
base64 -i release-key.jks | pbcopy   # macOS
base64 release-key.jks               # Linux

# encode the Play Console service account JSON
base64 -i service-account.json | pbcopy   # macOS
base64 service-account.json               # Linux
```

### Service account JSON setup

Set `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64` to the **base64 encoded value** of a service account JSON file shaped like this:

```json
{
  "type": "service_account",
  "project_id": "your-project-id",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "your-service-account@your-project.iam.gserviceaccount.com",
  "client_id": "...",
  ...
}
```

---

## Related workflows

### Production deployment
- **File:** `PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD.yaml`
- **Trigger:** push to the main branch
- **Purpose:** deploy to Play Store Internal Testing

### Test build
- **File:** `PROJECT-FLUTTER-ANDROID-TEST-APK.yaml`
- **Trigger:** an `@projectops build app` or `@projectops apk build` comment (repository_dispatch)
- **Purpose:** test APK builds from a PR or issue

### Self-hosted server (SMB) deployment
- **File:** `PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD.yaml`
- **Trigger:** push to the main branch
- **Purpose:** deploy the APK to an SMB share on your own server (Synology NAS, other NAS, Linux, etc.)

---

## Troubleshooting

### Signing errors

```
❌ Error: Keystore was tampered with, or password was incorrect
```

**Fix:**
1. Check that `RELEASE_KEYSTORE_PASSWORD` / `RELEASE_KEY_PASSWORD` are correct
2. Check that `RELEASE_KEYSTORE_BASE64` was Base64 encoded correctly
3. Check that the Keystore file is not corrupted

### Service account errors

```
❌ Error: The caller does not have permission
```

**Fix:**
1. Check that the service account has been granted Play Console permissions
2. Play Console → Users and permissions → add the service account
3. The "Release apps to testing tracks" permission is required

### AAB file errors

```
❌ Error: AAB file not found
```

**Fix:**
1. Check that the Flutter build succeeded
2. Run `flutter build appbundle --release`
3. Check that the AAB file path is correct: `build/app/outputs/bundle/release/app-release.aab`

### Application ID mismatch

```
❌ Error: Package name does not match
```

**Fix:**
1. Check that `package_name` in the Fastfile matches `applicationId` in `android/app/build.gradle`
2. Check that it matches the package name registered in Play Console

---

## File structure

```
.github/util/flutter/
├── _shared/                            # assets shared by all three wizards
│   ├── wizard.css                      #   shared component styles
│   ├── wizard-common.js                #   shared utilities (escaping, clipboard, state saving, etc.)
│   ├── check-consistency.py            #   consistency check across the three wizards
│   └── test_wizard_cli.py              #   CLI contract and dry-run safety tests
└── playstore-wizard/
    ├── playstore-wizard.html           # wizard web UI
    ├── playstore-wizard.js             # wizard logic
    ├── playstore-wizard.py             # setup script (setup / apply / detect-app-id, works on every OS)
    ├── version.json                    # version info
    ├── version-sync.sh                 # version.json → HTML sync
    └── templates/
        ├── Fastfile.playstore.template         # Fastfile template
        └── build.gradle.kts.signing.template   # signing config template
```

> `_shared/` is the canonical source shared by the three wizards. If you changed a wizard, make sure `check-consistency.py` and `test_wizard_cli.py` pass before you commit. Details: [`_shared/README.md`](../../.github/util/flutter/_shared/README.md)

---

## Related docs

- [Flutter CI/CD overview](./flutter-cicd-overview.md)
- [Test build trigger](./flutter-test-build-trigger.md)
- [Google Play Console documentation](https://developer.android.com/distribute/console)
