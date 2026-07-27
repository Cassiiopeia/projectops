---
name: pro-implement
description: "Implement Mode (DO 실제 구현) - 사용자가 '/pro-implement'를 명시적으로 호출했을 때만 사용한다. 자동으로 트리거하지 않는다. plan/analyze 산출물을 입력받아 실제 코드를 작성/수정하며, 코드 자체가 결과라 별도 산출 md를 만들지 않는다. 독립적인 변경 단위는 서브에이전트에 병렬 위임 가능."
---

# Implement Mode (DO 실제 구현)

> **책임 분리**:
> - `plan` = WHAT (`docs/projectops/plan/YYYYMMDD_{이슈번호}_{제목}.md`)
> - `analyze` = HOW (`docs/projectops/analyze/YYYYMMDD_{이슈번호}_{제목}.md`)
> - `implement` = DO (실제 코드 편집 + 검증 + Finishing. 별도 산출 md 없음. 보고서 필요하면 Phase 6 후 `/report` 호출)

> ⛔ **HARD-GATE (구현 전 설계 필수)**: 다음 조건 중 하나라도 해당하면 **코드를 쓰기 전에 analyze/plan을 먼저 권장**한다:
> - 2개 이상 파일에 영향
> - 새 기능 추가 (기존 기능 수정이 아님)
> - 외부 동작·API·스키마 변경
> - 여러 구현 대안이 존재하는 설계 결정
>
> 이런 작업에 plan이 없다면 Phase 0-1에서 "analyze/plan을 먼저 돌리는 것을 **강하게 권장**합니다" 로 안내하고, 사용자가 **명시적으로 "바로 구현해"라고 지시한 경우에만** 스킵. "그냥 해" 같은 중립 응답으로는 스킵 불가.

## 시작 전

1. `references/common-rules.md`의 **작업 시작 프로토콜** 수행
2. **페르소나 로드 (필수, 이중)**: `references/personas.md`에서 공통 마인드셋 6종 + **Software Developer**(주) + **SDET**(부) 카드를 장착한다. Phase 2 구현은 Developer로(Pre-mortem·Surgical Precision), Phase 3 검증은 SDET로(Destructive Testing — '성공 증명'이 아니라 '실패의 반증') context-switching한다.
3. `/plan`, `/analyze` 산출물이 있으면 Phase 0에서 자동 로드

## 절대 규칙

1. **추측 금지.** 편집 전 대상 파일을 반드시 Read 한다. 함수가 실제로 존재하는지, 시그니처가 맞는지 확인.
2. **plan/analyze 산출물이 있으면 무조건 먼저 읽는다.** `{PROJECT_ROOT}/docs/projectops/plan/` · `analyze/`에서 가장 최근의 `.md` 파일 또는 사용자가 지정한 파일을 Read.
3. **plan을 벗어나는 변경은 사용자에게 먼저 통지한다.** "plan에 없는 부분을 만지려 합니다 — 진행할까요?"
4. **빌드/타입체크/테스트를 직접 돌린다.** "린트 통과해야 함"이라고 적기만 하면 안 된다. 실제로 실행하고 결과를 본다 (단, 내부망 환경에서 외부 패키지 설치가 필요한 명령은 사용자에게 위임).
5. **커밋하지 않는다.** 사용자가 명시적으로 요청할 때만. (글로벌 룰에 따라 git commit 자동 실행 금지)
6. **HARD-GATE 스킵 금지.** 위 HARD-GATE 조건 해당 작업에 plan 없이 진행하려면 사용자의 명시적 "plan 없이 바로 구현해" 지시가 있어야 한다.

---

## Phase 0-0 — 브랜치 가드

> **목적**: 보호 브랜치(`main`/`master`/`develop`/`*release*`/`R_*` 등) 위에서 곧장 편집이 시작되는 사고 방지.

### 0-0-1. 현재 브랜치 조회

```bash
git rev-parse --abbrev-ref HEAD
```

- 실패 시 (not a git repo) → 가드 스킵, Phase 0으로 바로 진행
- `HEAD` 가 반환됨 (detached HEAD) → 보호 브랜치로 간주 (안전 우선)

### 0-0-2. 보호 브랜치 판정

다음 중 하나라도 매치되면 보호 브랜치:

- 정확 일치: `main`, `master`, `develop`
- 패턴 매치 (case-insensitive): `*release*`, `^R_\d+$`, `.*_R_\d+$`
- `git symbolic-ref refs/remotes/origin/HEAD` 결과 (있으면)

### 0-0-3. 보호 브랜치 아니면 통과

Phase 0으로 진행.

### 0-0-4. 보호 브랜치면 3옵션 제시

```
⚠ 현재 '<branch>' 브랜치 위에 있습니다 (보호 브랜치).
어떻게 진행할까요?

1. worktree 새로 만들기 (권장)
2. 현재 위치에서 새 브랜치만 생성 (git checkout -b)
3. 그냥 이 브랜치에서 진행
```

### 0-0-5. 옵션별 분기

**옵션 1 (worktree)**:
- `init-worktree` 스킬에 위임
- 사용자가 최초 메시지에서 이미 준 정보(이슈 번호 등) 전달
- 생성 완료 후 사용자가 선택한 워크트리 경로 안내
- 메시지: "새 세션에서 `{경로}` 로 이동 후 `/implement` 다시 호출하세요"
- **현 세션 implement 흐름은 여기서 종료** (현 세션에서는 워크트리 이동 불가)

**옵션 2 (새 브랜치만)**:
1. "새 브랜치명을 알려주세요" 질문
2. `git checkout -b {입력받은_이름}` 실행
3. Phase 0으로 진행

**옵션 3 (현 브랜치에서 진행)**:
- 사용자가 3을 선택하면 바로 Phase 0으로 진행
- 재확인 없음 (사용자가 이미 선택했으므로)

---

## Phase 0 — 입력 수집

### 0-1. plan/analyze 자동 로드

**흐름**: `plan → analyze → implement`

**먼저** `docs/projectops/` 하위 두 폴더를 스캔한다. 사용자가 `/implement`를 직접 불렀어도 이 스캔을 먼저 한다.

```
docs/projectops/plan/     → plan 산출물 (.md)
docs/projectops/analyze/  → analyze 산출물 (.md)
```

현재 요청과 관련된 파일인지 날짜·제목·내용으로 판단. 관련 없으면 무시.

| 상태 | 행동 |
|------|------|
| analyze.md 있음 | HOW 계획 완료. analyze.md 읽고 구현 시작. "analyze(`{경로}`)를 읽었습니다. 구현을 시작합니다." 한 줄 알림 |
| plan.md만 있음 | HOW 없음. `analyze` 스킬 자동 호출해 HOW 구체화 → analyze 완료 후 구현 시작 |
| 아무것도 없음 | HARD-GATE 조건 충족 작업이면 `plan` 자동 호출 → analyze → implement 순. 단순 작업이면 사용자 확인 후 바로 진행 |
| 사용자가 파일 직접 지정 | 그 파일 사용 (위 판단 스킵) |

> **판단 원칙**: 파일이 있어도 날짜가 오래됐거나 맥락이 다르면 무시. 애매하면 사용자에게 보여주고 판단 위임.

### 0-2. 컨텍스트 추출

plan/analyze를 읽고 다음을 머리에 정리:
- 변경 대상 파일 목록
- 각 변경의 "왜"(이유 — 나중에 대안 발견 시 plan 의도와 비교 기준)
- 검증 방법(plan에 명시된 시나리오)
- 의사결정 로그(이미 결정된 트레이드오프 — 다시 흔들지 말 것)

---

## Phase 1 — 작업 단위 분해 (TaskCreate)

analyze.md의 "변경 파일 목록" 표(§1)를 그대로 TaskCreate에 등록한다. 한 행 = 한 task.

각 task는 다음 중 하나:
- **순차 task**: 이전 변경에 의존 (예: 모델 변경 → 그걸 쓰는 서비스 변경)
- **병렬 task**: 독립적 (예: 서로 다른 페이지의 UI 수정)

병렬 task가 2개 이상이면 **서브에이전트 병렬 위임을 검토** (Phase 2-B).

---

## Phase 2 — 구현 실행

### 2-A. 직접 구현 (기본 경로)

순차 task 또는 메인 컨텍스트 안에서 처리할 작업.

각 task마다:

1. **TaskUpdate → in_progress**
2. **대상 파일 Read** (편집 전 무조건. 이미 읽었어도 최신 상태인지 재확인)
3. **편집 (Edit / Write)** — *Developer: Surgical Precision*
   - 기존 코드 스타일을 따른다 (들여쓰기, 따옴표, 명명 규칙)
   - **필요하고 관련된 부분만 외과적으로 수정한다.** 무관한 블록을 일괄 변경하지 않는다 — regression·merge conflict·불필요한 코드 churn 최소화.
   - plan에 없는 "개선"을 끼워 넣지 않는다
   - **Pre-mortem**: 편집 전 "이 코드가 미래에 실패한다면 원인은?"을 자문하고 방어 로직(null/경계/예외)을 함께 설계한다
   - 주석은 로직이 자명하지 않은 곳에만
4. **즉시 검증** — 작은 단위로 (편집 → 빌드/타입체크 → 다음 편집). 한꺼번에 10개 파일 수정하고 마지막에 확인하지 말 것.
5. **TaskUpdate → completed**

**plan 범위 밖 문제 발견 시 처리**: 편집 중 "이왕 건드리는 김에 이것도 고쳐야겠다"는 충동이 들어도 **즉흥적으로 손대지 않는다**. 대신:
1. 발견 내용을 메모리에 보관 (Phase 6 Finishing 후 사용자에게 별건으로 보고)
2. 현재 task를 계획대로 마무리
3. 그 task 완료 후 사용자에게 **별건으로** 보고

### 2-B. 서브에이전트 병렬 위임 (선택)

다음 모든 조건을 만족할 때만 사용:
- 작업이 **2개 이상**이고 서로 **독립적** (같은 파일을 만지지 않고, 순서 의존이 없음)
- 각 작업이 명확한 입력/출력 명세를 가짐 (서브에이전트는 우리 대화 컨텍스트가 없음)
- 대규모 탐색이나 반복 패턴 변경 (예: "10개 파일에 같은 임포트 추가")

위임 프롬프트 작성 시 반드시 포함:
- 변경 대상 파일의 절대 경로
- 변경 전/후 예시 (스타일까지 보여줌)
- 검증 명령 (있으면)
- "⚠ **절대 `git commit` / `git push` 하지 말 것** — 글로벌 룰: 사용자가 커밋 컨벤션 준 경우만 커밋"
- "**plan에 없는 추가 변경 금지**"
- "**완료 선언 전 검증 명령 실제 실행 필수** — '통과될 것 같다' 금지. 실행 결과 출력 그대로 보고"
- "끝나면 변경 파일 목록과 핵심 diff 요약을 100자 이내로 보고"
- "한국어로 응답하시오"

서브에이전트 결과를 받으면 메인 컨텍스트에서 **병합 검증**(전체 빌드/타입체크) 한 번 더 돌린다.

> 단일 짧은 작업에 서브에이전트를 쓰지 말 것 — 오히려 컨텍스트와 시간만 낭비한다.

---

## Phase 3 — 검증 (실제로 명령 실행) — *SDET: Destructive Testing*

> **SDET 페르소나 전환**: 검증의 목표는 '성공 증명'이 아니라 **'실패의 반증'**이다. happy path만 보지 말고, 이 변경을 깨뜨릴 **invalid input·경계값·실패 모드를 최소 1개 의도적으로 시도**한다. 시스템이 거기서 안전하게 실패(또는 방어)하는지 확인한다. (단순 버그픽스면 핵심 경계 1개 시도로 갈음 — Fast-Track)

체크리스트로 끝내지 말고, 실제 명령을 돌린다. 결과 출력은 메모리 보관 → Phase 6에서 PR 설명/report에 사용.

| 검증 종류 | 실행 (예시) | 비고 |
|-----------|------------|------|
| 타입 체크 | `tsc --noEmit`, `mypy`, `dart analyze` | 외부망 필요 시 사용자 위임 |
| 단위 테스트 | `npm test`, `pytest`, `mvn test` | plan에 명시된 시나리오 우선 |
| 린트/포맷 | `eslint`, `ruff`, `dart format` | 포맷터는 항상 돌림 |
| 수동 시나리오 | plan의 "검증 방법"에 적힌 단계 | 사용자가 직접 수행할 항목은 명시 |

> **내부망 환경 주의**: `npm install`, `pub get` 등 외부 패키지 다운로드가 필요한 명령은 실행하지 말고 사용자에게 위임. 글로벌 룰에 명시됨.

검증 실패 시:
1. 에러 메시지를 그대로 본다 (요약하지 말고)
2. 원인을 한 가지로 좁힌다 (추측 금지 → Read로 확인)
3. 같은 실패를 두 번 반복하면 멈추고 사용자에게 보고

### ⛔ 완료 선언 금지 패턴

다음 표현은 실제 검증 출력 없이 절대 사용 금지:
- "통과될 것 같습니다" / "문제없을 것으로 보입니다"
- "should pass" / "looks good" / "잘 될 것 같아요"
- 체크리스트만 채우고 명령 미실행

올바른 패턴:
```
[실행] mvn test -pl module-name
[출력] Tests run: 42, Failures: 0, Errors: 0, Skipped: 0
→ "테스트 42개 통과 확인됨"
```

완료 선언 = 실제 실행 결과 인용. 예외 없음.

---

## Phase 4 — 작업 중 발견 사항 메모 (메모리만, 산출 파일 없음)

implement는 별도 산출물 md를 만들지 않는다. 코드 자체가 결과.

다만 작업 중 다음 정보는 메모리에 보관해 Phase 6(Finishing)에서 사용:
- **변경 파일 목록** (PR 설명·report 호출 시 사용)
- **검증 결과 출력** (실제 명령 출력 그대로)
- **[REVIEW_LOG] (SDET Devil's Advocate)**: 시도한 파괴적 검증(invalid input·경계값·실패 모드)과 그 결과 — Phase 6에서 사용자에게 보고
- **plan/analyze와 다르게 진행한 부분** (있으면)
- **관련 문제 발견** (plan 범위 밖, 별건 처리 권장 이슈)

변경 보고서가 필요하면 Phase 6 완료 후 `/report` 스킬 호출 — 별도 산출물 분리.

---

## Phase 5 — Self-Review

방금 작성한 변경에 대해 `references/self-review-checklist.md`의 **implement 체크리스트** 적용. 문제 발견 시 인라인 수정 후 Phase 6 진행.

---

## 우선순위 (충돌 시)

1. **plan/사용자 의도 준수** — "더 좋은 방법"이 보여도 임의로 바꾸지 말 것
2. **동작하는 코드** — 기능 요구사항 충족
3. **기존 스타일 일관성** — 들여쓰기/명명/패턴
4. **읽기 쉬움** — 복잡한 추상화보다 직설적 코드
5. **최적화** — 측정 없이 최적화하지 말 것

---

## Phase 6 — Finishing (모든 태스크 완료 후)

> superpowers finishing-a-development-branch 패턴 + SUH GitHub 환경 특화.

**진입 조건**: 모든 Phase 2 태스크 completed + Phase 3 검증 통과. 미충족 시 이 Phase 진입 금지.

### Step 1: 최종 테스트 검증

빌드/타입체크/주요 테스트 실제 실행. 출력 그대로 인용.

실패 시:
```
테스트 실패 — Finishing 진입 불가.
실패 내용: {출력 그대로}
수정 후 Phase 3부터 다시 진행하세요.
```

### Step 2: 환경 감지 + 변수 보관

```bash
GIT_DIR=$(git rev-parse --git-dir)
GIT_COMMON=$(git rev-parse --git-common-dir)
WORKTREE_PATH=$(git rev-parse --show-toplevel)
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
BASE_BRANCH=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||' || echo "main")
MAIN_ROOT=$(git -C "$GIT_COMMON/.." rev-parse --show-toplevel)
```

판정:
- `GIT_DIR != GIT_COMMON` → worktree 환경 (옵션 2/4에서 worktree 정리)
- `BASE_BRANCH` → 옵션 2 머지 대상 (감지 실패 시 사용자에게 질문)
- `CURRENT_BRANCH`, `WORKTREE_PATH`, `MAIN_ROOT` → Step 4에서 사용

### Step 3: 옵션 제시

```
구현이 완료되었습니다. 어떻게 진행할까요?

1. GitHub PR 생성 (권장)
2. 로컬 브랜치 머지
3. 보관 (나중에 처리)
4. 폐기

번호를 선택하세요.
```

### Step 4: 옵션별 실행

**옵션 1 — GitHub PR 생성**:
- `github` 스킬 호출 (⚠ `gh pr create` 직접 호출 금지 — common-rules의 전용 스킬 경유 강제)
- PR 제목: `[#{GitHub 이슈번호}] {plan 한 줄 요약}` (이슈 없으면 한 줄 요약만)
- worktree 유지 (PR 피드백 반영 위해)

**옵션 2 — 로컬 머지**:
```bash
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)
cd "$MAIN_ROOT"
git checkout <base-branch>
git pull
git merge <feature-branch>
```
머지 후 테스트 재검증 → 통과 시 worktree 정리:
```bash
git worktree remove "$WORKTREE_PATH"
git worktree prune
git branch -d <feature-branch>
```

**옵션 3 — 보관**:
"브랜치 `{name}` 보관됨. worktree: `{path}`"
worktree 유지.

**옵션 4 — 폐기**:
```
⚠ 다음을 영구 삭제합니다:
- 브랜치: {name}
- 커밋: {목록}
- worktree: {path} (있으면)

확인하려면 'discard' 를 입력하세요.
```
확인 후:
```bash
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)
cd "$MAIN_ROOT"
git worktree remove "$WORKTREE_PATH"   # worktree 있을 때만
git worktree prune
git branch -D <feature-branch>
```

### Step 5: 변경 보고서 안내 (선택)

옵션 1~4 실행 후 사용자에게 한 줄 안내:
> "변경 보고서가 필요하면 `/report` 호출하면 됩니다 (Phase 4에서 메모리 보관한 변경 파일 목록 + 검증 결과 활용)."

자동 호출 안 함 — 사용자 선택.

### Finishing 안티 패턴

| ❌ | ✅ |
|---|---|
| 테스트 실패 상태로 옵션 제시 | Step 1 통과 후에만 Step 3 진입 |
| `gh pr create` 직접 사용 | `github` 스킬 호출 |
| 폐기 확인 없이 브랜치 삭제 | 'discard' typed confirmation |
| worktree 안에서 `git worktree remove` | MAIN_ROOT로 cd 후 실행 |
| 옵션 1/3 후 worktree 삭제 | 옵션 2/4만 worktree 정리 |
| `impl.md` 산출물 자동 생성 | implement는 산출물 없음. `/report` 별도 호출 |

---

## 안티 패턴 (구현 단계)

| ❌ | ✅ |
|---|---|
| "구현 시작합니다" 하고 plan/analyze 안 읽기 | Phase 0에서 무조건 plan/analyze Read |
| 10개 파일 수정 후 마지막에 빌드 | 작은 단위 → 즉시 검증 → 다음 |
| 검증 체크리스트만 채우고 명령 안 돌림 | 실제 명령 실행, 결과 그대로 기록 |
| 한 번에 끝내려고 plan에 없는 리팩터 끼워 넣기 | 발견하면 사용자에게 통지 후 결정 |
| 짧은 작업에도 서브에이전트 위임 | 2개 이상 독립 작업일 때만 |
| 실패해도 "통과"라고 기록 | 실패는 실패로, 원인 분석 후 보고 |
| happy path만 검증하고 완료 선언 | SDET — 파괴적 검증(경계/invalid) 1개 이상 시도 |
| 무관한 블록까지 일괄 수정 | Surgical Precision — 관련 부분만 외과적 수정 |
| 자동 git commit | 절대 금지 (글로벌 룰) |
| `npm install` 자동 실행 | 내부망 룰: 사용자 위임 |

## 다음 단계

구현 완료 후 → 사용자 수동 검증 → (선택) `/review` 코드 리뷰 → (선택) `/report` 변경 보고서 → 사용자가 직접 커밋 또는 `/commit` 호출
