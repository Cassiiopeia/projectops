# GitHub Projects Sync Wizard 상세 가이드

GitHub Projects Status와 Issue Label 간 **양방향 실시간 동기화**를 설정하는 완전 가이드입니다.

---

## 목차

1. [개요](#개요)
2. [아키텍처](#아키텍처)
3. [마법사 사용법](#마법사-사용법-4단계-간소화)
4. [수동 설정 방법](#수동-설정-방법)
5. [트러블슈팅](#트러블슈팅)
6. [유지보수](#유지보수)
7. [FAQ](#faq)

---

## 개요

### 문제점

GitHub Actions는 `projects_v2_item` 이벤트를 트리거로 지원하지 않습니다.

```yaml
# ❌ 이 코드는 작동하지 않음
on:
  projects_v2_item:
    types: [edited]
```

이로 인해 Projects Board에서 Status를 변경해도 Issue Label이 자동으로 동기화되지 않습니다.

### 해결책

**Cloudflare Workers**를 사용하여 GitHub Organization Webhook을 직접 수신하고 처리합니다.

| 동기화 방향 | 담당 | 트리거 |
|------------|------|--------|
| Label → Status | GitHub Actions | Issue Label 변경 |
| Status → Label | Cloudflare Worker | Projects Status 변경 |

---

## 아키텍처

### 전체 흐름

```
┌─────────────────────────────────────────────────────────────────────┐
│                      GitHub Projects Board                          │
│                                                                     │
│   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌──────────┐   ┌───────┐│
│   │ 작업전  │ → │ 작업중  │ → │ 피드백  │ → │담당자확인│ → │작업완료││
│   └─────────┘   └─────────┘   └─────────┘   └──────────┘   └───────┘│
│                      │                                              │
│                      │ 카드 드래그 (Status 변경)                    │
└──────────────────────┼──────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  GitHub Organization Webhook                         │
│   Event: projects_v2_item                                            │
│   Action: edited                                                     │
└──────────────────────────────────────────────────────────────────────┘
                       │
                       │ HTTPS POST (with X-Hub-Signature-256)
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Cloudflare Worker (Edge)                          │
│                                                                      │
│   처리 순서:                                                          │
│   1. Webhook Secret 검증 (HMAC-SHA256)                               │
│   2. 이벤트 필터링 (projects_v2_item + edited만 처리)                │
│   3. GraphQL API로 현재 Status 조회                                  │
│   4. REST API로 Issue Label 동기화                                   │
└──────────────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         GitHub Issue                                 │
│   Labels: [enhancement] [작업 중] ← 자동으로 변경됨!                 │
└──────────────────────────────────────────────────────────────────────┘
```

### 양방향 동기화

```
┌─────────────┐                           ┌─────────────┐
│ Issue Label │ ◀───────────────────────▶ │  Projects   │
│             │       항상 동기화됨       │   Status    │
└──────┬──────┘                           └──────┬──────┘
       │                                         │
       │ Label 변경 시                           │ Status 변경 시
       ▼                                         ▼
┌─────────────┐                           ┌─────────────┐
│   GitHub    │                           │  Cloudflare │
│   Actions   │                           │   Worker    │
└─────────────┘                           └─────────────┘
```

---

## 마법사 사용법 (4단계 간소화)

### Step 1: 마법사에서 정보 입력

`.github/util/common/projects-sync-wizard/projects-sync-wizard.html` 파일을 브라우저에서 열고:

1. **GitHub Projects URL 입력:**
   ```
   https://github.com/orgs/YOUR-ORG/projects/1
   ```
   URL을 입력하면 Organization Name과 Project Number가 자동으로 추출됩니다.

2. **Worker 이름 설정** (기본값: `github-projects-sync-worker`)
   - 배포 시 이름이 충돌하면 스크립트에서 새 이름을 입력할 수 있습니다.

3. **Status Labels 확인/커스텀** (issue-labels.yml 기본값 제공)
   - 작업전, 작업중, 담당자확인, 피드백, 작업완료, 보류, 취소
   - **중요:** Label 이름은 GitHub Projects의 Status 컬럼 이름과 **정확히 일치**해야 합니다.

4. **Webhook Secret** (자동 생성)

5. **"Worker 파일 ZIP 다운로드"** 클릭

### Step 2: 스크립트 한 번 실행

```bash
# ZIP 압축 해제 후 폴더로 이동
cd github-projects-sync-worker

# Mac/Linux
./projects-sync-worker-setup.sh

# Windows PowerShell
.\projects-sync-worker-setup.ps1
```

스크립트가 자동으로 처리하는 작업:
1. npm 의존성 설치 (SSL 오류 자동 대응)
2. Cloudflare 로그인 (브라우저 자동 오픈)
3. Worker 배포 (이름 충돌 시 재입력 가능)
4. GITHUB_TOKEN 입력 받기
5. WEBHOOK_SECRET 자동 설정
6. Worker URL 출력

### Step 3: GitHub Webhook 수동 설정

1. Organization Settings → Webhooks 이동
   ```
   https://github.com/organizations/YOUR-ORG/settings/hooks
   ```
2. "Add webhook" 클릭
3. 설정 입력:
   - **Payload URL:** 스크립트에서 출력된 Worker URL
   - **Content type:** `application/json`
   - **Secret:** config.json의 webhookSecret 값
   - **Events:** "Let me select individual events" → "Project v2 items" 체크
4. "Add webhook" 클릭

### Step 4: 테스트

1. GitHub Projects Board에서 Issue 카드를 다른 Status 컬럼으로 이동
2. Issue 페이지에서 Label이 자동으로 변경되는지 확인
3. 문제 발생 시 Worker 로그 확인: `npx wrangler tail`

---

## 수동 설정 방법

마법사 없이 직접 설정하는 방법입니다.

### Cloudflare Worker 수동 설정

#### 1. wrangler.toml 생성

```toml
name = "github-projects-sync-worker"
main = "src/index.ts"
compatibility_date = "2024-01-01"

[vars]
PROJECT_NUMBER = "1"
STATUS_FIELD = "Status"
STATUS_LABELS = '["작업전","작업중","담당자확인","피드백","작업완료","보류","취소"]'
ORG_NAME = "YOUR-ORG"
```

#### 2. Secrets 설정

```bash
npx wrangler secret put GITHUB_TOKEN
# GitHub PAT 입력 (repo, project 권한)

npx wrangler secret put WEBHOOK_SECRET
# 임의의 비밀키 입력 (예: openssl rand -hex 32)
```

### GitHub Actions 워크플로우

`PROJECT-COMMON-PROJECTS-SYNC-MANAGER.yaml` 파일의 환경 변수를 수정합니다:

```yaml
env:
  STATUS_LABELS: '["작업전", "작업중", "담당자확인", "피드백", "작업완료", "보류", "취소"]'
  PROJECT_NUMBER: '1'
  ORG_NAME: 'YOUR-ORG'
```

---

## 트러블슈팅

### SSL 오류 (UNABLE_TO_GET_ISSUER_CERT_LOCALLY)

**원인:** 회사/학교 네트워크 프록시 또는 보안 소프트웨어

**해결:**

```bash
# npm install 시
npm config set strict-ssl false
npm install
npm config set strict-ssl true

# wrangler 명령어 시
export NODE_TLS_REJECT_UNAUTHORIZED=0  # Mac/Linux
$env:NODE_TLS_REJECT_UNAUTHORIZED=0    # Windows PowerShell
```

### Cloudflare 이메일 인증 오류

**에러:** `You need to verify your email address to use Workers. [code: 10034]`

**해결:**
1. [Cloudflare 대시보드](https://dash.cloudflare.com) 접속
2. 상단 이메일 인증 배너 확인
3. 이메일 확인하여 인증 링크 클릭

### 서브도메인 충돌

**에러:** `Subdomain is unavailable, please try a different subdomain`

**해결:** 다른 서브도메인 이름 사용 (예: `my-org-sync`, `project-sync` 등)

### Webhook 401 에러

**원인:** Webhook Secret 불일치

**해결:**
1. GitHub Webhook 설정에서 Secret 확인
2. Cloudflare Worker의 WEBHOOK_SECRET과 동일한지 확인
3. 불일치 시 둘 다 동일한 값으로 재설정

```bash
npx wrangler secret put WEBHOOK_SECRET
```

### Label이 동기화되지 않음

**체크리스트:**
1. Worker 로그 확인: `npx wrangler tail`
2. Webhook Delivery 확인: Organization Settings → Webhooks → Recent Deliveries
3. Issue가 해당 Project에 연결되어 있는지 확인
4. Label이 프로젝트의 Status 컬럼 이름과 정확히 일치하는지 확인

---

## 유지보수

### GitHub PAT 만료 시

```bash
cd github-projects-sync-worker
export NODE_TLS_REJECT_UNAUTHORIZED=0
npx wrangler secret put GITHUB_TOKEN
# 새 토큰 입력
```

### Status Label 추가/변경 시

1. `wrangler.toml`의 `STATUS_LABELS` 수정
2. Worker 재배포

```bash
npx wrangler deploy
```

3. GitHub Actions 워크플로우의 `STATUS_LABELS`도 동일하게 수정

### Worker 코드 업데이트

```bash
cd github-projects-sync-worker
export NODE_TLS_REJECT_UNAUTHORIZED=0
npx wrangler deploy
```

### Worker 로그 확인

```bash
npx wrangler tail
```

---

## FAQ

### Q: 비용이 드나요?

**A:** Cloudflare Workers Free Tier로 완전 무료입니다.
- 일일 요청 100,000건
- 일반적인 사용량은 100건 미만

### Q: Organization이 아닌 개인 저장소에서 사용할 수 있나요?

**A:** 아니요, GitHub Projects V2는 Organization 레벨에서만 Webhook을 지원합니다.
개인 저장소의 Projects는 이 방법으로 동기화할 수 없습니다.

### Q: 여러 프로젝트에서 사용할 수 있나요?

**A:** 프로젝트마다 별도의 Worker를 배포하거나, Worker 코드를 수정하여 여러 프로젝트를 처리하도록 확장할 수 있습니다.

### Q: 무한 루프가 발생하나요?

**A:** 아니요, Worker 코드에 무한 루프 방지 로직이 포함되어 있습니다.
이미 동일한 Label이 있으면 업데이트를 스킵합니다.

### Q: PR에도 적용되나요?

**A:** 네, Worker 코드는 Issue와 Pull Request 모두 지원합니다.

---

## 관련 파일

| 파일 | 설명 |
|------|------|
| `.github/util/common/projects-sync-wizard/` | 마법사 UI 폴더 |
| `.github/workflows/PROJECT-COMMON-PROJECTS-SYNC-MANAGER.yaml` | Label → Status 동기화 |

---

## 버전 히스토리

| 버전 | 날짜 | 변경사항 |
|------|------|---------|
| 2.0.0 | 2026-01-21 | 4단계 간소화, 원클릭 설치 스크립트 추가 |
| 1.0.0 | 2026-01-21 | 초기 릴리즈 |
