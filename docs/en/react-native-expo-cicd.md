# React Native Expo CI/CD

> CI, test builds and store deploys for Expo apps, on GitHub Actions only (no EAS)

---

## Overview

Install with `--type react-native-expo` (or let the wizard detect `app.json` and the `expo` dependency).
In a monorepo, pass the app folder: `--paths "react-native-expo=mobile"`.

Five workflows are installed:

| Workflow | Trigger | What it does |
|---|---|---|
| `PROJECT-REACT-NATIVE-EXPO-CI` | PR and push to `develop` | Install, `tsc --noEmit`, ESLint, Jest (each only when the project has it) |
| `PROJECT-REACT-NATIVE-EXPO-ANDROID-TEST-APK` | Manual, or `@projectops app build` / `apk build` comment | `expo prebuild` > signed APK as a run artifact |
| `PROJECT-REACT-NATIVE-EXPO-IOS-TESTFLIGHT` | Push to `main` (release), manual, or `@projectops app build` / `ios build` comment (test) | `expo prebuild` > signed IPA > TestFlight |
| `PROJECT-REACT-NATIVE-EXPO-ANDROID-PLAYSTORE-CICD` | Push to `main`, manual | Signed AAB > Play Store internal testing > closed testing |
| `PROJECT-REACT-NATIVE-EXPO-PROJECTOPS-APP-BUILD-TRIGGER` | Issue or PR comment | Starts the test APK and TestFlight builds for the comment's branch |

When `version.yml` sets `deploy_trigger_branch`, the two store workflows run on that branch instead of `main`.

## How the builds work

- **No EAS.** `npx expo prebuild` generates `android/` and `ios/` on the runner. Only GitHub Actions minutes are used.
  If you commit the native folders (no prebuild), the workflows build them as they are.
- **Versions.** `version.yml` is the source. `version` goes to `expo.version`, `version_code` goes to
  `expo.android.versionCode` for Play Store releases. The release workflow also keeps `app.json` in sync.
  Test builds and iOS builds use a time-based build number (`build_number.py`), so they never collide.
- **Android signing** is injected with Gradle `-Pandroid.injected.signing.*` properties, so nothing is written into the generated project.
  The test APK falls back to the debug key when no keystore is set.
- **iOS signing.** The team ID is read from the provisioning profile and written to `ios.appleTeamId` before prebuild.
  `ExportOptions.plist` and the fastlane upload lane are generated on the runner (`expo_app.py ios-signing`),
  then the same archive, number check, upload and retry logic as the Flutter workflows runs (`ios_release.py`).
  Builds go to TestFlight only. Submit for App Store review in App Store Connect.
- **Package and bundle ID** come from the resolved app config (`npx expo config`, so `app.config.js` works too).

## GitHub Secrets

Names are the same as the Flutter workflows, so switching stacks keeps the setup.

| Secret | Used by | Required |
|---|---|---|
| `RELEASE_KEYSTORE_BASE64` | Play Store, test APK | Play Store: yes. Test APK: no (debug key) |
| `RELEASE_KEYSTORE_PASSWORD`, `RELEASE_KEY_ALIAS`, `RELEASE_KEY_PASSWORD` | Play Store, test APK | With the keystore |
| `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64` | Play Store | Yes |
| `APPLE_CERTIFICATE_BASE64`, `APPLE_CERTIFICATE_PASSWORD` | TestFlight | Yes |
| `APPLE_PROVISIONING_PROFILE_BASE64` | TestFlight | Yes (App Store profile for the bundle ID) |
| `APP_STORE_CONNECT_API_KEY_ID`, `APP_STORE_CONNECT_ISSUER_ID`, `APP_STORE_CONNECT_API_KEY_BASE64` | TestFlight | Yes |
| `IOS_BUNDLE_ID` | TestFlight | No (overrides `expo.ios.bundleIdentifier`) |
| `ENV_FILE` | All builds | No (written to the app's `.env`) |
| `GOOGLE_SERVICES_JSON`, `GOOGLE_SERVICE_INFO_PLIST` | Android, iOS builds | No (Firebase) |

Optional repository variables: `NODE_VERSION`, `JAVA_VERSION`, `XCODE_VERSION`, `IOS_RUNNER` (`xcode-27` for the iOS 27 SDK),
`ANDROID_PROMOTE_TO_CLOSED_TESTING` (default `true`), `ANDROID_CLOSED_TESTING_TRACK` (default `alpha`),
`ANDROID_RELEASE_STATUS` (`completed` or `draft`), `ANDROID_PACKAGE_NAME`.

## First-time setup

1. **Play Console:** create the app and upload one AAB by hand (the API cannot upload to an app with no package bound yet).
   While the app is still a draft, Play accepts only draft releases: the upload retries as a draft with a warning
   (set `ANDROID_RELEASE_STATUS=draft` to skip the first attempt).
2. **App Store Connect:** create the app record for the bundle ID, an App Store provisioning profile and an API key.
3. Register the secrets above, for example with `/pro-github secrets set`.
4. Build once from an issue comment: `@projectops app build <branch>`.

## Notes

- `expo lint` is not called: on some SDKs it rejects ESLint 9. CI runs `npx eslint .` when an ESLint config exists.
- Native builds for four ABIs take long on hosted runners. The Play Store job allows 90 minutes;
  the test APK builds `arm64-v8a` only (`ANDROID_ARCHITECTURES` in the workflow env).
- `react-native` (bare, without Expo) has no app workflows yet; only version sync is installed.
