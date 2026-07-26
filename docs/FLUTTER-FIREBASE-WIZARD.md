# Firebase App Distribution 마법사

> Flutter Android 앱을 Firebase App Distribution으로 배포하기 위한 설정을 5단계 웹 마법사로 자동 생성합니다.

---

## 목차

- [개요](#개요)
- [실행 방법](#실행-방법)
- [5단계 흐름](#5단계-흐름)
- [GitHub Secrets 설정](#github-secrets-설정)
- [워크플로우 env 설정](#워크플로우-env-설정)
- [CLI 사용법](#cli-사용법)
- [연관 워크플로우](#연관-워크플로우)
- [트러블슈팅](#트러블슈팅)

---

## 개요

Play Store 심사 없이 테스터에게 바로 APK를 배포하고 싶을 때 사용합니다. Play Store 배포와 **동일한 서명 Secret**을 쓰고, 업로드 대상만 Firebase로 달라집니다.

| 항목 | 값 |
|------|-----|
| **위치** | `.github/util/flutter/firebase-wizard/` |
| **구성** | `firebase-wizard.html` (웹 UI) / `firebase-wizard.js` / `firebase-wizard.py` (CLI) |
| **배포 대상** | Firebase App Distribution |
| **연동 워크플로우** | `PROJECT-FLUTTER-ANDROID-FIREBASE-CICD.yaml` |

> 모든 파일 변환(base64 인코딩 등)은 **브라우저 안에서만** 수행되며 외부 서버로 전송되지 않습니다.

---

## 실행 방법

```bash
open .github/util/flutter/firebase-wizard/firebase-wizard.html
```

Windows에서는 파일 탐색기에서 `firebase-wizard.html`을 더블클릭하거나 브라우저로 드래그하세요.

단계 사이는 자유롭게 이동할 수 있습니다 (상단 단계 표시를 클릭).

---

## 5단계 흐름

| 단계 | 내용 | 결과물 |
|------|------|--------|
| **1. Firebase Console 가이드** | 프로젝트 생성, Android 앱 등록, **App Distribution 활성화**, 테스터 그룹 생성 | `google-services.json` 다운로드, 앱 ID / 그룹 별칭 확보 |
| **2. Service Account 발급** | GitHub Actions가 Firebase에 업로드할 때 쓸 서비스 계정 키 발급 | Service Account JSON 다운로드 |
| **3. 앱 정보 입력** | 1단계에서 확보한 **앱 ID**와 **테스터 그룹 별칭** 입력 | 워크플로우 placeholder 치환용 setup 명령 생성 |
| **4. 파일 업로드** | Service Account JSON(필수), `google-services.json`(선택) 업로드 | base64 인코딩된 Secret 값 |
| **5. Secrets 등록** | 등록할 GitHub Secrets 목록 확인 및 산출물 다운로드 | JSON / TXT / ZIP(setup 스크립트 포함) |

> ⚠️ **1단계의 App Distribution 활성화를 건너뛰면 배포가 `404 not found`로 실패합니다.** 반드시 수행하세요.
>
> ⚠️ 3단계에 넣을 테스터 그룹 값은 화면에 보이는 **"표시 이름"이 아니라 "그룹 별칭(alias)"** 입니다.

---

## GitHub Secrets 설정

### 마법사가 생성해주는 Secret

| Secret 이름 | 설명 | 값 형식 |
|------------|------|---------|
| `FIREBASE_SERVICE_ACCOUNT_JSON_BASE64` | Firebase 서비스 계정 JSON | Base64 인코딩 |
| `GOOGLE_SERVICES_JSON` (선택) | `google-services.json` 내용 | JSON 문자열 |

### 직접 등록해야 하는 서명 Secret

Play Store 배포와 **동일한 이름**을 사용합니다. 이미 Play Store 마법사를 돌렸다면 추가 작업이 없습니다.

| Secret 이름 | 설명 | 값 형식 |
|------------|------|---------|
| `RELEASE_KEYSTORE_BASE64` | 서명용 keystore (.jks) | Base64 인코딩 |
| `RELEASE_KEYSTORE_PASSWORD` | Keystore 비밀번호 | 문자열 |
| `RELEASE_KEY_ALIAS` | 키 별칭 | 문자열 |
| `RELEASE_KEY_PASSWORD` | 키 비밀번호 | 문자열 |
| `ENV_FILE` 또는 `ENV` (선택) | `.env` 파일 내용 (`ENV_FILE` 우선) | 문자열 |

---

## 워크플로우 env 설정

`PROJECT-FLUTTER-ANDROID-FIREBASE-CICD.yaml`의 env 섹션에서 다음 두 값을 프로젝트에 맞게 수정합니다. 마법사 3단계의 setup 명령(또는 아래 CLI)이 자동으로 치환해줍니다.

```yaml
env:
  FIREBASE_APP_ID: "your-firebase-app-id"     # 예: 1:905325245238:android:86db...
  FIREBASE_TESTER_GROUP: "testers"            # 테스터 그룹 별칭
```

---

## CLI 사용법

웹 마법사를 쓰지 않고 값만 치환하려면 `firebase-wizard.py`를 직접 실행합니다 (stdlib 전용, macOS/Windows 공통).

```bash
python3 .github/util/flutter/firebase-wizard/firebase-wizard.py setup \
  --project-path /path/to/project \
  --app-id "1:905325245238:android:86db..." \
  --tester-group "testers"
```

| 옵션 | 설명 |
|------|------|
| `--dry-run` | 실제 파일을 수정하지 않고 변경 예정 내용만 출력 |
| `--non-interactive` | 확인 프롬프트 없이 진행 (CI용) |
| `--no-backup` | 수정 전 백업 파일을 만들지 않음 |

---

## 연관 워크플로우

### 본 배포
- **파일:** `PROJECT-FLUTTER-ANDROID-FIREBASE-CICD.yaml`
- **트리거:** main 브랜치 push (+ `workflow_dispatch`)
- **용도:** APK 빌드 후 Firebase App Distribution 업로드

### 테스트 빌드
- **파일:** `PROJECT-FLUTTER-ANDROID-TEST-APK.yaml`
- **트리거:** `@projectops build app` 또는 `@projectops apk build` 댓글 (repository_dispatch)
- **용도:** PR/이슈에서 테스트 APK 빌드 (Firebase 업로드 옵션 포함)

---

## 트러블슈팅

### 404 not found

```
❌ Error: Requested entity was not found
```

**해결:**
1. Firebase Console → App Distribution이 **활성화**되어 있는지 확인 (마법사 1단계 3번)
2. `FIREBASE_APP_ID`가 실제 앱 ID와 일치하는지 확인

### 테스터에게 배포되지 않음

**확인 사항:**
1. `FIREBASE_TESTER_GROUP`에 **표시 이름이 아니라 그룹 별칭**을 넣었는지 확인
2. Firebase Console에서 해당 그룹에 테스터가 등록되어 있는지 확인

### 인증 실패

```
❌ Error: Could not authenticate
```

**해결:**
1. `FIREBASE_SERVICE_ACCOUNT_JSON_BASE64`가 base64 인코딩된 값인지 확인 (JSON 원문 아님)
2. 서비스 계정에 Firebase App Distribution 권한이 있는지 확인

### 서명 오류

```
❌ Error: Keystore was tampered with, or password was incorrect
```

**해결:** [Play Store 마법사 가이드](FLUTTER-PLAYSTORE-WIZARD.md#트러블슈팅)의 서명 관련 항목과 동일합니다.

---

## 관련 문서

- [Flutter CI/CD 전체 가이드](FLUTTER-CICD-OVERVIEW.md)
- [Android Play Store 마법사](FLUTTER-PLAYSTORE-WIZARD.md)
- [테스트 빌드 트리거](FLUTTER-TEST-BUILD-TRIGGER.md)
