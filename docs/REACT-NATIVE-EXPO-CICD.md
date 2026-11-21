# React Native Expo CI/CD

> Expo 앱의 CI, 테스트 빌드, 스토어 배포를 GitHub Actions만으로 처리합니다 (EAS 없음)

---

## 개요

`--type react-native-expo`로 설치합니다 (마법사가 `app.json`과 `expo` 의존성을 보고 자동 감지하기도 합니다).
모노레포라면 앱 폴더를 넘깁니다: `--paths "react-native-expo=mobile"`.

설치되는 워크플로 5개:

| 워크플로 | 실행 시점 | 하는 일 |
|---|---|---|
| `PROJECT-REACT-NATIVE-EXPO-CI` | `develop` PR·push | 설치, `tsc --noEmit`, ESLint, Jest (프로젝트에 있는 것만) |
| `PROJECT-REACT-NATIVE-EXPO-ANDROID-TEST-APK` | 수동, 또는 `@projectops app build` / `apk build` 댓글 | `expo prebuild` > 서명된 APK를 실행 결과물로 |
| `PROJECT-REACT-NATIVE-EXPO-IOS-TESTFLIGHT` | `main` push(릴리스), 수동, `@projectops app build` / `ios build` 댓글(테스트) | `expo prebuild` > 서명된 IPA > TestFlight |
| `PROJECT-REACT-NATIVE-EXPO-ANDROID-PLAYSTORE-CICD` | `main` push, 수동 | 서명된 AAB > Play 스토어 내부 테스트 > 비공개 테스트 |
| `PROJECT-REACT-NATIVE-EXPO-PROJECTOPS-APP-BUILD-TRIGGER` | 이슈·PR 댓글 | 댓글의 브랜치로 테스트 APK·TestFlight 빌드 시작 |

`version.yml`에 `deploy_trigger_branch`가 있으면 스토어 워크플로 2개는 `main` 대신 그 브랜치에서 돕니다.

## 빌드 방식

- **EAS 없음.** `npx expo prebuild`가 러너에서 `android/`·`ios/`를 만듭니다. GitHub Actions 시간만 씁니다.
  네이티브 폴더를 커밋해 두었다면(prebuild 미사용) 그대로 빌드합니다.
- **버전.** `version.yml`이 원본입니다. `version`은 `expo.version`으로, `version_code`는 Play 스토어 릴리스의
  `expo.android.versionCode`로 들어갑니다. 릴리스 워크플로도 `app.json`을 같이 맞춥니다.
  테스트 빌드와 iOS 빌드는 시간 기반 빌드 번호(`build_number.py`)를 써서 겹치지 않습니다.
- **Android 서명**은 Gradle `-Pandroid.injected.signing.*` 속성으로 넣어 생성된 프로젝트를 고치지 않습니다.
  테스트 APK는 키 저장소가 없으면 디버그 키로 서명합니다.
- **iOS 서명.** 팀 ID를 프로비저닝 프로파일에서 읽어 prebuild 전에 `ios.appleTeamId`에 넣습니다.
  `ExportOptions.plist`와 fastlane 업로드 lane은 러너에서 만들고(`expo_app.py ios-signing`),
  아카이브·번호 확인·업로드·재시도는 Flutter 워크플로와 같은 `ios_release.py`가 처리합니다.
  TestFlight까지만 올립니다. App Store 심사 제출은 App Store Connect에서 합니다.
- **패키지·번들 ID**는 해석된 앱 설정(`npx expo config`, `app.config.js`도 지원)에서 읽습니다.

## GitHub Secrets

Flutter 워크플로와 이름이 같아서 스택을 바꿔도 설정을 그대로 씁니다.

| Secret | 쓰는 곳 | 필수 |
|---|---|---|
| `RELEASE_KEYSTORE_BASE64` | Play 스토어, 테스트 APK | Play 스토어: 필수. 테스트 APK: 선택(디버그 키) |
| `RELEASE_KEYSTORE_PASSWORD`, `RELEASE_KEY_ALIAS`, `RELEASE_KEY_PASSWORD` | Play 스토어, 테스트 APK | 키 저장소와 함께 |
| `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64` | Play 스토어 | 필수 |
| `APPLE_CERTIFICATE_BASE64`, `APPLE_CERTIFICATE_PASSWORD` | TestFlight | 필수 |
| `APPLE_PROVISIONING_PROFILE_BASE64` | TestFlight | 필수 (번들 ID의 App Store 프로파일) |
| `APP_STORE_CONNECT_API_KEY_ID`, `APP_STORE_CONNECT_ISSUER_ID`, `APP_STORE_CONNECT_API_KEY_BASE64` | TestFlight | 필수 |
| `IOS_BUNDLE_ID` | TestFlight | 선택 (`expo.ios.bundleIdentifier` 대신 사용) |
| `ENV_FILE` | 모든 빌드 | 선택 (앱 `.env`로 기록) |
| `GOOGLE_SERVICES_JSON`, `GOOGLE_SERVICE_INFO_PLIST` | Android·iOS 빌드 | 선택 (Firebase) |

선택 레포 변수: `NODE_VERSION`, `JAVA_VERSION`, `XCODE_VERSION`, `IOS_RUNNER`(iOS 27 SDK는 `xcode-27`),
`ANDROID_PROMOTE_TO_CLOSED_TESTING`(기본 `true`), `ANDROID_CLOSED_TESTING_TRACK`(기본 `alpha`),
`ANDROID_RELEASE_STATUS`(`completed` 또는 `draft`), `ANDROID_PACKAGE_NAME`.

## 처음 설정

1. **Play Console:** 앱을 만들고 AAB를 한 번 손으로 올립니다 (패키지가 묶이기 전에는 API로 올릴 수 없습니다).
   앱이 아직 초안이면 Play가 draft 릴리스만 받기 때문에, 업로드가 경고와 함께 draft로 다시 시도합니다
   (`ANDROID_RELEASE_STATUS=draft`로 두면 첫 시도를 건너뜁니다).
2. **App Store Connect:** 번들 ID의 앱 레코드, App Store 프로비저닝 프로파일, API 키를 만듭니다.
3. 위 Secret을 등록합니다 (예: `/pro-github secrets set`).
4. 이슈 댓글로 한 번 빌드해 봅니다: `@projectops app build <브랜치>`.

## 참고

- `expo lint`는 쓰지 않습니다. 일부 SDK에서 ESLint 9를 거부합니다. ESLint 설정이 있으면 CI가 `npx eslint .`를 돌립니다.
- 4개 ABI 네이티브 빌드는 호스팅 러너에서 오래 걸립니다. Play 스토어 작업은 90분까지 허용하고,
  테스트 APK는 `arm64-v8a`만 빌드합니다 (워크플로 env의 `ANDROID_ARCHITECTURES`).
- Expo 없는 `react-native`(bare)는 아직 앱 워크플로가 없고 버전 동기화만 설치됩니다.
