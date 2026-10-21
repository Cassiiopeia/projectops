# GitHub Actions workflow comment standard

> Comment rules that apply to every workflow file in projectops

The workflow files themselves use Korean comments, so the example comment blocks below are kept exactly as written in the workflows. Follow their wording and layout when you write a new workflow header.

---

## 1. Basic principles

### 1.1 Separator standard

```yaml
# ===================================================================
```

- **Use the 67-character separator in every file**
- Do not use short separators (44 characters, 51 characters, etc.)

### 1.2 Core rules

| Rule | Description |
|------|------|
| Do not mention GITHUB_TOKEN | It is provided automatically, so there is no need to document it |
| Do not mark required items | Required is the default, so leave it out |
| Mark only optional items with `(선택)` ("optional") | `SECRET_NAME (선택): description` |
| One-line format | `SECRET_NAME: description` (no indentation) |

### 1.3 Secrets format

```yaml
# 🔑 필수 GitHub Secrets
# ===================================================================
# ENV_FILE: .env 파일 내용
# DOCKERHUB_USERNAME: DockerHub 사용자명
# DOCKERHUB_TOKEN: DockerHub 액세스 토큰
# APPLICATION_PROD_YML (선택): application-prod.yml 내용
# ===================================================================
```

**Only when a detailed explanation is needed:**

```yaml
# _GITHUB_PAT_TOKEN: PR 머지용 PAT
#   - 권한: repo
#   - 설정: Settings → Secrets → Actions
```

---

## 2. Workflow classification

| Class | Characteristics | Examples |
|------|------|------|
| **Type A: Simple** | No Secrets, simple function | SYNC-ISSUE-LABELS, VERSION-CONTROL |
| **Type B: Basic** | Has Secrets, simple environment variables | RELEASE-CHANGELOG, NEXUS-CI |
| **Type C: CI** | Build verification, many configuration options | FLUTTER-CI, REACT-CI |
| **Type D: CD** | Deployment, detailed environment variable guide | SPRING-SIMPLE-CICD, PYTHON-SIMPLE-CICD |
| **Type E: Special** | Wizard integration, complex explanation | IOS-TESTFLIGHT, PLAYSTORE-CICD, FIREBASE-CICD |

---

## 3. Type A: Simple workflows

> No Secrets, uses only GITHUB_TOKEN

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

**Applies to:**
- SYNC-ISSUE-LABELS
- VERSION-CONTROL
- README-VERSION-UPDATE
- QA-ISSUE-CREATION-BOT
- TEMPLATE-INITIALIZER

---

## 4. Type B: Basic workflows

> Has Secrets, but simple environment variables

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

**When Secrets need a detailed explanation (exceptional):**

> One line is enough for most Secrets. Explain permissions and setup steps in a separate document.

**Applies to:**
- RELEASE-CHANGELOG
- PROJECTS-SYNC-MANAGER
- NEXUS-CI
- NEXUS-PUBLISH

---

## 5. Type C: CI workflows

> Build verification, many configuration options

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

**Applies to:**
- FLUTTER-CI
- REACT-CI

- PYTHON-CI

---

## 6. Type D: CD workflows

> Deployment, needs a detailed environment variable guide

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

**Applies to:**
- PROJECT-SPRING-SIMPLE-CICD
- PROJECT-SPRING-NONSTOP-TRAEFIK-CICD
- PROJECT-SPRING-NONSTOP-NGINX-CICD
- PROJECT-PYTHON-SIMPLE-CICD
- PROJECT-REACT-CICD
- PROJECT-COMMON-VERCEL-DEPLOY
- PROJECT-COMMON-SECRET-FILE-UPLOAD
- PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD

---

## 7. Type E: Special workflows

> Wizard integration, needs a complex explanation

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

**Applies to:**
- PROJECT-FLUTTER-IOS-TESTFLIGHT / -IOS-TEST-TESTFLIGHT
- PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD / -ANDROID-TEST-APK
- PROJECT-FLUTTER-ANDROID-FIREBASE-CICD
- PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER
- PROJECT-SPRING-PR-PREVIEW / PROJECT-PYTHON-PR-PREVIEW

---

## 8. Icon rules

| Icon | Use | Example |
|--------|------|------|
| 🔑 | Header of the required GitHub Secrets section | `# 🔑 필수 GitHub Secrets` |
| 🔐 | Group header for certificates and security | `# 🔐 Apple 인증서:` |
| 📝 | Environment settings (optional items) | `# 📝 환경 설정 (선택):` |
| 🔧 | Per-project settings | `# 🔧 프로젝트별 설정 (env 섹션)` |
| 🌐 | Port and network settings | `# 🌐 포트 및 컨테이너 설정` |
| 🔌 | SSH and connection settings | `# 🔌 SSH 연결 설정` |
| ⏱️ | Health check and timeouts | `# ⏱️ 헬스체크 설정` |
| 💡 | Examples and tips | `# 💡 HEALTHCHECK_PATH 예시:` |
| ⚠️ | Cautions | `# ⚠️ README.md 파일 버전 표기 가이드라인:` |
| 🛠️ | Setup steps and procedures | `# 🛠️ 설정 방법:` |
| ★ | Emphasis on a special architecture | `# ★ 마법사 우선 아키텍처 ★` |
| 🔥 | Safeguards and important warnings | `# 🔥 안전장치:` |

---

## 9. Environment variable format

> Use a simple one-line format instead of a table

### Basic format

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

### Group headers

Group related environment variables under an icon:
- 🌐 Ports and network
- 🔌 SSH and connections
- ⏱️ Health checks and timeouts
- 📦 Volumes and storage

---

## 10. Status per file

> This table covers **every current workflow**. When you add, rename or delete a workflow, update this table too.

### Template repository only (exists only at the root, not copied into user projects)

| File | Type | Status |
|------|------|------|
| PROJECT-TEMPLATE-INITIALIZER | A | ✅ |
| PROJECT-TEMPLATE-CI | C | ✅ |
| PROJECT-TEMPLATE-NPM-PUBLISH | B | ✅ |
| PROJECT-TEMPLATE-PLUGIN-VERSION-SYNC | A | ✅ |

### project-types/common/ (kept identical to the root `PROJECT-COMMON-*` copies)

| File | Type | Status |
|------|------|------|
| PROJECT-COMMON-VERSION-CONTROL | A | ✅ |
| PROJECT-COMMON-RELEASE-CHANGELOG | B | ✅ |
| PROJECT-COMMON-README-VERSION-UPDATE | A | ✅ |
| PROJECT-COMMON-SYNC-ISSUE-LABELS | A | ✅ |
| PROJECT-COMMON-QA-ISSUE-CREATION-BOT | A | ✅ |
| PROJECT-COMMON-SUH-ISSUE-HELPER | B | ✅ |
| PROJECT-COMMON-PROJECTS-SYNC-MANAGER | B | ✅ |
| PROJECT-COMMON-TEMPLATE-UTIL-VERSION-SYNC | A | ✅ |

#### common/deploy/vercel/ (included only with `--deploy vercel`)

| File | Type | Status |
|------|------|------|
| PROJECT-COMMON-VERCEL-DEPLOY | D | ✅ |

#### common/secret-backup/ (`--secret-backup` opt-in)

| File | Type | Status |
|------|------|------|
| PROJECT-COMMON-SECRET-FILE-UPLOAD | D | ✅ |

### project-types/flutter/

| File | Type | Status |
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

| File | Location | Type | Status |
|------|------|------|------|
| PROJECT-SPRING-SIMPLE-CICD | server-deploy/ | D | ✅ |
| PROJECT-SPRING-NONSTOP-TRAEFIK-CICD | server-deploy/ | D | ✅ |
| PROJECT-SPRING-NONSTOP-NGINX-CICD | server-deploy/ | D | ✅ |
| PROJECT-SPRING-PR-PREVIEW | server-deploy/ | E | ✅ |
| PROJECT-SPRING-NEXUS-CI | publish/nexus/ | B | ✅ |
| PROJECT-SPRING-NEXUS-PUBLISH | publish/nexus/ | B | ✅ |
| PROJECT-SPRING-GITHUB-PACKAGES-PUBLISH | publish/github-packages/ | B | ✅ |

### project-types/python/

| File | Location | Type | Status |
|------|------|------|------|
| PROJECT-PYTHON-CI | directly under the type folder | C | ✅ |
| PROJECT-PYTHON-SIMPLE-CICD | server-deploy/ | D | ✅ |
| PROJECT-PYTHON-PR-PREVIEW | server-deploy/ | E | ✅ |

### project-types/react/ (includes Next.js; the next type was absorbed in v4.1.0)

| File | Type | Status |
|------|------|------|
| PROJECT-REACT-CI | C | ✅ |
| PROJECT-REACT-CICD | D | ✅ |

### project-types/node/

| File | Location | Type | Status |
|------|------|------|------|
| PROJECT-NODE-NPM-PUBLISH | publish/npm/ | B | ✅ |

> **The location is the inclusion condition.** Files directly under a type folder are always copied when that type is selected, `server-deploy/` is copied only with `--deploy docker-ssh`, and `publish/<target>/` is copied only when that publish target is selected. **When you add a new server deployment workflow, always put it under `server-deploy/`.**

---

## 11. Writing a new workflow

### Step 1: Choose the type

1. No Secrets -> **Type A**
2. Has Secrets and simple environment variables -> **Type B**
3. CI (build verification) -> **Type C**
4. CD (deployment) -> **Type D**
5. Wizard integration or complex -> **Type E**

### Step 2: Apply the template

Start by copying the template for that type.

### Step 3: Checklist

- [ ] Uses the 67-character separator
- [ ] No mention of GITHUB_TOKEN
- [ ] Secrets in one-line format (`SECRET_NAME: description`)
- [ ] `(선택)` marked only on optional items
- [ ] Icons used for their intended purpose
- [ ] Environment variables in one-line format (no tables)

---

## 12. Related documents

- [CLAUDE.md](../../CLAUDE.md) - Overall project guide
- [version-control.md](./version-control.md) - Version control system
- [changelog-automation.md](./changelog-automation.md) - Changelog automation
