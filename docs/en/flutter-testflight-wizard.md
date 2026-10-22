# iOS TestFlight wizard guide

> A setup wizard for deploying a Flutter iOS app to TestFlight

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

The TestFlight wizard is a web UI tool that generates the settings files needed for iOS deployment.

**Location:** `.github/util/flutter/testflight-wizard/`

**Version:** 1.5.0 (for the exact value, see the version badge in the wizard header or `version.json`)

**Compatibility:**
- Flutter >= 3.0.0
- Xcode >= 15.0
- Fastlane >= 2.220.0

---

## Prerequisites

Before running the wizard, prepare the following in the Apple Developer Portal:

### 1. Enroll in the Apple Developer Program
- Enroll at [developer.apple.com](https://developer.apple.com)
- Costs $99 per year

### 2. Create a certificate
- You need an **Apple Distribution** certificate
- Create it in Keychain Access or Xcode
- Export it as a `.p12` file

### 3. Register an App ID
- Create an App ID under Identifiers
- Set the Bundle ID (for example `com.company.appname`)

### 4. Create a Provisioning Profile
- Choose the **App Store** type
- Link the App ID you created
- Link the distribution certificate

### 5. Create an App Store Connect API Key
- App Store Connect → Users and Access → Integrations → Keys
- Choose the **App Manager** or **Admin** role
- Download the `.p8` file (you can only do this once!)

---

## Using the wizard

### How to run it

```bash
# open the wizard in a browser
open .github/util/flutter/testflight-wizard/testflight-wizard.html
```

### The 9-step wizard

| Step | Contents | Input |
|------|------|-----------|
| 1 | Start | Wizard introduction |
| 2 | Certificate | Certificate creation guide |
| 3 | App ID | Bundle ID registration guide |
| 4 | Profile | Provisioning Profile creation guide |
| 5 | ASC registration | Register the app in App Store Connect |
| 6 | App info | Enter Team ID, Bundle ID, Profile Name |
| 7 | API Key | Enter the App Store Connect API Key details |
| 8 | Fastlane | Download the generated settings files |
| 9 | Done | Confirm the setup is complete |

### What you need to enter

```yaml
# Step 6: app info
Team ID: "XXXXXXXXXX"           # Apple Developer Team ID (10 characters)
Bundle ID: "com.company.app"    # the app's Bundle Identifier
Profile Name: "App Distribution" # Provisioning Profile name

# Step 7: API Key
API Key ID: "XXXXXXXXXX"        # App Store Connect API Key ID
Issuer ID: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # Issuer ID (UUID)
```

### Running the local script directly (CLI)

Instead of the web wizard, you can set things up with a command.

```bash
python3 .github/util/flutter/testflight-wizard/testflight-wizard.py setup \
  --project-path . \
  --bundle-id com.example.myapp \
  --team-id ABC1234DEF \
  --profile-name "MyApp Distribution"
```

| Option | Description |
|------|------|
| `--project-path` | Root path of the Flutter project |
| `--bundle-id` | iOS app Bundle ID |
| `--team-id` | Apple Developer Team ID (10 characters) |
| `--profile-name` | Provisioning Profile name |
| `--uses-encryption` | Whether the app uses encryption (`true`/`false`, default `false`) |

#### Common options (same for all three wizards)

| Option | Description |
|------|------|
| `--dry-run` | Prints only what would change and leaves files untouched |
| `--no-backup` | Does not create backups (`.bak`) of existing files |
| `--non-interactive` | Proceeds without confirmation prompts (for CI) |

> `--dry-run` takes **the same decision path** as a real run. You can rely on it to check before applying.
>
> The old positional form (`setup PROJECT_PATH BUNDLE_ID TEAM_ID PROFILE_NAME`) still works. You do not need to fix commands you have already copied.

---

## Generated files

### 1. ExportOptions.plist

The IPA export settings file.

**Location:** `ios/ExportOptions.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store</string>
    <key>teamID</key>
    <string>{{TEAM_ID}}</string>
    <key>provisioningProfiles</key>
    <dict>
        <key>{{BUNDLE_ID}}</key>
        <string>{{PROFILE_NAME}}</string>
    </dict>
    <key>signingStyle</key>
    <string>manual</string>
    <key>signingCertificate</key>
    <string>Apple Distribution</string>
</dict>
</plist>
```

### 2. Fastfile

The Fastlane deployment automation script.

**Location:** `ios/fastlane/Fastfile`

**Lanes provided:**
- `upload_testflight` - for CI (the IPA is already built)
- `build_and_deploy` - for local development (build + upload)

**Required environment variables** (not GitHub Secrets; values the workflow passes to fastlane):
- `APP_STORE_CONNECT_API_KEY_ID`
- `APP_STORE_CONNECT_ISSUER_ID`
- `API_KEY_PATH`: path to the restored `.p8` key file
- `APP_IDENTIFIER`: bundle ID
- `IPA_PATH`
- `APP_VERSION` / `BUILD_NUMBER`
- `RELEASE_NOTES`: the default text is used if empty
- `DEPLOY_MODE`: deployment mode such as `testflight_only` or review submission
- `DELIVER_LOCALES`: locales for the review metadata

### 3. Gemfile

The Fastlane dependency file.

**Location:** `ios/Gemfile`

```ruby
source "https://rubygems.org"

gem "fastlane"
```

---

## GitHub Secrets setup

Set the following Secrets so the workflows can run:

| Secret name | Description | Value format |
|------------|------|---------|
| `APPLE_CERTIFICATE_BASE64` | Apple Distribution certificate (.p12) | Base64 encoded |
| `APPLE_CERTIFICATE_PASSWORD` | Certificate password | String |
| `APPLE_PROVISIONING_PROFILE_BASE64` | Provisioning Profile (.mobileprovision) | Base64 encoded |
| `IOS_PROVISIONING_PROFILE_NAME` | Provisioning Profile name | String |
| `APP_STORE_CONNECT_API_KEY_ID` | API Key ID (10 characters) | String |
| `APP_STORE_CONNECT_ISSUER_ID` | Issuer ID | UUID format |
| `APP_STORE_CONNECT_API_KEY_BASE64` | AuthKey_XXXXXX.p8 file | Base64 encoded |
| `IOS_BUNDLE_ID` (optional) | Bundle ID. Can also be set as a repository variable (`vars`) | String |
| `ENV_FILE` (optional) | Contents of the `.env` file | String |
| `SECRETS_XCCONFIG` (optional) | Contents of `ios/Flutter/Secrets.xcconfig` | String |

> ⚠️ Secret names must match the names the workflows reference **exactly**. Certificate secrets use the `APPLE_` prefix, and the App Store Connect API Key body uses the `..._BASE64` suffix.

### How to Base64 encode

```bash
# encode the certificate
base64 -i Certificates.p12 | pbcopy

# encode the Provisioning Profile
base64 -i AppDistribution.mobileprovision | pbcopy

# encode the App Store Connect API Key
base64 -i AuthKey_XXXXXXXXXX.p8 | pbcopy
```

---

## Related workflows

### Production deployment
- **File:** `PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml`
- **Trigger:** push to the main branch
- **Purpose:** official TestFlight deployment

### Test build
- **File:** `PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml`
- **Trigger:** an `@projectops build app` or `@projectops ios build` comment (repository_dispatch)
- **Purpose:** test builds from a PR or issue

---

## Troubleshooting

### Certificate errors

```
❌ Error: No signing certificate "Apple Distribution" found
```

**Fix:**
1. Check that the `APPLE_CERTIFICATE_BASE64` Secret is set correctly
2. Check that the certificate has not expired
3. Check that the certificate password is correct

### Provisioning Profile errors

```
❌ Error: No profile matching 'App Distribution' found
```

**Fix:**
1. Check that `IOS_PROVISIONING_PROFILE_NAME` matches the actual Profile name
2. Check in the Apple Developer Portal that the Profile is valid
3. Check that the Profile is linked to the certificate

### App Store Connect API errors

```
❌ Error: Could not authenticate with App Store Connect
```

**Fix:**
1. Check that the API Key ID and Issuer ID are correct
2. Check that the API Key has the right role (App Manager or higher)
3. Check that the API Key contents were copied completely (including -----BEGIN PRIVATE KEY-----)

### ExportOptions.plist errors

```
❌ Error: exportArchive: No applicable devices found
```

**Fix:**
1. Check that `teamID` is correct
2. Check that the Bundle ID in `provisioningProfiles` matches the app
3. Check that the Profile name is correct

---

## File structure

```
.github/util/flutter/
├── _shared/                        # assets shared by all three wizards
│   ├── wizard.css                  #   shared component styles
│   ├── wizard-common.js            #   shared utilities (escaping, clipboard, state saving, etc.)
│   ├── check-consistency.py        #   consistency check across the three wizards
│   └── test_wizard_cli.py          #   CLI contract and dry-run safety tests
└── testflight-wizard/
    ├── testflight-wizard.html      # wizard web UI
    ├── testflight-wizard.js        # wizard logic
    ├── testflight-wizard.py        # setup script (setup subcommand)
    ├── version.json                # version info
    ├── version-sync.sh             # version.json → HTML sync
    └── templates/
        ├── ExportOptions.plist
        ├── Fastfile.ios.template
        └── Gemfile
```

> `_shared/` is the canonical source shared by the three wizards. If you changed a wizard, make sure `check-consistency.py` and `test_wizard_cli.py` pass before you commit. Details: [`_shared/README.md`](../../.github/util/flutter/_shared/README.md)

---

## Related docs

- [Flutter CI/CD overview](./flutter-cicd-overview.md)
- [Test build trigger](./flutter-test-build-trigger.md)
- [Apple Developer documentation](https://developer.apple.com/documentation/)
