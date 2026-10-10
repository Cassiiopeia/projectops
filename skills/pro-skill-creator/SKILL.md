---
name: pro-skill-creator
description: 표준 skill을 생성(create)·리뷰(review)·개선(improve)할 때 사용한다. 트리거 발화 — "skill 만들어줘", "skill 추가해줘", "이거 skill로 만들자", "이 skill 리뷰해줘", "skill 검증해줘", "skill 개선해줘", "skill 고쳐줘", "create a skill", "review this skill". 호출 즉시 사용자 의도를 create/review/improve 셋 중 하나로 분류한 뒤, 모드별 Phase를 순서대로 실행한다. 한 번에 한 질문·자동 추론 우선·하드코딩 금지·설정 분리 등 8대 원칙을 기계적으로 강제한다.
version: 2.3
---

# Skill Creator

이 문서는 **글이 아니라 의사결정 절차**다. 위에서 아래로 실행하고, 각 Phase의 "종료 조건"이 충족될 때까지 다음 Phase로 넘어가지 않는다.

> **호출 즉시**: 아래 §1에서 **모드를 판정** → `TaskCreate` 등록 → 해당 모드 Phase 1부터. 분석/설명 글을 먼저 쓰지 않는다.
> **판단 원칙**: 애매하면 억지 추론 금지 — 즉시 질문. 한 메시지 = 한 질문. 이미 준 정보는 다시 묻지 않음. 위험한 작업은 실행 전 확인.

## 어디를 읽나

| 지금 하는 것 | 자세히 |
|---|---|
| CREATE Phase 0 — Scope·접근법·경계 합의 | `references/phase0_brainstorming.md` |
| CREATE Phase 1 — 6개 슬롯 정의·자동 추론 | `references/phase1_slots.md` |
| CREATE Phase 2 — 한 번에 하나씩 질문 포맷 | `references/phase2_question_format.md` |
| CREATE Phase 3 · IMPROVE Phase 2 — 본문 쓰기 메타 원칙, 신규 skill Python CLI 3-layer 표준 | `references/meta_principles.md` |
| CREATE Phase 4 · REVIEW Phase 2 — 8대 원칙 체크표 | `references/phase4_checklist.md` |
| CREATE Phase 5 고급 — 공식 `run_loop.py` 정량 최적화 | `references/trigger_optimization.md` |
| CREATE Phase 6 · IMPROVE Phase 4 — 보고 표준 포맷 | `references/phase6_report_format.md` |
| REVIEW · IMPROVE 모드 전체 절차 | `references/review_improve.md` |
| 막혔을 때 — 실패 패턴 모음 | `references/anti_patterns.md` |
| config / Python CLI 뼈대 | `templates/config.json.example` · `templates/python_cli_script.py` |

## 0. 절대 규칙 (Hard Constraints)

어느 Phase·모드에서도 위반 금지. 위반 감지 시 즉시 멈추고 알린다.

| ID | 규칙 | 왜 중요한가 |
|----|------|-----------|
| H1 | 한 메시지에 질문은 **최대 1개** | 여러 개를 던지면 사용자는 한두 개만 답하고, agent는 나머지를 "답변 거부"로 오해해 잘못된 추측으로 진행한다. |
| H2 | 사용자가 이미 준 정보는 다시 묻지 않는다 | "방금 말했는데 또 묻나" — 신뢰를 잃는다. 추출하지 못한 agent의 실패다. |
| H3 | 실제 도메인/IP/이메일/사번/회사명을 SKILL.md 본문에 박지 않는다 | skill이 다른 프로젝트로 가면 남의 계정·회사 정보가 박혀 쓸 수 없다. 플레이스홀더 사용. |
| H4 | 사용자별로 다른 값은 SKILL.md가 아니라 별도 config에 둔다 | 팀원마다 PEM 키·PAT·계정이 다르다. 공유 문서에 개인 값이 들어가면 충돌한다. |
| H5 | 전문 용어는 처음 등장 시 한 줄 설명 | 용어에서 막히면 skill을 아예 안 쓴다. |
| H6 | UI 안내는 메뉴 경로 + 필드명까지 구체화 | "거기서 찾으세요"는 UI가 바뀌면 무용지물. "제어판 → 외부 액세스 → DDNS 탭 → 호스트이름 컬럼"처럼 쪼개면 근처를 찾을 수 있다. |

나머지 2개 원칙(자동 추론 우선·유연한 입력)은 Phase 1 절차로 강제된다.

## 1. 모드 판정

| 모드 | 트리거 예시 발화 | 진입 |
|------|----------------|-----------|
| **CREATE** | "skill 만들어줘", "이 작업 skill로 만들자", "~에 대한 skill 추가" | §2 |
| **REVIEW** | "이 skill 리뷰해줘", "어디 고칠 거 있어?", "평가해줘", "점검해줘" | `references/review_improve.md` |
| **IMPROVE** | "리뷰 결과 반영해줘", "1~4번만 고쳐줘", "skill 개선해줘 + 기존 skill 지정" | `references/review_improve.md` |

**판정 우선순위**:
1. 특정 **기존 skill 경로** + "리뷰"/"점검" → REVIEW
2. 특정 **기존 skill 경로** + "개선"/"고쳐" → IMPROVE
3. 둘 다 아니면서 새 기능 제안 → CREATE
4. 애매하면 한 번만 묻는다: "새로 만들까요, 기존 skill을 리뷰/개선할까요?"

판정 후 모드별 task 목록을 `TaskCreate`로 등록한다 (CREATE는 아래, REVIEW/IMPROVE는 references에 있다).

## 2. 모드 CREATE — 새 skill 생성

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

### Phase 0 — 브레인스토밍

- 목표: Scope·접근법·경계·기존 skill과의 관계를 합의. 출력: "무엇을 만들지" 한 줄 합의 + 선택된 접근법.
- 종료 조건: Scope 적절 / 접근법 1개 선택 / 경계 명확 / 중복 정리 (4개 모두) → Phase 1.
- 짧아도 되지만 **건너뛰지 말 것** — 5분 설계가 수백 번 호출의 품질을 좌우한다. "너무 간단해서 설계 필요 없다"는 anti-pattern.
- 절차·2~3개 접근법 제시 포맷·scope 판정 기준: `references/phase0_brainstorming.md`.
- **건너뛸 수 있는 조건**: 사용자가 scope·접근법·기존 skill과의 관계를 이미 명시. 이때도 "Phase 0 스킵 이유: ~"를 한 줄 알린다.

### Phase 1 — 의도 흡수 + 자동 추출

- 6개 슬롯 `purpose`, `triggers`, `inputs`, `outputs`, `auto_extract`, `pain_points` 상태표를 **메모리에만** 유지한다 (정의·추론 규칙: `references/phase1_slots.md`).
- 종료 조건: 6개 모두 "값 있음" 또는 "추론 가능". 빈 슬롯 0개 → Phase 3 / 1개 이상 → Phase 2.
- 사용자에게는 **한 줄 의도 요약만** 보여주고 "이 이해가 맞나요?"로 확인 — 슬롯 표를 통째로 보여주면 압도된다.

### Phase 2 — 부족한 정보만 하나씩 질문

한 메시지 = 한 슬롯 (`references/phase2_question_format.md`). 사용자가 여러 슬롯의 답을 함께 주면 모두 받고 빈 슬롯만 다시 확인. 빈 슬롯이 없으면 생략.

### Phase 3 — SKILL.md 작성 (+ config/scripts)

- 출력: SKILL.md (필수) + config.json.example (선택) + scripts/ (선택). 종료 조건: 파일 존재 + 필수 섹션 포함.
- Frontmatter: `name`, `description` 필수, `version` 권장.
- 본문 골격:

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

- 스크립트/config가 필요하면 `templates/config.json.example`(계정/URL 분리 설정 표준), `templates/python_cli_script.py`(stdlib CLI 뼈대 — UTF-8 콘솔, SSL opt-out, 구조화 에러)를 복사한다. Python 호출은 **3-layer 표준**과 "스크립트 찾기 1회 + `{PYTHON} {SCRIPTS}/x_cli.py` 재사용" 라우터 형식을 따른다 → `references/meta_principles.md` §2.
- 쓰는 법(이유 붙이기·객관식 우선·복잡도에 맞는 분량·섹션별 확인·뒤로 돌아가기): `references/meta_principles.md` §1.

### Phase 4 — 8대 원칙 self-review

방금 쓴 파일을 **반드시 `Read`로 다시 읽고** 8개 검사를 한 줄씩 채운다 ("방금 썼으니 안다" 금지). 검사 표·조치: `references/phase4_checklist.md`. FAIL이 하나라도 있으면 수정 후 재검사 — 위반 0건까지.

### Phase 5 — 트리거 발화 검증

별도 CLI 없이 agent가 시뮬레이션한다.

1. **should-trigger 3개** — 실제로 할 법한 발화, skill 이름을 직접 부르지 않는 표현.
2. **should-not-trigger 2개** — 근처 주제지만 호출되면 안 되는 경우.
3. 각각 "description만 보고 이 skill을 호출할까?" 자문. 5/5면 통과, 하나라도 틀리면 description을 고쳐 다시.

정량 최적화(공식 `run_loop.py`)는 선택 — `references/trigger_optimization.md`.

### Phase 6 — 사용자 보고 + 합의

`references/phase6_report_format.md` 형식. 8개 원칙 결과표가 전부 ✅일 때만 보고하고, ⚠️/❌가 있으면 Phase 4로 돌아간다.

### Phase 7 — 실제 호출 동작 확인 (강권)

"지금 한 번 호출해서 테스트해볼까요?"를 제안한다 — 써보면 description 누락·스크립트 에러·설정 불일치가 바로 드러난다. "나중에"면 스킵.
