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
- 테스트 버전 `0.0.0` 고정 (운영 버전과 분리)
- **플랫폼별 독립 빌드 카운트** (빌드 번호 중복 방지)
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

빌드 번호는 **PR/이슈 번호 + 2자리 카운트**로 자동 생성됩니다.

### 형식
```
{PR/이슈번호}{빌드횟수(2자리)}
```

### 플랫폼별 독립 카운트

**중요**: 각 빌드 타입은 **독립적인 카운트**를 가집니다.

| 빌드 타입 | 카운트 기준 댓글 |
|-----------|-----------------|
| `build app` | `@projectops` + `build app` 포함 댓글 |
| `apk build` | `@projectops` + `apk build` 포함 댓글 |
| `ios build` | `@projectops` + `ios build` 포함 댓글 |

> **Note**: 트리거 요청 댓글 자체를 카운트하므로, 빌드 실패 여부와 관계없이 정확한 빌드 번호가 생성됩니다.

이를 통해 `apk build`와 `ios build`를 혼용해도 빌드 번호가 중복되지 않습니다.

### 예시: 플랫폼별 독립 카운트

| 실행 순서 | 명령어 | 카운트 기준 | 빌드 번호 |
|-----------|--------|-------------|-----------|
| 1 | `@projectops apk build` | APK 카운트: 0 | `38700` |
| 2 | `@projectops ios build` | iOS 카운트: 0 | `38700` |
| 3 | `@projectops apk build` | APK 카운트: 1 | `38701` |
| 4 | `@projectops ios build` | iOS 카운트: 1 | `38701` |
| 5 | `@projectops build app` | 앱 카운트: 0 | `38700` |

> **Note**: Android와 iOS가 같은 빌드 번호를 가질 수 있지만, 각 플랫폼 내에서는 고유합니다.

### 앱 버전 형식
```
0.0.0(38700)
```
- 버전: `0.0.0` (테스트용 고정)
- 빌드 번호: `38700` (고유 식별자)

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
   - 빌드 번호 생성 (플랫폼별 독립 카운트)
       ↓
3. repository_dispatch 이벤트 발생 (빌드 타입에 따라)
   - build app: Android + iOS 모두 트리거
   - apk build: Android만 트리거
   - ios build: iOS만 트리거
       ↓
4. 선택된 워크플로우 실행
   ┌─────────────────────────────────┐
   │ ANDROID-TEST-APK               │
   │ - Flutter 빌드                  │
   │ - APK 생성                      │
   │ - 아티팩트 업로드               │
   │ - 결과 댓글 작성                │
   └─────────────────────────────────┘
   ┌─────────────────────────────────┐
   │ IOS-TEST-TESTFLIGHT            │
   │ - Flutter 빌드                  │
   │ - IPA 생성                      │
   │ - TestFlight 업로드            │
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
| 📦 버전 | `0.0.0(38700)` |
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
| 📦 버전 | `0.0.0(38700)` |
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
| 📦 버전 | `0.0.0(38700)` |
| 🌿 브랜치 | `feature/20240101_#123_기능명` |
| ⏱️ 소요 시간 | 2분 15초 |

**🔗 로그 확인**
[GitHub Actions 워크플로우 로그](링크)
```

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
