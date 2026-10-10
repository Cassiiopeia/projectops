---
name: pro-changelog-deploy
description: "develop 브랜치를 push하고 main으로 릴리스 PR(deploy PR)을 생성한 뒤 즉시 릴리스 노트를 본문에 담아 RELEASE-CHANGELOG 워크플로우가 그 본문을 그대로 써서 automerge를 진행하게 한다. automerge 실패 시 기존 PR을 닫고 새 PR을 열어 재트리거하는 fix 기능도 포함. 앱스토어/플레이스토어 심사로 직결되는 레포(앱 심사 인지)는 릴리스 노트에 심사 경고 배너를 띄우고 정제를 더 엄격히 적용한다. 'deploy해줘', '배포해줘', 'deploy PR 올려줘', 'changelogfix', 'deploy 머지 안 됐어', 'PR 다시 열어줘' 등의 요청 시 사용."
---

# Changelog Deploy Mode

> **⚠️ 모델 권고**: 이 스킬은 릴리스 노트 작성이 주 작업이다. **lite(haiku) 모델로 실행을 권장**한다. 커밋 분석과 자연어 재작성만 하면 되므로 강력한 모델이 불필요하다.

projectops 전용 스킬. `PROJECT-COMMON-RELEASE-CHANGELOG` 워크플로우와 연동한다 — 릴리스 PR 감지 → 본문에 릴리스 노트가 있으면 그대로 사용, 없으면 provider 사다리(키 있으면 AI → 커밋 분석)로 생성 → 버전 확정 → CHANGELOG 업데이트 → automerge. CodeRabbit을 기다리지 않는다 (#566).

이 스킬은 head push → 릴리스 노트 작성 → **노트를 본문에 담아** base로 릴리스 PR 생성 → automerge 확인까지 한다. 실패하면 fix 모드로 기존 PR을 닫고 새 PR로 재트리거한다. 노트는 `Summary by CodeRabbit` 형식으로 담는다 — 형식 이름만 CodeRabbit일 뿐 봇이 필요하지 않다. 워크플로우가 그 본문을 존중해 곧바로 파싱·automerge한다.

인자: $ARGUMENTS

## 이때는 쓰지 마라

- 배포가 아닌 일반 커밋/PR 작업
- 릴리스 head 브랜치([시작 전 §5]에서 확정한 개발 브랜치, 표준 `develop`)가 원격에 없는 프로젝트 — head → base 릴리스 PR 구조 전용이다. 브랜치 이름 자체는 고정이 아니다
- `PROJECT-COMMON-RELEASE-CHANGELOG` 워크플로우가 설정되지 않은 저장소

## 핵심 원칙 (안전 규칙 — 의미를 바꾸지 않는다)

- `git push --force`는 절대 실행하지 않는다
- **사용자 확인 없이 PR을 닫거나 열지 않는다** (fix 모드)
- **릴리스 노트 본문은 PR 생성 전 사용자에게 보여준다** (deploy 5.5 / fix 4.5). 자동 모드로 명시 설정된 경우만 표시 후 즉시 진행
- **앱 심사 레포(`APP_RELEASE == true`)는 자동 모드여도 매번 승인을 받는다** — 스토어 심사 제출로 직결되므로 포괄 위임이 적용되지 않는다 (#821)
- **릴리스 PR 전에 base → head 역방향 차이를 먼저 병합한다** (deploy 1-1). 릴리스 워크플로우가 버전 커밋을 base에만 남기므로 생략하면 다음 배포에서 버전 파일이 충돌한다
- **PR 생성은 릴리스 노트 작성 뒤 맨 마지막이다** (아래 레이스 방지)
- **사용자에게 config 키 이름·파일 경로를 노출하지 않는다**. 자동/수동 토글은 자연어 응답을 받아 agent가 직접 갱신한다
- **브랜치를 하드코딩하지 않는다 (#456)**. head/base 브랜치와 provider는 **config(우선) → version.yml(폴백)**. `develop`/`main`/`commit`은 값을 못 읽었을 때의 폴백일 뿐이다. 아래 절차의 `develop`/`main`은 확정값으로 치환한다
- **사용자는 config를 직접 수정하지 않는다**. 판정 가능하면 묻지 않고, 애매할 때만 자연어로 묻고 기록하며, 한 번 기록하면 재질문하지 않는다

## 무엇을 하려는가 → 명령 → 자세한 문서

모든 명령은 `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/changelog_cli.py <명령>` 이다.

| 하려는 것 | 명령 | 자세히 |
|---|---|---|
| 릴리스 브랜치·provider·앱 심사 신호 읽기 (PAT 불필요) | `detect-release-context --project-root {PROJECT_ROOT}` | `references/config.md` |
| deploy PR 상태 종합 판정 (머지·본문·워크플로우·HEAD) | `deploy-status {OWNER} {REPO} [--pr N] --base B [--head H]` | 아래 verdict 표 |
| 노트를 본문에 담아 릴리스 PR 생성 | `create-pr {OWNER} {REPO} "{제목}" "{노트 파일}" {HEAD} {BASE}` | `references/deploy-steps.md` 6단계 |
| 기존 PR 본문 갱신 · 닫기 | `update-pr {OWNER} {REPO} {N} "{노트 파일}"` · `update-pr ... "-" --state closed` | `references/deploy-steps.md` · `references/fix-steps.md` |
| PR 목록 | `list-prs {OWNER} {REPO} --state open` | — |
| 워크플로우 실패 로그 | `actions show-run\|joblog\|list-failed\|resolve-pr\|resolve-branch {OWNER} {REPO} [arg]` | `../pro-github/references/actions.md` |
| PAT · 자동 승인 · 앱 심사 · 브랜치 판정과 config 기록 | — (Read/Write 도구) | `references/config.md` |
| 노트 작성 원칙 · 고정 구조 · 승인 문구 | — | `references/release-notes.md` |

## 시작 전

### 1) 스크립트 · OWNER · REPO · PYTHON · PROJECT_ROOT (한 번)

**Bash는 stateless다** — 변수·`export`가 호출 간 유지되지 않는다. 아래에서 나온 값을 **기억해 두고 이후 모든 블록에 실제 값으로 써넣는다**(`{PYTHON}` 자리 등, 또는 블록 첫 줄에 `OWNER="..."; ...`로 재선언). 이전 호출의 변수가 살아 있다고 가정하지 않는다.

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "❌ Python을 찾을 수 없습니다."; exit 1; }
SKILL=pro-changelog-deploy; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
OWNER=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/]([^/]+)/.*|\1|')
REPO=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/][^/]+/([^/.]+)(\.git)?$|\1|')
echo "PROJECT_ROOT=$PROJECT_ROOT PYTHON=$PYTHON SCRIPTS=$SCRIPTS OWNER=$OWNER REPO=$REPO"
PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPTS/changelog_cli.py" detect-release-context --project-root "$PROJECT_ROOT"
```

`detect-release-context` 출력의 `branches`(브랜치·provider)와 `signals`·`hint`(앱 심사 신호)를 기억한다.

### 2)~5) config에서 값 정하기 — 상세 `references/config.md`

| § | 값 | 규칙 |
|---|---|---|
| 2 | `PAT` | **agent가 Read 도구로** `~/.projectops/config/config.json`을 직접 읽는다 (bash Python 추출 금지 — Windows `$HOME` 경로 버그). 고정 경로만, 캐시 탐색 금지. repo별 `pat` → `global_pat`. 없으면 "`/pro-github`로 PAT 먼저 등록" 안내 후 종료 |
| 3 | `AUTO_APPROVE`, `CONFIG_HAS_KEY` | `changelog_deploy.auto_approve`: 레포별 → 글로벌 → 없으면 `false`(수동). 옛 키 `auto_approve_release_notes`는 무시 |
| 4 | `APP_RELEASE` | `changelog_deploy.app_release`: **레포별만** → 없으면 `unset` |
| 5 | `HEAD_BRANCH`, `BASE_BRANCH`, `PROVIDER`, `BRANCH_CONFIG_HAS_KEY` | 레포별 → 글로벌 → 최초 판정(`detect-release-context` + 애매할 때만 질문 → config 기록) |

**provider 3단 규칙 (#821)** — `branches.provider`는 CLI가 이미 적용한 값이다: ① version.yml `changelog.provider` 명시값 → ② 미설정 + 레포 루트 `.coderabbit.yaml` → `coderabbit` → ③ 둘 다 없음 → `commit`. 워크플로우도 같은 규칙이라 판단이 갈리지 않는다. `github-ai`(서비스 종료)는 CLI가 `commit`으로 돌려준다. provider는 묻지 않는다.

## 모드 판별

- **deploy 모드**: "deploy해줘", "배포해줘", "PR 올려줘" → 1단계부터
- **fix 모드**: "머지 안 됐어", "changelogfix", "다시 해줘", "PR 재시도" → fix 1단계부터

## deploy 모드 — 단계와 판단 (명령·문구는 `references/deploy-steps.md`)

**1단계 커밋 상태 확인** — `git status --short` · `git fetch origin` · 현재 브랜치 · `git log origin/{BASE}..HEAD` · `git log origin/{HEAD}..HEAD`를 **각각 따로** 실행한다.
- 미커밋 변경이 **내 것**(이번 작업에서 만든 것)이면 멈추고 `/pro-commit`을 먼저 한다.
- **의도를 모르는 남의 변경**(다른 세션)이면 건드리지 말고 목록을 알린 뒤 진행한다 — 배포는 커밋만 push한다. 단 1-1 merge가 그 파일과 겹쳐 실패하면 멈추고 사용자에게 넘긴다.
- 현재 브랜치가 `HEAD_BRANCH`가 아니면 **멈추고** 안내한다. 브랜치를 임의로 바꾸지 않는다 (다른 세션이 옮긴 것일 수 있다).
- 두 log가 **모두 비었을 때만** "deploy할 커밋이 없습니다" 후 종료. 하나라도 있으면 1-1로.

**1-1단계 base 최신화 (생략 금지)** — 순서가 계약이다:
1. `git pull --rebase origin {HEAD}` 로 head를 원격과 먼저 맞춘다 (merge 커밋을 만든 뒤 pull --rebase 하면 merge가 풀린다).
   작업트리에 **남의 미커밋 변경**이 있어 pull --rebase 가 거부되면 stash 하지 않고 `git fetch origin` → `git merge --ff-only origin/{HEAD}` 로 맞춘다(겹치는 파일이 없으면 더러운 트리에서도 된다). ff 가 안 되면(내 로컬 커밋과 갈라짐) 멈추고 묻는다.
2. `git log origin/{HEAD}..origin/{BASE}` 로 역방향 차이를 본다. 비었으면 2단계로.
3. 있으면 목록을 보여주고 `git merge --no-edit origin/{BASE}`. **충돌이 나면 멈추고** 사용자와 해소 방향을 정한다 — `merge --abort`·`reset`·한쪽 버리기를 임의로 하지 않는다.

**1.5단계 릴리스 컨텍스트 인지** — `hint` × `APP_RELEASE`:

| 상황 | 동작 |
|------|------|
| `hint == backend_only` | **조용히 통과.** 경고·질문 없이, config도 건드리지 않는다 |
| 앱 심사 감지(`strong_app`/`app_release_likely`/`unknown`) **AND** `APP_RELEASE == unset` | 확인 메시지를 **한 번** 띄우고 답을 config에 저장 (`config.md` §4) |
| `APP_RELEASE == true` | 묻지 않는다. 5·5.5단계에서 심사 경고 배너·엄격 정제 적용 |
| `APP_RELEASE == false` | 묻지 않고 경고 없이 진행 |

**2단계 push 전 확인** — push할 커밋 목록을 보여주고 승인받는다.
**3단계 push** — `git push origin {HEAD}`. 여기서 pull --rebase를 다시 하지 않는다(1-1 merge가 풀린다). non-fast-forward면 **강제 푸시 금지**, `git pull --rebase=merges origin {HEAD}` 후 다시 push (남의 미커밋 때문에 거부되면 멈추고 묻는다 — stash 금지). 버전은 여기서 오르지 않는다(릴리스 PR에서 확정).

> **⚠️ 단계 순서 (레이스컨디션 방지 — 반드시 지킨다)**
> RELEASE-CHANGELOG는 deploy PR `opened` 시점에 본문을 확인해 `Summary by CodeRabbit`이 **없으면 본문을 초기화**한다. 빈 본문으로 PR을 먼저 만들면 워크플로우가 끼어들어 노트가 사라진다. 그래서 **커밋 분석(4) → 노트 작성(5) → 승인(5.5) → 노트를 본문에 담아 PR 생성(6)** 순서로 PR 생성을 맨 마지막에 둔다. (워크플로우 로직은 수정하지 않는다.)

**4단계 커밋 분석** — `git log origin/{BASE}..origin/{HEAD}` (HEAD가 아니라 `origin/{HEAD}` 기준 — README 버전 워크플로우 등이 원격을 앞서게 할 수 있다). 분류·재작성 기준은 `references/release-notes.md`.

**5단계 릴리스 노트 작성** — `PROVIDER`로 분기:

| PROVIDER | 이 단계 | 5.5단계 |
|----------|---------|---------|
| `copilot`·`openai`·`gemini`·`claude`·`groq`·`mistral`·`ollama`·`coderabbit` | skill이 노트를 **선제 작성**. 워크플로우는 본문을 존중하므로 생성기를 부르지 않는다 | 진입 |
| `commit` (기본) | **한 번 묻는다**: "릴리스 노트를 제가 다듬어 드릴까요, 아니면 커밋 내역 자동 생성에 맡길까요?" → **다듬기**면 선제 작성, **맡기기**면 노트 파일 없이 6단계(빈 본문 PR — 워크플로우 fallback job이 커밋 분석으로 채움) | 다듬기=진입 / 맡기기=건너뜀 |

선제 작성이 provider와 무관하게 안전한 이유: 워크플로우는 skill이 미리 넣은 `Summary by CodeRabbit`을(`already_found`) provider 무관하게 그대로 존중한다. 유일한 예외가 `commit` "맡기기"다.
노트는 `~/.projectops/tmp/{OWNER}__{REPO}__release_notes.md`에 고정 구조로 Write한다 (`references/release-notes.md`).
**5단계 후속 — 스토어 언어별 번역 초안** — 노트 파일을 쓴 직후 `version.yml`의 `metadata.template.options.store_locales`를 Read로 확인한다. **언어가 둘 이상이면** `references/store-translations.md`를 읽고 번역 초안을 노트 파일 끝에 덧붙인다(외부 AI 호출 없이 직접 번역). 키가 없거나 하나면 이 단계는 없는 것과 같다.
> **⚠️ AGENT 필독: 노트 파일을 만든 뒤 반드시 6단계(PR 생성)까지 실행한다. 단, 곧바로 가지 않고 5.5단계부터 거친다.**

**5.5단계 승인 게이트** (문구는 `references/release-notes.md`):
- **🔒 `APP_RELEASE == true`면 `AUTO_APPROVE`와 무관하게 B(수동)**, 본문 위에 **심사 경고 배너**를 먼저 출력하고 C는 띄우지 않는다. "맡기기"여도 6단계 직전에 "자동 생성에 맡기고 앱 심사로 이어지는 배포 PR을 만들까요?"를 묻는다.
- commit "맡기기"(앱 심사 아님) → 5.5를 건너뛰고 6단계.
- **A. 자동** (`AUTO_APPROVE == true` AND `APP_RELEASE != true`) — 노트를 표시만 하고 즉시 6단계. 사용자가 "확인받게 해줘"라고 하면 6단계 **전에** config를 갱신하고 B로 전환.
- **B. 수동** (`AUTO_APPROVE == false` OR `APP_RELEASE == true`) — 노트 표시 + 승인. 수정 지시면 노트를 다시 쓰고 5.5 처음으로 (승인될 때까지 루프).
- **C. 첫 실행 자동화 제안** — B에서 승인 + `CONFIG_HAS_KEY == false` + `APP_RELEASE != true`일 때만, 6단계 직전에 한 번.

**6단계 deploy PR 생성** — `deploy-status --head`로 open deploy PR을 먼저 찾는다. **있으면 닫지 않고 재사용**해 `update-pr`로 본문만 갱신하고(새로 열면 워크플로우가 재트리거돼 본문 초기화 위험), 없으면 `create-pr`에 노트 파일 절대경로를 body로 넘긴다(맡기기면 빈 문자열). 끝나면 노트 파일을 지운다.

**7단계 automerge 검증** — `deploy-status --pr {N} --base {BASE}` 한 번으로 판정한다 (`/tmp` 즉석 Python 금지). 아래 verdict 표.

**8단계 결과 안내** — push 대상·PR 번호·노트 작성 여부·Actions 링크.

## deploy-status verdict → 다음 행동

| verdict | 의미 | 행동 |
|---------|------|------|
| `merged` | automerge 완료 | 결과 안내, 종료 |
| `waiting_for_automerge` | 정상 대기 중 (워크플로우 in_progress 포함) | **sleep 금지.** `ScheduleWakeup(delaySeconds=60)`으로 60초 간격 재확인 (보통 60초 안에 끝난다. 60초가 ScheduleWakeup 최소값). **PR 생성 후 10분이 지나도 이 verdict면** 멈추고 fix 모드를 안내한다. ScheduleWakeup 이 없는 하네스면 대기하지 말고 PR 링크와 재확인 명령(`deploy-status --pr N`)을 알리고 끝낸다 |
| `missing_coderabbit_summary` | 워크플로우는 끝났는데 본문에 `Summary by CodeRabbit`이 없음 | **즉시 fix 모드로 가지 않고 즉시 `update-pr`도 하지 않는다.** 60초 후 `deploy-status`로 한 번 더 확인하고, **두 번 연속 같은 verdict일 때만** fix 모드 안내. 한 번이면 race를 우선 가정한다 (#331 — 워크플로우 PATCH와 겹쳐 본문 사라짐이 반복된 실사고) |
| `workflow_failed` | 워크플로우 실패 | `workflow.run_url` 안내 + fix 모드로 재실행 |
| `conflict` | 머지 충돌/차단 | 충돌 상태 안내, 수동 확인 요청 |
| `no_pr` | open deploy PR 없음 | `deploy_branch.head_sha`로 이미 머지됐는지 확인 후 안내 |

## fix 모드 — 단계와 판단 (명령·문구는 `references/fix-steps.md`)

1. **상태 확인** — `deploy-status --base {BASE}`(`--pr` 없이 open deploy PR 자동 탐색). `no_pr` → 3단계로 / `merged` → 안내 후 종료 / 그 외 → `pr.number`를 `EXISTING_PR`로 기억하고 2단계로.
2. **기존 PR 닫기** — **사용자에게 확인받은 뒤에만** `update-pr ... "-" --state closed`.
3. **커밋 분석** — deploy 4단계와 같다. 곧장 fix로 들어와 `APP_RELEASE == unset`이면 이 단계 전에 deploy 1.5단계를 한 번 수행한다.
4. **노트 작성** — deploy 5단계와 같은 위치·구조(스토어 언어별 번역 초안 포함 — `references/store-translations.md`). 곧바로 5단계로 가지 않는다.
4.5. **승인 게이트** — deploy 5.5단계와 **완전히 같은** 분기(A/B/C, 앱 심사면 배너 + 수동 승인).
5. **새 PR 생성** — 노트를 본문에 담아 `create-pr`(제목 `🚀 Deploy {YYYYMMDD} (재시도)`). fix도 **PR 생성이 맨 마지막**이다.
6. **결과 안내** 후 `deploy-status --pr`로 검증한다.

## 주의사항

- **PR 생성/재시도 후 반드시 `deploy-status`로 검증한다.** 상태 확인용 Python을 `/tmp`에 즉석 생성하지 않는다.
- **PR은 노트를 본문에 담아 생성한다.** 빈 본문으로 먼저 만든 뒤 채우면 레이스컨디션으로 노트가 사라진다.
- **승인 게이트를 건너뛰지 않는다.** 자동 모드로 명시 설정된 경우만 표시 후 진행하고, 앱 심사 레포는 자동 모드여도 승인을 받는다. 안내는 자연어로만, config 키·경로를 표면화하지 않는다.
- fix 모드로 넘어가는 기준은 위 verdict 표 하나다(`missing_coderabbit_summary` 2회 연속 · `workflow_failed` · `waiting_for_automerge` 10분 초과).
- deploy PR이 이미 있으면 닫지 않고 재사용한다.
- **Windows 내부망에서 curl exit 35 (SSL 오류)**: curl 호출에 `--ssl-no-revoke` 추가 (`../references/common-rules.md` Windows 내부망 환경 섹션).
