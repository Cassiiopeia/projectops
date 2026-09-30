# Flutter 테스트 빌드 트리거 가이드

> PR/이슈 댓글로 Android APK와 iOS TestFlight 빌드를 자동으로 트리거하는 기능

---

## 목차

- [개요](#개요)
- [사용 방법](#사용-방법)
- [빌드 번호 규칙](#빌드-번호-규칙)
- [워크플로우 동작 흐름](#워크플로우-동작-흐름)
- [빌드 결과 댓글](#빌드-결과-댓글)
- [필요한 설정](#필요한-설정)
- [트러블슈팅](#트러블슈팅)

---

## 개요

테스트 빌드 트리거는 PR 또는 이슈에 빌드 명령어 댓글을 작성하면 자동으로 Android APK와 iOS TestFlight 빌드를 실행하는 기능입니다.

**주요 특징:**
- PR과 이슈 모두 지원
- **3가지 빌드 옵션**: 전체 빌드 / Android만 / iOS만
- 빌드 번호는 시각 기반이라 동시에 여러 이슈에서 빌드해도 겹치지 않음
- 출시 후 닫힌 버전으로 iOS 테스트 빌드를 걸면 다음 패치 버전으로 자동 전환
- 빌드 결과 자동 댓글 작성

---

## 사용 방법

### PR에서 빌드 트리거

PR에 다음 댓글 중 하나를 작성합니다:

| 명령어 | 빌드 대상 |
|--------|----------|
| `@projectops build app` | Android + iOS 모두 |
| `@projectops apk build` | Android만 |
| `@projectops ios build` | iOS만 |

```
@projectops build app    # 양쪽 모두 빌드
@projectops apk build    # Android만 빌드
@projectops ios build    # iOS만 빌드
```

### 이슈에서 빌드 트리거

이슈에서 빌드하려면 **"Guide by SUH-LAB"** 댓글이 먼저 있어야 합니다.

1. 이슈에 "Guide by SUH-LAB" 형식의 댓글이 존재해야 함
2. 해당 댓글에 브랜치 정보가 포함되어 있어야 함

```markdown
### 브랜치
```
feature/20240101_#123_기능명
```
```

3. 위 조건이 충족된 이슈에 빌드 명령어 댓글 작성

### 지원하는 키워드

다음 패턴 중 하나가 포함되어 있으면 트리거됩니다:

| 패턴 | 필요한 키워드 | 빌드 대상 |
|------|--------------|----------|
| 전체 빌드 | `@projectops` + `build` + `app` | Android + iOS |
| APK만 | `@projectops` + `apk` + `build` | Android |
| iOS만 | `@projectops` + `ios` + `build` | iOS |

**예시:**
```
@projectops build app                      # Android + iOS 빌드
@projectops apk build                      # Android만 빌드
@projectops ios build                      # iOS만 빌드
@projectops 으로 build 해서 app 테스트해주세요  # Android + iOS 빌드
```

---

## 빌드 번호 규칙

빌드 번호는 이슈 번호나 댓글 횟수와 무관하게 **시각 기반**으로 정해집니다. 규칙은 `.github/scripts/build_number.py` 한 곳에 있습니다.

```
빌드 번호 = max( 2024-01-01 00:00:00 UTC부터 지난 초,
                 App Store Connect 최근 빌드 번호 + 1,      (조회될 때만)
                 Apple 거부 메시지가 요구한 번호 + 1 )      (재시도일 때만)
```

- 예: 2026-09-30 05:04:00 UTC는 `86677440`. 2026년 기준 약 8,700만입니다.
- 시간은 거꾸로 가지 않으므로 **나중에 뽑은 번호가 항상 더 큽니다.** 여러 이슈에서 동시에 빌드해도, 빌드 순서가 뒤바뀌어도 우상향합니다.
- 두 번째와 세 번째 값은 하한입니다. 첫 번째 값이 이미 더 크면 쓰이지 않습니다. 예전에 날짜형(예: `2026093001`) 번호를 쓴 앱이 있으면 두 번째 값이 그 위로 맞춰 줍니다.
- 같은 초에 두 빌드가 같은 번호를 뽑으면 Apple이 중복으로 거부합니다. 재시도가 새 번호로 이어지는 조건은 아래 "번호 거부 시 자동 재시도"를 참고하세요.

### 적용 범위

| 빌드 | 번호 |
|------|------|
| iOS 테스트 (TestFlight) | 위 규칙, 아카이브 직전에 결정 |
| iOS 릴리스 (TestFlight, 심사 제출) | 위 규칙 |
| Android 테스트 (APK, Firebase) | 위 규칙 (App Store Connect 하한과 재시도 없음) |
| Android 릴리스 (Play Store, Firebase CICD, 자체 서버) | 이 규칙과 무관 ([VERSION-CONTROL.md](VERSION-CONTROL.md#version_code-관리)) |

`version.yml`에는 번호를 다시 쓰지 않습니다. 트리거 워크플로우가 보내는 `build_number` 값은 옛 사용자 레포와의 호환용으로 빈 값만 남아 있고, 빌드 워크플로우는 읽지 않습니다.

> **iOS 번호는 한 번 올라가면 이전 체계로 되돌릴 수 없습니다.** 시각 기반을 계속 쓰는 한 문제는 없습니다.

### 앱 버전 형식
```
2.1.3(86677440)
```
- 버전: `version.yml`의 버전입니다 (테스트용 고정 버전이 아닙니다).
- 빌드 번호: 위 규칙으로 정해진 값입니다.

### 출시 후 버전 자동 전환 (iOS 테스트)

`version.yml` 버전이 App Store에서 이미 출시되어 닫힌 버전이면 TestFlight가 업로드를 거부합니다. iOS 테스트 빌드는 이를 미리 확인해 **닫힌 버전 중 최대값의 다음 패치**로 빌드합니다.

- 준비 단계에서 App Store Connect 버전 목록을 조회해 판단하고, 바뀌었으면 준비 완료 후 진행 댓글에 `버전 조정: ...` 한 줄로 이유를 남깁니다.
- 조회가 안 되면(키 없음, 권한 부족, 네트워크) 경고만 남기고 `version.yml` 버전으로 진행합니다. 그래도 업로드가 닫힌 버전으로 거부되면 거부 메시지에서 닫힌 버전을 읽어 다음 패치로 다시 아카이브합니다.
- `version.yml`은 수정하지 않습니다.
- iOS 릴리스는 버전을 몰래 바꾸지 않습니다. 닫힌 버전이면 빌드 전에 실패하므로 `version.yml` 버전을 올린 뒤 다시 실행하세요.

### 번호 거부 시 자동 재시도 (iOS)

업로드가 거부되면 원인을 분류해 다시 시도합니다. 최대 5회이고 Flutter 빌드는 다시 하지 않고 아카이브부터 다시 합니다.

| 거부 원인 | 동작 |
|-----------|------|
| 번호 중복 | 번호를 새로 뽑아 재시도 (단, 그 번호가 이미 App Store Connect에 보이면 아래 규칙대로 실패) |
| 번호가 너무 낮음 | 메시지가 요구한 번호 + 1 이상으로 재시도 |
| 버전이 닫힘 (테스트) | 다음 패치 버전으로 재시도 |
| 버전이 닫힘 (릴리스) | 재시도 없이 실패 |
| 그 외 | 재시도 없이 실패 |

이미 올라간 빌드는 다시 올리지 않습니다. 재시도 전에 App Store Connect에 이번 번호가 있는지 확인하고(반영 지연을 고려해 20초 간격으로 3회), 있으면 재업로드 없이 실패합니다. 업로드 후 단계가 실패했거나 동시 빌드와 번호가 겹친 경우이며, 다시 실행하면 새 번호를 씁니다. 이 확인이 안 되면 중복 업로드를 피하려고 재시도하지 않고 실패합니다.

---

## 워크플로우 동작 흐름

```
1. PR/이슈에 빌드 명령어 댓글 작성
   (@projectops build app / apk build / ios build)
       ↓
2. BUILD-TRIGGER 워크플로우 실행
   - 👀 리액션 추가
   - 빌드 타입 판별 (app/apk/ios)
   - PR/이슈 정보 추출
       ↓
3. repository_dispatch 이벤트 발생 (빌드 타입에 따라)
   - build app: Android + iOS 모두 트리거
   - apk build: Android만 트리거
   - ios build: iOS만 트리거
       ↓
4. 선택된 워크플로우 실행
   ┌─────────────────────────────────┐
   │ ANDROID-TEST-APK               │
   │ - 빌드 번호 결정 (시각 기반)    │
   │ - Flutter 빌드                  │
   │ - APK 생성                      │
   │ - 아티팩트 업로드               │
   │ - 결과 댓글 작성                │
   └─────────────────────────────────┘
   ┌─────────────────────────────────┐
   │ IOS-TEST-TESTFLIGHT            │
   │ - 버전 사전 점검 (닫힌 버전)    │
   │ - Flutter 빌드                  │
   │ - 번호 결정, IPA 생성           │
   │ - TestFlight 업로드 (재시도)    │
   │ - 결과 댓글 작성                │
   └─────────────────────────────────┘
       ↓
5. 빌드 결과 댓글 자동 작성
```

---

## 빌드 결과 댓글

### 빌드 진행 상황

빌드 트리거 후 각 플랫폼별로 **진행상황 댓글**이 자동 생성되어 실시간으로 업데이트됩니다.

**Android 진행상황 댓글 예시:**
```markdown
## 🤖 Android APK 빌드 중...

| 단계 | 상태 | 소요 시간 |
|------|------|----------|
| 🔧 준비 | ✅ 완료 | 1분 23초 |
| 🔨 APK 빌드 | ⏳ 진행 중... | - |
| 📤 업로드 | ⏸️ 대기 | - |

📋 **[실시간 로그 보기](링크)**
```

**iOS 진행상황 댓글 예시:**
```markdown
## 🍎 iOS TestFlight 빌드 중...

| 단계 | 상태 | 소요 시간 |
|------|------|----------|
| 🔧 준비 | ✅ 완료 | 2분 15초 |
| 🔨 IPA 빌드 | ⏳ 진행 중... | - |
| 📤 TestFlight 배포 | ⏸️ 대기 | - |

📋 **[실시간 로그 보기](링크)**
```

빌드 완료 시 최종 결과로 업데이트됩니다.

### Android 빌드 성공 댓글

```markdown
✅ **Android 테스트 APK 빌드 완료**

| 항목 | 내용 |
|------|------|
| 📦 버전 | `2.1.3(86677440)` |
| 🌿 브랜치 | `feature/20240101_#123_기능명` |
| 📝 커밋 | `abc1234` |
| ⏱️ 소요 시간 | 5분 32초 |

**📥 다운로드**
[GitHub Actions 아티팩트에서 APK 다운로드](링크)
```

### iOS 빌드 성공 댓글

```markdown
✅ **iOS TestFlight 빌드 완료**

| 항목 | 내용 |
|------|------|
| 📦 버전 | `2.1.3(86677440)` |
| 🌿 브랜치 | `feature/20240101_#123_기능명` |
| 📝 커밋 | `abc1234` |
| ⏱️ 소요 시간 | 12분 15초 |

**📱 TestFlight 설치**
TestFlight 앱에서 최신 빌드를 확인하세요.
```

### 빌드 실패 댓글

```markdown
❌ **Android 테스트 APK 빌드 실패**

| 항목 | 내용 |
|------|------|
| 📦 버전 | `2.1.3(86677440)` |
| 🌿 브랜치 | `feature/20240101_#123_기능명` |
| ⏱️ 소요 시간 | 2분 15초 |

**🔗 로그 확인**
[GitHub Actions 워크플로우 로그](링크)
```

iOS 빌드가 실패하면 댓글에 `**사유**: ...` 한 줄이 함께 표시됩니다 (예: 닫힌 버전으로 거부됨, 재시도 횟수 초과, 번들 번호 불일치).

---

## 필요한 설정

### 워크플로우 파일

다음 3개의 워크플로우 파일이 필요합니다:

| 파일 | 용도 |
|------|------|
| `PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml` | 댓글 감지 및 빌드 트리거 |
| `PROJECT-FLUTTER-ANDROID-TEST-APK.yaml` | Android APK 빌드 |
| `PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml` | iOS TestFlight 빌드 |

### GitHub Secrets

**Android 빌드용:**
- `RELEASE_KEYSTORE_BASE64`
- `RELEASE_KEYSTORE_PASSWORD`
- `RELEASE_KEY_ALIAS`
- `RELEASE_KEY_PASSWORD`
- `GOOGLE_SERVICES_JSON` (선택) — Firebase `google-services.json`
- `FIREBASE_SERVICE_ACCOUNT_JSON_BASE64` (선택) — Firebase 업로드를 함께 쓸 때
- `ENV_FILE` 또는 `ENV` (선택)

**iOS 빌드용:**
- `APPLE_CERTIFICATE_BASE64`
- `APPLE_CERTIFICATE_PASSWORD`
- `APPLE_PROVISIONING_PROFILE_BASE64`
- `IOS_PROVISIONING_PROFILE_NAME`
- `APP_STORE_CONNECT_API_KEY_ID`
- `APP_STORE_CONNECT_ISSUER_ID`
- `APP_STORE_CONNECT_API_KEY_BASE64`
- `SECRETS_XCCONFIG` (선택) — `ios/Flutter/Secrets.xcconfig` 내용
- `ENV_FILE` 또는 `ENV` (선택)

> ⚠️ Secret 이름이 하나라도 다르면 인증서·키스토어 복원 단계에서 빌드가 실패합니다. 전체 목록은 [Flutter CI/CD 전체 가이드](FLUTTER-CICD-OVERVIEW.md#github-secrets-전체-목록)를 참고하세요.

### Repository 권한

워크플로우에 다음 권한이 필요합니다:

```yaml
permissions:
  contents: write
  pull-requests: write
  issues: write
```

---

## 트러블슈팅

### "Guide by SUH-LAB" 댓글을 찾을 수 없음

```
❌ 이슈에서 "Guide by SUH-LAB" 댓글을 찾을 수 없습니다.
```

**해결:**
- 이슈에 "Guide by SUH-LAB" 형식의 댓글이 있어야 합니다
- 또는 PR에서 빌드를 트리거하세요

### 브랜치 정보를 파싱할 수 없음

```
❌ "Guide by SUH-LAB" 댓글에서 브랜치 정보를 파싱할 수 없습니다.
```

**해결:**
- "Guide by SUH-LAB" 댓글에 `### 브랜치` 섹션이 있어야 합니다
- 브랜치명이 코드 블록(```)으로 감싸져 있어야 합니다

### 빌드 워크플로우가 실행되지 않음

**확인 사항:**
1. `repository_dispatch` 이벤트를 받는 워크플로우 파일이 있는지 확인
2. 워크플로우 파일이 기본 브랜치에 있는지 확인
3. Actions 탭에서 워크플로우가 활성화되어 있는지 확인

### 빌드 실패

**Android:**
- `flutter build apk` 로컬에서 성공하는지 확인
- 필요한 Secrets가 설정되어 있는지 확인

**iOS:**
- 인증서와 Provisioning Profile이 유효한지 확인
- App Store Connect API Key 권한 확인
- ExportOptions.plist 설정 확인

---

## 파일 구조

```
.github/workflows/project-types/flutter/
├── PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml  # 빌드 트리거
├── PROJECT-FLUTTER-ANDROID-TEST-APK.yaml           # Android 테스트 빌드
└── PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml        # iOS 테스트 빌드
```

---

## 환경변수 설정

각 워크플로우에서 설정 가능한 환경변수:

```yaml
env:
  FLUTTER_VERSION: "3.24.5"      # Flutter 버전
  XCODE_VERSION: "16.4"          # Xcode 버전 (iOS만)
  ENV_FILE_PATH: ".env"          # 환경 파일 경로
```

---

## 관련 문서

- [Flutter CI/CD 전체 가이드](FLUTTER-CICD-OVERVIEW.md)
- [iOS TestFlight 마법사](FLUTTER-TESTFLIGHT-WIZARD.md)
- [Android Play Store 마법사](FLUTTER-PLAYSTORE-WIZARD.md)
