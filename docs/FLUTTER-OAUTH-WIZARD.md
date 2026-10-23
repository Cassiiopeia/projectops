# OAuth 로그인 마법사 (Kakao · Google)

> Flutter 앱에 Kakao·Google 로그인을 붙이는 설정 마법사 — 콘솔 등록, 네이티브 설정, GitHub Secrets, CI/CD, `.gitignore`까지 맞춰 릴리스 빌드·테스트 빌드·댓글 트리거 빌드 모두 로그인되게 합니다.

---

## 목차

- [개요](#개요)
- [실행 방법](#실행-방법)
- [단계](#단계)
- [어떤 키가 어떤 빌드를 서명하나](#어떤-키가-어떤-빌드를-서명하나)
- [GitHub Secrets](#github-secrets)
- [CI/CD 변경](#cicd-변경)
- [CLI](#cli)
- [트러블슈팅](#트러블슈팅)
- [출처](#출처)

---

## 개요

| 항목 | 값 |
|------|-----|
| **위치** | `.github/util/flutter/oauth-wizard/` |
| **파일** | `oauth-wizard.html` (웹 UI) / `oauth-wizard*.js` / `oauth-wizard.py` (CLI, Python 표준 라이브러리만 사용) |
| **공통 자산** | `.github/util/flutter/_shared/` (CSS, JS, 언어 전환, 검사) |
| **패키지** | `kakao_flutter_sdk_user` (2.x), `google_sign_in` (7.x) |
| **언어** | 기본 영어, 한국어 전환 (`?lang=ko`) |

입력한 값은 모두 브라우저(localStorage)에만 남습니다. 페이지는 입력값으로 네트워크 요청을 보내지 않으며, 끌어다 놓은 파일(`google-services.json`, `GoogleService-Info.plist`)도 브라우저 안에서만 읽습니다.

---

## 실행 방법

```bash
open .github/util/flutter/oauth-wizard/oauth-wizard.html
```

Windows에서는 파일을 더블클릭하거나 브라우저로 끌어다 놓습니다. 단계 표시줄을 눌러 원하는 단계로 바로 이동할 수 있습니다.

---

## 단계

1단계에서 제공자를 고르며, Kakao·Google 단계는 선택했을 때만 나타납니다 (전체 7–10단계).

| 단계 | 할 일 | 결과 |
|------|-------|------|
| **제공자** | Kakao, Google 또는 둘 다 선택 | 필요한 단계만 남음 |
| **앱 ID** | Android `applicationId`와 iOS 번들 ID 확인 (또는 `oauth-wizard.py detect` 실행) | 모든 콘솔에서 쓰는 ID |
| **서명 키** | 디버그·업로드·Play 앱 서명 키의 SHA-1 확인 | SHA-1 목록 + Kakao 키 해시 (브라우저에서 계산) |
| **Kakao** | 앱 생성, 네이티브 앱 키 복사, Android(패키지 + 키 해시)·iOS(번들 ID) 등록, 카카오 로그인 활성화 | 네이티브 앱 키, manifest / Info.plist / Dart 스니펫 |
| **Google** | Firebase 또는 Google Cloud 경로 선택, Android·iOS·Web OAuth 클라이언트 생성 | iOS 클라이언트 ID, Web 클라이언트 ID (`serverClientId`), Info.plist / Dart 스니펫 |
| **Secrets** | 커밋하면 안 되는 파일 등록 | Secret 표, JSON / TXT / ZIP 다운로드 |
| **CI/CD** | 워크플로우별로 필요한 것 확인 | 정확한 스텝과 붙여 넣을 위치 |
| **.gitignore** | 비밀 파일을 Git에서 제외 | 추가할 줄, `git rm --cached` 명령 |
| **적용** | 명령 하나 실행 (`--dry-run` 먼저) | `AndroidManifest.xml`, `Info.plist` 수정 |
| **체크리스트** | 모두 체크 | 빌드 준비 완료 |

### Google 경로

| 경로 | 언제 | 앱과 함께 나가는 파일 |
|------|------|----------------------|
| `firebase-sdk` | 앱이 Firebase SDK(`firebase_core`, `firebase_auth` 등)를 사용 | `google-services.json`, `GoogleService-Info.plist` (CI에서 Secret으로 복원) |
| `firebase-ids` | Firebase 콘솔이 OAuth 클라이언트를 만들고, 앱에는 Firebase SDK가 없음 | 없음 — 클라이언트 ID만 사용 |
| `cloud` | Google Cloud에서 OAuth 클라이언트를 직접 생성 | 없음 — 클라이언트 ID만 사용 |

iOS의 `google_sign_in`은 `Info.plist`에서 `GIDClientID`(선택적으로 `GIDServerClientID`)를 읽고, 역순 클라이언트 ID URL scheme이 필요합니다. 로그인만 한다면 `GoogleService-Info.plist`는 필요 없습니다.

---

## 어떤 키가 어떤 빌드를 서명하나

지문이 등록되지 않은 키로 서명한 빌드는 로그인할 수 없습니다. CI를 붙인 뒤 가장 흔한 OAuth 실패 원인입니다.

| 빌드 | 서명 키 | 등록할 값 |
|------|---------|-----------|
| `flutter run` | 로컬 디버그 키 `~/.android/debug.keystore` (컴퓨터마다 다름) | 디버그 SHA-1 / 키 해시 |
| `ANDROID-TEST-APK` (`@projectops apk build`), `ANDROID-FIREBASE-CICD` | `RELEASE_KEYSTORE_BASE64`의 업로드 키 | 업로드 SHA-1 / 키 해시 |
| Google Play에서 설치 (`ANDROID-PLAYSTORE-CICD`) | Play 앱 서명 키 (Google이 다시 서명) | Play 앱 서명 SHA-1 / 키 해시 |
| `ANDROID-SELFHOSTED-CICD` | `DEBUG_KEYSTORE` Secret (`ANDROID_SELFHOSTED_RELEASE_SIGNING=true`이면 제외) | 그 키스토어의 SHA-1 / 키 해시 |

iOS는 지문이 필요 없습니다. 두 제공자 모두 번들 ID로 대조합니다.

---

## GitHub Secrets

Kakao 키와 Google 클라이언트 ID는 앱 안에 들어가는 공개 식별자라 커밋되는 파일에 두며 Secret이 필요 없습니다. Kakao REST API 키·Admin 키나 Google 클라이언트 시크릿은 절대 앱에 넣지 마세요.

Secret은 `firebase-sdk` 경로에서만 필요합니다.

| Secret | 값 | 사용처 |
|--------|-----|--------|
| `GOOGLE_SERVICES_JSON` | `google-services.json` 원문 텍스트 | Android 워크플로우 4종과 Flutter CI |
| `GOOGLE_SERVICE_INFO_PLIST` | `GoogleService-Info.plist` 원문 텍스트 (또는 base64) | iOS TestFlight 워크플로우 2종과 Flutter CI |

파일은 원문 텍스트 그대로 붙여 넣습니다. CI가 값을 바이트 그대로 되돌려 쓰므로 JSON/plist 형식이 깨지지 않습니다. 추가 Secret으로 넣는 바이너리 파일은 자동으로 base64로 변환됩니다.

파일을 커밋해도 됩니다. 이때는 Secret을 비워 두면 CI가 커밋된 파일을 씁니다. 둘 다 있으면 Secret이 우선합니다.

---

<a id="cicd-변경"></a>

## CI/CD 변경

**추가할 것이 없습니다.** 템플릿이 `.github/scripts/firebase_config_files.py`로 두 파일을 복원합니다 (#785).

- `GOOGLE_SERVICES_JSON` > `android/app/google-services.json`, `GOOGLE_SERVICE_INFO_PLIST` > `ios/Runner/GoogleService-Info.plist` (원문 텍스트 또는 base64)
- Secret이 설정됐을 때만 동작 — 빈 Secret은 커밋된 파일을 덮어쓰지 않음
- Gradle 플러그인(`com.google.gms.google-services`)이나 Xcode 프로젝트가 필요로 하는 파일이 없으면 해당 Secret 이름을 담은 `::error`를 출력

| 워크플로우 | `firebase-sdk` 경로 | 다른 경로 |
|------------|---------------------|-----------|
| `PROJECT-FLUTTER-ANDROID-TEST-APK` · `-PLAYSTORE-CICD` · `-FIREBASE-CICD` · `-SELFHOSTED-CICD` | 변경 없음 — `GOOGLE_SERVICES_JSON` 등록 | 변경 없음 |
| `PROJECT-FLUTTER-IOS-TESTFLIGHT` · `-IOS-TEST-TESTFLIGHT` | 변경 없음 — `GOOGLE_SERVICE_INFO_PLIST` 등록 (`Ensure .env file exists` 바로 뒤에 복원) | 변경 없음 |
| `PROJECT-FLUTTER-CI` | 변경 없음 — 설정되어 있으면 둘 다 복원 | 변경 없음 |
| `PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER` | 변경 없음 (테스트 빌드 워크플로우 2종을 호출만 함) | 변경 없음 |

plist는 Runner 타깃에도 한 번 들어가 있어야 합니다 (Xcode에서 **Runner**로 끌어다 놓고 `project.pbxproj`를 커밋). 파일 자체는 Git 밖에 둬도 됩니다.

### 이전 설치본

`.github/scripts/firebase_config_files.py`가 없다면 복원 스크립트보다 오래된 템플릿입니다. 워크플로우를 손으로 고치지 말고 템플릿을 업데이트하세요.

```bash
ls .github/scripts/firebase_config_files.py   # missing?
npx projectops                                # update the templates
```

> ⚠️ `repository_dispatch`는 기본 브랜치의 워크플로우 정의로 실행됩니다. 업데이트한 뒤 `main`에 머지하고 나서 `@projectops ios build`로 테스트하세요.

당장 업데이트할 수 없을 때만, 마법사가 iOS job 2개(`build-upload-ios`, `build-upload-ios-test`, `Ensure .env file exists` 바로 뒤)에 넣을 수동 대체 스텝을 보여 줍니다. 스크립트처럼 Secret이 비어 있으면 건너뛰지만, plist 원문 텍스트만 받습니다. 업데이트한 뒤에는 지우세요. 그대로 두면 파일이 두 번 쓰입니다.

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

`oauth-wizard.py`는 Python 표준 라이브러리만 사용하며 macOS, Linux, Windows에서 동작합니다.

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

| `setup` 옵션 | 의미 |
|--------------|------|
| `--kakao-native-app-key` | manifest에 `AuthCodeHandlerActivity`(`kakao{KEY}://oauth`), Info.plist에 `kakao{KEY}` URL scheme과 `kakaokompassauth`, `kakaolink` 추가 |
| `--google-ios-client-id` | Info.plist에 `GIDClientID`와 역순 클라이언트 ID URL scheme 추가 |
| `--google-server-client-id` | `GIDServerClientID` 추가 |
| `--update-gitignore` | 마법사 내보내기 파일 제외, `--firebase-files`와 함께 쓰면 Firebase 설정 파일 2개도 제외 |
| `--dry-run` | 변경 내용을 모두 출력하고 아무것도 쓰지 않음 |
| `--no-backup` | `*.bak` 사본을 만들지 않음 |
| `--non-interactive` | 확인 질문 없음 |

`setup`은 멱등입니다. 두 번째 실행은 `already configured`를 출력합니다. Kakao 키나 Google 클라이언트 ID가 바뀌면 scheme을 하나 더 추가하지 않고 기존 것을 교체합니다. 쓰기 전에 모든 변경을 먼저 계산하므로, 파일 하나라도 없거나 잘못되어 있으면 아무것도 바뀌지 않습니다.

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `flutter run`에서는 Kakao 로그인이 되는데 CI 빌드에서는 안 됨 | CI 빌드가 업로드 키(또는 Play 앱 서명 키)로 서명되는데 그 키 해시가 등록되지 않음 | Kakao Developers에 그 키 해시 추가 |
| Android에서만 Google 로그인 실패 | Google 쪽에 SHA-1 또는 패키지 이름 누락 | SHA-1 추가 (Firebase 지문, 또는 SHA-1마다 Android OAuth 클라이언트 하나씩) |
| Android Google 로그인이 `No credentials available`로 실패 | 기기에 Google 계정이 없음(Credential Manager가 계정을 요구), 또는 Android OAuth 클라이언트를 만든 지 몇 분 안 됨 | 기기 설정에서 Google 계정 추가. 새 클라이언트면 몇 분 기다린 뒤 다시 시도 |
| Google이 `401 invalid_client` / "The OAuth client was not found" 표시 | `GIDClientID`(iOS)나 `serverClientId`의 클라이언트 ID가 Google Cloud에 없음 | Google Cloud에서 클라이언트 ID를 다시 복사해 `setup` 재실행 |
| iOS에서 Google 로그인 시 앱이 죽거나 아무 반응 없음 | `GIDClientID` 또는 역순 클라이언트 ID URL scheme 누락 | `--google-ios-client-id`로 `setup` 실행 |
| iOS 빌드 실패: `GoogleService-Info.plist` 없음 (CI 로그에 `GOOGLE_SERVICE_INFO_PLIST`를 가리키는 `::error`) | plist가 Xcode 프로젝트에는 있지만 커밋되지도 Secret에 있지도 않음 | `GOOGLE_SERVICE_INFO_PLIST` 등록, 오래된 템플릿이면 `npx projectops` 실행 |
| Android 빌드가 Google Services Gradle 태스크에서 실패 (`GOOGLE_SERVICES_JSON`을 가리키는 `::error`) | Gradle 플러그인에 `google-services.json`이 필요한데 커밋되지도 Secret에 있지도 않음 | `GOOGLE_SERVICES_JSON` 등록 |

---

## 출처

- Kakao Flutter SDK 시작하기: https://developers.kakao.com/docs/ko/flutter/getting-started
- Flutter 카카오 로그인: https://developers.kakao.com/docs/ko/kakaologin/flutter
- Kakao iOS 허용 목록과 URL scheme: https://developers.kakao.com/docs/ko/ios/getting-started
- Kakao Android 키 해시: https://developers.kakao.com/docs/ko/android/getting-started
- `kakao_flutter_sdk_user`: https://pub.dev/packages/kakao_flutter_sdk_user
- `google_sign_in`: https://pub.dev/packages/google_sign_in
- Android 연동: https://pub.dev/packages/google_sign_in_android
- iOS 연동: https://pub.dev/packages/google_sign_in_ios
- Google Cloud OAuth 클라이언트: https://support.google.com/cloud/answer/15549257
