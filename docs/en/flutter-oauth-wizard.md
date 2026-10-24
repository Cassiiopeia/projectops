# OAuth Login Wizard (Kakao · Google)

> Set up Kakao and Google login for a Flutter app — console registration, native config, GitHub Secrets, CI/CD and `.gitignore` — so that release builds, test builds and comment-triggered builds all log in.

---

## Contents

- [Overview](#overview)
- [Run it](#run-it)
- [Steps](#steps)
- [Which key signs which build](#which-key-signs-which-build)
- [GitHub Secrets](#github-secrets)
- [CI/CD changes](#cicd-changes)
- [CLI](#cli)
- [Troubleshooting](#troubleshooting)
- [Sources](#sources)

---

## Overview

| Item | Value |
|------|-------|
| **Location** | `.github/util/flutter/oauth-wizard/` |
| **Files** | `oauth-wizard.html` (web UI) / `oauth-wizard*.js` / `oauth-wizard.py` (CLI, Python stdlib only) |
| **Shared assets** | `.github/util/flutter/_shared/` (CSS, JS, language toggle, checks) |
| **Packages** | `kakao_flutter_sdk_user` (2.x), `google_sign_in` (7.x) |
| **Languages** | English by default, Korean toggle (`?lang=ko`) |

Everything you enter stays in the browser (localStorage). The page makes no network calls with your values; files you drop (`google-services.json`, `GoogleService-Info.plist`) are read in the browser only.

---

## Run it

```bash
open .github/util/flutter/oauth-wizard/oauth-wizard.html
```

On Windows, double-click the file or drag it into a browser. You can jump to any step by clicking the step bar.

---

## Steps

Step 1 picks the providers; Kakao and Google steps appear only when selected (7–10 steps in total).

| Step | What you do | Result |
|------|-------------|--------|
| **Providers** | Pick Kakao, Google or both | Only the needed steps remain |
| **App IDs** | Find the Android `applicationId` and iOS bundle ID (or run `oauth-wizard.py detect`) | IDs used by every console |
| **Signing keys** | Get the SHA-1 of the debug, upload and Play App Signing keys | SHA-1 list + Kakao key hashes (computed in the browser) |
| **Kakao** | Create the app, copy the Native App Key, register Android (package + key hashes) and iOS (bundle ID), turn on Kakao Login | Native App Key, manifest / Info.plist / Dart snippets |
| **Google** | Firebase or Google Cloud route; create Android, iOS and Web OAuth clients | iOS client ID, Web client ID (`serverClientId`), Info.plist / Dart snippets |
| **Secrets** | Register files that must not be committed | Secret table, JSON / TXT / ZIP download |
| **CI/CD** | See which workflow needs what | Exact step and where to paste it |
| **.gitignore** | Keep secret files out of Git | Lines to add, `git rm --cached` command |
| **Apply** | Run one command (`--dry-run` first) | `AndroidManifest.xml` and `Info.plist` patched |
| **Checklist** | Tick everything off | Ready to build |

### Kakao console

These are the actual screens of the Kakao Developers console as of October 2026, checked end to end with a real app and a real login on iOS.

1. **Create app**: app name, company name and category are required. An individual developer can enter their own name as the company. Tick the operating policy box and save.
2. **App → Platform Key**: copy the **Native App Key**. The REST API, JavaScript and Admin keys are on the same page; never put the REST API or Admin key in the app.
3. Click the Native App Key's card. Android (package name, key hashes) and iOS (bundle ID) are registered on that page, then press **Save**. Enter one key hash per field; the **+** button next to the field adds another.
4. **Kakao Login → General**: switch the status to **ON** and confirm **Activate**. An app that reads only the user ID needs no consent item.

| You are | What changes |
|---|---|
| Individual developer | Everything above works without a business registration. Email as a **required** consent item needs a Biz app: verify your identity and agree to the Kakao Business terms to switch, and add an app icon first |
| Business with a registration number | Register it under **App → General → Business information** to switch to a Biz app (app icon required). A Biz app can also connect a business channel and create up to five test apps |

Also set an unlink webhook so you learn when a user disconnects your app outside of it.

### Google routes

| Route | When | Files shipped with the app |
|-------|------|----------------------------|
| `firebase-sdk` | The app uses Firebase SDKs (`firebase_core`, `firebase_auth`, …) | `google-services.json`, `GoogleService-Info.plist` (restored in CI from secrets) |
| `firebase-ids` | Firebase console creates the OAuth clients, no Firebase SDKs in the app | None — client IDs only |
| `cloud` | You create the OAuth clients in Google Cloud | None — client IDs only |

`google_sign_in` on iOS reads `GIDClientID` (and optionally `GIDServerClientID`) from `Info.plist` and needs the reversed client ID URL scheme. It does not need `GoogleService-Info.plist` for sign-in alone.

---

## Which key signs which build

A build signed with a key whose fingerprint is not registered cannot log in. This is the most common OAuth failure after CI is set up.

| Build | Signed with | Register |
|-------|-------------|----------|
| `flutter run` | Local debug key `~/.android/debug.keystore` (differs per computer) | Debug SHA-1 / key hash |
| `ANDROID-TEST-APK` (`@projectops apk build`), `ANDROID-FIREBASE-CICD` | Upload key from `RELEASE_KEYSTORE_BASE64` | Upload SHA-1 / key hash |
| Installed from Google Play (`ANDROID-PLAYSTORE-CICD`) | Play App Signing key (Google re-signs) | Play App Signing SHA-1 / key hash |
| `ANDROID-SELFHOSTED-CICD` | `DEBUG_KEYSTORE` secret, unless `ANDROID_SELFHOSTED_RELEASE_SIGNING=true` | That keystore's SHA-1 / key hash |

iOS needs no fingerprint: both providers match the bundle ID.

---

## GitHub Secrets

Kakao keys and Google client IDs are public identifiers that end up inside the app, so they live in committed files and need no secret. Never put the Kakao REST API / Admin key or a Google client secret in the app.

Secrets are needed only for the `firebase-sdk` route:

| Secret | Value | Used by |
|--------|-------|---------|
| `GOOGLE_SERVICES_JSON` | Raw text of `google-services.json` | The four Android workflows and Flutter CI |
| `GOOGLE_SERVICE_INFO_PLIST` | Raw text (or base64) of `GoogleService-Info.plist` | Both iOS TestFlight workflows and Flutter CI |

Paste the files as raw text: CI writes the value back byte for byte, so the JSON/plist format cannot break. Binary files added as extra secrets are converted to base64 automatically.

Committing the files instead is also fine: leave the secrets unset and CI uses the committed file. When both exist, the secret wins.

---

<a id="cicd-changes"></a>

## CI/CD changes

**Nothing to add.** The templates restore both files with `.github/scripts/firebase_config_files.py` (#785):

- `android/app/google-services.json` from `GOOGLE_SERVICES_JSON`, `ios/Runner/GoogleService-Info.plist` from `GOOGLE_SERVICE_INFO_PLIST` (raw text or base64)
- only when the secret is set — an empty secret never overwrites a committed file
- when the Gradle plugin (`com.google.gms.google-services`) or the Xcode project needs a file that is missing, it prints an `::error` naming the secret

| Workflow | `firebase-sdk` route | Other routes |
|----------|----------------------|--------------|
| `PROJECT-FLUTTER-ANDROID-TEST-APK` · `-PLAYSTORE-CICD` · `-FIREBASE-CICD` · `-SELFHOSTED-CICD` | No change — register `GOOGLE_SERVICES_JSON` | No change |
| `PROJECT-FLUTTER-IOS-TESTFLIGHT` · `-IOS-TEST-TESTFLIGHT` | No change — register `GOOGLE_SERVICE_INFO_PLIST` (restored right after `Ensure .env file exists`) | No change |
| `PROJECT-FLUTTER-CI` | No change — restores both when set | No change |
| `PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER` | No change (it only dispatches the two test-build workflows) | No change |

The plist must also be in the Runner target once (drag it into **Runner** in Xcode and commit `project.pbxproj`); the file itself can stay out of Git.

### Older installs

If `.github/scripts/firebase_config_files.py` is missing, your templates predate the restore script. Update them instead of editing workflows by hand:

```bash
ls .github/scripts/firebase_config_files.py   # missing?
npx projectops                                # update the templates
```

> ⚠️ `repository_dispatch` runs the workflow definition on the default branch. After updating, merge to `main` before testing with `@projectops ios build`.

Only if you cannot update yet, the wizard shows a manual fallback step for the two iOS jobs (`build-upload-ios`, `build-upload-ios-test`, right after `Ensure .env file exists`). Like the script it skips when the secret is empty, but it takes raw plist text only. Remove it after updating, or the file is written twice.

```yaml
      - name: Create GoogleService-Info.plist
        env:
          GOOGLE_SERVICE_INFO_PLIST: ${{ secrets.GOOGLE_SERVICE_INFO_PLIST }}
        run: |
          if [ -z "$GOOGLE_SERVICE_INFO_PLIST" ]; then
            echo "GOOGLE_SERVICE_INFO_PLIST not set, skipping"
            exit 0
          fi
          mkdir -p ios/Runner
          printf '%s\n' "$GOOGLE_SERVICE_INFO_PLIST" > ios/Runner/GoogleService-Info.plist
```

---

## CLI

`oauth-wizard.py` uses only the Python standard library and runs on macOS, Linux and Windows.

```bash
# Detect applicationId, bundle ID and existing OAuth entries (read-only JSON)
python3 .github/util/flutter/oauth-wizard/oauth-wizard.py detect --project-path .

# SHA-1, SHA-256 and Kakao key hash of a keystore (debug keystore by default)
python3 .github/util/flutter/oauth-wizard/oauth-wizard.py fingerprints \
  --keystore android/app/keystore/key.jks --alias YOUR_KEY_ALIAS --storepass YOUR_STORE_PASSWORD

# SHA-1 (e.g. from Play Console) -> Kakao key hash
python3 .github/util/flutter/oauth-wizard/oauth-wizard.py key-hash --sha1 AA:BB:...:FF

# Patch AndroidManifest.xml, Info.plist and .gitignore (preview first)
python3 .github/util/flutter/oauth-wizard/oauth-wizard.py setup --project-path . \
  --kakao-native-app-key YOUR_NATIVE_APP_KEY \
  --google-ios-client-id YOUR_IOS_CLIENT_ID.apps.googleusercontent.com \
  --google-server-client-id YOUR_WEB_CLIENT_ID.apps.googleusercontent.com \
  --update-gitignore --dry-run
```

| `setup` option | Meaning |
|----------------|---------|
| `--kakao-native-app-key` | Adds `AuthCodeHandlerActivity` (`kakao{KEY}://oauth`) to the manifest, the `kakao{KEY}` URL scheme and `kakaokompassauth`, `kakaolink` to Info.plist |
| `--google-ios-client-id` | Adds `GIDClientID` and the reversed client ID URL scheme to Info.plist |
| `--google-server-client-id` | Adds `GIDServerClientID` |
| `--update-gitignore` | Ignores the wizard's export files; with `--firebase-files` also the two Firebase config files |
| `--dry-run` | Prints every change, writes nothing |
| `--no-backup` | No `*.bak` copies |
| `--non-interactive` | No confirmation prompt |

`setup` is idempotent: a second run reports `already configured`. A changed Kakao key or Google client ID replaces the old scheme instead of adding a second one. It computes every change before writing, so if one file is missing or invalid, nothing is changed.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Kakao login works with `flutter run` but not from a CI build | The CI build is signed with the upload key (or Play App Signing key) whose key hash is not registered | Add that key hash in Kakao Developers |
| Kakao login on a simulator or emulator stops at "2-step verification" and then says the login has expired | A Kakao account with 2-step verification sends a confirmation to KakaoTalk that is valid for 5 minutes | Press **Confirm** in KakaoTalk within 5 minutes, or choose email verification on that screen |
| Google Sign-In fails on Android only | SHA-1 or package name missing on the Google side | Add the SHA-1 (Firebase fingerprint or one Android OAuth client per SHA-1) |
| Android Google Sign-In fails with `No credentials available` | No Google account on the device (Credential Manager needs one), or the Android OAuth client was created minutes ago and is not active yet | Add a Google account in the device settings; for a new client, wait a few minutes and retry |
| Google shows `401 invalid_client` / "The OAuth client was not found" | The client ID in `GIDClientID` (iOS) or `serverClientId` does not exist in Google Cloud | Copy the client IDs again from Google Cloud and re-run `setup` |
| iOS crashes or does nothing on Google Sign-In | `GIDClientID` or the reversed client ID URL scheme is missing | Run `setup` with `--google-ios-client-id` |
| iOS build fails: `GoogleService-Info.plist` not found (CI log has an `::error` naming `GOOGLE_SERVICE_INFO_PLIST`) | The plist is in the Xcode project but neither committed nor in a secret | Register `GOOGLE_SERVICE_INFO_PLIST`; on old templates run `npx projectops` |
| Android build fails in the Google Services Gradle task (`::error` naming `GOOGLE_SERVICES_JSON`) | The Gradle plugin needs `google-services.json`, but it is neither committed nor in a secret | Register `GOOGLE_SERVICES_JSON` |

---

## Sources

- Kakao Flutter SDK getting started: https://developers.kakao.com/docs/ko/flutter/getting-started
- Kakao Login for Flutter: https://developers.kakao.com/docs/ko/kakaologin/flutter
- Kakao iOS allowlist and URL scheme: https://developers.kakao.com/docs/ko/ios/getting-started
- Kakao Android key hash: https://developers.kakao.com/docs/ko/android/getting-started
- `kakao_flutter_sdk_user`: https://pub.dev/packages/kakao_flutter_sdk_user
- `google_sign_in`: https://pub.dev/packages/google_sign_in
- Android integration: https://pub.dev/packages/google_sign_in_android
- iOS integration: https://pub.dev/packages/google_sign_in_ios
- Google Cloud OAuth clients: https://support.google.com/cloud/answer/15549257
