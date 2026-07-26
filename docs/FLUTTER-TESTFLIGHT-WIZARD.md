# iOS TestFlight 마법사 상세 가이드

> Flutter iOS 앱을 TestFlight에 배포하기 위한 설정 마법사

---

## 목차

- [개요](#개요)
- [사전 요구사항](#사전-요구사항)
- [마법사 사용법](#마법사-사용법)
- [생성되는 파일](#생성되는-파일)
- [GitHub Secrets 설정](#github-secrets-설정)
- [연관 워크플로우](#연관-워크플로우)
- [트러블슈팅](#트러블슈팅)

---

## 개요

TestFlight 마법사는 웹 UI를 통해 iOS 배포에 필요한 설정 파일들을 자동으로 생성해주는 도구입니다.

**위치:** `.github/util/flutter/testflight-wizard/`

**버전:** 1.5.0 (정확한 값은 마법사 헤더의 버전 배지 또는 `version.json` 참조)

**호환성:**
- Flutter >= 3.0.0
- Xcode >= 15.0
- Fastlane >= 2.220.0

---

## 사전 요구사항

마법사 실행 전에 Apple Developer Portal에서 다음 항목들을 준비해야 합니다:

### 1. Apple Developer Program 등록
- [developer.apple.com](https://developer.apple.com) 에서 등록
- 연간 $99 비용

### 2. 인증서 생성
- **Apple Distribution** 인증서 필요
- Keychain Access 또는 Xcode에서 생성
- `.p12` 파일로 내보내기

### 3. App ID 등록
- Identifiers에서 App ID 생성
- Bundle ID 설정 (예: `com.company.appname`)

### 4. Provisioning Profile 생성
- **App Store** 타입 선택
- 생성한 App ID 연결
- 배포 인증서 연결

### 5. App Store Connect API Key 생성
- App Store Connect → Users and Access → Integrations → Keys
- **App Manager** 또는 **Admin** 권한 선택
- `.p8` 파일 다운로드 (한 번만 가능!)

---

## 마법사 사용법

### 실행 방법

```bash
# 브라우저에서 마법사 열기
open .github/util/flutter/testflight-wizard/testflight-wizard.html
```

### 9단계 마법사 진행

| 단계 | 내용 | 입력 정보 |
|------|------|-----------|
| 1 | 시작 | 마법사 소개 |
| 2 | 인증서 | 인증서 생성 가이드 |
| 3 | App ID | Bundle ID 등록 가이드 |
| 4 | Profile | Provisioning Profile 생성 가이드 |
| 5 | ASC 등록 | App Store Connect 앱 등록 |
| 6 | 앱 정보 | Team ID, Bundle ID, Profile Name 입력 |
| 7 | API Key | App Store Connect API Key 정보 입력 |
| 8 | Fastlane | 생성된 설정 파일 다운로드 |
| 9 | 완료 | 설정 완료 확인 |

### 입력해야 할 정보

```yaml
# Step 6: 앱 정보
Team ID: "XXXXXXXXXX"           # Apple Developer Team ID (10자리)
Bundle ID: "com.company.app"    # 앱의 Bundle Identifier
Profile Name: "App Distribution" # Provisioning Profile 이름

# Step 7: API Key
API Key ID: "XXXXXXXXXX"        # App Store Connect API Key ID
Issuer ID: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # Issuer ID (UUID)
```

### 로컬 스크립트 직접 실행 (CLI)

웹 마법사 대신 명령어로 바로 설정할 수 있습니다.

```bash
python3 .github/util/flutter/testflight-wizard/testflight-wizard.py setup \
  --project-path . \
  --bundle-id com.example.myapp \
  --team-id ABC1234DEF \
  --profile-name "MyApp Distribution"
```

| 옵션 | 설명 |
|------|------|
| `--project-path` | Flutter 프로젝트 루트 경로 |
| `--bundle-id` | iOS 앱 Bundle ID |
| `--team-id` | Apple Developer Team ID (10자리) |
| `--profile-name` | Provisioning Profile 이름 |
| `--uses-encryption` | 암호화 사용 여부 (`true`/`false`, 기본 `false`) |

#### 공통 옵션 (마법사 3종 동일)

| 옵션 | 설명 |
|------|------|
| `--dry-run` | 무엇을 바꿀지만 출력하고 파일은 건드리지 않음 |
| `--no-backup` | 기존 파일 백업(`.bak`)을 만들지 않음 |
| `--non-interactive` | 확인 프롬프트 없이 진행 (CI용) |

> `--dry-run`은 실제 실행과 **동일한 판단 경로**를 탑니다. 적용 전 점검용으로 신뢰할 수 있습니다.
>
> 구 위치인자 형식(`setup PROJECT_PATH BUNDLE_ID TEAM_ID PROFILE_NAME`)도 계속 동작합니다. 이미 복사해 둔 명령어를 고칠 필요는 없습니다.

---

## 생성되는 파일

### 1. ExportOptions.plist

IPA 내보내기 설정 파일입니다.

**위치:** `ios/ExportOptions.plist`

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

Fastlane 배포 자동화 스크립트입니다.

**위치:** `ios/fastlane/Fastfile`

**제공하는 lane:**
- `upload_testflight` - CI용 (IPA가 이미 빌드된 상태)
- `build_and_deploy` - 로컬 개발용 (빌드 + 업로드)

**필요한 환경변수** (GitHub Secret이 아니라 워크플로우가 fastlane에 넘기는 값):
- `APP_STORE_CONNECT_API_KEY_ID`
- `APP_STORE_CONNECT_ISSUER_ID`
- `API_KEY_PATH` — 복원된 `.p8` 키 파일 경로
- `APP_IDENTIFIER` — 번들 ID
- `IPA_PATH`
- `APP_VERSION` / `BUILD_NUMBER`
- `RELEASE_NOTES` — 비어 있으면 기본 문구 사용
- `DEPLOY_MODE` — `testflight_only` / 심사 제출 등 배포 모드
- `DELIVER_LOCALES` — 심사 메타데이터 로케일

### 3. Gemfile

Fastlane 의존성 파일입니다.

**위치:** `ios/Gemfile`

```ruby
source "https://rubygems.org"

gem "fastlane"
```

---

## GitHub Secrets 설정

워크플로우 실행을 위해 다음 Secrets를 설정해야 합니다:

| Secret 이름 | 설명 | 값 형식 |
|------------|------|---------|
| `APPLE_CERTIFICATE_BASE64` | Apple Distribution 인증서 (.p12) | Base64 인코딩 |
| `APPLE_CERTIFICATE_PASSWORD` | 인증서 비밀번호 | 문자열 |
| `APPLE_PROVISIONING_PROFILE_BASE64` | Provisioning Profile (.mobileprovision) | Base64 인코딩 |
| `IOS_PROVISIONING_PROFILE_NAME` | Provisioning Profile 이름 | 문자열 |
| `APP_STORE_CONNECT_API_KEY_ID` | API Key ID (10자리) | 문자열 |
| `APP_STORE_CONNECT_ISSUER_ID` | Issuer ID | UUID 형식 |
| `APP_STORE_CONNECT_API_KEY_BASE64` | AuthKey_XXXXXX.p8 파일 | Base64 인코딩 |
| `IOS_BUNDLE_ID` (선택) | 번들 ID. 저장소 변수(`vars`)로도 지정 가능 | 문자열 |
| `ENV_FILE` (선택) | `.env` 파일 내용 | 문자열 |
| `SECRETS_XCCONFIG` (선택) | `ios/Flutter/Secrets.xcconfig` 내용 | 문자열 |

> ⚠️ Secret 이름은 워크플로우가 참조하는 이름과 **정확히** 일치해야 합니다. 인증서 계열은 `APPLE_` 접두사, App Store Connect API Key 본문은 `..._BASE64` 접미사입니다.

### Base64 인코딩 방법

```bash
# 인증서 인코딩
base64 -i Certificates.p12 | pbcopy

# Provisioning Profile 인코딩
base64 -i AppDistribution.mobileprovision | pbcopy

# App Store Connect API Key 인코딩
base64 -i AuthKey_XXXXXXXXXX.p8 | pbcopy
```

---

## 연관 워크플로우

### 본 배포
- **파일:** `PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml`
- **트리거:** main 브랜치 push
- **용도:** 정식 TestFlight 배포

### 테스트 빌드
- **파일:** `PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml`
- **트리거:** `@projectops build app` 또는 `@projectops ios build` 댓글 (repository_dispatch)
- **용도:** PR/이슈에서 테스트 빌드

---

## 트러블슈팅

### 인증서 관련 오류

```
❌ Error: No signing certificate "Apple Distribution" found
```

**해결:**
1. `APPLE_CERTIFICATE_BASE64` Secret이 올바르게 설정되었는지 확인
2. 인증서가 만료되지 않았는지 확인
3. 인증서 비밀번호가 맞는지 확인

### Provisioning Profile 오류

```
❌ Error: No profile matching 'App Distribution' found
```

**해결:**
1. `IOS_PROVISIONING_PROFILE_NAME`이 실제 Profile 이름과 일치하는지 확인
2. Profile이 유효한지 Apple Developer Portal에서 확인
3. Profile과 인증서가 연결되어 있는지 확인

### App Store Connect API 오류

```
❌ Error: Could not authenticate with App Store Connect
```

**해결:**
1. API Key ID와 Issuer ID가 맞는지 확인
2. API Key에 적절한 권한(App Manager 이상)이 있는지 확인
3. API Key 내용이 완전히 복사되었는지 확인 (-----BEGIN PRIVATE KEY----- 포함)

### ExportOptions.plist 오류

```
❌ Error: exportArchive: No applicable devices found
```

**해결:**
1. `teamID`가 정확한지 확인
2. `provisioningProfiles`의 Bundle ID가 앱과 일치하는지 확인
3. Profile 이름이 정확한지 확인

---

## 파일 구조

```
.github/util/flutter/
├── _shared/                        # 마법사 3종 공통 자산
│   ├── wizard.css                  #   공통 컴포넌트 스타일
│   ├── wizard-common.js            #   공통 유틸 (이스케이프·클립보드·상태 저장 등)
│   ├── check-consistency.py        #   3종 정합성 검증
│   └── test_wizard_cli.py          #   CLI 계약 · dry-run 안전성 테스트
└── testflight-wizard/
    ├── testflight-wizard.html      # 마법사 웹 UI
    ├── testflight-wizard.js        # 마법사 로직
    ├── testflight-wizard.py        # 설정 스크립트 (setup 서브커맨드)
    ├── version.json                # 버전 정보
    ├── version-sync.sh             # version.json → HTML 동기화
    └── templates/
        ├── ExportOptions.plist
        ├── Fastfile.ios.template
        └── Gemfile
```

> `_shared/`는 3종이 함께 쓰는 정본입니다. 마법사를 수정했다면 `check-consistency.py`와 `test_wizard_cli.py`를 통과시킨 뒤 커밋하세요. 상세: [`_shared/README.md`](../.github/util/flutter/_shared/README.md)

---

## 관련 문서

- [Flutter CI/CD 전체 가이드](FLUTTER-CICD-OVERVIEW.md)
- [테스트 빌드 트리거](FLUTTER-TEST-BUILD-TRIGGER.md)
- [Apple Developer 공식 문서](https://developer.apple.com/documentation/)
