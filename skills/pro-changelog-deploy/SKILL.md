---
name: pro-changelog-deploy
description: "develop 브랜치를 push하고 main으로 릴리스 PR(deploy PR)을 생성한 뒤 즉시 릴리스 노트를 작성해 RELEASE-CHANGELOG 워크플로우가 CodeRabbit 10분 대기 없이 automerge를 진행하게 한다. automerge 실패 시 기존 PR을 닫고 새 PR을 열어 재트리거하는 fix 기능도 포함. 앱스토어/플레이스토어 심사로 직결되는 레포(앱 심사 인지)는 릴리스 노트에 심사 경고 배너를 띄우고 정제를 더 엄격히 적용한다. 'deploy해줘', '배포해줘', 'deploy PR 올려줘', 'changelogfix', 'deploy 머지 안 됐어', 'PR 다시 열어줘' 등의 요청 시 사용."
---

# Changelog Deploy Mode

> **⚠️ 모델 권고**: 이 스킬은 릴리스 노트 작성이 주 작업이다. **lite(haiku) 모델로 실행을 권장**한다. 커밋 분석과 자연어 재작성만 하면 되므로 강력한 모델이 불필요하다.

projectops 전용 스킬. `PROJECT-COMMON-RELEASE-CHANGELOG` (develop→main 릴리스 PR 감지 → CodeRabbit 대기 → 버전 확정 → CHANGELOG 업데이트 → automerge) 워크플로우와 연동.

develop 브랜치 push → main으로 릴리스 PR 생성 → 릴리스 노트 즉시 작성 → automerge 자동 진행.
automerge 실패 시 기존 PR 닫고 새 PR 재생성 → 릴리스 노트 재작성.

`CodeRabbit` (AI PR 리뷰 봇) 10분 대기 없이 스킬이 직접 릴리스 노트를 작성하므로,
워크플로우 폴링 중 `Summary by CodeRabbit`을 감지하면 즉시 automerge가 진행된다.

## 이때는 쓰지 마라

- 배포가 아닌 일반 커밋/PR 작업
- `develop` 브랜치가 없는 프로젝트 (이 스킬은 develop → main 릴리스 PR 구조 전용)
- `PROJECT-COMMON-RELEASE-CHANGELOG` 워크플로우가 설정되지 않은 저장소

## 핵심 원칙

- `git push --force`는 절대 실행하지 않는다
- **사용자 확인 없이 PR을 닫거나 열지 않는다** (fix 모드)
- **릴리스 노트 본문은 PR 생성 전 사용자에게 보여준다** (deploy 5.5단계 / fix 4.5단계). 자동 모드로 명시 설정된 경우만 표시 후 즉시 진행
- **사용자에게 config 키 이름·파일 경로를 노출하지 않는다**. 자동/수동 모드 토글은 자연어 응답을 받아 agent가 직접 갱신한다
- **브랜치를 하드코딩하지 않는다 (#456)**. 릴리스 head/base 브랜치와 changelog provider는 **config(우선) → version.yml(폴백)에서 읽는다** — [시작 전 §5] 참조. `develop`/`main`/`coderabbit`은 값을 못 읽었을 때의 폴백일 뿐, 다른 브랜치·provider 구조를 쓰는 레포에서는 확정값을 따른다.
- **사용자는 config를 직접 수정하지 않는다**. 브랜치·provider·자동모드 등 모든 설정은 skill이 자연어로 묻고 답을 config에 기록한다. 판정 가능하면 묻지 않고, 애매할 때만 묻는다. 한 번 물어 기록하면 재질문하지 않는다.

## 브랜치·provider 해석 (#456 — 하드코딩 금지)

deploy PR을 만들기 전에 `detect-release-context`로 릴리스 브랜치·provider를 먼저 읽는다.
출력 JSON의 `branches`가 SSOT다:

```bash
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
SKILL=pro-changelog-deploy; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPTS/changelog_cli.py" detect-release-context --project-root "$(git rev-parse --show-toplevel)"
```

- `branches.head` = 릴리스 PR의 head 브랜치(= `metadata.deploy_branch`, 폴백 `develop`). push·PR 생성의 소스.
- `branches.base` = 릴리스 PR의 base 브랜치(= `metadata.default_branch`, 폴백 `main`). 프로덕션.
- `branches.provider` = changelog 생성기(`commit`/`github-ai`/`coderabbit` 등, 폴백 `coderabbit`).
  - `provider == "commit"`이면 워크플로우가 커밋 분석으로 릴리스 노트를 즉시 만든다 → 스킬은 예쁜 노트를 선제 작성할지 사용자에게 물어보고, 원치 않으면 워크플로우에 맡긴다.
  - `coderabbit`/`github-ai`/`openai`이면 기존처럼 스킬이 릴리스 노트를 선제 작성해 CodeRabbit/AI 대기를 우회한다.

아래 절차에서 `develop`/`main`이 나오면 이 `branches.head`/`branches.base`로 치환해 사용한다.

## 시작 전

**Config 파일 위치**: `~/.projectops/config/config.json` (글로벌 단일 파일)

상세 경로 규칙: `../references/config-rules.md §2~3` 참조.

> **⚠️ 실행 모델 (반드시 숙지)**: Claude Code의 Bash 도구는 **stateless**다 — 변수·`export`가 호출 간 유지되지 **않는다**.
> 한 Bash 호출에서 `export GITHUB_PAT=...` 해도 다음 Bash 호출에선 빈값이다.
> 따라서 이 스킬은 PAT·OWNER·REPO·PYTHON·PROJECT_ROOT 5개 값을 **agent가 아래에서 한 번 알아내 기억해 두고, 이 값들이 필요한 모든 Bash 블록 맨 앞에 실제 값으로 인라인 prefix(`VAR="값" ...`)** 한다. 셸 변수 재사용에 의존하지 않는다.

### 1) OWNER · REPO · PYTHON · PROJECT_ROOT 알아내기 (bash)

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(
  for _py in python3 python; do
    _path=$(command -v "$_py" 2>/dev/null) || continue
    "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break
  done
)
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
OWNER=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/]([^/]+)/.*|\1|')
REPO=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/][^/]+/([^/.]+)(\.git)?$|\1|')
echo "PROJECT_ROOT=$PROJECT_ROOT"; echo "PYTHON=$PYTHON"; echo "OWNER=$OWNER"; echo "REPO=$REPO"
```

출력된 4개 값을 **그대로 기억**한다 (이후 모든 Bash 블록의 placeholder를 이 실제 값으로 치환). `PYTHON`이 비면 "❌ Python을 찾을 수 없습니다." 안내 후 종료.

### 2) PAT 추출 — **agent가 `Read` 도구로 직접 읽는다 (bash Python 추출 금지)**

> **중요**: PAT 추출은 bash 인라인 Python으로 하지 않는다.
> Windows Git Bash의 `$HOME`은 `/c/Users/...` (POSIX 경로)라 네이티브 Windows Python `open()`이 파일을 못 연다 → PAT 추출 실패(NO_PAT). 실측 검증된 버그다.
> 따라서 **agent가 `Read` 도구로 config 파일을 직접 읽어** PAT를 얻는다 — OS·셸 보간 무관하게 항상 동작한다.

1. `Read` 도구로 config 파일을 읽는다. **이 고정 경로 한 곳만 본다 — `ls`·glob으로 탐색하거나 플러그인 캐시(`~/.claude/plugins/cache/...`, 스크립트 전용)를 뒤지지 마라. config는 캐시 안에 없다.**
   - Windows: `C:\Users\<사용자>\.projectops\config\config.json`
   - macOS/Linux: `~/.projectops/config/config.json`
   - 파일이 없으면 → "❌ PAT 없음. `/pro-github`로 config(PAT)를 먼저 등록하세요." 안내 후 종료.
2. `github` 섹션에서 PAT 선택:
   - `repos[]` 중 `repo == 위에서 구한 REPO` 이고 `pat`이 non-null이면 그 값 사용
   - 아니면 `global_pat` 사용
   - 둘 다 없으면 → 위와 동일 안내 후 종료.
3. 추출한 PAT 값을 **기억**한다. (PAT는 `ghp_`+영숫자라 따옴표 이스케이프 불필요.)

> **이후 모든 Bash 블록의 사용 규칙**: PAT/OWNER/REPO/PYTHON/PROJECT_ROOT가 등장하는 블록은 **그 블록 맨 앞에 실제 값을 인라인 prefix**로 붙인다. 예:
> ```bash
> GITHUB_PAT="{PAT}" OWNER="Cassiiopeia" REPO="projectops" \
> PYTHON="/c/Users/USER/.../python" PROJECT_ROOT="/d/0-suh/.../projectops" \
>   bash -c '...아래 블록 내용...'
> ```
> 또는 더 간단히, 블록 첫 줄에서 `GITHUB_PAT="..."; OWNER="..."; REPO="..."; PYTHON="..."; PROJECT_ROOT="..."` 로 재선언한 뒤 나머지를 실행한다. **핵심은 "이전 Bash 호출의 변수가 살아있다"고 가정하지 않는 것.**

### 3) 자동 승인 모드 판정 — Read 도구로 config에서 직접 추출

§2에서 이미 읽은 `config.json`의 동일 내용에서 `changelog_deploy.auto_approve` 값을 결정한다.

해석 우선순위 (위→아래로 검사, 먼저 발견되는 값 채택):

1. `github.repos[]` 중 `owner == 위 OWNER && repo == 위 REPO`인 항목의 `changelog_deploy.auto_approve`
2. `github.changelog_deploy.auto_approve` (글로벌 기본값)
3. 어디에도 없으면 `false` (안전 default — 수동 승인)

> **이전 키 `auto_approve_release_notes`는 명시적 break**. 더 이상 인식하지 않으며 config에 남아 있어도 무시한다. 자동 모드를 원하면 1회 토글 발화로 `auto_approve: true`를 새로 저장한다.

판정 결과를 두 값으로 **기억**한다:

- `AUTO_APPROVE` — boolean (`true` / `false`)
- `CONFIG_HAS_KEY` — boolean (`true`면 위 우선순위 1 또는 2에서 키 발견. `false`면 둘 다 없어 첫 실행 케이스)

`CONFIG_HAS_KEY=false`인 경우는 deploy 5.5단계 / fix 4.5단계의 **첫 실행 안내 분기** 트리거로 사용한다.

> **사용자에게 노출하는 안내는 자연어로만 한다.** "auto_approve", "config.json", "changelog_deploy 섹션" 같은 키 이름·파일 경로를 사용자 메시지에 절대 쓰지 않는다. 사용자는 "자동으로 진행" / "매번 확인" 같은 자연어로 의사 표시하며 agent가 config를 직접 갱신한다.

### 4) 앱 심사 인지 값 판정 — 같은 config에서 `app_release` 추출

§2에서 이미 읽은 `config.json`에서 현 OWNER/REPO 항목의 `changelog_deploy.app_release` 값을 결정한다.

해석 우선순위:

1. `github.repos[]` 중 `owner == 위 OWNER && repo == 위 REPO`인 항목의 `changelog_deploy.app_release`
2. 어디에도 없으면 **키 없음** (첫 실행 케이스 — 1.5단계에서 감지 후 한 번 확인)

판정 결과를 두 값으로 **기억**한다:

- `APP_RELEASE` — `true` / `false` / `unset`(키 없음)
- 이 값은 [1.5단계: 릴리스 컨텍스트 인지]와 [5.5단계 심사 경고 배너]에서 사용한다

> 글로벌 기본값(`github.changelog_deploy.app_release`)은 두지 않는다 — 앱 심사 여부는 레포마다 다르므로 **레포별로만** 기억한다.

### 5) 릴리스 브랜치·provider 판정 — config 우선, version.yml 폴백, 없으면 1회 판정

릴리스 PR의 head/base 브랜치와 릴리스 노트 생성 방식(provider)을 확정한다.
**사용자는 config를 직접 손대지 않는다 — 값이 없어 애매할 때만 자연어로 묻고, 답을 config에 기록한다.**

**우선순위 (위→아래, 먼저 발견되는 값 채택):**

1. config `github.repos[]` 중 `owner == OWNER && repo == REPO`인 항목의 `changelog_deploy.{head_branch, base_branch, provider}`
2. config `github.changelog_deploy.{head_branch, base_branch, provider}` (글로벌)
3. **최초 판정** — 1·2에 값이 없으면 `detect-release-context`(version.yml 폴백)로 자동 추론하고, 애매하면 사용자에게 물은 뒤 config에 기록

1 또는 2에서 세 값을 모두 얻었으면 그대로 쓰고 **묻지 않는다**. 기억할 값:

- `HEAD_BRANCH` — 릴리스 PR head(소스). 폴백 `develop`.
- `BASE_BRANCH` — 릴리스 PR base(프로덕션). 폴백 `main`.
- `PROVIDER` — `coderabbit`|`commit`|`github-ai`|`openai`. 폴백 `coderabbit`.
- `BRANCH_CONFIG_HAS_KEY` — boolean. 우선순위 1·2에서 세 값을 모두 찾았으면 `true`, 아니면 `false`(최초 판정 케이스).

**`BRANCH_CONFIG_HAS_KEY == false`(최초 판정)일 때만** 아래를 수행한다.

먼저 `detect-release-context`로 version.yml 신호를 읽는다:

```bash
# ⚠️ Bash stateless — PROJECT_ROOT·PYTHON을 [시작 전]에서 구한 실제 값으로 채운다.
PROJECT_ROOT="..."; PYTHON="..."
SKILL=pro-changelog-deploy; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPTS/changelog_cli.py" detect-release-context --project-root "$PROJECT_ROOT"
```

반환 JSON의 `branches.{head,base,provider}`를 초기 후보로 삼는다.

**브랜치 확정:**
- version.yml에서 `deploy_branch`/`default_branch`를 읽었으면(폴백이 아닌 실제 값) 그대로 확정.
- 폴백(develop/main)이고 실제 원격에 `develop`이 있으며 default가 `main`이면 → 표준 구조로 조용히 확정.
- 그 외(develop 없음/default가 main 아님 등 애매) → 사용자에게 자연어로 묻는다:
  ```
  이 저장소의 릴리스는 어느 브랜치에서 어느 브랜치로 진행하나요?
  (예: 개발 브랜치에서 배포 브랜치로)
  1. develop → main (표준)
  2. 직접 알려주기 (예: "release 브랜치에서 production 브랜치로")
  ```
  응답에서 head/base를 확정.

**provider 확정:**
- `branches.provider`가 폴백(`coderabbit`)이 아닌 실제 값이면 그대로 확정.
- 폴백이고 레포 루트에 `.coderabbit.yaml`이 있으면 → `coderabbit`으로 조용히 확정.
- 폴백이고 `.coderabbit.yaml`도 없으면 → 사용자에게 묻는다:
  ```
  릴리스 노트를 어떻게 만들까요?
  1. CodeRabbit(AI 리뷰 봇)이 요약을 달아줍니다 (이 레포에 CodeRabbit 사용 시)
  2. 커밋 내역을 분석해 자동 생성합니다 (외부 봇 없이 항상 동작)
  ```
  → 1이면 `coderabbit`, 2면 `commit`.

`.coderabbit.yaml` 존재 확인:
```bash
PROJECT_ROOT="..."
[ -f "$PROJECT_ROOT/.coderabbit.yaml" ] && echo "coderabbit_config=yes" || echo "coderabbit_config=no"
```

**config 기록 (config-rules.md §4 규칙 — 전체 Read 후 해당 키만 Write):**
확정한 `head_branch`/`base_branch`/`provider`를, `github.repos[]`에 현 OWNER/REPO 매칭 항목이 있으면 그 항목의 `changelog_deploy`에, 없으면 `github.changelog_deploy`(글로벌)에 Write한다. PAT·다른 repos 항목·기존 `auto_approve`/`app_release`를 절대 날리지 않는다.

기록 후 사용자에게 자연어로만 안내(키·경로 노출 금지):
```
✅ 이 저장소 릴리스 방식을 기억했습니다 ({HEAD_BRANCH} → {BASE_BRANCH}, {provider 자연어}).
   바꾸고 싶으면 "배포 브랜치 바꿔줘" 또는 "릴리스 노트 방식 바꿔줘"라고 말씀해주세요.
```
(provider 자연어: coderabbit→"CodeRabbit 요약", commit→"커밋 분석", github-ai/openai→"AI 생성")

> **재설정 발화 처리**: 사용자가 이후 "배포 브랜치 바꿔줘"/"릴리스 노트 방식 바꿔줘"라고 하면, 위 질문을 다시 하고 config의 해당 키를 갱신한다(config-rules.md §4 규칙 준수).

## 사용자 입력

$ARGUMENTS

## 모드 판별

사용자 요청에 따라 두 모드 중 하나로 진행:

- **deploy 모드**: "deploy해줘", "배포해줘", "PR 올려줘" → [1단계]부터 시작
- **fix 모드**: "머지 안 됐어", "changelogfix", "다시 해줘", "PR 재시도" → [fix 1단계]부터 시작

---

## deploy 모드

### 1단계: 커밋 상태 확인

아래 명령어를 **각각 별도로** 실행한다. 절대 한 줄로 합치지 않는다.

```bash
git status --short
```

```bash
git fetch origin
```

```bash
# main(프로덕션) 대비 미반영 커밋 목록 (이게 핵심 — develop→main PR이 목적이므로)
git log origin/main..HEAD --oneline 2>/dev/null
```

```bash
# 위 결과가 비어 있을 경우 대비용 — develop remote 대비도 함께 확인
git log origin/develop..HEAD --oneline 2>/dev/null
```

**판단 기준**:

- `git status --short` 결과에 미커밋 변경사항이 있으면 **즉시 멈추고** 안내:
  ```
  커밋되지 않은 변경사항이 있습니다. 먼저 커밋 후 다시 실행해주세요.
  /pro-commit 으로 커밋할 수 있습니다.
  ```
- `git log origin/main..HEAD` 결과가 비어 있으면 → `git log origin/develop..HEAD` 결과도 확인
- **두 결과 모두 비어 있을 때만** "deploy할 커밋이 없습니다" 안내 후 종료
- 둘 중 하나라도 커밋이 있으면 다음 단계 진행

### 1.5단계: 릴리스 컨텍스트 인지 (앱 심사 연관 레포 판단)

> **왜 필요한가**: 앱스토어/플레이스토어 심사 자동 제출이 켜진 레포에서는 `main` 릴리스가 "내부 배포"가 아니라 **사용자 대면 출시**가 된다. 릴리스 노트가 그대로 스토어 "이번 업데이트" 출시노트가 되어 심사에 들어간다. 따라서 이 레포가 앱 심사에 직결되는지 먼저 인지하고, 그렇다면 릴리스 노트를 더 신중히 다룬다. **백엔드 레포(spring/python 등)는 아무 영향 없이 조용히 통과한다.**

#### 1) 신호 수집 — `detect-release-context` 호출 (PAT 불필요, 로컬 파일만 스캔)

```bash
# ⚠️ Bash stateless — PROJECT_ROOT를 [시작 전]에서 구한 실제 값으로 채운다. PAT·OWNER·REPO 불필요.
PROJECT_ROOT="..."

SKILL=pro-changelog-deploy; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
cd "$SCRIPTS" || exit 1
PYTHONIOENCODING=utf-8 "$PYTHON" changelog_cli.py \
  detect-release-context --project-root "$PROJECT_ROOT"
cd "$PROJECT_ROOT"
```

반환 JSON의 `signals`(사실)와 `hint`(약한 힌트)를 얻는다. **`hint`는 참고일 뿐, 최종 판단은 agent가 한다.**

#### 2) 분기 — `hint` × [시작 전 §4]의 `APP_RELEASE` 조합

| 상황 | agent 동작 |
|------|-----------|
| `hint == backend_only` | **조용히 통과.** 경고·질문 없이 2단계로 진행. config도 건드리지 않는다 |
| 앱 심사 감지(`strong_app`/`app_release_likely`/`unknown`) **AND** `APP_RELEASE == unset` (첫 실행) | 아래 [확인 메시지]를 **한 번** 띄우고, 답을 config에 저장 |
| `APP_RELEASE == true` (이미 앱 심사로 확정) | 묻지 않는다. **5단계·5.5단계에서 심사 경고 배너를 적용**하도록 기억하고 2단계로 진행 |
| `APP_RELEASE == false` (사용자가 "일반 배포"로 확정) | 묻지 않고 경고 없이 2단계로 진행 |

> **앱 심사 감지 시 "항상 한 번은 확인"하되, 그 결과를 config에 기억해 다음 배포부터는 묻지 않는다.** (issue·changelog 스킬의 첫 실행 패턴과 동일 철학.)

#### 3) 확인 메시지 (자연어만 — config 키·파일 경로 노출 금지)

```
📱 이 저장소는 앱스토어/플레이스토어 심사로 이어지는 배포로 보입니다.
   그렇다면 지금 작성하는 릴리스 노트가 그대로 스토어 "이번 업데이트"
   출시노트가 되어 심사에 들어갑니다.

이 저장소를 앞으로 "앱 심사 배포"로 보고, 릴리스 노트를 더 신중히 다룰까요?
1. 네 (앱 심사 배포가 맞습니다)
2. 아니요 (일반 배포입니다)
```

응답에 따라 agent가 Read/Write로 `config.json`을 갱신한다:

- **1 선택** → `github.repos[]`의 현 OWNER/REPO 항목 `changelog_deploy` 객체에 `app_release: true` 추가. 이번 배포부터 심사 경고 배너 적용
- **2 선택** → 같은 위치에 `app_release: false` 추가. 경고 없이 진행, 다음부터 묻지 않음

> **갱신 시 주의**: `../references/config-rules.md §4` 규칙대로 전체 파일을 Read로 먼저 읽고 다른 섹션을 보존한 채 `changelog_deploy` 객체에 `app_release` 키만 추가/수정해 Write한다. PAT·`auto_approve`·다른 repos 항목을 절대 날리지 않는다. 항목에 `changelog_deploy` 객체가 없으면 새로 만든다.

이후 2단계로 진행한다.

### 2단계: push 전 확인

push할 커밋 목록을 보여주고 사용자 승인받기:

```
📋 push할 커밋 ({HEAD_BRANCH} → {BASE_BRANCH} 미반영):
  - {커밋 메시지 1}
  - {커밋 메시지 2}

{HEAD_BRANCH} 브랜치에 push할까요?
1. 네, push합니다
2. 취소
```
> `{HEAD_BRANCH}`/`{BASE_BRANCH}`는 [시작 전 §5]에서 확정한 값으로 치환해 표시한다.

### 3단계: push

```bash
# HEAD_BRANCH는 [시작 전 §5]에서 확정한 릴리스 head 브랜치(폴백 develop).
HEAD_BRANCH="..."
git pull --rebase origin "$HEAD_BRANCH"
git push origin "$HEAD_BRANCH"
```

push 후 버전은 증가하지 않는다 — 버전은 릴리스 PR에서 RELEASE-CHANGELOG이 머지 직전 확정한다(릴리스당 +1).

> **⚠️ 단계 순서 (레이스컨디션 방지 — 반드시 지킨다)**
>
> RELEASE-CHANGELOG 워크플로우는 deploy PR(develop→main 릴리스 PR) `opened` 시점에 본문을 확인해, 본문에 `Summary by CodeRabbit`이 **없으면 본문을 초기화**한다. 따라서 빈 본문으로 PR을 먼저 만들면, 워크플로우가 그 순간 끼어들어 본문을 비워 릴리스 노트가 사라진다.
>
> 이를 막기 위해 **PR 생성을 맨 마지막에** 둔다: 커밋 분석(4단계) → 릴리스 노트 작성(5단계) → 릴리스 노트를 본문에 담아 PR 생성(6단계). PR이 처음부터 `Summary by CodeRabbit`을 담고 태어나므로 워크플로우가 본문을 지우지 않는다. (워크플로우 로직은 수정하지 않는다.)

### 4단계: 커밋 분석

PR을 만들기 **전에** 먼저 head → base 변경분을 분석한다:

```bash
# HEAD_BRANCH/BASE_BRANCH는 [시작 전 §5]에서 확정한 값(폴백 develop/main).
HEAD_BRANCH="..."; BASE_BRANCH="..."
git fetch origin "$BASE_BRANCH" "$HEAD_BRANCH" 2>/dev/null || true
# 분석 base는 HEAD가 아닌 origin/$HEAD_BRANCH — README 버전 워크플로우 등이 원격을 앞서게 할 수 있다
git log "origin/$BASE_BRANCH..origin/$HEAD_BRANCH" --pretty=format:"%s" | grep -v "\[skip ci\]" | head -60
```

커밋 메시지를 타입별로 분류:

| prefix | 분류 |
|--------|------|
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `refactor` / `perf` / `style` | 개선 |
| `docs` | 문서 |
| 나머지 | 기타 |

**커밋 메시지를 그대로 쓰지 않는다.** 이슈 제목, URL, 타입 prefix, 파일명, 기술 용어를 모두 제거하고
**클라이언트(사용자)가 이해할 수 있는 기능/변경 관점**으로 재작성한다.

### 5단계: 릴리스 노트 작성

#### provider별 본문 생성 분기 ([시작 전 §5]에서 확정한 `PROVIDER` 사용)

| PROVIDER | 이 단계 행동 | 5.5단계 |
|----------|-------------|---------|
| `coderabbit` | skill이 릴리스 노트를 **선제 작성**(아래 절차) | 정상 진입 |
| `github-ai` / `openai` | `coderabbit`과 동일하게 **선제 작성** | 정상 진입 |
| `commit` | 사용자에게 **한 번 묻는다**: "릴리스 노트를 제가 다듬어 드릴까요, 아니면 커밋 내역 자동 생성에 맡길까요?" → **다듬기** 선택 시 선제 작성, **맡기기** 선택 시 릴리스 노트 파일을 만들지 않고 6단계로(빈 본문 PR — 워크플로우 fallback job이 커밋 분석으로 채움) | 다듬기=진입 / 맡기기=건너뜀 |

> **왜 provider 무관하게 선제 작성이 안전한가**: 워크플로우(`PROJECT-COMMON-RELEASE-CHANGELOG.yaml`)는 "skill이 미리 `Summary by CodeRabbit`을 본문에 넣었으면(`already_found`) provider 무관하게 그대로 존중"한다. 따라서 skill이 선제 작성하면 CodeRabbit 폴링·fallback 없이 그 본문을 바로 파싱한다 → 경합 없음. 유일한 예외가 `commit` "맡기기" — 이때만 skill이 손 떼고 워크플로우 fallback job에 위임한다.

아래 "릴리스 노트 작성 원칙"은 **선제 작성하는 경우**(coderabbit/github-ai/openai, 또는 commit에서 다듬기 선택)에만 수행한다.

> **⚠️ AGENT 필독: 노트 파일을 만든 뒤 반드시 6단계(PR 생성)를 실행한다. PR 생성 없이 끝내지 않는다.**

**릴리스 노트 작성 원칙 — 앱스토어 업데이트 노트처럼 쓴다**:

일반 사용자가 "이번 업데이트에서 뭐가 바뀌었지?" 를 읽는다고 생각하고 작성한다.

- 파일명, 클래스명, 함수명, 변수명 **절대 언급 금지**
- `fix:`, `feat:`, `refactor:`, `chore:` 등 기술 prefix **절대 금지**
- API 호출, DB 쿼리, 알고리즘, 라이브러리명 등 내부 구현 **절대 금지**
- 이슈 번호, GitHub URL **절대 금지**
- **사용자가 직접 느끼는 변화**로만 서술
- 항목 하나당 한 줄, 40자 이내, 간결하게
- **[1.5단계]에서 앱 심사 레포(`APP_RELEASE == true`)로 확정된 경우, 정제 기준을 한 단계 더 엄격히 적용한다.** 조금이라도 내부·CICD·테스트·빌드 성격이면 출시노트에서 **제외**한다 (이 노트가 곧 실제 심사 제출물이므로)

**좋은 예 vs 나쁜 예**:
```
❌ PYTHONPATH 환경변수 패턴으로 크로스플랫폼 호환성 수정
✅ Windows와 macOS에서 실행 오류가 발생하던 문제 해결

❌ config-rules.md §7 Skill별 Config 스키마 인라인화
✅ 설정 초기화 과정이 더 간단해졌습니다

❌ Node.js 20 → 24 Dockerfile 업그레이드 (npm ci lock 파일 불일치 해결)
✅ 빌드 시 패키지 설치 오류가 발생하던 문제 해결

❌ .projectops/ 폴더 삭제 및 .gitignore 정리
✅ 앱 설치 용량이 소폭 감소했습니다
```

릴리스 노트 본문 파일은 워크플로우가 파싱하는 형식과 **100% 동일한 구조**로 작성한다. 카테고리명은 아래 고정값만 사용하고, 항목이 없는 카테고리는 생략한다.

**Write tool로 `~/.projectops/tmp/{OWNER}__{REPO}__release_notes.md`에 저장한다** (레포 내부가 아닌 홈 디렉토리 — config와 동일 위치라 레포 오염이 없고, 파일명의 `{OWNER}__{REPO}` prefix로 여러 레포·에이전트 동시 deploy 시 충돌이 없다). `{OWNER}`·`{REPO}`는 [시작 전]에서 구한 실제 값으로 치환한다. Windows는 `C:\Users\<사용자>\.projectops\tmp\{OWNER}__{REPO}__release_notes.md`, macOS/Linux는 `~/.projectops/tmp/{OWNER}__{REPO}__release_notes.md`. **tmp 폴더가 없으면 Write 전에 생성**한다. 이후 cli 호출 시 이 **절대경로**(아래 `NOTES_FILE`)를 그대로 넘긴다:

```
<!-- This is an auto-generated comment: release notes by coderabbit.ai -->

## Summary by CodeRabbit

## 릴리스 노트

* **새 기능**
  * (항목)

* **버그 수정**
  * (항목)

* **개선**
  * (항목)

* **문서**
  * (항목)

* **기타**
  * (항목)

<!-- end of auto-generated comment: release notes by coderabbit.ai -->
```

이 파일이 완성되면 **곧바로 6단계로 가지 않고 5.5단계(사용자 승인 게이트)부터 거친다.**

### 5.5단계: 사용자 승인 게이트

> **commit provider + "맡기기" 선택 시**: 5단계에서 릴리스 노트 파일을 만들지 않았으므로 이 5.5단계를 **건너뛰고** 바로 6단계로 간다(빈 본문 PR 생성 → 워크플로우 fallback job이 채움). 아래 승인 게이트는 릴리스 노트를 선제 작성한 경우에만 적용된다.

> **🔔 심사 경고 배너 (앱 심사 레포 전용)**: [1.5단계]에서 `APP_RELEASE == true`로 확정된 경우, 아래 A/B 어느 분기든 **릴리스 노트 본문 위에 배너 한 줄을 먼저 출력**한다 (자동 모드여도 배너는 표시). `APP_RELEASE != true`면 배너를 출력하지 않는다.
>
> ```
> ⚠️ 이 배포는 실제 앱스토어/플레이스토어 심사에 들어갑니다.
>    아래 릴리스 노트가 그대로 스토어 "이번 업데이트" 출시노트가 됩니다.
>    CICD·내부 개선·테스트 항목은 빼고, 사용자가 직접 느끼는 변경만 담겼는지 확인하세요.
> ```

[시작 전 §3]에서 판정한 `AUTO_APPROVE` / `CONFIG_HAS_KEY` 값에 따라 분기한다.

#### A. 자동 모드 (`AUTO_APPROVE == true`)

본문을 사용자에게 표시만 하고 즉시 6단계로 진행한다. 사용자 응답을 기다리지 않는다.

사용자에게 출력할 메시지 형식:

```
🤖 이 레포는 확인 없이 바로 배포되도록 설정돼 있어 릴리스 노트만 안내드리고 PR을 만듭니다.
   (다시 매번 확인받고 싶으시면 "확인받게 해줘"라고 말씀해주세요.)

📋 릴리스 노트:
{_release_notes.md 본문 그대로}

PR을 생성합니다.
```

이후 6단계 진행.

> 사용자가 메시지를 보고 "확인받게 해줘", "수동으로 바꿔줘", "다음부턴 확인받아줘" 같은 자연어로 응답하면, 6단계를 진행하기 **전에** Read/Write 도구로 `config.json`을 갱신한다. 우선순위 1(레포별)에 키가 있었다면 그 값을 `false`로, 없었다면 우선순위 2(글로벌)를 `false`로 설정한다. 갱신 후 본문은 그대로 두고 다시 사용자 승인을 받는다(B 분기로 전환).

#### B. 수동 모드 (`AUTO_APPROVE == false`)

본문을 표시하고 사용자 승인을 받는다.

```
📋 릴리스 노트 본문:

{_release_notes.md 본문 그대로}

이대로 PR을 만들까요?
1. 네, 만들어주세요
2. 수정해주세요 (어떻게 수정할지 말씀해주세요)
```

응답 분기:

- **1 선택** → 6단계 진행. 단, `CONFIG_HAS_KEY == false`(첫 실행)이면 6단계 **직전**에 아래 [C. 첫 실행 자동화 제안]을 한 번만 실행한다
- **2 선택 / 수정 지시** → 사용자 지시를 반영해 5단계의 `_release_notes.md`를 재작성한 뒤 5.5단계 처음으로 되돌아온다 (승인 떨어질 때까지 루프)

#### C. 첫 실행 자동화 제안 (B에서 1 선택 + `CONFIG_HAS_KEY == false`일 때만, 한 번)

사용자에게 묻는다 (사용자가 처음 보는 화면이므로 **무엇을** 자동화하는지 분명히 안내한다):

```
💡 다음 배포부터 어떻게 진행할까요?

매번 배포 직전에 릴리스 노트를 보여드리고 확인받는 방식이 기본입니다.
원하시면 이 확인 단계를 건너뛰고 곧바로 배포 PR이 만들어지도록 바꿀 수 있습니다.

1. 이 레포 배포는 앞으로 확인 없이 바로 진행해주세요
2. 모든 레포 배포를 앞으로 확인 없이 바로 진행해주세요
3. 지금처럼 매번 릴리스 노트 확인받겠습니다

(언제든 "다시 확인받게 해줘" / "자동으로 바꿔줘"라고 말씀하시면 바꿀 수 있습니다)
```

응답에 따라 agent가 Read/Write 도구로 `config.json`을 갱신한다:

- **1 선택** → `github.repos[]`에서 현 OWNER/REPO 매칭 항목에 `changelog_deploy.auto_approve: true` 추가
- **2 선택** → `github.changelog_deploy.auto_approve: true` 추가 (객체가 없으면 생성)
- **3 선택** → `github.changelog_deploy.auto_approve: false` 추가 (다음 실행부터 묻지 않도록 키 자체는 남긴다)

갱신 후 사용자에게 안내:

- 1: "✅ 이 레포는 다음 배포부터 확인 없이 바로 진행합니다."
- 2: "✅ 모든 레포에서 다음 배포부터 확인 없이 바로 진행합니다."
- 3: "✅ 앞으로도 매번 릴리스 노트 확인받습니다."

이후 6단계 진행.

> **갱신 시 주의**: `../references/config-rules.md §4` 규칙대로 전체 파일을 Read로 먼저 읽고 다른 섹션을 보존한 채 해당 키만 추가/수정해 Write한다. PAT·다른 repos 항목을 절대 날리지 않는다.

### 6단계: deploy PR 생성 (릴리스 노트 본문 포함)

VERSION-CONTROL 워크플로우 완료를 기다리지 않고 deploy PR을 생성한다. **5단계에서 만든 릴리스 노트 파일을 본문으로 담아 생성**하는 것이 핵심이다 — PR이 처음부터 `Summary by CodeRabbit`을 담고 있어야 RELEASE-CHANGELOG 워크플로우가 본문을 초기화하지 않는다.

```bash
# ⚠️ Bash stateless — 이 블록 맨 앞 변수를 [시작 전]에서 구한 실제 값으로 채운다.
# HEAD_BRANCH/BASE_BRANCH는 [시작 전 §5]에서 확정한 릴리스 브랜치(폴백 develop/main).
GITHUB_PAT="..."; OWNER="..."; REPO="..."; PYTHON="..."; PROJECT_ROOT="..."; HEAD_BRANCH="..."; BASE_BRANCH="..."

# 릴리스 노트 임시 파일 — 5단계에서 Write한 그 절대경로와 동일해야 한다.
# 홈 디렉토리 + {OWNER}__{REPO} prefix → cwd 무관·레포별 격리. (Windows Git Bash도 $HOME 정상 동작)
NOTES_FILE="$HOME/.projectops/tmp/${OWNER}__${REPO}__release_notes.md"
# commit provider에서 "맡기기" 선택 시 5단계가 노트 파일을 만들지 않는다.
# 파일이 없으면 빈 문자열로 넘겨 빈 본문 PR 생성 → 워크플로우 fallback job이 커밋 분석으로 채운다.
[ -f "$NOTES_FILE" ] || NOTES_FILE=""

TODAY=$(date '+%Y%m%d')
TITLE="🚀 Deploy ${TODAY}"

SKILL=pro-changelog-deploy; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
cd "$SCRIPTS" || exit 1
DEPLOY_STATUS=$(GITHUB_PAT="$GITHUB_PAT" PYTHONIOENCODING=utf-8 "$PYTHON" changelog_cli.py \
  deploy-status "$OWNER" "$REPO" --base "$BASE_BRANCH")
EXISTING_PR=$(DEPLOY_STATUS="$DEPLOY_STATUS" "$PYTHON" -c "import os,json; d=json.loads(os.environ['DEPLOY_STATUS']); print((d.get('pr') or {}).get('number',''))")

# 기존 open deploy PR이 있으면 재사용 — 닫지 않는다 (새로 열면 워크플로우 재트리거되어 본문 초기화 위험)
if [ -n "$EXISTING_PR" ]; then
  # 재사용 케이스: 이미 PR이 존재하므로 update-pr로 릴리스 노트 본문만 갱신한다.
  PR_NUMBER=$EXISTING_PR
  echo "기존 deploy PR #$PR_NUMBER 재사용 → 본문 업데이트"
  RESULT_OUT=$(GITHUB_PAT="$GITHUB_PAT" PYTHONIOENCODING=utf-8 "$PYTHON" changelog_cli.py \
    update-pr "$OWNER" "$REPO" "$PR_NUMBER" "$NOTES_FILE"
  )
else
  # 신규 케이스: create-pr의 body_file에 릴리스 노트 파일 절대경로를 넘겨 본문 포함 PR 생성.
  # NOTES_FILE이 빈 문자열(commit 맡기기)이면 빈 본문 PR 생성 → 워크플로우가 채운다.
  # 브랜치는 [시작 전 §5]에서 확정한 HEAD_BRANCH→BASE_BRANCH (하드코딩 금지).
  RESULT_OUT=$(GITHUB_PAT="$GITHUB_PAT" PYTHONIOENCODING=utf-8 "$PYTHON" changelog_cli.py \
    create-pr "$OWNER" "$REPO" "$TITLE" "$NOTES_FILE" "$HEAD_BRANCH" "$BASE_BRANCH")
  PR_NUMBER=$(RESULT_OUT="$RESULT_OUT" "$PYTHON" -c "import os,json; print(json.loads(os.environ['RESULT_OUT']).get('number',''))")
  echo "새 deploy PR #$PR_NUMBER 생성 (릴리스 노트 본문 포함)"
fi
rm -f "$NOTES_FILE"
cd "$PROJECT_ROOT"

if [ -z "$PR_NUMBER" ]; then
  echo "❌ PR 생성/업데이트 실패. GitHub API 응답을 확인하세요. ($RESULT_OUT)"
  exit 1
fi
```

출력 JSON(`{"number","url"}`)으로 성공을 확인한다.

### 7단계: automerge 검증 (deploy-status)

PR 생성 직후, **`/tmp`에 즉석 Python을 만들지 말고** 아래 재사용 커맨드 한 번으로 상태를 확인한다. owner/repo/PR번호만 주면 PR 머지·CodeRabbit 본문·워크플로우 run·deploy HEAD를 한 번에 조회해 `verdict`로 판정한 JSON을 반환한다.

```bash
# ⚠️ Bash stateless — 변수를 [시작 전]에서 구한 실제 값으로 채운다. PR_NUMBER는 6단계에서 구한 값.
# BASE_BRANCH는 [시작 전 §5]에서 확정한 base 브랜치(폴백 main).
GITHUB_PAT="..."; OWNER="..."; REPO="..."; PYTHON="..."; PROJECT_ROOT="..."; PR_NUMBER="..."; BASE_BRANCH="..."

SKILL=pro-changelog-deploy; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
cd "$SCRIPTS" || exit 1
GITHUB_PAT="$GITHUB_PAT" PYTHONIOENCODING=utf-8 "$PYTHON" changelog_cli.py \
  deploy-status "$OWNER" "$REPO" --pr "$PR_NUMBER" --base "$BASE_BRANCH"
cd "$PROJECT_ROOT"
```

반환 JSON의 `verdict`를 보고 라우팅한다:

| verdict | 의미 | 행동 |
|---------|------|------|
| `merged` | automerge 완료 | 8단계 결과 안내, 종료 |
| `waiting_for_automerge` | 정상 대기 중 (워크플로우 in_progress 포함) | **sleep 금지.** `ScheduleWakeup(delaySeconds=60)`으로 재확인하고, `merged`가 될 때까지 **60초 간격으로 계속 반복**한다 (automerge는 보통 60초 안에 완료). 60초는 ScheduleWakeup이 허용하는 최소값이다 |
| `missing_coderabbit_summary` | 워크플로우는 끝났는데 본문에 `Summary by CodeRabbit`이 없는 상태 | **즉시 fix 모드로 가지 않는다.** 60초 후 한 번 더 `deploy-status`로 재확인하고, **두 번 연속 같은 verdict일 때만** fix 모드 안내. 한 번이면 race 가능성을 우선 가정한다 (이슈 #331) |
| `workflow_failed` | 워크플로우 실패 | `workflow.run_url` 안내 + fix 모드로 재실행 |
| `conflict` | 머지 충돌/차단 | 사용자에게 충돌 상태 안내, 수동 확인 요청 |
| `no_pr` | open deploy PR 없음 | `deploy_branch.head_sha`로 이미 머지됐는지 확인 후 안내 |

> **`missing_coderabbit_summary` 시 즉시 `update-pr` 호출 금지** (실측 사고: 이슈 #331).
> 워크플로우 step과 CodeRabbit 봇 PATCH가 동시에 본문을 갱신하는 race 구간이 있어, agent가 즉시 update-pr로 본문을 재주입하면 워크플로우 PATCH와 또 race를 일으켜 본문 사라짐이 반복된다. 반드시 60초 재확인 후 두 번 연속일 때만 fix 모드로 간다.

> **재확인 시 sleep을 쓰지 않는다.** Claude Code Bash는 `sleep 120`을 차단한다. 대기가 필요하면 `ScheduleWakeup`으로 자기 페이스를 잡고, 깨어나면 `next` 힌트의 `deploy-status` 커맨드를 다시 호출한다.
>
> **재확인 주기 (실측 기반)**: 릴리스 노트를 본문에 담아 PR을 만들면 CodeRabbit 10분 대기가 없으므로 automerge는 **보통 60초 안에** 끝난다 (VERSION-CONTROL → CHANGELOG → automerge 한 사이클, 실측 #317·#318 모두 60초 내 머지). 따라서 `ScheduleWakeup(delaySeconds=60)`으로 재확인하고, `merged`가 될 때까지 60초 간격으로 반복한다. **`ScheduleWakeup`의 최소 허용값이 60초**이므로 45·30초 등 더 짧은 값을 줘도 60초로 클램프된다 — 60초가 사실상 최단 주기다. 90초 같은 긴 값은 이미 끝난 배포를 늦게 확인해 시간을 낭비하므로 쓰지 않는다. (60초는 캐시 유지 구간 270초 이내라 비용 페널티 없음.)

### 8단계: 결과 안내

```
✅ 완료!

📋 요약:
  • push: origin/develop
  • deploy PR: #NNN
  • 릴리스 노트: 작성 완료

RELEASE-CHANGELOG 워크플로우가 "Summary by CodeRabbit"을 감지하면
CHANGELOG 업데이트 후 main 브랜치 automerge가 자동 진행됩니다.

진행 상황: https://github.com/{owner}/{repo}/actions
```

---

## fix 모드 (automerge 실패 시 재트리거)

### fix 1단계: 현재 deploy PR 상태 확인 (deploy-status)

curl 즉석 파싱 대신 deploy-status로 현재 상태를 종합 조회한다. `--pr` 없이 호출하면 open deploy PR을 자동 탐색한다.

```bash
# ⚠️ Bash stateless — 변수를 실제 값으로 채운다. BASE_BRANCH는 [시작 전 §5]에서 확정(폴백 main).
GITHUB_PAT="..."; OWNER="..."; REPO="..."; PYTHON="..."; PROJECT_ROOT="..."; BASE_BRANCH="..."

SKILL=pro-changelog-deploy; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
cd "$SCRIPTS" || exit 1
GITHUB_PAT="$GITHUB_PAT" PYTHONIOENCODING=utf-8 "$PYTHON" changelog_cli.py \
  deploy-status "$OWNER" "$REPO" --base "$BASE_BRANCH"
cd "$PROJECT_ROOT"
```

반환 JSON의 `verdict`로 분기한다:

- `no_pr` → open PR 없음. fix 3단계(새 PR 생성)로 이동
- `merged` → 이미 머지됨. 재시도 불필요, 사용자에게 안내 후 종료
- 그 외(`waiting_for_automerge`/`missing_coderabbit_summary`/`workflow_failed`/`conflict`) → `pr.number`를 EXISTING_PR로 기억하고 fix 2단계(기존 PR 닫기)로 진행

### fix 2단계: 기존 PR 닫기 (사용자 확인 후)

```
현재 open된 deploy PR #NNN이 있습니다.
이 PR을 닫고 새로 열어서 워크플로우를 재트리거할까요?

1. 네, 닫고 새로 생성합니다
2. 취소
```

확인 후 실행:

```bash
# ⚠️ Bash stateless — 변수 + EXISTING_PR(fix 1단계 번호)을 실제 값으로 채운다.
GITHUB_PAT="..."; OWNER="..."; REPO="..."; PYTHON="..."; PROJECT_ROOT="..."; EXISTING_PR="..."

SKILL=pro-changelog-deploy; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
cd "$SCRIPTS" || exit 1
GITHUB_PAT="$GITHUB_PAT" PYTHONIOENCODING=utf-8 "$PYTHON" changelog_cli.py \
  update-pr "$OWNER" "$REPO" "$EXISTING_PR" "-" --state closed
cd "$PROJECT_ROOT"
```

> **⚠️ fix 모드도 deploy 모드와 동일하게 PR 생성을 맨 마지막에 둔다.** 빈 본문으로 새 PR을 먼저 열면 워크플로우가 본문을 초기화한다. 따라서 커밋 분석(fix 3단계) → 릴리스 노트 작성(fix 4단계) → 릴리스 노트 본문 담아 PR 생성(fix 5단계) 순으로 진행한다.

### fix 3단계: 커밋 분석

새 PR을 만들기 **전에** head → base 변경분을 먼저 분석한다:

```bash
# HEAD_BRANCH/BASE_BRANCH는 [시작 전 §5]에서 확정한 값(폴백 develop/main).
HEAD_BRANCH="..."; BASE_BRANCH="..."
git fetch origin "$BASE_BRANCH" "$HEAD_BRANCH" 2>/dev/null || true
# 분석 base는 origin/$HEAD_BRANCH (deploy 4단계와 동일 이유 — HEAD가 origin/$HEAD_BRANCH보다 뒤일 수 있음).
git log "origin/$BASE_BRANCH..origin/$HEAD_BRANCH" --pretty=format:"%s" | grep -v "\[skip ci\]" | head -60
```

커밋 메시지를 deploy 모드 4·5단계와 **완전히 동일한 기준**으로 분류 및 재작성한다.
앱스토어 업데이트 노트처럼 — 파일명·기술 prefix·구현 방식·이슈 번호·URL 모두 금지. 사용자가 직접 느끼는 변화만, 40자 이내로 간결하게.

### fix 4단계: 릴리스 노트 작성

> **⚠️ AGENT 필독: 노트 파일을 만든 뒤 fix 5단계(PR 생성)로 곧바로 가지 않고 fix 4.5단계(사용자 승인 게이트)부터 거친다.**

deploy 6단계와 **동일한 고정 구조**로 릴리스 노트 파일을 작성한다 (Write tool로 `~/.projectops/tmp/{OWNER}__{REPO}__release_notes.md`에 저장 — deploy 5단계와 동일 위치·파일명 규칙, tmp 폴더 없으면 먼저 생성). 구조는 deploy 5단계의 고정 템플릿(`Summary by CodeRabbit` 포함)을 그대로 따른다.

### fix 4.5단계: 사용자 승인 게이트

**deploy 5.5단계와 동일한 로직**을 적용한다. [시작 전 §3]에서 판정한 `AUTO_APPROVE` / `CONFIG_HAS_KEY` 값을 그대로 사용한다.

> **🔔 심사 경고 배너**: deploy 5.5단계와 동일하게, `APP_RELEASE == true`면 릴리스 노트 본문 위에 심사 경고 배너를 먼저 출력한다. fix 모드는 보통 [1.5단계]를 이미 거친 재시도이므로 `APP_RELEASE` 값이 이미 정해져 있다. 만약 fix 모드로 곧장 진입해 `APP_RELEASE == unset`이면, fix 3단계(커밋 분석) **전에** [1.5단계]의 신호 수집·확인 절차를 한 번 수행해 값을 정한다.

- 자동 모드(`AUTO_APPROVE == true`): 본문 표시만 하고 즉시 fix 5단계 진행. 사용자가 "수동으로 바꿔줘"라고 응답하면 config 갱신 후 수동 분기로 전환
- 수동 모드(`AUTO_APPROVE == false`): 본문 표시 + 승인/수정 분기. 수정 요청 시 fix 4단계로 돌아가 노트 재작성 후 fix 4.5단계 재진입
- 첫 실행(`CONFIG_HAS_KEY == false`): 수동 모드에서 승인 받은 직후 한 번만 자동화 제안(이 레포만 / 모든 레포 / 매번 확인)을 묻고 응답에 따라 config를 갱신

세부 메시지 문구·갱신 절차는 deploy 5.5단계의 A/B/C 분기와 **완전히 동일**하므로 그대로 따른다.

### fix 5단계: 새 deploy PR 생성 (릴리스 노트 본문 포함)

fix 4단계에서 만든 릴리스 노트 파일을 **본문으로 담아** 새 PR을 생성한다. PR이 처음부터 `Summary by CodeRabbit`을 담고 태어나야 워크플로우가 본문을 초기화하지 않는다.

```bash
# ⚠️ Bash stateless — 변수를 실제 값으로 채운다.
# HEAD_BRANCH/BASE_BRANCH는 [시작 전 §5]에서 확정한 릴리스 브랜치(폴백 develop/main).
GITHUB_PAT="..."; OWNER="..."; REPO="..."; PYTHON="..."; PROJECT_ROOT="..."; HEAD_BRANCH="..."; BASE_BRANCH="..."

# 릴리스 노트 임시 파일 — fix 4단계에서 Write한 그 절대경로와 동일해야 한다.
NOTES_FILE="$HOME/.projectops/tmp/${OWNER}__${REPO}__release_notes.md"
# commit provider "맡기기"로 노트 파일이 없으면 빈 문자열 → 빈 본문 PR (워크플로우가 채움).
[ -f "$NOTES_FILE" ] || NOTES_FILE=""

TODAY=$(date '+%Y%m%d')
TITLE="🚀 Deploy ${TODAY} (재시도)"

# create-pr의 body_file에 릴리스 노트 파일 절대경로를 넘겨 본문 포함 PR 생성 (deploy 6단계와 동일 패턴).
# 브랜치는 [시작 전 §5]에서 확정한 HEAD_BRANCH→BASE_BRANCH (하드코딩 금지).
SKILL=pro-changelog-deploy; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
cd "$SCRIPTS" || exit 1
CREATE_OUT=$(GITHUB_PAT="$GITHUB_PAT" PYTHONIOENCODING=utf-8 "$PYTHON" changelog_cli.py \
  create-pr "$OWNER" "$REPO" "$TITLE" "$NOTES_FILE" "$HEAD_BRANCH" "$BASE_BRANCH")
PR_NUMBER=$(CREATE_OUT="$CREATE_OUT" "$PYTHON" -c "import os,json; print(json.loads(os.environ['CREATE_OUT']).get('number',''))")
rm -f "$NOTES_FILE"
cd "$PROJECT_ROOT"

if [ -z "$PR_NUMBER" ]; then
  echo "❌ PR 생성 실패. GitHub API 응답을 확인하세요. ($CREATE_OUT)"
  exit 1
fi
echo "✅ PR #$PR_NUMBER 생성 완료 (릴리스 노트 본문 포함)"
```

출력 JSON(`{"number","url"}`)으로 성공을 확인한다.

### fix 6단계: 결과 안내

```
✅ PR #NNN 본문 업데이트 완료!

워크플로우가 폴링 중 "Summary by CodeRabbit"을 감지하면 automerge가 자동 진행됩니다.
진행 상황: https://github.com/{owner}/{repo}/actions
```

---

## 주의사항

- **PR 생성/재시도 후 반드시 `deploy-status` 커맨드로 검증한다.** PR 상태·automerge·워크플로우 확인용 Python을 `/tmp`에 즉석 생성하지 않는다 — `deploy-status`가 그 모든 것을 JSON으로 반환한다.
- **PR은 릴리스 노트를 본문에 담아 생성한다** (deploy 6단계 / fix 5단계). PR이 처음부터 `Summary by CodeRabbit`을 담고 있어 워크플로우가 본문 초기화를 건너뛴다. 빈 본문으로 먼저 만든 뒤 나중에 본문을 채우면 레이스컨디션으로 노트가 사라진다.
- **PR 생성 전 사용자 승인 게이트를 건너뛰지 않는다** (deploy 5.5단계 / fix 4.5단계). 자동 모드로 명시 설정된 경우만 본문 표시 후 즉시 진행한다. 사용자에게 노출되는 안내는 자연어로만 작성하며 config 키 이름·파일 경로를 표면화하지 않는다.
- 그래도 워크플로우가 본문을 지워버린 정황이 보이면 fix 모드로 재실행한다.
- deploy PR이 이미 있으면 닫지 않고 재사용한다 — 새로 열면 워크플로우가 다시 트리거되어 본문이 초기화될 수 있다.
- 10분이 지나도 automerge가 안 되면 fix 모드로 재실행한다.
- **Windows 내부망에서 curl exit 35 (SSL 오류) 발생 시**: curl 호출에 `--ssl-no-revoke` 옵션 추가 (`../references/common-rules.md` Windows 내부망 환경 섹션 참조).
