---
name: pro-plan
description: "Plan Mode (WHAT 전략 수립) - 사용자가 '/pro-plan'을 명시적으로 호출했을 때만 사용한다. 자동으로 트리거하지 않는다. 구현 전 '무엇을, 왜' 만들 것인지 확정하며, HOW(파일/함수/라인 단위 구현 계획)는 포함하지 않는다. 코드 수정 금지."
---

# Plan Mode (WHAT 전략 수립)

> **핵심 원칙**: WHAT(무엇을, 왜)만 확정. HOW(어떻게, 어느 파일)는 절대 금지.
> **흐름**: `plan → analyze → implement`
> **질문 규칙**: 한 메시지 = 한 질문. 사용자 답변 대기. 추론 가능하면 묻지 말고 "가정:" 처리.

> ⛔ **HARD-GATE**: 아래 내용을 plan 문서에 포함하면 즉시 실패:
> - 파일 경로 + 함수명 + 라인 번호 조합 (HOW 영역)
> - "변경 계획" 표 또는 구현 순서 표
> - Before/After 코드 예시
> HOW가 필요하면 "→ `/analyze`에서 구체화하겠습니다" 한 줄로 대체.

## 무엇을 하려는가 → 어디서 → 자세히

| 하려는 것 | 어디서 | 자세히 |
|---|---|---|
| 저장 경로 받기 | `plan_cli.py get-output-path` | 아래 "스크립트 찾기" |
| 질문 포맷 · 문서 템플릿 · 안티 패턴 | Phase 1~2 | `references/plan-template.md` |
| 시작 전 질문 · 저장 전 승인 | 전 과정 | `../references/approval-and-questions.md` |
| 제출 전 자체검토 | Phase 3 | `../references/self-review-checklist.md` |

## 시작 전

- `../references/common-rules.md`의 **작업 시작 프로토콜** + **분석 전용 스킬 규칙** 적용.
- **페르소나 로드 (필수)**: `../references/personas.md`에서 공통 마인드셋 6종 + **System Architect**. 사용자 지시를 액면 그대로
  받지 않고(Intentional Doubt), 단일 해법에 안주하지 않으며(Alternative Thinking), 자기 가설을 의심한다(Anti-Confirmation Bias).
- **승인 게이트 (#526)**: `../references/approval-and-questions.md`를 따른다 — 결과가 크게 달라지는 항목만 한 번에 하나씩 묻고(답이 이미 있으면 안 묻는다),
  저장 전 내용을 보여 승인받는다(자동 모드면 요약만 안내 후 저장). 첫 실행 1회 "앞으로 확인 없이 진행할지" 묻고 기억한다. 설정 키·파일 경로는 사용자에게 노출하지 않는다.

## 스크립트 찾기 — 한 번만

**Bash 도구는 호출마다 상태가 초기화된다.** 한 번 찾은 뒤 출력된 실제 경로를 이후 블록에 값으로 써넣는다.
경로는 직접 조립하지 않는다 (`../references/doc-output-path.md`).

```bash
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-plan; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPTS/plan_cli.py" get-output-path plan --title "{제목}"
```

결과 JSON 의 `path` 에 저장한다(이슈번호·순번·제목 정규화는 CLI 가 처리). 실패하면 `code` 로 판단한다:

| code | 다음 행동 |
|---|---|
| `git_not_found` | git 저장소 루트에서 다시 실행. 저장소가 아니면 사용자에게 저장 위치를 묻는다 |
| `unknown_skill_id` | 위치 인자를 `plan` 으로 고쳐 다시 부른다 |
| `bad_args` | `available_subcommands` 를 보고 인자를 고친다 |

## 절대 규칙

- **코드 수정 금지.** Read/Grep/Glob/Bash(읽기)만. 마지막 plan 문서 1개 작성만 허용.
- **HOW 작성 금지.** "이 파일을 수정하면 됩니다", "이 함수를 바꾸면 됩니다" 금지.
- **추측으로 plan 쓰지 않는다.** 모호한 부분은 질문하거나 "가정" 섹션에 명시.
- **승인 없이 analyze로 넘어가지 않는다.** Phase 4에서 사용자 명시 승인 후에만.

## Phase -1 — 외부 컨텍스트 수집 (가장 먼저)

- `#숫자` / `github.com/.../issues/숫자` / `이슈 번호 숫자` / `이슈 #숫자` 패턴 감지 → `github` 스킬로 이슈 제목·본문·라벨·댓글 fetch
- fetch 실패 → "이슈 내용을 여기에 붙여넣기 해주세요." 1회 요청
- 이슈 정보 전혀 없음 → "관련 GitHub 이슈 번호나 내용을 알 수 있을까요? (없으면 '없음'이라고 하시면 됩니다)" 1회 질문

수집 완료(또는 수집 불가 확인) 후 Phase 0.

## Phase 0 — 의도 추출 (자동 추론 우선)

| 항목 | 추출 단서 |
|------|---------|
| 작업 종류 | "버그", "추가", "수정", "리팩터링" 등 동사 |
| 대상 | 이슈 제목, 첨부 파일명, 언급된 기능명 |
| 제약 | "기존 API 유지", "스키마 못 바꿈", "급함" 등 |
| 성공 기준 | 이슈의 완료 조건, 첨부된 테스트, 수치 목표 |
| 우선순위/마감 | 이슈 라벨(`priority: urgent`/`status: todo`/`status: in progress` 등, 한글 `긴급`/`작업전`/`작업중`), "급함", "이번 스프린트" |

추출 후 **한 줄 요약** → "이 이해가 맞나요?" 확인 (첫 번째 질문).

## Phase 1 — 부족한 정보만 질문 (brainstorming 패턴)

**한 메시지 = 한 질문.** 포맷은 `references/plan-template.md` §질문 포맷. 전문 용어는 한 줄 풀이.

> **Architect — Intentional Doubt (필수)**: 질문 전, 사용자 지시의 숨은 의도·누락된 제약·모호함을 **최소 1개** 파고든다.
> "A라고 했지만 진짜 풀려는 문제는 B 아닐까?" — 유효하면 질문으로, 추론 가능하면 `## 7. 가정`에 명시. 결과는 `[REVIEW_LOG]`에도 반영.

**Scope 판정** — 다음 **모두** 해당하면 단순 작업: 파일 2개 이하 · 함수 1개 범위 · 외부 동작(API/스키마) 변경 없음 · 명백한 유사 패턴 존재.
Phase 0 직후 이슈·설명만으로 판단하고, 코드를 안 읽었거나 파일 수가 불확실하면 **복잡 작업으로 간주**(보수적).

- 단순 → "이 작업은 단순해서 `/analyze` 없이 바로 `/implement`로 넘어가도 됩니다. 어떻게 할까요?"
- 복잡 또는 독립 서브시스템 3개 이상 → sub-project 분해 제안: 목록 → 의존/우선순위 → "어느 것부터 plan할까요?"

## Phase 2 — Plan 문서 작성

`references/plan-template.md`의 템플릿(요약·배경·시나리오·Must/Should/Nice·제약·DoD·가정·미해결·다음 단계·`[REVIEW_LOG]`)으로 쓴다.
템플릿에 변경 계획 표·파일+함수 조합·Before/After를 **추가하지 않는다**.
저장 전 `../references/common-rules.md`의 **파일 저장 직전 자체검토 프로토콜** — 민감 정보는 플레이스홀더로 교체.

## Phase 3 — Self-Review

방금 쓴 파일을 `Read`로 다시 읽고 `../references/self-review-checklist.md`의 **plan 체크리스트** 적용. 문제는 인라인 수정.

## Phase 4 — 제출 (HARD-GATE)

> "Plan이 `{경로}`에 작성되었습니다. 검토 후 수정할 부분 있으면 말씀해주세요.
> 승인하시면:
> - 복잡 작업 → `/analyze`로 HOW 구체화
> - 단순 작업 → `/implement`로 바로 구현"

**종료 조건**: 사용자 명시적 승인 ("OK", "진행", "analyze 해줘", "implement 해줘" 등).
❌ 사용자 답변 전 analyze/implement 자동 호출 금지.
