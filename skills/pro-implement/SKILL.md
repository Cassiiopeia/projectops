---
name: pro-implement
description: "Implement Mode (DO 실제 구현) - 사용자가 '/pro-implement'를 명시적으로 호출했을 때만 사용한다. 자동으로 트리거하지 않는다. plan/analyze 산출물을 입력받아 실제 코드를 작성/수정하며, 코드 자체가 결과라 별도 산출 md를 만들지 않는다. 독립적인 변경 단위는 서브에이전트에 병렬 위임 가능."
---

# Implement Mode (DO 실제 구현)

> **책임 분리**: `plan` = WHAT · `analyze` = HOW · `implement` = DO (실제 코드 편집 + 검증 + Finishing).
> implement는 **별도 산출 md를 만들지 않는다** — 보고서가 필요하면 Phase 6 후 `/report`.

> ⛔ **HARD-GATE (구현 전 설계 필수)**: 아래 중 하나라도 해당하면 코드를 쓰기 전에 analyze/plan을 **강하게 권장**한다.
> 2개 이상 파일 영향 · 새 기능 추가 · 외부 동작·API·스키마 변경 · 구현 대안이 여럿인 설계 결정.
> 사용자가 **명시적으로 "plan 없이 바로 구현해"** 라고 한 경우에만 스킵. "그냥 해" 같은 중립 응답으로는 스킵 불가.

## 단계 → 자세히

| 단계 | 하는 일 | 자세히 |
|---|---|---|
| 0-0 브랜치 가드 | 보호 브랜치 위면 worktree / 새 브랜치 / 그대로 3옵션 | `references/branch-guard.md` |
| 0 입력 수집 | `find-inputs` 로 plan·analyze 자리를 받아 Read | 아래 |
| 1~2 분해·구현 | TaskCreate, 외과적 편집, 독립 작업은 서브에이전트 위임 | `references/execution.md` |
| 3 검증 | 실제 명령 실행 + 파괴적 검증 1개 이상 | `references/execution.md` |
| 4~5 메모·Self-Review | 변경 목록·검증 출력 보관, `../references/self-review-checklist.md` implement 체크리스트 | `references/execution.md` |
| 6 Finishing | PR / 로컬 머지 / 보관 / 폐기 | `references/finishing.md` |

## 시작 전

1. `../references/common-rules.md`의 **작업 시작 프로토콜** 수행
2. **페르소나 로드 (필수, 이중)**: `../references/personas.md`에서 공통 마인드셋 6종 + **Software Developer**(주) + **SDET**(부).
   Phase 2 구현은 Developer(Pre-mortem·Surgical Precision), Phase 3 검증은 SDET(Destructive Testing — '성공 증명'이 아니라 '실패의 반증')로 전환한다.

## 절대 규칙

1. **추측 금지.** 편집 전 대상 파일을 반드시 Read 한다. 함수 존재·시그니처를 확인.
2. **plan/analyze 산출물이 있으면 무조건 먼저 읽는다.** 자리는 `find-inputs` 가 알려준다.
3. **plan을 벗어나는 변경은 먼저 통지한다.** "plan에 없는 부분을 만지려 합니다 — 진행할까요?" 범위 밖 문제는 메모해 두고 별건으로 보고.
4. **빌드/타입체크/테스트를 직접 돌린다.** 적기만 하지 않는다. 외부 패키지 설치가 필요한 명령(`npm install`·`pub get`)은 사용자에게 위임(내부망).
5. **커밋하지 않는다.** 사용자가 명시적으로 요청할 때만.
6. **HARD-GATE 스킵 금지.**
7. **완료 선언 = 실제 실행 결과 인용.** "통과될 것 같다"·"looks good" 금지.

## Phase 0-0 — 브랜치 가드 (요약)

`git rev-parse --abbrev-ref HEAD` 로 현재 브랜치를 본다 (git 레포 아니면 스킵, detached HEAD 는 보호로 간주).
보호 브랜치: `main`·`master`·`develop`·`*release*`·`R_<숫자>`·`origin/HEAD`.
**개발 브랜치 직행 레포**(레포 `CLAUDE.md`·`AGENTS.md`에 develop 직행 규칙)에서 현재가 개발 브랜치
(`version.yml`의 `metadata.deploy_branch`, 없으면 `develop`)면 묻지 않고 통과한다 — `main`/`master`/기본 브랜치는 예외 없음.
그 밖의 보호 브랜치면 3옵션을 제시한다 → `references/branch-guard.md`.

## Phase 0 — plan/analyze 자동 로드

흐름은 `plan → analyze → implement`. 사용자가 직접 불렀어도 이 단계를 먼저 한다.
**경로를 박아 쓰지 않는다** (#623 — 산출물 루트를 옮긴 팀에서 빈 폴더를 뒤져 "계획 없음"으로 오판한다).

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-implement; ROOT="$PROJECT_ROOT"
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPTS/implement_cli.py" find-inputs
```

돌려주는 `inputs.plan.latest` · `inputs.analyze.latest` 를 Read 한다. 둘 다 비어 있으면 `next` 안내를 따른다.
현재 요청과 관련된 파일인지 날짜·제목·내용으로 판단하고, 관련 없으면 무시. 애매하면 보여주고 사용자에게 맡긴다.

| 상태 | 행동 |
|------|------|
| analyze.md 있음 | 읽고 구현 시작. "analyze(`{경로}`)를 읽었습니다. 구현을 시작합니다." 한 줄 알림 |
| plan.md만 있음 | `analyze` 스킬 호출해 HOW 구체화 → 완료 후 구현 |
| 아무것도 없음 | HARD-GATE 작업이면 `plan` → `analyze` → implement. 단순 작업이면 사용자 확인 후 진행 |
| 사용자가 파일 직접 지정 | 그 파일 사용 (위 판단 스킵) |

## Phase 1~5 — 핵심 결정 규칙

- analyze.md의 "변경 파일 목록" 표를 그대로 TaskCreate (한 행 = 한 task).
- **편집 → 즉시 검증 → 다음 편집.** 10개 파일 고치고 마지막에 빌드하지 않는다.
- 서브에이전트 위임은 **독립 작업 2개 이상**일 때만. 위임 프롬프트 필수 항목(절대 경로, 전/후 예시, 커밋 금지, plan 밖 변경 금지, 검증 실제 실행)은 `references/execution.md`. 결과를 받으면 메인에서 병합 검증을 한 번 더 돌린다.
- 검증 실패: 에러를 그대로 보고 → 원인 하나로 좁힘(Read) → **같은 실패 2회면 멈추고 보고.**
- Phase 5: `../references/self-review-checklist.md` 의 implement 체크리스트 적용, 문제는 인라인 수정.

**우선순위 (충돌 시)**: plan/사용자 의도 준수 > 동작하는 코드 > 기존 스타일 일관성 > 읽기 쉬움 > 최적화(측정 없이 하지 않음).

## Phase 6 — Finishing (요약)

진입 조건: 모든 task completed + 검증 통과. 옵션 1 PR(권장) · 2 로컬 머지 · 3 보관 · 4 폐기('discard' 입력 확인) → `references/finishing.md`.

- **머지·PR 대상(`BASE_BRANCH`)은 개발(릴리스 소스) 브랜치다** — `version.yml` `metadata.deploy_branch`, 없으면 `develop`. `origin/HEAD` 로 잡지 않는다.
- **`BASE_BRANCH`가 `main`/`master`이거나 기본(배포) 브랜치와 같으면 옵션 2(로컬 머지)를 막는다** — 기본 브랜치는 릴리스 PR(`/pro-changelog-deploy`)로만 갱신된다. 옵션 1만 안내.
- PR 은 `github` 스킬로 만든다 (`gh pr create` 금지). 제목은 `pro-github` PR 제목 규칙.
- 로컬 머지는 **공유 작업 트리에서 checkout 하지 않는다** — `MAIN_ROOT` 가 이미 `BASE_BRANCH` 일 때만, `git pull --rebase` 로 통합.
- worktree 정리는 옵션 2/4만, `MAIN_ROOT` 로 이동해서.
- 끝나면 "변경 보고서가 필요하면 `/report`" 한 줄 안내 (자동 호출 안 함).

## 다음 단계

구현 완료 → 사용자 수동 검증 → (선택) `/review` → (선택) `/report` → 사용자가 직접 커밋 또는 `/commit`
