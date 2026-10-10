# 시작 전 — PAT · 자동 승인 · 앱 심사 · 브랜치/provider 판정과 config 기록

> 언제 읽나: [시작 전] §2~§5 값을 처음 정할 때, 사용자에게 브랜치·앱 심사 여부를 물어 config에 기록해야 할 때, "배포 브랜치 바꿔줘"/"릴리스 노트 방식 바꿔줘"/"확인받게 해줘" 같은 재설정 발화를 받았을 때.

**Config 파일 위치**: `~/.projectops/config/config.json` (글로벌 단일 파일). 상세 경로 규칙은 `../../references/config-rules.md §2~3`.

**config 갱신은 언제나** `../../references/config-rules.md §4` 규칙대로 전체 파일을 Read로 먼저 읽고 다른 섹션을 보존한 채 해당 키만 추가/수정해 Write한다. PAT · 다른 repos 항목 · 기존 `auto_approve`/`app_release`/브랜치 값을 절대 날리지 않는다. 항목에 `changelog_deploy` 객체가 없으면 새로 만든다.

**사용자에게 노출하는 안내는 자연어로만 한다.** "auto_approve", "config.json", "changelog_deploy 섹션" 같은 키 이름·파일 경로를 사용자 메시지에 절대 쓰지 않는다. 사용자는 "자동으로 진행" / "매번 확인" 같은 자연어로 의사 표시하며 agent가 config를 직접 갱신한다.

## §2 PAT 추출 — agent가 `Read` 도구로 직접 읽는다 (bash Python 추출 금지)

> Windows Git Bash의 `$HOME`은 `/c/Users/...` (POSIX 경로)라 네이티브 Windows Python `open()`이 파일을 못 연다 → PAT 추출 실패(NO_PAT). 실측 검증된 버그다. 그래서 **agent가 `Read` 도구로 config 파일을 직접 읽어** PAT를 얻는다 — OS·셸 보간 무관하게 항상 동작한다.

1. `Read` 도구로 config 파일을 읽는다. **이 고정 경로 한 곳만 본다 — `ls`·glob으로 탐색하거나 플러그인 캐시(`~/.claude/plugins/cache/...`, 스크립트 전용)를 뒤지지 마라. config는 캐시 안에 없다.**
   - Windows: `C:\Users\<사용자>\.projectops\config\config.json`
   - macOS/Linux: `~/.projectops/config/config.json`
   - 파일이 없으면 → "❌ PAT 없음. `/pro-github`로 config(PAT)를 먼저 등록하세요." 안내 후 종료.
2. `github` 섹션에서 PAT 선택:
   - `repos[]` 중 `repo == REPO` 이고 `pat`이 non-null이면 그 값
   - 아니면 `global_pat`
   - 둘 다 없으면 → 위와 동일 안내 후 종료.
3. PAT 값을 **기억**한다. (PAT는 `ghp_`+영숫자라 따옴표 이스케이프 불필요.)

## §3 자동 승인 모드 — `changelog_deploy.auto_approve`

§2에서 읽은 같은 내용에서 결정한다. 먼저 발견되는 값 채택:

1. `github.repos[]` 중 `owner == OWNER && repo == REPO`인 항목의 `changelog_deploy.auto_approve`
2. `github.changelog_deploy.auto_approve` (글로벌 기본값)
3. 어디에도 없으면 `false` (안전 default — 수동 승인)

> **이전 키 `auto_approve_release_notes`는 명시적 break**. 더 이상 인식하지 않으며 config에 남아 있어도 무시한다. 자동 모드를 원하면 1회 토글 발화로 `auto_approve: true`를 새로 저장한다.

기억할 값: `AUTO_APPROVE`(boolean), `CONFIG_HAS_KEY`(1 또는 2에서 키 발견이면 `true`, 아니면 첫 실행 `false`). `CONFIG_HAS_KEY=false`는 deploy 5.5단계 / fix 4.5단계의 **첫 실행 자동화 제안(C)** 트리거다.

**토글 발화 처리**
- 자동 모드 안내를 본 사용자가 "확인받게 해줘", "수동으로 바꿔줘", "다음부턴 확인받아줘"라고 하면 PR 생성 **전에** 갱신한다: 우선순위 1(레포별)에 키가 있었다면 그 값을 `false`로, 없었다면 우선순위 2(글로벌)를 `false`로. 갱신 후 본문은 그대로 두고 다시 사용자 승인을 받는다(수동 분기로 전환).
- 첫 실행 자동화 제안(C) 응답: **1** → `github.repos[]` 현 OWNER/REPO 항목에 `changelog_deploy.auto_approve: true` / **2** → `github.changelog_deploy.auto_approve: true`(객체가 없으면 생성) / **3** → `github.changelog_deploy.auto_approve: false`(다음 실행부터 묻지 않도록 키 자체는 남긴다).

## §4 앱 심사 인지 — `changelog_deploy.app_release`

§2에서 읽은 같은 내용에서 현 OWNER/REPO 항목의 값을 결정한다:

1. `github.repos[]` 중 `owner == OWNER && repo == REPO`인 항목의 `changelog_deploy.app_release`
2. 어디에도 없으면 **키 없음** (첫 실행 — 1.5단계에서 감지 후 한 번 확인)

기억할 값: `APP_RELEASE` — `true` / `false` / `unset`. 1.5단계와 5.5단계 심사 경고 배너에서 쓴다.

> 글로벌 기본값(`github.changelog_deploy.app_release`)은 두지 않는다 — 앱 심사 여부는 레포마다 다르므로 **레포별로만** 기억한다.

1.5단계 확인 응답: **1(앱 심사 맞음)** → 현 OWNER/REPO 항목 `changelog_deploy`에 `app_release: true`, 이번 배포부터 심사 경고 배너 적용 / **2(일반 배포)** → `app_release: false`, 경고 없이 진행하고 다음부터 묻지 않음.

## §5 릴리스 브랜치 · provider 판정

**사용자는 config를 직접 손대지 않는다 — 값이 없어 애매할 때만 자연어로 묻고, 답을 config에 기록한다.** 판정 가능하면 묻지 않고, 한 번 물어 기록하면 재질문하지 않는다.

**우선순위 (먼저 발견되는 값 채택):**

1. `github.repos[]` 중 현 OWNER/REPO 항목의 `changelog_deploy.{head_branch, base_branch, provider}`
2. `github.changelog_deploy.{head_branch, base_branch, provider}` (글로벌)
3. **최초 판정** — 1·2에 값이 없으면 `detect-release-context`(version.yml 폴백)로 자동 추론하고, 애매하면 사용자에게 물은 뒤 config에 기록

1 또는 2에서 세 값을 모두 얻었으면 그대로 쓰고 **묻지 않는다**. 기억할 값:

- `HEAD_BRANCH` — 릴리스 PR head(소스). 폴백 `develop`.
- `BASE_BRANCH` — 릴리스 PR base(프로덕션). 폴백 `main`.
- `PROVIDER` — `commit`|`copilot`|`openai`|`gemini`|`claude`|`groq`|`mistral`|`ollama`|`coderabbit`. 미설정 시 `.coderabbit.yaml` 있으면 `coderabbit`, 없으면 `commit`. (`github-ai`는 종료됨 → `commit`으로 취급)
- `BRANCH_CONFIG_HAS_KEY` — 우선순위 1·2에서 세 값을 모두 찾았으면 `true`, 아니면 `false`(최초 판정).

### 최초 판정 (`BRANCH_CONFIG_HAS_KEY == false`일 때만)

`detect-release-context`의 `branches.{head,base,provider}`를 초기 후보로 삼는다 (SKILL.md "스크립트 찾기" 블록 끝에서 이미 호출).

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/changelog_cli.py detect-release-context --project-root "{PROJECT_ROOT}"
```

**브랜치 확정:**
- version.yml에서 `deploy_branch`/`default_branch`를 읽었으면(폴백이 아닌 실제 값) 그대로 확정.
- 폴백(develop/main)이고 실제 원격에 `develop`이 있으며 default가 `main`이면 → 표준 구조로 조용히 확정.
- 그 외(develop 없음/default가 main 아님 등 애매) → 자연어로 묻고 응답에서 head/base를 확정:
  ```
  이 저장소의 릴리스는 어느 브랜치에서 어느 브랜치로 진행하나요?
  (예: 개발 브랜치에서 배포 브랜치로)
  1. develop → main (표준)
  2. 직접 알려주기 (예: "release 브랜치에서 production 브랜치로")
  ```

**provider 확정 (묻지 않는다):**
- `branches.provider`를 그대로 확정한다. CLI가 이미 3단 규칙을 적용했다: ① version.yml `changelog.provider` 명시 → 그 값 ② 미설정 + 레포 루트 `.coderabbit.yaml` 존재 → `coderabbit` (CodeRabbit 사용 레포의 기존 동작 보존) ③ 둘 다 없음 → `commit`.
- 워크플로우도 같은 규칙으로 판정하므로 스킬과 워크플로우의 판단이 갈리지 않는다. 규칙을 바꾸면 두 곳(`changelog_cli.py` `_read_release_branches`, 워크플로우 "버전 정보 확인" 스텝)을 함께 고친다.
- `github-ai`가 저장돼 있던 레포도 CLI가 `commit`으로 돌려주므로 따로 처리하지 않는다.

**config 기록:** 확정한 `head_branch`/`base_branch`/`provider`를, `github.repos[]`에 현 OWNER/REPO 매칭 항목이 있으면 그 항목의 `changelog_deploy`에, 없으면 `github.changelog_deploy`(글로벌)에 Write한다.

기록 후 자연어로만 안내(키·경로 노출 금지):
```
✅ 이 저장소 릴리스 방식을 기억했습니다 ({HEAD_BRANCH} → {BASE_BRANCH}, {provider 자연어}).
   바꾸고 싶으면 "배포 브랜치 바꿔줘" 또는 "릴리스 노트 방식 바꿔줘"라고 말씀해주세요.
```
(provider 자연어: commit→"커밋 분석(AI 키가 있으면 AI)", copilot→"Copilot 생성", openai/gemini/claude/groq/mistral/ollama→"AI 생성", coderabbit→"CodeRabbit 요약 존중, 없으면 커밋 분석")

> **재설정 발화 처리**: 이후 "배포 브랜치 바꿔줘"/"릴리스 노트 방식 바꿔줘"라고 하면 위 질문을 다시 하고 config의 해당 키를 갱신한다.

### provider 값 참고

- 값: `commit`(기본) / `copilot` / `openai`·`gemini`·`claude`·`groq`·`mistral`·`ollama` / `coderabbit`.
- `github-ai`는 **서비스 종료(2026-07-30)** — 저장값이 남아 있어도 CLI가 `commit`으로 돌려준다(업데이트 시 `commit`으로 이전).
- 워크플로우 사다리: ① PR 본문에 릴리스 노트가 있으면 그대로 → ② 지정 provider(또는 AI 키가 있으면 AI) → ③ commit(항상 완주). `coderabbit`은 기다리지 않고 ①에서 존중될 뿐이다.
