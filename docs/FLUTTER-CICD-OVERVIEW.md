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
