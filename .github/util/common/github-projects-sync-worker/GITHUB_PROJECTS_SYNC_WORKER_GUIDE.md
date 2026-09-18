# GitHub Projects Sync Worker 가이드

GitHub Projects의 Status 변경을 감지하여 Issue Label을 자동으로 동기화하는 Cloudflare Worker입니다.

---

## 📌 개요

```
Projects Board에서 카드 이동 (Status 변경)
          │
          ▼
GitHub Webhook (projects_v2_item)
          │
          ▼
Cloudflare Worker (이 모듈)
          │
          ▼
Issue Label 자동 업데이트
```

**기능**: Projects Status가 변경되면 Issue의 Label도 자동으로 동기화

---

## 🚀 빠른 시작

### 사전 요구사항

- Node.js (v18 이상 권장)
- Cloudflare 계정 (무료)
- GitHub Personal Access Token (repo, project 권한)

### 1단계: 의존성 설치

```bash
cd .github/util/common/github-projects-sync-worker
npm install
```

> **SSL 에러 발생 시**:
> ```bash
> npm config set strict-ssl false
> npm install
> npm config set strict-ssl true  # 설치 후 다시 활성화
> ```

### 2단계: Cloudflare 로그인

```bash
export NODE_TLS_REJECT_UNAUTHORIZED=0  # SSL 에러 방지
npx wrangler login
```

브라우저가 열리면 Cloudflare 계정으로 로그인하여 권한을 부여하세요.

### 3단계: Secret 설정

```bash
# GitHub Personal Access Token 설정
npx wrangler secret put GITHUB_TOKEN
# 프롬프트에 토큰 입력

# Webhook Secret 설정
npx wrangler secret put WEBHOOK_SECRET
# 프롬프트에 비밀키 입력 (GitHub Webhook에 설정할 값과 동일하게)
```

### 4단계: 배포

```bash
npx wrangler deploy
```

배포 완료 시 Worker URL이 표시됩니다:
```
https://github-projects-sync-worker.<your-subdomain>.workers.dev
```

### 5단계: GitHub Webhook 설정

1. GitHub Organization Settings → Webhooks 접속
2. **Add webhook** 클릭
3. 설정:
   - **Payload URL**: Worker URL 입력
   - **Content type**: `application/json`
   - **Secret**: Step 3에서 입력한 WEBHOOK_SECRET과 동일한 값
   - **Events**: "Let me select individual events" → `Project v2 items` 체크
4. **Add webhook** 클릭

---

## ⚙️ 설정 커스터마이징

### wrangler.toml 설정

```toml
[vars]
# Projects 번호 (URL에서 확인: /orgs/ORG_NAME/projects/NUMBER)
PROJECT_NUMBER = "6"

# Projects의 Status 필드명
STATUS_FIELD = "Status"

# 동기화할 Label 목록 (JSON 배열)
STATUS_LABELS = '["작업전","작업중","담당자확인","피드백","작업완료","보류","취소"]'

# Organization 이름
ORG_NAME = "your-org"
```

### 다른 프로젝트에 적용하기

1. `wrangler.toml`의 `[vars]` 섹션 수정
2. `name` 필드 변경 (다른 Worker 이름 사용 시)
3. 재배포: `npx wrangler deploy`

---

## 🔧 주요 명령어

| 명령어 | 설명 |
|--------|------|
| `npm install` | 의존성 설치 |
| `npx wrangler login` | Cloudflare 로그인 |
| `npx wrangler deploy` | Worker 배포 |
| `npx wrangler tail` | 실시간 로그 확인 |
| `npx wrangler secret put <NAME>` | Secret 설정 |
| `npx wrangler secret list` | Secret 목록 확인 |
| `npx wrangler dev` | 로컬 개발 서버 실행 |

---

## 📁 파일 구조

```
github-projects-sync-worker/
├── .gitignore              # Git 제외 파일 목록
├── package.json            # 의존성 정의
├── package-lock.json       # 의존성 잠금
├── tsconfig.json           # TypeScript 설정
├── wrangler.toml           # Cloudflare Worker 설정
├── GITHUB_PROJECTS_SYNC_WORKER_GUIDE.md  # 이 가이드
└── src/
    └── index.ts            # Worker 메인 코드
```

---

## 🔐 필요한 권한

### GitHub Personal Access Token

다음 권한이 필요합니다:
- `repo` - 리포지토리 접근
- `project` - Projects 접근 (읽기/쓰기)

토큰 생성: https://github.com/settings/tokens

### Cloudflare

무료 계정으로 충분합니다. 이메일 인증이 필요합니다.

---

## ⚠️ 트러블슈팅

### SSL 인증서 오류

**에러**: `UNABLE_TO_GET_ISSUER_CERT_LOCALLY`

**해결**:
```bash
# npm 설치 시
npm config set strict-ssl false
npm install
npm config set strict-ssl true

# wrangler 명령어 실행 시
export NODE_TLS_REJECT_UNAUTHORIZED=0
npx wrangler <command>
```

### Cloudflare 이메일 인증 필요

**에러**: `You need to verify your email address to use Workers. [code: 10034]`

**해결**: https://dash.cloudflare.com 접속 → 이메일 인증 완료

### Webhook 401 에러

**원인**: WEBHOOK_SECRET이 일치하지 않음

**해결**:
1. GitHub Webhook의 Secret 값 확인
2. Worker의 WEBHOOK_SECRET과 동일한지 확인
3. 다르면 재설정: `npx wrangler secret put WEBHOOK_SECRET`

### Worker가 동작하지 않음

1. **로그 확인**: `npx wrangler tail`
2. **Webhook 배달 확인**: GitHub Webhook → Recent Deliveries
3. **Content type 확인**: `application/json` 인지 확인
4. **Event 확인**: `Project v2 items`가 체크되어 있는지 확인

---

## 🧪 테스트 방법

### 1. Webhook 연결 테스트

GitHub Webhook 생성 시 자동으로 `ping` 이벤트가 전송됩니다.
Recent Deliveries에서 `200 OK` 응답 확인.

### 2. 실제 동작 테스트

1. `npx wrangler tail`로 로그 모니터링 시작
2. Projects Board에서 Issue 카드를 다른 Status 컬럼으로 이동
3. 로그에서 처리 과정 확인
4. Issue 페이지에서 Label 변경 확인

### 예상 로그

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔄 GitHub Projects Sync Worker
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Webhook signature verified
📌 Event type: projects_v2_item
📌 Action: edited
📌 Processing item: PVTI_xxx
📌 Issue: acme-org/acme-app#123
📌 Current Labels: enhancement, 작업전
📌 New Status: "작업중"
🗑️ Labels to remove: 작업전
  ✅ Label "작업전" 제거됨
➕ Adding label: "작업중"
  ✅ Label "작업중" 추가됨
🎉 Label sync completed!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 📊 비용

| 항목 | Cloudflare Free Tier |
|------|---------------------|
| 일일 요청 수 | 100,000건 |
| 요청당 CPU 시간 | 10ms |
| **월간 비용** | **무료** |

일반적인 사용량(하루 수십~수백 건)에서는 완전 무료입니다.

---

## 🔄 유지보수

### GitHub Token 갱신

토큰 만료 시:
```bash
npx wrangler secret put GITHUB_TOKEN
# 새 토큰 입력
```

### Status Label 변경

`wrangler.toml`의 `STATUS_LABELS` 수정 후:
```bash
npx wrangler deploy
```

### 코드 수정 후 배포

```bash
npx wrangler deploy
```

---

## 📚 관련 문서

- [Cloudflare Workers 문서](https://developers.cloudflare.com/workers/)
- [Wrangler CLI 문서](https://developers.cloudflare.com/workers/wrangler/)
- [GitHub Webhooks 문서](https://docs.github.com/en/webhooks)
- [GitHub Projects API](https://docs.github.com/en/graphql/reference/objects#projectv2item)

---

## 🏗️ 아키텍처

### 동작 원리

1. **Webhook 수신**: GitHub에서 `projects_v2_item` 이벤트 발생 시 Worker로 POST 요청
2. **보안 검증**: `X-Hub-Signature-256` 헤더로 HMAC-SHA256 서명 검증
3. **이벤트 필터링**: `edited` 액션만 처리 (Status 변경)
4. **GraphQL 조회**: Projects Item의 현재 Status와 Issue 정보 조회
5. **Label 동기화**: 기존 Status Label 제거 → 새 Status Label 추가
6. **무한 루프 방지**: 이미 동일한 Label이 있으면 스킵

### 보안

- **HMAC-SHA256**: Webhook 요청 진위 검증
- **Timing-safe comparison**: 타이밍 공격 방지
- **Secret 암호화**: Cloudflare에서 안전하게 저장

---

## 📝 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2026-01-20 | 1.0.0 | 초기 버전 |
