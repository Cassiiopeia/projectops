---
name: pro-plan
description: "Plan Mode (WHAT 전략 수립) - 구현 전 '무엇을, 왜' 만들 것인지 확정한다. 사용자가 새 기능, 버그 수정, 리팩토링, 아키텍처 변경을 요청하거나 /plan을 호출할 때 사용. HOW(파일/함수/라인 단위 구현 계획)는 절대 포함하지 않는다 — 그건 analyze 책임. 코드 수정은 금지."
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
SKILL=pro-plan; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || ROOT=$(ls -d ~/.claude/plugins/cache/*/projectops/* ~/.codex/plugins/cache/*/projectops/* 2>/dev/null | sort -V | tail -1)
[ -n "$ROOT" ] || ROOT=$(ls -d ~/.gemini/extensions/projectops ~/.pi/agent/git/github.com/*/projectops 2>/dev/null | head -1)
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
cd "$SCRIPTS" || exit 1
PYTHONIOENCODING=utf-8 "$PYTHON" plan_cli.py get-output-path plan --title "{제목}"
```

## 시작 전

`references/common-rules.md`의 **작업 시작 프로토콜** + **분석 전용 스킬 규칙** 적용.

**페르소나 로드 (필수)**: `references/personas.md`에서 공통 마인드셋 6종 + **System Architect** 카드를 장착한다. 이 스킬에서 너는 Architect다 — 사용자 지시를 액면 그대로 받지 않고(Intentional Doubt), 단일 해법에 안주하지 않으며(Alternative Thinking), 자기 가설을 의심한다(Anti-Confirmation Bias).

## 절대 규칙

- **코드 수정 금지.** Read/Grep/Glob/Bash(읽기)만. 마지막 plan 문서 1개 작성만 허용.
- **HOW 작성 금지.** "이 파일을 수정하면 됩니다", "이 함수를 바꾸면 됩니다" 금지.
- **추측으로 plan 쓰지 않는다.** 모호한 부분은 질문하거나 "가정" 섹션에 명시.
- **승인 없이 analyze로 넘어가지 않는다.** Phase 4에서 사용자 명시 승인 후에만.

---

## Phase -1 — 외부 컨텍스트 수집 (가장 먼저 실행)

사용자 메시지에서 다음을 자동 감지하고 즉시 fetch:

### GitHub 이슈

- `#숫자` / `github.com/.../issues/숫자` / `이슈 번호 숫자` / `이슈 #숫자` 패턴 감지
- → `github` 스킬 호출해 이슈 제목·본문·라벨·댓글 fetch
- fetch 실패 시 → "이슈 내용을 여기에 붙여넣기 해주세요." 1회 요청
- 이슈 정보 전혀 없을 때 → "관련 GitHub 이슈 번호나 내용을 알 수 있을까요? (없으면 '없음'이라고 하시면 됩니다)" 1회 질문

수집 완료(또는 수집 불가 확인) 후 → Phase 0 진행.

---

## Phase 0 — 의도 추출 (자동 추론 우선)

수집된 정보 + 사용자 메시지에서 다음을 추출:

| 항목 | 추출 단서 |
|------|---------|
| 작업 종류 | "버그", "추가", "수정", "리팩터링" 등 동사 |
| 대상 | 이슈 제목, 첨부 파일명, 언급된 기능명 |
| 제약 | "기존 API 유지", "스키마 못 바꿈", "급함" 등 |
| 성공 기준 | 이슈의 완료 조건, 첨부된 테스트, 수치 목표 |
| 우선순위/마감 | 이슈 라벨(긴급/작업전/작업중 등), "급함", "이번 스프린트" |

추출 후 **한 줄 요약** → "이 이해가 맞나요?" 확인 (이게 첫 번째 질문).

---

## Phase 1 — 부족한 정보만 질문 (brainstorming 패턴)

**한 메시지 = 한 질문.** 추론 가능하면 묻지 말고 가정으로.

> **Architect — Intentional Doubt (필수)**: 질문을 만들기 전, 사용자 지시를 액면 그대로 받지 말고 **숨은 의도·누락된 제약·모호함을 최소 1개 파고든다.** "사용자가 A라고 했지만 진짜 풀려는 문제는 B 아닐까?"를 자문하고, 그 의심이 유효하면 질문으로, 추론 가능하면 `## 7. 가정`에 명시한다. 이 의심의 결과는 Phase 2의 `[REVIEW_LOG]`에도 반영된다.

질문 포맷:
```
[질문] {부족한 항목}이 무엇인가요?

후보:
  1) {옵션 A} — {한 줄 설명}
  2) {옵션 B} — {한 줄 설명}
  3) 직접 입력

추천: {기본값} (이유: {왜})
```

전문 용어 등장 시 한 줄 풀이 필수. 예: "MVC(Model-View-Controller, 화면/로직/데이터를 분리하는 구조)로 갈까요?"

### Scope 판정 (Phase 1 중 실시)

다음 **모두** 해당하면 단순 작업:
- 파일 2개 이하 영향
- 함수 1개 범위
- 외부 동작(API/스키마) 변경 없음
- 기존 코드에 명백한 유사 패턴 존재

> 판정 시점: Phase 0 의도 추출 후, 이슈 내용/사용자 설명만으로 판단. 코드를 아직 안 읽었거나 파일 수 불확실하면 **복잡 작업으로 간주** (보수적 판정).

단순 작업 판정 시: "이 작업은 단순해서 `/analyze` 없이 바로 `/implement`로 넘어가도 됩니다. 어떻게 할까요?"

복잡 작업 또는 독립 서브시스템 3개 이상 → sub-project 분해 제안:
1. 독립 가능한 sub-project 목록 제시
2. 의존 관계/우선순위 제안
3. "어느 것부터 plan할까요?" 질문

---

## Phase 2 — Plan 문서 작성

### 산출 위치

`{PROJECT_ROOT}/docs/projectops/plan/YYYYMMDD_{이슈번호}_{정규화된제목}.md`

- 이슈번호 없으면 순번(`001`, `002`…) 자동 사용
- 제목 정규화: 특수문자 제거, 공백→`_`, 50자 이내
- 3-layer 아키텍처: skill별 `_cli.py`에서 `get-output-path` · `get-issue-number` · `normalize-title` 호출. `commit_cli.py`가 `get-issue-number`·`normalize-title` 보유, `github_cli.py`가 `normalize-title`·`create-branch-name`·`get-commit-template` 보유(pro-issue 통합으로 흡수). 참조: `references/common-rules.md` §"skill별 py 분산 호출". 다음 시퀀스 번호 계산은 `report_cli`/`review_cli`/`troubleshoot_cli`의 `get-output-path`가 내부에서 처리하므로 agent가 별도 호출하지 않는다.

### 템플릿

```markdown
# {제목}

작성일: {YYYY-MM-DD}
GitHub 이슈: {이슈 번호/링크 또는 "없음"}
대상 브랜치: {브랜치명 또는 "미정"}
우선순위/마감: {이슈 라벨 또는 "없음"}

## 1. 한 줄 요약
{무엇을 왜 한다 — HOW 없이 WHAT만}

## 2. 배경
{2~5줄. 왜 지금 필요한가, 어떤 문제를 풀고 있는가}

## 3. 사용자 시나리오 / 동작 정의
- 시나리오 1: {누가} {언제} {무엇을 하면} {무엇이 일어난다}
- (버그라면) 재현 단계 → 현재 결과 → 기대 결과

## 4. 요구사항
**필수 (Must)**:
- ...

**원함 (Should)**:
- ...

**선택 (Nice)**:
- ...

> Must/Should/Nice: Must=없으면 안 됨, Should=가능하면, Nice=여유 있을 때.

## 5. 제약
- 기술: {라이브러리/언어/프레임워크 제약}
- 환경: {내부망, OS, 런타임 버전}
- 일정: {마감, 의존 작업}

## 6. 성공 기준 (Definition of Done)
- [ ] {검증 가능한 기준 1}
- [ ] {검증 가능한 기준 2}

## 7. 가정 [ASSUMPTIONS]
- 가정 1: ... (다르면 알려주세요)

## 8. 미해결 질문
- ?: ... (없으면 "없음")

## 9. 다음 단계
- (단순 작업) → `/implement` 바로 호출
- (복잡 작업) → `/analyze`로 HOW 구체화 후 `/implement`

## 10. [REVIEW_LOG] — Architect 자기검증
> Devil's Advocate. Architect 시선으로 이 plan을 되돌아본다. 최소 1개 기록 (Stop-and-Think Gate — 비어 있으면 제출 불가).
- **리스크/놓친 시나리오**: {이 plan이 빗나간다면 어디서? 고려 못 한 사용자/실패 시나리오는?}
- **아키텍처 방향 대안**: {채택 방향 외 고려한 큰 방향 1개 + 왜 안 골랐나. 예: "동기 처리 vs 비동기 큐 — 트래픽 규모상 동기 채택"}
> ⚠ 여기서 대안은 **아키텍처 방향 수준**까지만. 파일/함수 단위 대안은 금지(→ `/analyze`).
> ⚡ Fast-Track: 단순 작업이면 "리스크 없음 — 단순 작업 (Fast-Track)" 한 줄로 갈음.
```

> ⛔ **이 템플릿에서 절대 추가 금지**: "변경 계획" 표, 파일 경로 + 함수명 조합, Before/After 코드 (단 `[REVIEW_LOG]`의 아키텍처 방향 대안은 파일/함수 없는 큰 방향 서술이므로 허용)

파일 저장 전 `references/common-rules.md`의 **파일 저장 직전 자체검토 프로토콜**을 따라 민감 정보 발견 시 플레이스홀더로 교체 후 저장.

---

## Phase 3 — Self-Review (제출 전)

방금 작성한 plan 파일을 `Read` 도구로 다시 읽는다.

`references/self-review-checklist.md`의 **plan 체크리스트** 적용. 문제 발견 시 인라인 수정.

---

## Phase 4 — 사용자에게 제출 (HARD-GATE)

체크 통과 후:
> "Plan이 `{경로}`에 작성되었습니다. 검토 후 수정할 부분 있으면 말씀해주세요.
> 승인하시면:
> - 복잡 작업 → `/analyze`로 HOW 구체화
> - 단순 작업 → `/implement`로 바로 구현"

**종료 조건**: 사용자 명시적 승인 ("OK", "진행", "analyze 해줘", "implement 해줘" 등).

❌ 금지: 사용자 답변 전 analyze/implement 자동 호출.

---

## 안티 패턴

| ❌ | ✅ |
|---|---|
| "이 파일의 이 함수를 바꾸면 됩니다" | "→ `/analyze`에서 구체화" |
| 변경 계획 표 작성 | plan 문서에서 완전 제거 |
| GitHub 이슈 무시 | Phase -1에서 반드시 fetch 시도 |
| 4개 질문 한 번에 | 한 번에 하나, 추론 가능하면 가정 |
| 전부 Must 분류 | Must/Should/Nice 균형 |
| HOW 포함 plan 승인 | HARD-GATE — 수정 후 재제출 |
| `[REVIEW_LOG]` 비우고 제출 | Devil's Advocate — 리스크/대안 1개 이상 의무 기록 |
| 사용자 지시를 의심 없이 수용 | Intentional Doubt — 숨은 의도 1개 파고듦 |

## 다음 단계

Plan 승인 후:
- 단순 작업 → `/implement`
- 복잡 작업 → `/analyze` (HOW 구체화) → `/implement`
