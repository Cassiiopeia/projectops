# GitHub Actions 워크플로우 주석 표준 가이드라인

> projectops의 모든 워크플로우 파일에 적용되는 주석 작성 규칙

---

## 1. 기본 원칙

### 1.1 구분선 표준

```yaml
# ===================================================================
```

- **모든 파일에서 67자 구분선 사용**
- 짧은 구분선(44자, 51자 등) 사용 금지

### 1.2 핵심 규칙

| 규칙 | 설명 |
|------|------|
| GITHUB_TOKEN 언급 금지 | 자동 제공되므로 문서화 불필요 |
| 필수는 표시 안함 | 기본이 필수이므로 생략 |
| 선택만 `(선택)` 표시 | `SECRET_NAME (선택): 설명` |
| 1줄 형식 | `SECRET_NAME: 설명` (들여쓰기 없음) |

### 1.3 Secrets 작성 형식

```yaml
# 🔑 필수 GitHub Secrets
# ===================================================================
# ENV_FILE: .env 파일 내용
# DOCKERHUB_USERNAME: DockerHub 사용자명
# DOCKERHUB_TOKEN: DockerHub 액세스 토큰
# APPLICATION_PROD_YML (선택): application-prod.yml 내용
# ===================================================================
```

**상세 설명이 필요한 경우만:**

```yaml
# _GITHUB_PAT_TOKEN: PR 머지용 PAT
#   - 권한: repo
#   - 설정: Settings → Secrets → Actions
```

---

## 2. 워크플로우 분류

| 분류 | 특징 | 예시 |
|------|------|------|
| **Type A: 단순** | Secrets 없음, 기능 단순 | SYNC-ISSUE-LABELS, VERSION-CONTROL |
| **Type B: 기본** | Secrets 있음, 환경변수 단순 | RELEASE-CHANGELOG, NEXUS-CI |
| **Type C: CI** | 빌드 검증, 설정 옵션 다수 | FLUTTER-CI, REACT-CI |
| **Type D: CD** | 배포, 환경변수 상세 가이드 | SPRING-SIMPLE-CICD, PYTHON-SIMPLE-CICD |
| **Type E: 특수** | 마법사 연동, 복잡한 설명 | IOS-TESTFLIGHT, PLAYSTORE-CICD, FIREBASE-CICD |

---

## 3. Type A: 단순 워크플로우

> Secrets 없음, GITHUB_TOKEN만 사용

```yaml
# ===================================================================
# PROJECT-COMMON-SYNC-ISSUE-LABELS.yaml
# Issue Labels 동기화
# ===================================================================
#
# .github/config/issue-labels.yml 파일을 기준으로
# GitHub 레포지토리의 Labels를 동기화합니다.
#
# ===================================================================
# 트리거:
# - .github/config/issue-labels.yml 파일 변경 시
# - 수동 실행 (workflow_dispatch)
# ===================================================================

name: PROJECT-SYNC-GITHUB-LABELS
```

**적용 파일:**
- SYNC-ISSUE-LABELS
- VERSION-CONTROL
- README-VERSION-UPDATE
- QA-ISSUE-CREATION-BOT
- TEMPLATE-INITIALIZER

---

## 4. Type B: 기본 워크플로우

> Secrets 있지만 환경변수 단순

```yaml
# ===================================================================
# PROJECT-COMMON-RELEASE-CHANGELOG.yaml
# CodeRabbit 기반 CHANGELOG 자동 생성
# ===================================================================
#
# main 브랜치로 릴리스 PR(develop→main)이 생성될 때 CodeRabbit AI의 리뷰를
# 자동으로 파싱하여 CHANGELOG를 업데이트합니다.
#
# ===================================================================
# 🔑 필수 GitHub Secrets
# ===================================================================
# _GITHUB_PAT_TOKEN: PR 머지용 PAT (권한: repo)
# ===================================================================
#
# 작동 방식:
# 1. main 브랜치로 릴리스 PR(develop→main) 생성 시 트리거
# 2. CodeRabbit Summary 요청 후 대기
# 3. CHANGELOG 파일 업데이트
# 4. PR 자동 머지
# ===================================================================

name: PROJECT-COMMON-RELEASE-CHANGELOG
```

**Secrets 상세 설명이 필요한 경우 (예외적):**

> 대부분의 Secrets는 1줄로 충분합니다. 권한이나 설정 방법은 별도 문서로 안내하세요.

**적용 파일:**
- RELEASE-CHANGELOG
- PROJECTS-SYNC-MANAGER
- NEXUS-CI
- NEXUS-PUBLISH

---

## 5. Type C: CI 워크플로우

> 빌드 검증, 설정 옵션 다수

```yaml
# ===================================================================
# Flutter CI (코드 분석 및 빌드 검증)
# ===================================================================
#
# PR 생성 또는 main 브랜치 푸시 시
# 코드 정적 분석과 빌드를 검증합니다.
#
# 주요 특징:
# - flutter analyze로 코드 품질 검사
# - Android/iOS 빌드 개별 활성화 가능
# - Analyze Only 모드 지원
#
# ===================================================================
# 🔑 필수 GitHub Secrets
# ===================================================================
# ENV_FILE (선택): .env 파일 내용
#
# ※ CI는 빌드 검증 목적이므로 서명/배포 Secrets 불필요
# ===================================================================
#
# 🔧 프로젝트별 설정 (env 섹션)
# ===================================================================
# ANALYZE_ONLY    : true면 analyze만 실행 (기본: false)
# ENABLE_ANDROID  : Android 빌드 활성화 여부
# ENABLE_IOS      : iOS 빌드 활성화 여부
# FLUTTER_VERSION : Flutter SDK 버전
# ===================================================================

name: PROJECT-Flutter-CI
```

**적용 파일:**
- FLUTTER-CI
- REACT-CI

- PYTHON-CI

---

## 6. Type D: CD 워크플로우

> 배포, 환경변수 상세 가이드 필요

```yaml
# ===================================================================
# Spring Boot CI/CD 배포 (SSH + Docker)
# ===================================================================
#
# main 브랜치 푸시 시 Docker 이미지를 빌드하고
# SSH 접속 가능한 서버(Synology NAS·AWS EC2·일반 Linux 등)에 자동 배포합니다.
#
# ===================================================================
# 🔑 필수 GitHub Secrets
# ===================================================================
# APPLICATION_PROD_YML (선택): application-prod.yml 내용
# DOCKERHUB_USERNAME: DockerHub 사용자명
# DOCKERHUB_TOKEN: DockerHub 액세스 토큰
# SERVER_HOST: 배포 서버 주소
# SERVER_USER: SSH 사용자명
# SERVER_PASSWORD: SSH 비밀번호
# ===================================================================
#
# 🔧 환경변수 설정 (env 섹션에서 설정)
# ===================================================================
#
# 🌐 포트 및 컨테이너:
# CONTAINER_INTERNAL_PORT: 내부 포트 (기본: 8080)
# DEPLOY_PORT: 배포 포트
# CONTAINER_NAME: 컨테이너 이름 (기본: PROJECT_NAME)
#
# 🔌 SSH 연결:
# SSH_PORT: SSH 포트 (기본: 2022)
# SSH_COMMAND_TIMEOUT: 명령 타임아웃 (기본: 600s)
#
# ⏱️ 헬스체크:
# HEALTHCHECK_PATH: HTTP 경로 (비어있으면 로그만 사용)
# HEALTHCHECK_LOG_PATTERN: 로그 검색 패턴
#
# 💡 HEALTHCHECK_PATH 예시:
#   Spring Boot (Actuator): "/actuator/health"
#   FastAPI: "/docs"
# ===================================================================

name: PROJECT-SPRING-SIMPLE-CICD
```

**적용 파일:**
- PROJECT-SPRING-SIMPLE-CICD
- PROJECT-SPRING-NONSTOP-TRAEFIK-CICD
- PROJECT-SPRING-NONSTOP-NGINX-CICD
- PROJECT-PYTHON-SIMPLE-CICD
- PROJECT-REACT-CICD
- PROJECT-COMMON-VERCEL-DEPLOY
- PROJECT-COMMON-SECRET-FILE-UPLOAD
- PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD

---

## 7. Type E: 특수 워크플로우

> 마법사 연동, 복잡한 설명 필요

```yaml
# ===================================================================
# Flutter iOS TestFlight 자동 배포
# ===================================================================
#
# Flutter iOS 앱을 빌드하여 TestFlight에 자동 배포합니다.
#
# ★ 마법사 우선 아키텍처 ★
# - 설정 파일은 웹 마법사가 생성합니다
# - 마법사: .github/util/flutter/testflight-wizard/
#
# ===================================================================
# 🔑 필수 GitHub Secrets
# ===================================================================
#
# 🔐 Apple 인증서:
# APPLE_CERTIFICATE_BASE64: .p12 인증서 (base64)
# APPLE_CERTIFICATE_PASSWORD: 인증서 비밀번호
# APPLE_PROVISIONING_PROFILE_BASE64: 프로비저닝 프로파일 (base64)
# IOS_PROVISIONING_PROFILE_NAME: 프로파일 이름
#
# 🔑 App Store Connect API:
# APP_STORE_CONNECT_API_KEY_ID: API Key ID
# APP_STORE_CONNECT_ISSUER_ID: Issuer ID
# APP_STORE_CONNECT_API_KEY_BASE64: .p8 파일 (base64)
#
# 📝 환경 설정 (선택):
# ENV_FILE: .env 파일 내용
# ===================================================================
#
# 🛠️ 설정 방법:
# 1. 마법사 실행 (브라우저에서 열기)
# 2. GitHub Secrets 설정
# 3. 생성된 파일 커밋
# 4. main 브랜치 푸시
# ===================================================================

name: PROJECT-iOS-TestFlight-Deploy
```

**적용 파일:**
- PROJECT-FLUTTER-IOS-TESTFLIGHT / -IOS-TEST-TESTFLIGHT
- PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD / -ANDROID-TEST-APK
- PROJECT-FLUTTER-ANDROID-FIREBASE-CICD
- PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER
- PROJECT-SPRING-PR-PREVIEW / PROJECT-PYTHON-PR-PREVIEW

---

## 8. 아이콘 사용 규칙

| 아이콘 | 용도 | 예시 |
|--------|------|------|
| 🔑 | 필수 GitHub Secrets 섹션 헤더 | `# 🔑 필수 GitHub Secrets` |
| 🔐 | 인증서/보안 관련 그룹 헤더 | `# 🔐 Apple 인증서:` |
| 📝 | 환경 설정 (선택 항목) | `# 📝 환경 설정 (선택):` |
| 🔧 | 프로젝트별 설정 | `# 🔧 프로젝트별 설정 (env 섹션)` |
| 🌐 | 포트/네트워크 설정 | `# 🌐 포트 및 컨테이너 설정` |
| 🔌 | SSH/연결 설정 | `# 🔌 SSH 연결 설정` |
| ⏱️ | 헬스체크/타임아웃 | `# ⏱️ 헬스체크 설정` |
| 💡 | 예시/팁 | `# 💡 HEALTHCHECK_PATH 예시:` |
| ⚠️ | 주의사항 | `# ⚠️ README.md 파일 버전 표기 가이드라인:` |
| 🛠️ | 설정 방법/절차 | `# 🛠️ 설정 방법:` |
| ★ | 특수 아키텍처 강조 | `# ★ 마법사 우선 아키텍처 ★` |
| 🔥 | 안전장치/중요 경고 | `# 🔥 안전장치:` |

---

## 9. 환경변수 작성 형식

> 테이블 형식 대신 간단한 1줄 형식 사용

### 기본 형식

```yaml
# 🔧 환경변수 설정 (env 섹션에서 설정)
# ===================================================================
#
# 🌐 포트 및 컨테이너:
# CONTAINER_INTERNAL_PORT: 내부 포트 (기본: 8080)
# DEPLOY_PORT: 배포 포트
# CONTAINER_NAME: 컨테이너 이름 (기본: PROJECT_NAME)
#
# 🔌 SSH 연결:
# SSH_PORT: SSH 포트 (기본: 2022)
# SSH_COMMAND_TIMEOUT: 명령 타임아웃 (기본: 600s)
# ===================================================================
```

### 그룹 헤더 사용

관련 환경변수를 아이콘과 함께 그룹화합니다:
- 🌐 포트/네트워크
- 🔌 SSH/연결
- ⏱️ 헬스체크/타임아웃
- 📦 볼륨/스토리지

---

## 10. 파일별 적용 현황

> 이 표는 **현행 워크플로우 전수** 기준입니다. 워크플로우를 추가·리네임·삭제하면 이 표도 함께 갱신하세요.

### 템플릿 레포 전용 (루트에만 존재 — 사용자 프로젝트로 복사되지 않음)

| 파일 | 타입 | 상태 |
|------|------|------|
| PROJECT-TEMPLATE-INITIALIZER | A | ✅ |
| PROJECT-TEMPLATE-CI | C | ✅ |
| PROJECT-TEMPLATE-NPM-PUBLISH | B | ✅ |
| PROJECT-TEMPLATE-PLUGIN-VERSION-SYNC | A | ✅ |

### project-types/common/ (= 루트 `PROJECT-COMMON-*` 사본과 동일 유지)

| 파일 | 타입 | 상태 |
|------|------|------|
| PROJECT-COMMON-VERSION-CONTROL | A | ✅ |
| PROJECT-COMMON-RELEASE-CHANGELOG | B | ✅ |
| PROJECT-COMMON-README-VERSION-UPDATE | A | ✅ |
| PROJECT-COMMON-SYNC-ISSUE-LABELS | A | ✅ |
| PROJECT-COMMON-QA-ISSUE-CREATION-BOT | A | ✅ |
| PROJECT-COMMON-SUH-ISSUE-HELPER | B | ✅ |
| PROJECT-COMMON-PROJECTS-SYNC-MANAGER | B | ✅ |
| PROJECT-COMMON-TEMPLATE-UTIL-VERSION-SYNC | A | ✅ |

#### common/deploy/vercel/ (`--deploy vercel`일 때만 포함)

| 파일 | 타입 | 상태 |
|------|------|------|
| PROJECT-COMMON-VERCEL-DEPLOY | D | ✅ |

#### common/secret-backup/ (`--secret-backup` opt-in)

| 파일 | 타입 | 상태 |
|------|------|------|
| PROJECT-COMMON-SECRET-FILE-UPLOAD | D | ✅ |

### project-types/flutter/

| 파일 | 타입 | 상태 |
|------|------|------|
| PROJECT-FLUTTER-CI | C | ✅ |
| PROJECT-FLUTTER-IOS-TESTFLIGHT | E | ✅ |
| PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT | E | ✅ |
| PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD | E | ✅ |
| PROJECT-FLUTTER-ANDROID-FIREBASE-CICD | E | ✅ |
| PROJECT-FLUTTER-ANDROID-TEST-APK | E | ✅ |
| PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD | D | ✅ |
| PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER | E | ✅ |

### project-types/spring/

| 파일 | 위치 | 타입 | 상태 |
|------|------|------|------|
| PROJECT-SPRING-SIMPLE-CICD | server-deploy/ | D | ✅ |
| PROJECT-SPRING-NONSTOP-TRAEFIK-CICD | server-deploy/ | D | ✅ |
| PROJECT-SPRING-NONSTOP-NGINX-CICD | server-deploy/ | D | ✅ |
| PROJECT-SPRING-PR-PREVIEW | server-deploy/ | E | ✅ |
| PROJECT-SPRING-NEXUS-CI | publish/nexus/ | B | ✅ |
| PROJECT-SPRING-NEXUS-PUBLISH | publish/nexus/ | B | ✅ |
| PROJECT-SPRING-GITHUB-PACKAGES-PUBLISH | publish/github-packages/ | B | ✅ |

### project-types/python/

| 파일 | 위치 | 타입 | 상태 |
|------|------|------|------|
| PROJECT-PYTHON-CI | 직하위 | C | ✅ |
| PROJECT-PYTHON-SIMPLE-CICD | server-deploy/ | D | ✅ |
| PROJECT-PYTHON-PR-PREVIEW | server-deploy/ | E | ✅ |

### project-types/react/ (Next.js 포함 — next 타입은 v4.1.0에서 흡수)

| 파일 | 타입 | 상태 |
|------|------|------|
| PROJECT-REACT-CI | C | ✅ |
| PROJECT-REACT-CICD | D | ✅ |

### project-types/node/

| 파일 | 위치 | 타입 | 상태 |
|------|------|------|------|
| PROJECT-NODE-NPM-PUBLISH | publish/npm/ | B | ✅ |

> **위치가 곧 포함 조건입니다.** 타입 폴더 직하위는 그 타입을 선택하면 항상 복사되고, `server-deploy/`는 `--deploy docker-ssh`일 때만, `publish/<target>/`는 해당 publish 타겟을 골랐을 때만 복사됩니다. **서버 배포 워크플로우를 새로 추가하면 반드시 `server-deploy/` 아래에 두세요.**

---

## 11. 새 워크플로우 작성 가이드

### Step 1: 타입 결정

1. Secrets 없음 → **Type A**
2. Secrets 있고 환경변수 단순 → **Type B**
3. CI (빌드 검증) → **Type C**
4. CD (배포) → **Type D**
5. 마법사 연동/복잡 → **Type E**

### Step 2: 템플릿 적용

해당 타입의 템플릿을 복사하여 시작합니다.

### Step 3: 체크리스트

- [ ] 67자 구분선 사용
- [ ] GITHUB_TOKEN 언급 없음
- [ ] Secrets는 1줄 형식 (`SECRET_NAME: 설명`)
- [ ] 선택 항목에만 `(선택)` 표시
- [ ] 아이콘 용도에 맞게 사용
- [ ] 환경변수는 1줄 형식 (테이블 사용 금지)

---

## 12. 관련 문서

- [CLAUDE.md](../CLAUDE.md) - 프로젝트 전체 가이드
- [VERSION-CONTROL.md](./VERSION-CONTROL.md) - 버전 관리 시스템
- [CHANGELOG-AUTOMATION.md](./CHANGELOG-AUTOMATION.md) - 체인지로그 자동화
