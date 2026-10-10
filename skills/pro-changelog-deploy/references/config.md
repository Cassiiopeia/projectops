# 시작 전 — PAT · 자동 승인 · 앱 심사 · 브랜치/provider 판정과 config 기록

> 언제 읽나: [시작 전] §2~§5 값을 처음 정할 때, 사용자에게 브랜치(version.yml 없는 레포만)·앱 심사 여부를 물어 config에 기록해야 할 때, `detect-release-context`가 `conflict`를 냈을 때, "배포 브랜치 바꿔줘"/"릴리스 노트 방식 바꿔줘"/"확인받게 해줘" 같은 재설정 발화를 받았을 때.

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

**정본은 `detect-release-context`(version.yml)다 (#842).** 워크플로우(RELEASE-CHANGELOG)도 version.yml을 읽으므로, 스킬이 같은 곳을 봐야 판단이 갈리지 않는다. config는 version.yml이 **없는** 레포의 레포별 기록일 뿐이다.

**우선순위:**

| 순위 | 출처 | 언제 | `branches_source` |
|---|---|---|---|
| 1 | version.yml (`deploy_branch`·`default_branch`·`changelog.provider`, 폴백 포함) | version.yml이 있으면 **항상** | `version.yml` |
| 2 | `github.repos[]` 현 OWNER/REPO 항목의 `changelog_deploy.{head_branch, base_branch, provider}` | version.yml이 **없을 때만** | `config` |
| 3 | 폴백 `develop` → `main`, provider 3단 규칙 | 1·2 모두 없을 때 → 최초 판정 후 2에 기록 | `fallback` |

> **전역 `github.changelog_deploy.{head_branch, base_branch, provider}`는 읽지 않는다.** 레포 지식을 컴퓨터 전체에 두면 다른 레포의 version.yml을 덮어쓴다(#842 실사고 — 전역 `develop/main/commit`이 레포마다 다른 설정을 무시). 남아 있으면 CLI가 `config.ignored_global_keys`로 알려줄 뿐 값은 쓰지 않는다. **새로 쓰지도 않는다.** 같은 객체의 `auto_approve`는 그대로 전역 기본값으로 쓴다(§3).

판정은 CLI가 한다 — agent가 config의 브랜치 키를 따로 읽어 우선순위를 다시 계산하지 않는다. CLI는 PAT 자동 로드와 같은 방식으로 config를 **읽기만** 한다 (`../../references/config-rules.md §3`).

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/changelog_cli.py detect-release-context --project-root "{PROJECT_ROOT}"
# owner/repo는 origin URL에서, config는 고정 경로에서 자동으로 찾는다. 필요하면 --owner · --repo · --config 로 지정.
```

출력에서 기억할 값:

- `HEAD_BRANCH` = `branches.head`, `BASE_BRANCH` = `branches.base`, `PROVIDER` = `branches.provider`
  (`commit`|`copilot`|`openai`|`gemini`|`claude`|`groq`|`mistral`|`ollama`|`coderabbit`. `github-ai`는 CLI가 `commit`으로 돌려준다)
- `BRANCH_SOURCE` = `branches_source` (`version.yml` | `config` | `fallback`)
- `conflict` — version.yml 값과 레포별 config 값이 다른 키 목록 (`key`·`version_yml`·`config`·`version_yml_explicit`)

### `conflict`가 비어 있지 않을 때

**version.yml 값으로 진행한다.** 레포별 config 값은 version.yml이 생기기 전·바뀌기 전의 낡은 기록이다. 사용자에게 자연어로 한 줄만 알린다 (키·경로 노출 금지):

```
ℹ️ 예전에 기억해 둔 릴리스 방식({config 값})과 저장소 설정({version.yml 값})이 달라 저장소 설정을 따릅니다.
```

- `version_yml_explicit == false`면 version.yml에 그 키가 적혀 있지 않아 폴백값과 비교한 것이다. 이때는 위 안내 끝에 "저장소 설정에 값을 적어 두면 헷갈리지 않습니다"를 덧붙인다.
- config를 자동으로 고치지 않는다. 사용자가 정리를 원하면 그 레포 항목의 해당 키만 지운다(§4 config 갱신 규칙).

### 최초 판정 (`BRANCH_SOURCE == fallback`이고 version.yml이 없을 때만)

version.yml이 있으면(폴백값이어도) 여기로 오지 않는다 — 정본이 있으므로 묻지도 기록하지도 않는다.

**브랜치 확정:**
- 실제 원격에 `develop`이 있고 default가 `main`이면 → 표준 구조로 조용히 확정.
- 그 외(develop 없음/default가 main 아님 등 애매) → 자연어로 묻고 응답에서 head/base를 확정:
  ```
  이 저장소의 릴리스는 어느 브랜치에서 어느 브랜치로 진행하나요?
  (예: 개발 브랜치에서 배포 브랜치로)
  1. develop → main (표준)
  2. 직접 알려주기 (예: "release 브랜치에서 production 브랜치로")
  ```

**provider 확정 (묻지 않는다):**
- `branches.provider`를 그대로 확정한다. CLI가 이미 3단 규칙을 적용했다: ① version.yml `changelog.provider` 명시 → 그 값 ② 미설정 + 레포 루트 `.coderabbit.yaml` 존재 → `coderabbit` (CodeRabbit 사용 레포의 기존 동작 보존) ③ 둘 다 없음 → `commit`.
- 워크플로우도 같은 규칙으로 판정하므로 스킬과 워크플로우의 판단이 갈리지 않는다. 규칙을 바꾸면 두 곳(`changelog_cli.py` `_normalize_provider`, 워크플로우 "버전 정보 확인" 스텝)을 함께 고친다.

**config 기록:** 확정한 `head_branch`/`base_branch`/`provider`를 `github.repos[]`의 현 OWNER/REPO 항목 `changelog_deploy`에 Write한다. 항목이 없으면 항목을 새로 만든다(`owner`·`repo`·`name`, `pat: null`). **전역 `github.changelog_deploy`에는 쓰지 않는다.**

기록 후 자연어로만 안내(키·경로 노출 금지):
```
✅ 이 저장소 릴리스 방식을 기억했습니다 ({HEAD_BRANCH} → {BASE_BRANCH}, {provider 자연어}).
   바꾸고 싶으면 "배포 브랜치 바꿔줘" 또는 "릴리스 노트 방식 바꿔줘"라고 말씀해주세요.
```
(provider 자연어: commit→"커밋 분석(AI 키가 있으면 AI)", copilot→"Copilot 생성", openai/gemini/claude/groq/mistral/ollama→"AI 생성", coderabbit→"CodeRabbit 요약 존중, 없으면 커밋 분석")

> **재설정 발화 처리**: "배포 브랜치 바꿔줘"/"릴리스 노트 방식 바꿔줘"라고 하면
> - version.yml이 있는 레포 → config에 쓰지 않는다. 저장소 설정(version.yml `deploy_branch`·`default_branch`·`changelog.provider`)을 바꿔야 워크플로우도 같이 바뀐다고 자연어로 안내하고, 원하면 그 파일을 고친다.
> - version.yml이 없는 레포 → 위 질문을 다시 하고 레포별 config의 해당 키를 갱신한다.

### provider 값 참고

- 값: `commit`(기본) / `copilot` / `openai`·`gemini`·`claude`·`groq`·`mistral`·`ollama` / `coderabbit`.
- `github-ai`는 **서비스 종료(2026-07-30)** — 저장값이 남아 있어도 CLI가 `commit`으로 돌려준다(업데이트 시 `commit`으로 이전).
- 워크플로우 사다리: ① PR 본문에 릴리스 노트가 있으면 그대로 → ② 지정 provider(또는 AI 키가 있으면 AI) → ③ commit(항상 완주). `coderabbit`은 기다리지 않고 ①에서 존중될 뿐이다.
