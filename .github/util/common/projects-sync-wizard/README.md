# GitHub Projects Sync Wizard

GitHub Projects Status와 Issue Label 간 **양방향 실시간 동기화**를 위한 Cloudflare Worker 설정 마법사입니다.

## 문제점

GitHub Actions는 `projects_v2_item` 이벤트를 트리거로 지원하지 않습니다. 이로 인해 Projects Board에서 Status를 변경해도 Issue Label이 자동으로 동기화되지 않습니다.

## 해결책

**Cloudflare Workers**를 사용하여 GitHub Organization Webhook을 받아 실시간으로 Label을 동기화합니다.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    양방향 동기화 시스템                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌─────────────┐                           ┌─────────────┐         │
│   │ Issue Label │ ◀───────────────────────▶ │  Projects   │         │
│   │             │       항상 동기화됨       │   Status    │         │
│   └──────┬──────┘                           └──────┬──────┘         │
│          │                                         │                │
│          │ Label 변경 시                           │ Status 변경 시 │
│          ▼                                         ▼                │
│   ┌─────────────┐                           ┌─────────────┐         │
│   │   GitHub    │                           │  Cloudflare │         │
│   │   Actions   │                           │   Worker    │         │
│   └─────────────┘                           └─────────────┘         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## 사용 방법 (4단계)

### Step 1: 마법사에서 정보 입력

`projects-sync-wizard.html` 파일을 브라우저에서 열고:
- GitHub Projects URL 입력 (Organization 자동 파싱)
- Worker 이름 설정 (기본값: `github-projects-sync-worker`)
- Status Labels 확인/커스텀 (issue-label.yml 기본값 제공)
- **ZIP 다운로드** 클릭

### Step 2: 스크립트 한 번 실행

```bash
# ZIP 압축 해제 후
cd github-projects-sync-worker

# Mac/Linux
./projects-sync-worker-setup.sh

# Windows PowerShell
.\projects-sync-worker-setup.ps1
```

스크립트가 자동으로:
1. npm 의존성 설치 (SSL 오류 자동 대응)
2. Cloudflare 로그인 (브라우저 자동 오픈)
3. Worker 배포 (이름 충돌 시 재입력 가능)
4. GITHUB_TOKEN, WEBHOOK_SECRET 설정

### Step 3: GitHub Webhook 수동 설정

1. Organization Settings → Webhooks 이동
2. "Add webhook" 클릭
3. 설정 입력:
   - **Payload URL:** 스크립트에서 출력된 Worker URL
   - **Content type:** `application/json`
   - **Secret:** config.json의 webhookSecret 값
   - **Events:** "Project v2 items" 선택

### Step 4: 테스트

- Projects Board에서 Issue 카드 이동
- Issue Label 자동 변경 확인

## 필요한 Secrets

| Secret | 설명 |
|--------|------|
| `GITHUB_TOKEN` | GitHub PAT (repo, project 권한) |
| `WEBHOOK_SECRET` | Webhook 검증용 비밀키 (마법사에서 자동 생성) |

## 요구사항

- Node.js 18.0.0 이상
- Cloudflare 계정 (무료 티어 가능)
- GitHub Organization (Projects V2)

## 파일 구조

```
projects-sync-wizard/
├── version.json                     # 버전 정보
├── version-sync.sh                  # HTML 버전 동기화
├── projects-sync-wizard.html        # 마법사 UI (4단계)
├── projects-sync-wizard.js          # 클라이언트 로직
├── projects-sync-worker-setup.sh    # 원클릭 설치 스크립트 (Mac/Linux)
├── projects-sync-worker-setup.ps1   # 원클릭 설치 스크립트 (Windows)
├── README.md                        # 이 문서
└── templates/
    ├── wrangler.toml.template       # Cloudflare 설정 템플릿
    ├── package.json.template        # npm 패키지 템플릿
    ├── tsconfig.json.template       # TypeScript 설정 템플릿
    └── src/
        └── index.ts.template        # Worker 코드 템플릿
```

## ZIP 다운로드 내용

```
github-projects-sync-worker/
├── wrangler.toml                    # 설정값 적용됨
├── package.json
├── tsconfig.json
├── src/index.ts
├── config.json                      # Webhook Secret 등 설정 저장
├── projects-sync-worker-setup.sh    # Mac/Linux
├── projects-sync-worker-setup.ps1   # Windows
└── README.md
```

## 비용

Cloudflare Workers Free Tier로 **완전 무료** 운영 가능합니다.

| 항목 | Free Tier | 예상 사용량 |
|------|-----------|-------------|
| 일일 요청 수 | 100,000건 | ~100건 |
| 요청당 CPU 시간 | 10ms | ~5ms |

## 트러블슈팅

### Worker 이름 충돌

스크립트 실행 중 이름이 충돌하면 새 이름을 입력하라는 프롬프트가 표시됩니다.

### SSL 오류 (수동 설치 시)

```bash
# npm install 시
npm config set strict-ssl false
npm install
npm config set strict-ssl true

# wrangler login 시
export NODE_TLS_REJECT_UNAUTHORIZED=0  # Mac/Linux
$env:NODE_TLS_REJECT_UNAUTHORIZED=0    # Windows PowerShell
npx wrangler login
```

### Webhook 401 에러

- GitHub Webhook Secret과 Worker의 WEBHOOK_SECRET이 동일한지 확인
- config.json에서 webhookSecret 값 확인

## 관련 문서

- [GITHUB-PROJECTS-SYNC-WIZARD.md](../../../../docs/GITHUB-PROJECTS-SYNC-WIZARD.md) - 상세 가이드
- [PROJECT-COMMON-PROJECTS-SYNC-MANAGER.yaml](../../../workflows/PROJECT-COMMON-PROJECTS-SYNC-MANAGER.yaml) - Label → Status 동기화

## 버전 히스토리

- **v2.0.0** (2026-01-21): 4단계 간소화, 원클릭 설치 스크립트 추가
- **v1.0.0** (2026-01-21): 초기 릴리즈
