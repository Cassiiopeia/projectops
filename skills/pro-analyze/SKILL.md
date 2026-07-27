---
name: pro-analyze
description: "Analyze Mode (HOW 구체화) - 사용자가 '/pro-analyze'를 명시적으로 호출했을 때만 사용한다. 자동으로 트리거하지 않는다. plan 문서(WHAT)를 기반으로 '어떻게 만들 것인가'를 파일·함수·라인 단위로 구체화하며 placeholder를 금지한다. 코드 수정 금지."
---

# Analyze Mode (HOW 구체화)

> **핵심 원칙**: HOW(어떻게, 어느 파일/함수/라인)만 다룬다. plan.md(WHAT)가 없으면 먼저 만든다.
> **흐름**: `plan → analyze → implement`
> **writing-plans 패턴**: 각 변경 행에 파일+함수+라인 필수. placeholder(TBD/TODO/"적절히") 금지.

> ⛔ **HARD-GATE — No Placeholders**: 다음이 analyze 문서에 있으면 즉시 실패:
> - "TBD", "TODO", "나중에", "적절히", "필요 시", "유사하게"
> - 파일 경로 없는 변경 항목
> - 함수명/라인 없는 변경 항목
> - Before/After 코드 없는 코드 변경 항목

## 승인 게이트 · 시작 전 질문 (필수)

이 skill은 md 산출물을 만든다. **`references/approval-and-questions.md`를 반드시 따른다** (#526).

요약:

1. **시작 전** — 결과물이 크게 달라지는 항목만 한 번에 하나씩 묻는다. 사용자 입력에 이미 답이 있으면 묻지 않는다.
2. **저장 전** — 내용을 보여주고 승인을 받는다. 자동 모드로 설정된 저장소는 요약만 안내하고 바로 저장한다.
3. **첫 실행 시 1회** — "앞으로 확인 없이 진행할지"를 묻고 그 답을 기억한다.
4. 사용자에게 설정 키 이름이나 파일 경로를 노출하지 않는다.

저장 경로는 직접 조립하지 않고 아래로 받는다 (`references/doc-output-path.md`):

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-analyze; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || ROOT=$(ls -d ~/.claude/plugins/cache/*/projectops/* ~/.codex/plugins/cache/*/projectops/* 2>/dev/null | sort -V | tail -1)
[ -n "$ROOT" ] || ROOT=$(ls -d ~/.gemini/extensions/projectops ~/.pi/agent/git/github.com/*/projectops 2>/dev/null | head -1)
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
cd "$SCRIPTS" || exit 1
PYTHONIOENCODING=utf-8 "$PYTHON" analyze_cli.py get-output-path analyze --title "{제목}"
```

## 시작 전

`references/common-rules.md`의 **작업 시작 프로토콜** + **분석 전용 스킬 규칙** 적용.

**페르소나 로드 (필수, 이중)**: `references/personas.md`에서 공통 마인드셋 6종 + **System Architect**(주) + **Reviewer**(부) 카드를 장착한다. 한 스킬 안에서 context-switching한다 — Architect로 HOW를 설계하고, 그다음 Reviewer로 전환해 그 계획을 '신뢰할 수 없는 외부인의 취약한 코드'로 보고 **적대적으로 깬다**(Red Team Mindset). "정상 동작한다"가 아니라 "어떻게 깨지는가"를 본다.

## 절대 규칙

- **코드 수정 금지.** Read/Grep/Glob/Bash(읽기)만. 마지막 analyze 문서 1개 작성만 허용.
- **추측으로 HOW 쓰지 않는다.** 파일을 실제로 읽고 함수명·라인을 인용한다.
- **plan.md 없으면 시작 안 한다.** Phase -1에서 자동 처리.
- **승인 없이 implement로 넘어가지 않는다.** Phase 4에서 사용자 명시 승인 후에만.

---

## Phase -1 — 사전 상태 확인 (가장 먼저 실행)

> **Phase -1 역할**: 파일 존재 여부만 판단. 실제 파일 읽기는 Phase 0에서.

`docs/projectops/` 하위 스캔:

```
docs/projectops/plan/     → plan 산출물 (.md)
docs/projectops/analyze/  → analyze 산출물 (.md)
```

> implement는 별도 산출물 md를 만들지 않음 — 코드 자체가 결과.

현재 요청과 관련된 파일인지 날짜·제목·내용으로 판단.

| 상태 | 행동 |
|------|------|
| analyze.md 있음 | "analyze가 이미 완료됐습니다(`{경로}`). `/implement`로 넘어가면 됩니다." 안내 후 종료 |
| plan.md만 있음 | Phase 0으로 진행 (plan.md 실제 읽기는 Phase 0에서) |
| 아무것도 없음 | `plan` 스킬 자동 호출. plan 완료 후 Phase 0부터 재시작 |

---

## Phase 0 — plan.md 로드 및 의도 파악

plan.md를 읽고 다음을 정리:
- 작업 종류 (버그 수정 / 새 기능 / 리팩터링 / 마이그레이션)
- 핵심 요구사항 (Must 항목)
- 성공 기준
- 제약 사항

한 줄로 "이 plan 기반으로 HOW를 구체화하겠습니다: {한 줄 요약}" 알림 후 Phase 1 진행.

---

## Phase 1 — 코드베이스 정찰 (사실 수집)

추측 금지. 실제 파일을 읽고 인용.

체크리스트:
- [ ] 진입점 파일/함수/라우트 찾았는가? (Grep으로 함수명·이벤트명 검색)
- [ ] 변경이 닿을 모든 호출자/의존자 나열했는가?
- [ ] 비슷한 기존 패턴이 코드베이스에 있는가? (있으면 그 스타일 따라야 함)
- [ ] 관련 테스트가 있는가? 어디에?
- [ ] 데이터 모델/스키마 변경이 있는가?
- [ ] **Pre-mortem**: "이 변경 계획이 미래에 깨진다면 원인은 무엇일까?" — 호출자 영향·동시성·하위호환·경계값을 능동적으로 탐색했는가? (이 답은 §4 위험&완화 + §7 `[REVIEW_LOG]`의 입력이 된다)

> 탐색 범위가 크면 Explore 서브에이전트에 위임. 메인 컨텍스트에 raw grep 결과 쌓지 말 것.

---

## Phase 2 — 변경 계획 작성 (writing-plans 패턴)

### 산출 위치

`{PROJECT_ROOT}/docs/projectops/analyze/YYYYMMDD_{이슈번호}_{정규화된제목}.md`

- 이슈번호 없으면 순번(`001`, `002`…) 자동 사용
- 제목 정규화: 특수문자 제거, 공백→`_`, 50자 이내
- 3-layer 아키텍처: skill별 `_cli.py`에서 `get-output-path` 호출 (예: `report_cli.py`, `review_cli.py`, `note_cli.py`). 참조: `references/common-rules.md` §"skill별 py 분산 호출"

### No Placeholders 규칙

상단 HARD-GATE 참조. Phase 3 Self-Review에서 체크.

### 병렬 태스크 식별

태스크 간 의존 관계 확인:
- **순차**: 앞 태스크 결과에 의존 (예: 모델 변경 → 그걸 쓰는 서비스 변경)
- **병렬**: 독립적 (예: 서로 다른 모듈의 변경, 같은 파일 안 건드림) → 표에 `[병렬]` 표시

### 산출물 템플릿

````markdown
# {제목} — HOW 계획

작성일: {YYYY-MM-DD}
참조: docs/projectops/plan/{파일명}.md
GitHub 이슈: {이슈 번호 또는 없음}

## 1. 변경 파일 목록

| # | 파일 | 함수/위치 (라인) | 무엇을 | 실행 순서 |
|---|------|----------------|-------|---------|
| 1 | `path/to/File.java` | `methodName()` (L42~67) | A를 B로 교체 | 순차 |
| 2 | `path/to/Other.java` | `otherMethod()` (L88) | X 필드 추가 | [병렬] |

## 2. 태스크별 상세

### Task 1: {이름}

**파일**: `path/to/File.java`
**함수**: `methodName()` (line 42~67)
**변경 이유**: {plan Must 항목과 연결}

**Before**:
```java
// 현재 코드 (실제로 읽은 것)
public void methodName() {
    // 기존 로직
}
```

**After**:
```java
// 변경 후 코드
public void methodName() {
    // 새 로직
}
```

**검증**: {구체적 명령 또는 수동 확인 단계}
예: `mvn test -pl module-name -Dtest=ClassName#testMethodName`

---

### Task 2: {이름}
...

## 3. 현재 상태 (코드 인용)

실제로 읽은 파일/함수 요약:
- `path/to/File.java:42` — `methodName()`: 현재 X를 한다
- `path/to/Other.java:88` — `otherMethod()`: Y 역할

## 4. 위험 & 완화 [RISK]

- **[RISK]**: {Red Team이 찾은 결함/edge case. 예: 기존 호출자 영향, 동시성 경합} → **완화**: {예: 하위 호환 오버로드 추가}

## 5. 검증 방법

- [ ] {입력값 또는 시나리오} → {기대 결과}
- [ ] {회귀 확인 대상} — {확인 명령}
- [ ] {파괴적 검증: invalid input/경계값} → {기대되는 안전한 실패}

## 6. 다음 단계

구현 방식을 선택하세요:

**1. Subagent-Driven (권장)** — `/implement` 호출 시 태스크별 서브에이전트 + Self-Review 자동 진행
**2. Inline** — 현재 세션에서 순차 실행

병렬 태스크 있음: Task {N}, Task {M} → Subagent-Driven 선택 시 병렬 dispatch 가능.

## 7. [REVIEW_LOG] — Reviewer 적대적 검증
> Devil's Advocate. Reviewer 페르소나로 전환해 위 HOW 계획을 적대적으로 공격한다. 최소 1개 기록 (Stop-and-Think Gate — 비어 있으면 제출 불가).
- **[REVIEW_LOG]**: {이 계획의 결함/우회 가능 시나리오/극한 조건 실패 1개 이상. "정상 동작 확인"이 아니라 "어떻게 깨지는가". 발견 시 §1 표·§2 태스크에 반영했는가?}
> ⚡ Fast-Track: 단순 작업이면 "리스크 없음 — 단순 작업 (Fast-Track)" 한 줄로 갈음.

## 8. [ALTERNATIVES_CONSIDERED] — 기각한 대안
> 채택한 HOW 외에 고려했다가 기각한 구현 대안. 최소 1개 (Stop-and-Think Gate). analyze는 HOW 단계이므로 구현 수준 대안 비교가 정당하다.
- **기각 대안 1**: {대안 HOW} → **기각 이유**: {왜 채택안이 더 나은가}
> ⚡ Fast-Track: 단순 작업이면 "단일 자명 해법 — Fast-Track" 한 줄로 갈음.
````

파일 저장 전 `references/common-rules.md`의 **파일 저장 직전 자체검토 프로토콜** 적용.

---

## Phase 3 — Self-Review (제출 전)

방금 작성한 analyze 파일을 `Read` 도구로 다시 읽는다.

`references/self-review-checklist.md`의 **analyze 체크리스트** 적용. 문제 발견 시 인라인 수정.

---

## Phase 4 — 사용자에게 제출 (HARD-GATE)

> "Analyze가 `{경로}`에 작성되었습니다. 검토 후 수정할 부분 있으면 말씀해주세요.
> 승인하시면 구현 방식을 선택해주세요:
> 1. **Subagent-Driven (권장)** — 태스크별 서브에이전트 위임
> 2. **Inline** — 현재 세션 순차 실행"

**종료 조건**: 사용자 명시적 승인 + 방식 선택 ("1", "subagent", "2", "inline", "implement" 등).

❌ 금지: 사용자 답변 전 implement 자동 호출.

---

## 안티 패턴

| ❌ | ✅ |
|---|---|
| "이 클래스를 수정하면 됩니다" (파일만, 함수/라인 없음) | `path/File.java:42` — `method()` 명시 |
| Before/After 없이 "X를 Y로 변경" | 실제 코드 블록 포함 |
| TBD/TODO 남기기 | 모르면 사용자에게 질문, 가정이면 명시 |
| plan.md 안 읽고 analyze 작성 | Phase 0에서 반드시 Read |
| 코드 안 읽고 영향 범위 추정 | Read/Grep으로 호출자 직접 확인 |
| 모든 태스크 순차로만 표시 | 독립 태스크는 `[병렬]` 표시 |
| `[REVIEW_LOG]`·`[ALTERNATIVES_CONSIDERED]` 비우고 제출 | Devil's Advocate — 결함 1개 + 기각 대안 1개 의무 |
| 자기 계획을 "잘 됐다"고 통과 | Red Team — "어떻게 깨지는가"로 적대 검증 |

## 다음 단계

Analyze 승인 후 → `/implement` (Subagent-Driven 또는 Inline 선택)
