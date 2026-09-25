# Flutter CI/CD 전체 가이드

> Flutter 프로젝트를 위한 완전 자동화된 배포 파이프라인

---

## 목차

- [개요](#개요)
- [시스템 아키텍처](#시스템-아키텍처)
- [마법사 도구](#마법사-도구)
- [워크플로우 목록](#워크플로우-목록)
- [빠른 시작](#빠른-시작)
- [GitHub Secrets 전체 목록](#github-secrets-전체-목록)

---

## 개요

projectops의 Flutter CI/CD 시스템은 **마법사 도구**와 **GitHub Actions 워크플로우**의 조합으로 구성됩니다.

**핵심 특징:**
- 웹 UI 마법사로 복잡한 배포 설정 자동 생성
- PR/이슈 댓글로 테스트 빌드 트리거
- iOS TestFlight + Android Play Store + Firebase App Distribution 자동 배포

---

## 시스템 아키텍처

### 전체 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│                        초기 설정 단계                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  🧙 TestFlight 마법사    🧙 Play Store 마법사   🧙 Firebase 마법사│
│  ├─ ExportOptions.plist  ├─ Fastfile           ├─ 배포 설정      │
│  ├─ Fastfile             ├─ 서명 설정          └─ 테스터 그룹    │
│  └─ Gemfile              └─ 서명 키 가이드                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                        개발 중 검증·테스트                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  develop 푸시/PR → PROJECT-FLUTTER-CI.yaml (분석 + 빌드 검증)    │
│                                                                  │
│  PR/이슈에 빌드 명령어 댓글 (build app/apk build/ios build)     │
│                     ↓                                            │
│  PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml (트리거)      │
│                     ↓  repository_dispatch                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ PROJECT-FLUTTER-ANDROID-TEST-APK.yaml  → APK 아티팩트   │    │
│  │ PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml → TestFlight   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                     ↓                                            │
│  빌드 결과 댓글 자동 작성                                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                        본 배포 단계                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  main 브랜치 push                                                │
│           ↓                                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml       → TestFlight  │    │
│  │ PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD.yaml → Play Store│    │
│  │ PROJECT-FLUTTER-ANDROID-FIREBASE-CICD.yaml  → Firebase  │    │
│  │ PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD.yaml → 자체 서버│    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

> 본 배포 워크플로우 4종은 모두 `main` push 트리거입니다. 프로젝트에 필요 없는 워크플로우는 삭제하거나 비활성화하세요.

### 마법사-워크플로우 관계

```
.github/util/flutter/testflight-wizard/
    → 생성: ExportOptions.plist, Fastfile, Gemfile
    → 사용 워크플로우:
        - PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml (본 배포)
        - PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml (테스트)

.github/util/flutter/playstore-wizard/
    → 생성: Fastfile, build.gradle.kts 서명 설정
    → 사용 워크플로우:
        - PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD.yaml (본 배포)
        - PROJECT-FLUTTER-ANDROID-TEST-APK.yaml (테스트)

.github/util/flutter/firebase-wizard/
    → 생성: Firebase App Distribution 배포 설정
    → 사용 워크플로우:
        - PROJECT-FLUTTER-ANDROID-FIREBASE-CICD.yaml (본 배포)
        - PROJECT-FLUTTER-ANDROID-TEST-APK.yaml (Firebase 업로드 옵션)
```

---

## 마법사 도구

| 마법사 | 용도 | 상세 가이드 |
|--------|------|------------|
| **TestFlight 마법사** | iOS 배포 설정 자동 생성 | [FLUTTER-TESTFLIGHT-WIZARD.md](FLUTTER-TESTFLIGHT-WIZARD.md) |
| **Play Store 마법사** | Android Play Store 배포 설정 자동 생성 | [FLUTTER-PLAYSTORE-WIZARD.md](FLUTTER-PLAYSTORE-WIZARD.md) |
| **Firebase 마법사** | Firebase App Distribution 배포 설정 자동 생성 | [FLUTTER-FIREBASE-WIZARD.md](FLUTTER-FIREBASE-WIZARD.md) |

---

## 워크플로우 목록

### CI (코드 검증)

| 워크플로우 | 용도 | 트리거 |
|-----------|------|--------|
| `PROJECT-FLUTTER-CI.yaml` | 코드 분석 + 빌드 검증 | develop push / develop 대상 PR |

### 본 배포 워크플로우

| 워크플로우 | 용도 | 트리거 |
|-----------|------|--------|
| `PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml` | iOS TestFlight 배포 | main push |
| `PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD.yaml` | Android Play Store 내부 테스트 배포 | main push |
| `PROJECT-FLUTTER-ANDROID-FIREBASE-CICD.yaml` | Firebase App Distribution 배포 | main push |
| `PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD.yaml` | 자체 서버(SMB) APK 배포 | main push |

### 배포 범위는 어디까지 가는가 (`DEPLOY_MODE`)

**한 값이 두 플랫폼에서 서로 다른 지점까지 간다.** 같은 이름이라 헷갈리기 쉬워 표로 둔다.

| `DEPLOY_MODE` | iOS | Android |
|---|---|---|
| `store_only` (기본) | TestFlight 업로드까지 | 내부 테스트 트랙까지 |
| `store_prepare` | App Store 버전에 빌드를 붙임 (제출 안 함) | 프로덕션 **draft** 승급 (콘솔에서 "출시 시작"을 사람이 누름) |
| `store_submit` | App Store **심사 제출** | 프로덕션 **심사 자동 등록** |

> 구 별칭(`testflight_only`·`appstore_prepare`·`appstore_submit`)도 계속 받는다.
>
> **기본값은 `store_only` 다** — 워크플로도, Fastfile 내부도 같다. 예전에는 Android
> Fastfile 만 `store_submit` 이라, 워크플로를 거치지 않고 lane 을 직접 부르면 프로덕션
> 심사에 올라갔다 (#618 에서 교정).

### 스토어 '새로운 기능' 문구 (`STORE_WHATS_NEW_OVERRIDE`)

`store_prepare`/`store_submit` 때 스토어 '새로운 기능(What's New)' 칸(iOS '이 버전의 새로운 기능',
Android '출시 노트')에 들어갈 문구다. **사용자뿐 아니라 심사자도 본다.** 워크플로 파일 `env`에 둔다
(iOS·Android 같은 이름 — 두 곳을 함께 바꾼다).

| 값 | 동작 |
|---|---|
| `""` (템플릿 기본값) | CHANGELOG 해당 버전 항목을 넣는다 — 이전과 같다 |
| 문구 | 버전과 상관없이 매번 그 문구를 넣는다 |

- 공백만 있는 값은 빈 값으로 본다. 빌드 로그에 출처(`CHANGELOG` / `STORE_WHATS_NEW_OVERRIDE 덮어쓰기`)가 남는다.
- 수동 실행 입력 `whats_new_override`에 값을 주면 **그 실행만** 우선한다.
- iOS TestFlight 'What to Test'(내부 테스터용)는 이 값과 상관없이 항상 CHANGELOG를 쓴다.
- Android 출시 노트는 내부 테스트 업로드 때 정해져 승급에 그대로 따라가므로 모든 트랙에 같이 적용된다.
- 레포 변수가 아니라 `env`인 이유: 템플릿은 레포 변수를 미리 넣어 줄 수 없고, 거의 바꾸지 않는 값이라
  코드에서 보이고 git 이력이 남는 편이 낫다. (배포 모드는 급할 때 바로 꺼야 해서 레포 변수 그대로다.)

**iOS 심사 메모(Notes)** — `ios/fastlane/review_notes.txt`가 있으면 매번 그 내용을 넣고, 없거나 비어 있으면
App Store Connect 기존값을 그대로 둔다. (예전에는 빈 파일로 '초기화'하려 했지만 빈 값은 전송되지 않아
기존값이 남았다 — 실측.) 심사용 공용 계정 없이 로그인 안내를 Notes에만 두는 앱은 이 파일로 코드와 함께 관리한다.

### Android 트랙 — 내부 테스트만으로는 프로덕션에 못 간다 ⚠️

`DEPLOY_MODE` 는 **프로덕션 단계만** 정한다. 중간 트랙은 독립 스위치가 맡는다.

| 스위치 (레포 변수 / 수동 실행 입력) | 하는 일 | 기본 |
|---|---|---|
| `ANDROID_PROMOTE_TO_CLOSED_TESTING` | 비공개 테스트 트랙에도 올린다 | `false` |
| `ANDROID_PROMOTE_TO_OPEN_TESTING` | 공개 테스트 트랙에도 올린다 | `false` |
| `ANDROID_CLOSED_TESTING_TRACK` | 비공개 트랙 이름 | `alpha` |
| `ANDROID_OPEN_TESTING_TRACK` | 공개 트랙 이름 | `beta` |

| 트랙 | 구글 검토 | 반영 | 프로덕션 액세스 조건에 포함 |
|---|---|---|---|
| `internal` (내부) | **없음** | 수 분 | ❌ |
| `alpha` (비공개) | 있음 | 수십 분 ~ 수일 | ✅ |
| `beta` (공개) | 있음 | 〃 | ✅ |
| `production` | 있음 | 〃 | — |

> **2023-11-13 이후에 만든 개인 개발자 계정**은 테스터 12명 이상이 14일 이상 참여한
> **비공개 테스트**를 마쳐야 프로덕션 액세스를 받는다. 내부 테스트는 검토가 없어
> 편하지만 **그 조건에 잡히지 않는다** — 내부만 돌리면 조건이 영영 차지 않는다.
> (그 이전에 만든 계정과 조직 계정은 해당하지 않는다.)
>
> 트랙 이름은 콘솔에서 바꿀 수 있으므로 값으로 둔다. 박아두면 임의 이름을 쓰는
> 저장소에서 조용히 안 올라간다.

### 테스트 빌드 워크플로우

| 워크플로우 | 용도 | 트리거 |
|-----------|------|--------|
| `PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml` | 빌드 트리거 감지 | `@projectops build app` / `apk build` / `ios build` 댓글 |
| `PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml` | iOS 테스트 빌드 | repository_dispatch (`build-ios-app`) |
| `PROJECT-FLUTTER-ANDROID-TEST-APK.yaml` | Android APK 테스트 빌드 | repository_dispatch (`build-android-app`) |

상세 가이드: [FLUTTER-TEST-BUILD-TRIGGER.md](FLUTTER-TEST-BUILD-TRIGGER.md)

---

## 빠른 시작

### 1단계: 마법사로 설정 파일 생성

```bash
# iOS TestFlight 설정
open .github/util/flutter/testflight-wizard/testflight-wizard.html

# Android Play Store 설정
open .github/util/flutter/playstore-wizard/playstore-wizard.html

# Firebase App Distribution 설정
open .github/util/flutter/firebase-wizard/firebase-wizard.html
```

### 2단계: GitHub Secrets 설정

아래 [GitHub Secrets 전체 목록](#github-secrets-전체-목록)을 참고해 등록합니다.

> ⚠️ **Secret 이름은 워크플로우가 참조하는 이름과 정확히 일치해야 합니다.** 이름이 하나라도 다르면 인증서/키스토어 복원 단계에서 빌드가 실패합니다.

### 3단계: 워크플로우 설치

```bash
# npx 마법사로 Flutter 워크플로우 설치
npx projectops --mode workflows --type flutter
```

### 4단계: 테스트 빌드 실행

PR 또는 이슈에 댓글 작성:
```
@projectops build app    # Android + iOS 모두 빌드
@projectops apk build    # Android만 빌드
@projectops ios build    # iOS만 빌드
```

---

## GitHub Secrets 전체 목록

### iOS (TestFlight — 본 배포 / 테스트 빌드 공통)

| Secret | 설명 |
|--------|------|
| `APPLE_CERTIFICATE_BASE64` | Apple Distribution 인증서 `.p12` (base64 인코딩) |
| `APPLE_CERTIFICATE_PASSWORD` | `.p12` 인증서 비밀번호 |
| `APPLE_PROVISIONING_PROFILE_BASE64` | `.mobileprovision` 파일 (base64 인코딩) |
| `IOS_PROVISIONING_PROFILE_NAME` | 프로비저닝 프로파일 이름 |
| `APP_STORE_CONNECT_API_KEY_ID` | App Store Connect API Key ID (10자리) |
| `APP_STORE_CONNECT_ISSUER_ID` | Issuer ID (UUID 형식) |
| `APP_STORE_CONNECT_API_KEY_BASE64` | `AuthKey_XXXXXX.p8` 파일 (base64 인코딩) |
| `IOS_BUNDLE_ID` (선택) | 번들 ID. Secret 대신 저장소 변수(`vars`)로도 지정 가능 |
| `ENV_FILE` (선택) | `.env` 파일 내용 |
| `SECRETS_XCCONFIG` (선택) | `ios/Flutter/Secrets.xcconfig` 내용 |

### Android — Play Store 배포

| Secret | 설명 |
|--------|------|
| `RELEASE_KEYSTORE_BASE64` | 서명용 keystore `.jks` (base64 인코딩) |
| `RELEASE_KEYSTORE_PASSWORD` | keystore 비밀번호 |
| `RELEASE_KEY_ALIAS` | key alias |
| `RELEASE_KEY_PASSWORD` | key 비밀번호 |
| `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64` | Play Console 서비스 계정 JSON (base64 인코딩) |
| `GOOGLE_SERVICES_JSON` | Firebase `google-services.json` 내용 |
| `ENV_FILE` 또는 `ENV` (선택) | `.env` 파일 내용 (`ENV_FILE` 우선) |

### Android — Firebase App Distribution 배포

Play Store와 동일한 `RELEASE_*` 서명 Secret을 쓰고, 업로드 자격만 다릅니다.

| Secret | 설명 |
|--------|------|
| `RELEASE_KEYSTORE_BASE64` / `_PASSWORD` | 서명용 keystore 및 비밀번호 |
| `RELEASE_KEY_ALIAS` / `RELEASE_KEY_PASSWORD` | key alias 및 비밀번호 |
| `FIREBASE_SERVICE_ACCOUNT_JSON_BASE64` | Firebase 서비스 계정 JSON (base64 인코딩) |
| `GOOGLE_SERVICES_JSON` (선택) | Firebase `google-services.json` 내용 |
| `ENV_FILE` 또는 `ENV` (선택) | `.env` 파일 내용 |

### Android — 자체 서버(SMB) 배포

| Secret | 설명 |
|--------|------|
| `RELEASE_KEYSTORE_BASE64` / `_PASSWORD` | 서명용 keystore 및 비밀번호 |
| `RELEASE_KEY_ALIAS` / `RELEASE_KEY_PASSWORD` | key alias 및 비밀번호 |
| `SERVER_HOST` / `SERVER_USER` / `SERVER_PASSWORD` | SMB 접속 정보 |
| `GOOGLE_SERVICES_JSON` (선택) | Firebase `google-services.json` 내용 |
| `ENV_FILE` 또는 `ENV` (선택) | `.env` 파일 내용 |

> 각 워크플로우 파일 상단 `🔑 필수 GitHub Secrets` 주석이 항상 최신 기준입니다. 이 표와 어긋나면 워크플로우 주석을 신뢰하세요.

---

## 파일 위치 요약

```
.github/
├── util/flutter/
│   ├── testflight-wizard/           # iOS 마법사
│   │   ├── testflight-wizard.html
│   │   ├── testflight-wizard.js
│   │   ├── testflight-wizard.py
│   │   └── templates/
│   │       ├── ExportOptions.plist
│   │       ├── Fastfile.ios.template
│   │       └── Gemfile
│   │
│   ├── playstore-wizard/            # Android Play Store 마법사
│   │   ├── playstore-wizard.html
│   │   ├── playstore-wizard.js
│   │   ├── playstore-wizard.py
│   │   └── templates/
│   │       ├── Fastfile.playstore.template
│   │       └── build.gradle.kts.signing.template
│   │
│   └── firebase-wizard/             # Firebase App Distribution 마법사
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

## 관련 문서

- [iOS TestFlight 마법사 상세](FLUTTER-TESTFLIGHT-WIZARD.md)
- [Android Play Store 마법사 상세](FLUTTER-PLAYSTORE-WIZARD.md)
- [Firebase App Distribution 마법사 상세](FLUTTER-FIREBASE-WIZARD.md)
- [테스트 빌드 트리거 상세](FLUTTER-TEST-BUILD-TRIGGER.md)
