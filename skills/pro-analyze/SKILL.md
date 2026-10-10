---
name: pro-analyze
description: "Analyze Mode (HOW 구체화) - 사용자가 '/pro-analyze'를 명시적으로 호출했을 때만 사용한다. 자동으로 트리거하지 않는다. plan 문서(WHAT)를 기반으로 '어떻게 만들 것인가'를 파일·함수·라인 단위로 구체화하며 placeholder를 금지한다. 코드 수정 금지."
---

# Analyze Mode (HOW 구체화)

> **핵심 원칙**: HOW(어떻게, 어느 파일/함수/라인)만 다룬다. plan.md(WHAT)가 없으면 먼저 만든다.
> **흐름**: `plan → analyze → implement`. 각 변경 행에 파일+함수+라인 필수 (writing-plans 패턴).

> ⛔ **HARD-GATE — No Placeholders**: 다음이 analyze 문서에 있으면 즉시 실패:
> - "TBD", "TODO", "나중에", "적절히", "필요 시", "유사하게"
> - 파일 경로 없는 변경 항목 · 함수명/라인 없는 변경 항목 · Before/After 코드 없는 코드 변경 항목

## 무엇을 하려는가 → 어디서 → 자세히

| 하려는 것 | 어디서 | 자세히 |
|---|---|---|
| 저장 경로 받기 | `analyze_cli.py get-output-path` | 아래 "스크립트 찾기" |
| 문서 템플릿 · 병렬 표시 · 안티 패턴 | Phase 2 | `references/analyze-template.md` |
| 시작 전 질문 · 저장 전 승인 | 전 과정 | `../references/approval-and-questions.md` |
| 제출 전 자체검토 | Phase 3 | `../references/self-review-checklist.md` |

## 시작 전

- `../references/common-rules.md`의 **작업 시작 프로토콜** + **분석 전용 스킬 규칙** 적용.
- **페르소나 로드 (필수, 이중)**: `../references/personas.md`에서 공통 마인드셋 6종 + **System Architect**(주) + **Reviewer**(부).
  Architect로 HOW를 설계한 뒤 Reviewer로 전환해 그 계획을 '신뢰할 수 없는 외부인의 취약한 코드'로 보고 **적대적으로 깬다**(Red Team Mindset).
  "정상 동작한다"가 아니라 "어떻게 깨지는가"를 본다.
- **승인 게이트 (#526)**: `../references/approval-and-questions.md`를 따른다 — 결과가 크게 달라지는 항목만 한 번에 하나씩 묻고(답이 이미 있으면 안 묻는다),
  저장 전 내용을 보여 승인받는다(자동 모드면 요약만 안내 후 저장). 첫 실행 1회 "앞으로 확인 없이 진행할지" 묻고 기억한다. 설정 키·파일 경로는 사용자에게 노출하지 않는다.

## 스크립트 찾기 — 한 번만

**Bash 도구는 호출마다 상태가 초기화된다.** 한 번 찾은 뒤 출력된 실제 경로를 이후 블록에 값으로 써넣는다.
경로는 직접 조립하지 않는다 (`../references/doc-output-path.md`).

```bash
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-analyze; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPTS/analyze_cli.py" get-output-path analyze --title "{제목}"
```

결과 JSON 의 `path` 에 저장하고, `output_root` 아래에서 기존 산출물을 찾는다. 실패하면 `code` 로 판단한다:

| code | 다음 행동 |
|---|---|
| `git_not_found` | git 저장소 루트에서 다시 실행. 저장소가 아니면 사용자에게 저장 위치를 묻는다 |
| `unknown_skill_id` | 위치 인자를 `analyze` 로 고쳐 다시 부른다 |
| `bad_args` | `available_subcommands` 를 보고 인자를 고친다 |

## 절대 규칙

- **코드 수정 금지.** Read/Grep/Glob/Bash(읽기)만. 마지막 analyze 문서 1개 작성만 허용.
- **추측으로 HOW 쓰지 않는다.** 파일을 실제로 읽고 함수명·라인을 인용한다.
- **plan.md 없으면 시작 안 한다.** Phase -1에서 처리.
- **승인 없이 implement로 넘어가지 않는다.** Phase 4에서 사용자 명시 승인 후에만.

## Phase -1 — 사전 상태 확인 (가장 먼저)

파일 존재 여부만 판단한다(읽기는 Phase 0). **경로를 박아 쓰지 않는다** — get-output-path 가 돌려준 `output_root` 아래
`plan/`·`analyze/` 하위 `.md` 를 본다 (#623). implement는 별도 md를 만들지 않는다 — 코드 자체가 결과.
현재 요청과 관련된 파일인지 날짜·제목·내용으로 판단한다.

| 상태 | 행동 |
|------|------|
| analyze.md 있음 | "analyze가 이미 완료됐습니다(`{경로}`). `/implement`로 넘어가면 됩니다." 안내 후 종료 |
| plan.md만 있음 | Phase 0 진행 |
| 아무것도 없음 | `plan` 스킬 호출. plan 완료 후 Phase 0부터 재시작 |

## Phase 0 — plan.md 로드

plan.md를 읽고 작업 종류(버그/새 기능/리팩터링/마이그레이션) · Must 요구사항 · 성공 기준 · 제약을 정리한다.
"이 plan 기반으로 HOW를 구체화하겠습니다: {한 줄 요약}" 알린 뒤 Phase 1.

## Phase 1 — 코드베이스 정찰 (사실 수집, 추측 금지)

- [ ] 진입점 파일/함수/라우트 찾았는가? (Grep으로 함수명·이벤트명 검색)
- [ ] 변경이 닿을 모든 호출자/의존자 나열했는가?
- [ ] 비슷한 기존 패턴이 있는가? (있으면 그 스타일을 따른다)
- [ ] 관련 테스트가 있는가? 어디에?
- [ ] 데이터 모델/스키마 변경이 있는가?
- [ ] **Pre-mortem**: "이 계획이 미래에 깨진다면 원인은?" — 호출자 영향·동시성·하위호환·경계값 탐색 (→ §4 위험&완화 + §7 `[REVIEW_LOG]` 입력)

> 탐색 범위가 크면 Explore 서브에이전트에 위임. 메인 컨텍스트에 raw grep 결과를 쌓지 않는다.

## Phase 2 — 변경 계획 작성

`references/analyze-template.md`의 템플릿(변경 파일 표 · 태스크별 Before/After · 위험 · 검증 · `[REVIEW_LOG]` · `[ALTERNATIVES_CONSIDERED]`)으로 쓴다.
독립 태스크는 `[병렬]` 표시. 저장 전 `../references/common-rules.md`의 **파일 저장 직전 자체검토 프로토콜** 적용.

## Phase 3 — Self-Review

방금 쓴 파일을 `Read`로 다시 읽고 `../references/self-review-checklist.md`의 **analyze 체크리스트** 적용. 문제는 인라인 수정.

## Phase 4 — 제출 (HARD-GATE)

> "Analyze가 `{경로}`에 작성되었습니다. 검토 후 수정할 부분 있으면 말씀해주세요.
> 승인하시면 구현 방식을 선택해주세요:
> 1. **Subagent-Driven (권장)** — 태스크별 서브에이전트 위임
> 2. **Inline** — 현재 세션 순차 실행"

**종료 조건**: 사용자 명시적 승인 + 방식 선택 ("1", "subagent", "2", "inline", "implement" 등).
❌ 사용자 답변 전 implement 자동 호출 금지. 승인 후 → `/implement`.
