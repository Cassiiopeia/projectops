---
name: pro-skill-creator
description: 표준 skill을 생성(create)·리뷰(review)·개선(improve)할 때 사용한다. 트리거 발화 — "skill 만들어줘", "skill 추가해줘", "이거 skill로 만들자", "이 skill 리뷰해줘", "skill 검증해줘", "skill 개선해줘", "skill 고쳐줘", "create a skill", "review this skill". 호출 즉시 사용자 의도를 create/review/improve 셋 중 하나로 분류한 뒤, 모드별 Phase를 순서대로 실행한다. 한 번에 한 질문·자동 추론 우선·하드코딩 금지·설정 분리 등 8대 원칙을 기계적으로 강제한다.
version: 2.2
---

# Skill Creator

이 문서는 **글이 아니라 의사결정 절차**다. agent는 위에서 아래로 실행하고, 각 Phase의 "종료 조건"이 충족될 때까지 다음 Phase로 넘어가지 않는다.

> **Agent 판단 원칙** (전체 공통): 애매하면 억지 추론 금지 — 즉시 사용자에게 질문. 한 메시지 = 한 질문. 이미 준 정보는 다시 묻지 않음. 위험한 작업은 실행 전 확인. → `../../common/CONFIG_RULES.md` §10

> **호출 즉시 agent가 할 일**: §1에서 **모드를 판정**한다 → `TaskCreate` 등록 → 해당 모드의 Phase 1부터 시작. 분석/설명 글을 먼저 쓰지 않는다.

---

## 0. 절대 규칙 (Hard Constraints)

어느 Phase·어느 모드에서도 위반해선 안 되는 규칙. 위반 감지 시 즉시 멈추고 사용자에게 알린다.

| ID | 규칙 | 왜 중요한가 |
|----|------|-----------|
| H1 | 한 메시지에 사용자에게 던지는 질문은 **최대 1개** | 여러 질문을 한 번에 던지면 사용자는 보통 한두 개만 답하고 나머지를 놓친다. agent는 나머지를 "답변 거부"로 오해하고 잘못된 추측으로 진행한다. |
| H2 | 사용자가 이미 준 정보는 다시 묻지 않는다 | 사용자는 "방금 말했는데 또 묻나" 하고 신뢰를 잃는다. 이미 제공된 정보를 추출하지 못한 agent의 실패다. |
| H3 | 실제 도메인/IP/이메일/사번/회사명을 SKILL.md 본문에 박지 않는다 | 그 skill이 다른 프로젝트로 이동했을 때 다른 사람 계정·회사 정보가 박혀 있으면 쓸 수 없다. 플레이스홀더 사용. |
| H4 | 사용자별로 다른 값은 SKILL.md가 아니라 별도 config 파일에 둔다 | 팀원마다 PEM 키, PAT, 계정이 다르다. SKILL.md는 공유되는 문서이므로 개인 값이 들어가면 충돌한다. |
| H5 | 전문 용어는 처음 등장 시 한 줄 설명을 붙인다 | skill을 처음 쓰는 팀원이 용어에서 막히면 skill을 아예 안 쓴다. 한 줄 설명이 있으면 돌아서 문서 찾지 않아도 된다. |
| H6 | UI 안내는 메뉴 경로 + 필드명까지 구체화 | "거기서 찾으세요" 는 시간이 지나면 UI 바뀌어서 무용지물. "제어판 → 외부 액세스 → DDNS 탭 → 호스트이름 컬럼"처럼 쪼개면 UI 변경에도 사용자가 근처를 찾을 수 있다. |

나머지 2개 원칙(자동 추론 우선·유연한 입력)은 Phase 1의 절차로 강제된다.

---

## 1. 모드 판정 (Mode Dispatch)

agent는 호출 즉시 사용자의 의도를 아래 3개 모드 중 하나로 분류한다. 애매하면 사용자에게 한 번 묻고 진행한다.

| 모드 | 트리거 예시 발화 | 진입 Phase |
|------|----------------|-----------|
| **CREATE** | "skill 만들어줘", "이 작업 skill로 만들자", "~에 대한 skill 추가" | §2 |
| **REVIEW** | "이 skill 리뷰해줘", "어디 고칠 거 있어?", "평가해줘", "점검해줘" | §3 |
| **IMPROVE** | "리뷰 결과 반영해줘", "1~4번만 고쳐줘", "skill 개선해줘 + 기존 skill 지정" | §4 |

**판정 우선순위**:
1. 사용자가 특정 **기존 skill 경로**를 지적했고 "리뷰"/"점검"이라는 말 → REVIEW
2. 사용자가 특정 **기존 skill 경로**를 지적했고 "개선"/"고쳐" 라는 말 → IMPROVE
3. 위 둘 다 아니면서 새 기능 제안 → CREATE
4. 애매하면 한 번만 묻는다: "새로 만들까요, 기존 skill을 리뷰/개선할까요?"

**모드 판정 후 TaskCreate 등록** (모드별 task 이름이 다르니 해당 섹션 참조).

---

## 2. 모드 CREATE — 새 skill 생성

### Task 등록 (Initialization)

```
[create] Phase 0: 브레인스토밍 (무엇을·왜 만들까)
[create] Phase 1: 의도 흡수 + 자동 추출
[create] Phase 2: 부족한 정보만 한 번에 하나씩 질문
[create] Phase 3: SKILL.md 작성 (+ config/scripts 템플릿)
[create] Phase 4: 8대 원칙 self-review
[create] Phase 5: 트리거 발화 검증 (샘플 5개)
[create] Phase 6: 사용자 보고 + 합의
[create] Phase 7: 실제 호출 동작 확인
```

### Phase 0 — 브레인스토밍 (무엇을·왜 만들까)

| 메타 | 값 |
|------|-----|
| 목표 | Scope·접근법·경계·기존 skill과의 관계를 사용자와 합의 |
| 입력 | 사용자의 첫 요청 |
| 출력 | "무엇을 만들지" 한 줄 합의 + 선택된 접근법 |
| 종료 조건 | Scope 적절 / 접근법 1개 선택 / 경계 명확 / 중복 정리 (4개 모두) |
| 다음 | Phase 1 |

짧아도 괜찮지만 **건너뛰지 말 것**. 5분 설계가 나중 수백 번의 호출 품질을 좌우한다. "너무 간단해서 설계 필요 없다"는 anti-pattern.

절차 (Step A~E)·2~3개 접근법 제시 포맷·scope 판정 기준은 `references/phase0_brainstorming.md` 참조.

**건너뛸 수 있는 조건**: 사용자가 이미 scope·접근법·기존 skill과의 관계를 명시한 경우. 건너뛸 때도 "Phase 0 스킵 이유: ~" 를 한 줄 알리고 Phase 1로.

### Phase 1 — 의도 흡수 + 자동 추출

| 메타 | 값 |
|------|-----|
| 목표 | 사용자가 이미 준 정보를 추출하고 부족한 항목 식별 |
| 출력 | 아래 6개 슬롯 상태표 (메모리에만 유지, 사용자에게 통째로 보여주지 않음) |
| 종료 조건 | 6개 슬롯이 "값 있음" 또는 "추론 가능" 으로 모두 채워짐 |
| 다음 | 빈 슬롯 0개 → Phase 3 / 1개 이상 → Phase 2 |

6개 슬롯: `purpose`, `triggers`, `inputs`, `outputs`, `auto_extract`, `pain_points`.
상세 정의·추론 규칙은 `references/phase1_slots.md` 참조.

**사용자에게는 한 줄 의도 요약만 제시하고 "이 이해가 맞나요?"로 확인**. 슬롯 표를 통째로 보여주지 않는다 — 정보 과다로 사용자가 압도된다.

### Phase 2 — 부족한 정보만 한 번에 하나씩 질문

한 메시지 = 한 슬롯. 질문 형식은 `references/phase2_question_format.md` 참조. 사용자가 한 번에 여러 슬롯의 답을 함께 주면 모두 받아들이고 빈 슬롯만 다시 확인.

Phase 2를 건너뛸 수 있는 경우: Phase 1 종료 시 빈 슬롯이 없으면 곧장 Phase 3.

### Phase 3 — SKILL.md 작성 + 스크립트/config 템플릿

| 메타 | 값 |
|------|-----|
| 목표 | 8대 원칙 만족하는 SKILL.md 초안을 디스크에 작성 |
| 출력 | SKILL.md (필수) + config.json.example (선택) + scripts/ (선택) |
| 종료 조건 | 파일 존재 + 필수 섹션 포함 |

**Frontmatter 필수 필드**: `name`, `description`, `version` (선택이지만 권장).

**본문 골격**:

```markdown
# {Skill Name}

## 언제 사용하는가
- 트리거 시나리오 1
- 트리거 시나리오 2
- (반대로 "이때는 쓰지 마라"도 1줄 명시 권장)

## 사용 전 준비 (config 파일이 필요한 skill에만)

## 작업 흐름
### Phase 0 — 정보 수집
### Phase 1 — 실행
### Phase 2 — 검증/보고

## 자주 묻는 함정 (실경험 기반)
```

**스크립트/config가 필요한 경우** `templates/` 폴더의 템플릿을 복사해서 사용:
- `templates/config.json.example` — 계정/URL 분리 설정 표준
- `templates/python_cli_script.py` — stdlib만 쓰는 CLI 스크립트 뼈대 (UTF-8 콘솔, SSL opt-out, 구조화 에러 포함)

### Phase 4 — 8대 원칙 self-review

방금 쓴 파일을 **반드시 `Read` 도구로 다시 읽고** 8개 검사를 한 줄씩 채운다. "방금 썼으니 안 봐도 안다"는 금지 — Read 강제.

검사 표·조치 방법은 `references/phase4_checklist.md` 참조. 한 항목이라도 FAIL이면 즉시 수정 후 재검사. 위반 0건 될 때까지.

### Phase 5 — 트리거 발화 검증

description이 실제로 원하는 상황에서 호출되는지 간이 검증한다. 별도 CLI 실행은 필요 없고, **agent 스스로 시뮬레이션**한다.

1. **should-trigger 예시 3개** 작성 — 사용자가 실제로 할 법한 발화. "skill 이름"을 직접 안 부르는 표현이어야 의미 있음.
2. **should-not-trigger 예시 2개** 작성 — 근처 주제지만 이 skill은 호출되면 안 되는 경우.
3. 각 예시에 대해 "지금 description만 보고 이 skill을 호출할까?" 자문. 직관이 3 PASS / 2 PASS(5/5)면 통과. 하나라도 틀리면 description을 고쳐서 다시.

> 공식 skill-creator의 `run_loop.py` 로 정량 최적화도 가능하지만, 대부분 이 수준이면 충분하다. 상세는 `references/trigger_optimization.md`.

### Phase 6 — 사용자 보고 + 합의

표준 보고 형식은 `references/phase6_report_format.md`. 8개 원칙 결과표가 전부 ✅일 때만 사용자에게 보고한다. ⚠️/❌ 있으면 Phase 4로 돌아간다.

### Phase 7 — 실제 호출 동작 확인 (선택이지만 강권)

skill을 쓸 것이라면 사용자에게 "지금 한 번 호출해서 테스트해볼까요?"를 제안한다. 실제로 써보면 description 누락, 스크립트 에러, 설정 불일치가 즉시 드러난다. 사용자가 "나중에"라고 하면 스킵.

---

## 3. 모드 REVIEW — 기존 skill 리뷰

### Task 등록

```
[review] Phase 1: 타겟 skill 파일 읽기
[review] Phase 2: 8대 원칙 + 공식 모범사례 대조
[review] Phase 3: 우선순위별 이슈 리포트 생성
[review] Phase 4: 사용자 합의 (개선 범위 결정)
```

### Phase 1 — 타겟 skill 파일 읽기

타겟 경로를 사용자에게서 받거나 대화 문맥에서 추론한다. SKILL.md, 관련 스크립트, config 예시를 모두 `Read`로 확인. **절대 메모리로만 판단 금지**.

### Phase 2 — 대조 체크

아래 8개 + 공식 skill-creator의 4개 모범사례를 교차 적용한다.

**8대 원칙 (Phase 4 체크리스트 재사용)**: `references/phase4_checklist.md`.

**공식 skill-creator 모범사례**:

| # | 기준 | 체크 질문 |
|---|------|----------|
| a | Lean prompt | 빼도 결과에 영향 없는 문장·MUST·ALWAYS가 있는가? |
| b | Explain the why | "하지 말 것" 규칙에 이유가 붙어 있는가? 없으면 agent가 경계 케이스에서 잘못 판단. |
| c | Progressive disclosure | SKILL.md ≤ 500줄? 초과하면 references/로 분할되었는가? |
| d | Repeated work 번들화 | 여러 호출에서 반복될 로직이 scripts/로 분리되어 있는가? 아니면 매번 agent가 다시 짠다. |

### Phase 3 — 우선순위별 이슈 리포트

각 이슈를 🟥(버그급, 즉시 수정)/🟨(UX 저하, 권장)/🟩(니스 투 해브)로 분류하고 표로 정리. 각 이슈마다:

- **무엇이 문제인가** (근거: 파일·라인 인용)
- **어떻게 고치면 되는가** (구체적 패치 아이디어)
- **왜 그게 중요한가** (원칙·실제 부작용)

리포트는 기존 대화에 바로 출력. 별도 파일 만들지 않는다 (지시 없는 한).

### Phase 4 — 사용자 합의

사용자에게 "어디까지 반영할까요?" 묻는다. 선택지는:
- "1~2번만 (핵심만)"
- "전체 반영"
- "리뷰만 보고 끝"

**리뷰만 보고 끝** 이면 여기서 종료. 아니면 IMPROVE 모드로 넘어간다.

---

## 4. 모드 IMPROVE — 기존 skill 개선 적용

### Task 등록

```
[improve] Phase 1: 적용할 패치 목록 확정
[improve] Phase 2: 파일별로 Edit/Write 적용
[improve] Phase 3: 변경 사항 동작 확인 (가능한 한 실행)
[improve] Phase 4: 변경 요약 보고 + frontmatter version 증가
```

### Phase 1 — 적용할 패치 목록 확정

리뷰 리포트에서 사용자가 승인한 항목만 골라 "패치 N건" 형태의 목록을 만든다. 각 패치마다 target 파일·변경 요약·risk 레벨 표시.

**범위 제한 (targeted improvements only)**: 패치 작업 중 원래 범위 밖의 문제를 발견해도 **즉흥적으로 손대지 않는다**. 대신 리포트에 "관련 문제 발견: ~" 로 기록해두고, 현재 패치 끝난 후 사용자에게 "이것도 고칠까요?"를 묻는다.

> **이유**: "이왕 건드리는 김에..." 로 시작하는 리팩토링은 리뷰 범위를 흐려서 패치 본문에 뭐가 들어있는지 사용자가 추적 못 하게 한다. 작업 중인 코드의 문제는 고치되, 무관한 리팩토링은 별건으로.

### Phase 2 — 파일별 Edit/Write 적용

- 기존 파일 수정 → `Edit` 우선 사용 (diff 최소화)
- 새 파일 생성 → `Write`
- 여러 파일에 동일 변경 → 한 번에 하지 말고 파일 단위로 확인

### Phase 3 — 동작 확인

변경한 부분이 실행 가능한 코드·설정이면 가능한 한 **직접 호출해서 결과를 본다** (네트워크 제한으로 막히면 파싱 테스트라도). "코드가 맞을 것이다"로 넘기지 않는다.

### Phase 4 — 변경 요약 보고

| 항목 | 내용 |
|------|------|
| 적용된 패치 | 번호 · 대상 파일 · 요약 |
| 원칙 재평가 | 8대 원칙 표 업데이트 (개선된 ⭐ 표시) |
| 남은 개선 여지 | 이번에 반영 안 한 항목 / 후속 제안 |
| 버전 | frontmatter `version` 증가 (예: 1.0 → 1.1) |

---

## 5. 참고 자료 (references/)

SKILL.md 본문은 절차만 담고, 상세 템플릿·체크리스트·예시는 아래로 분리:

| 파일 | 내용 | 언제 읽는가 |
|------|------|-----------|
| `references/phase0_brainstorming.md` | Scope·접근법·경계 합의 절차 + 예시 | CREATE Phase 0 |
| `references/phase1_slots.md` | 6개 슬롯 정의·자동 추론 규칙·예시 | CREATE Phase 1 |
| `references/phase2_question_format.md` | 한 번에 하나씩 질문 포맷 + Good/Bad 예시 | CREATE Phase 2 |
| `references/phase4_checklist.md` | 8대 원칙 self-review 체크표 + 조치 방법 | CREATE Phase 4, REVIEW Phase 2 |
| `references/phase6_report_format.md` | 사용자 보고 표준 포맷 | CREATE Phase 6 |
| `references/trigger_optimization.md` | 공식 `run_loop.py` 사용법 (선택) | CREATE Phase 5 고급 |
| `references/anti_patterns.md` | 실패 패턴 모음 | agent가 막혔을 때 |
| `templates/config.json.example` | 표준 config 구조 (gitlab/jenkins/ssh 등) | CREATE Phase 3 |
| `templates/python_cli_script.py` | UTF-8·SSL·구조화 에러 처리 포함 CLI 뼈대 | CREATE Phase 3 |

---

## 6. 최종 원칙 (메타 규칙)

### 6.1 Explain the why — not ALL CAPS

agent에게 "절대 하지 마라"는 ALL CAPS보다, **"왜 그게 중요한가"** 를 한 문장으로 붙이는 편이 낫다. 모델은 똑똑하므로 이유를 알면 경계 케이스에서도 올바르게 판단한다. 규칙을 쓸 때는 항상 한 줄의 `(이유: ~)` 를 붙이는 습관.

### 6.2 Multiple choice를 우선 (객관식 > 주관식)

사용자에게 질문할 때는 가능한 한 **선택지를 제시**한다. 주관식은 사용자가 매번 생각을 짜내야 하고, 답도 제각각이라 agent가 다시 해석해야 한다. 객관식이면 사용자는 고르기만 하면 되고 agent도 분기하기 쉽다.

```
❌ "인증 방식은 뭘 쓸까요?"
✅ "인증 방식은 뭘 쓸까요?
   1) Personal Access Token (추천)
   2) ID/비밀번호
   3) 기타 직접 입력"
```

단, 사용자가 오히려 답변 폭을 좁히고 싶지 않은 경우(창의적 설계·이름 짓기 등)엔 주관식이 낫다. 상황 판단.

### 6.3 복잡도에 맞춰 분량 조절 (Scale to complexity)

skill의 모든 섹션을 같은 깊이로 쓸 필요 없다. **간단한 동작은 한 줄**, 복잡하면 200~300단어. 모든 action을 장황하게 문서화하면 사용자가 읽을 때 신호가 흐려진다.

예:
- `config-show`: "현재 설정 확인 (토큰/비번은 마스킹)" — 한 줄이면 충분
- `mr-create-from-branch`: 브랜치명 파싱 로직·타겟 자동 결정·충돌 확인 규칙 — 여러 단락 필요

### 6.4 Incremental validation — 섹션별 확인

긴 설계를 한 번에 몰아서 사용자에게 던지지 않는다. 섹션 하나 끝날 때마다 "여기까지 맞나요?" 확인. 중간에 오해가 있었다면 그 섹션만 고치면 되지, 설계 전체를 뒤엎지 않아도 된다.

Phase 0의 Step A~F도 이 원칙의 적용이다.

### 6.5 필요하면 뒤로 돌아가기 (Be flexible)

Phase 번호는 선형이지만 **고집스러운 절차는 아니다**. Phase 3 작성 중에 Phase 0의 scope가 잘못됐다고 판단되면 Phase 0로 돌아가 재합의한다. "이미 여기까지 왔으니 밀어붙이자"는 유혹을 이긴다.

돌아갈 때는 사용자에게 알린다: "Phase 3 중에 경계가 모호한 걸 발견해서 Phase 0으로 잠시 돌아가 재확인합니다."

---

이 문서는 그 습관의 결과로 짧고 Phase 중심이다. 상세는 references/에 있고, 여기서는 **"어느 Phase인지"** 와 **"종료 조건이 충족되었는가"** 두 질문만 agent가 계속 자신에게 묻게 한다.

---

## 7. 신규 skill에 Python 호출이 필요한 경우 (3-layer 표준)

신규 skill이 GitHub API·외부 시스템·서브커맨드 호출이 필요하면 **반드시 3-layer 표준을 따른다**:

1. **공유 도메인 로직 점검**: 필요한 함수가 `scripts/common/`에 이미 있나? (`gh_client`, `config`, `paths`, `title` 등). 있으면 import 재사용. 새로 작성하지 않는다.
2. **skill 전용 cli 작성**: `templates/python_cli_script.py` 골격을 복사.
   ```bash
   cp skills/pro-skill-creator/templates/python_cli_script.py skills/suh-<new>/scripts/<scope>_cli.py
   ```
3. **prog + 서브커맨드 교체**: 골격의 `<scope>_cli` 부분과 `cmd_example`을 실제 도메인으로 교체.
4. **공유 로직은 import**: `from common.<module> import ...` 형태. Layer 1 재작성 금지.
5. **SKILL.md 호출**: 표준 self-contained 5줄 패턴 (`../references/common-rules.md` §"skill별 py 분산 호출" 참조).
6. **공유 로직이 부족하면 Layer 1에 추가**: 단일 skill 전용 로직만 cli에 두고, 2개 이상 skill이 쓸 가능성이 있으면 `scripts/common/<new>.py`로 분리.

### 골격이 제공하는 것

- cwd 무관 동작 (`__file__` 기준 sys.path 자동 조작)
- argparse 자동 `--help`
- `common.emit.emit()` 헬퍼로 MCP-style JSON 4필드 자동 보장 (ok/code/summary/next)
- Windows Git Bash + macOS/WSL 양쪽 동작 (실측 검증)

### 검증

- 신규 skill cli 작성 후 dry-run: `cd skills/suh-<new>/scripts && python <scope>_cli.py --help` → argparse usage 출력 확인
- 한 개 서브커맨드 실측 호출 → JSON 4필드 확인

Phase 6의 표준은 이 표준에 종속된다 — 신규 skill 생성 시 py 호출 항목은 위 절차로 자동 수행한다.
