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
| `GOOGLE_SERVICES_JSON` | Raw text of `google-services.json` (existing secret name) | The four Android workflows — they already restore the file |
| `GOOGLE_SERVICE_INFO_PLIST` | Raw text of `GoogleService-Info.plist` | The step you add to the two iOS workflows |

Raw text, not base64: CI writes the value back byte for byte, so the JSON/plist format cannot break. Binary files added as extra secrets are converted to base64 automatically.

> ⚠️ `ANDROID-PLAYSTORE-CICD`, `ANDROID-FIREBASE-CICD` and `ANDROID-SELFHOSTED-CICD` write `android/app/google-services.json` on every build, even when the secret is empty. Register `GOOGLE_SERVICES_JSON` even if you commit the file.

---

## CI/CD changes

| Workflow | `firebase-sdk` route | Other routes |
|----------|----------------------|--------------|
| `PROJECT-FLUTTER-ANDROID-TEST-APK` · `-PLAYSTORE-CICD` · `-FIREBASE-CICD` · `-SELFHOSTED-CICD` | No change, register `GOOGLE_SERVICES_JSON` | No change |
| `PROJECT-FLUTTER-IOS-TESTFLIGHT` (job `build-upload-ios`) | Add the step below | No change |
| `PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT` (job `build-upload-ios-test`) | Add the step below | No change |
| `PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER` | No change (it only dispatches the two test-build workflows) | No change |

Paste right after `Ensure .env file exists` and before `Set up Flutter`:

```yaml
      # OAuth wizard: recreate GoogleService-Info.plist from the GitHub Secret (whole file)
      - name: Create GoogleService-Info.plist
        env:
          GOOGLE_SERVICE_INFO_PLIST: ${{ secrets.GOOGLE_SERVICE_INFO_PLIST }}
        run: |
          if [ -z "$GOOGLE_SERVICE_INFO_PLIST" ]; then
            echo "::error title=Missing secret::GOOGLE_SERVICE_INFO_PLIST is empty. Register it (OAuth wizard, Secrets step)."
            exit 1
          fi
          mkdir -p ios/Runner
          printf '%s\n' "$GOOGLE_SERVICE_INFO_PLIST" > ios/Runner/GoogleService-Info.plist
```

The secret goes through an environment variable, the same pattern the Android workflows use for `GOOGLE_SERVICES_JSON`, so no character in the file can change the script. The wizard also shows the equivalent `cat > file << 'EOF'` form.

The plist must also be in the Runner target once (drag it into **Runner** in Xcode and commit `project.pbxproj`); the file itself stays out of Git.

> ⚠️ `repository_dispatch` runs the workflow definition on the default branch. Merge the iOS step to `main` before testing it with `@projectops ios build`.

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
| Google Sign-In fails on Android only | SHA-1 or package name missing on the Google side | Add the SHA-1 (Firebase fingerprint or one Android OAuth client per SHA-1) |
| iOS crashes or does nothing on Google Sign-In | `GIDClientID` or the reversed client ID URL scheme is missing | Run `setup` with `--google-ios-client-id` |
| iOS build fails: `GoogleService-Info.plist` not found | The plist is in the Xcode project but not restored in CI | Add the CI step and the `GOOGLE_SERVICE_INFO_PLIST` secret |
| Android release build fails in the Google Services Gradle task | `GOOGLE_SERVICES_JSON` empty; the workflow wrote an empty file | Register the secret |

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
