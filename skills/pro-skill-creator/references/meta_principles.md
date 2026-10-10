# 메타 원칙 · 신규 skill의 Python 호출 표준

> 언제 읽나: SKILL.md 본문을 쓰거나 고칠 때(CREATE Phase 3 · IMPROVE Phase 2), 그리고 새 skill에 Python CLI가 필요할 때.

## 1. 메타 원칙

### 1.1 Explain the why — not ALL CAPS

agent에게 "절대 하지 마라"는 ALL CAPS보다, **"왜 그게 중요한가"** 를 한 문장으로 붙이는 편이 낫다. 모델은 똑똑하므로 이유를 알면 경계 케이스에서도 올바르게 판단한다. 규칙을 쓸 때는 항상 한 줄의 `(이유: ~)` 를 붙이는 습관.

### 1.2 Multiple choice를 우선 (객관식 > 주관식)

사용자에게 질문할 때는 가능한 한 **선택지를 제시**한다. 주관식은 사용자가 매번 생각을 짜내야 하고, 답도 제각각이라 agent가 다시 해석해야 한다. 객관식이면 사용자는 고르기만 하면 되고 agent도 분기하기 쉽다.

```
❌ "인증 방식은 뭘 쓸까요?"
✅ "인증 방식은 뭘 쓸까요?
   1) Personal Access Token (추천)
   2) ID/비밀번호
   3) 기타 직접 입력"
```

단, 사용자가 오히려 답변 폭을 좁히고 싶지 않은 경우(창의적 설계·이름 짓기 등)엔 주관식이 낫다. 상황 판단.

### 1.3 복잡도에 맞춰 분량 조절 (Scale to complexity)

skill의 모든 섹션을 같은 깊이로 쓸 필요 없다. **간단한 동작은 한 줄**, 복잡하면 200~300단어. 모든 action을 장황하게 문서화하면 사용자가 읽을 때 신호가 흐려진다.

예:
- `config-show`: "현재 설정 확인 (토큰/비번은 마스킹)" — 한 줄이면 충분
- `mr-create-from-branch`: 브랜치명 파싱 로직·타겟 자동 결정·충돌 확인 규칙 — 여러 단락 필요

### 1.4 Incremental validation — 섹션별 확인

긴 설계를 한 번에 몰아서 사용자에게 던지지 않는다. 섹션 하나 끝날 때마다 "여기까지 맞나요?" 확인. 중간에 오해가 있었다면 그 섹션만 고치면 되지, 설계 전체를 뒤엎지 않아도 된다.

Phase 0의 Step 단위 진행도 이 원칙의 적용이다.

### 1.5 필요하면 뒤로 돌아가기 (Be flexible)

Phase 번호는 선형이지만 **고집스러운 절차는 아니다**. Phase 3 작성 중에 Phase 0의 scope가 잘못됐다고 판단되면 Phase 0로 돌아가 재합의한다. "이미 여기까지 왔으니 밀어붙이자"는 유혹을 이긴다.

돌아갈 때는 사용자에게 알린다: "Phase 3 중에 경계가 모호한 걸 발견해서 Phase 0으로 잠시 돌아가 재확인합니다."

SKILL.md가 짧고 Phase 중심인 것도 이 습관의 결과다. 상세는 references/에 두고, 본문에서는 **"어느 Phase인지"** 와 **"종료 조건이 충족되었는가"** 두 질문만 agent가 계속 자신에게 묻게 한다.

## 2. 신규 skill에 Python 호출이 필요한 경우 (3-layer 표준)

신규 skill이 GitHub API·외부 시스템·서브커맨드 호출이 필요하면 **반드시 3-layer 표준을 따른다**:

1. **공유 도메인 로직 점검**: 필요한 함수가 `scripts/common/`에 이미 있나? (`gh_client`, `config`, `paths`, `title` 등). 있으면 import 재사용. 새로 작성하지 않는다.
2. **skill 전용 cli 작성**: `templates/python_cli_script.py` 골격을 복사.
   ```bash
   cp skills/pro-skill-creator/templates/python_cli_script.py skills/pro-<new>/scripts/<scope>_cli.py
   ```
3. **prog + 서브커맨드 교체**: 골격의 `<scope>_cli` 부분과 `cmd_example`을 실제 도메인으로 교체.
4. **공유 로직은 import**: `from common.<module> import ...` 형태. Layer 1 재작성 금지.
5. **SKILL.md 호출**: 표준 self-contained 5줄 패턴 (`../../references/common-rules.md` §"skill별 py 분산 호출" 참조). 스크립트 찾기 블록은 SKILL.md에 **한 번만** 두고, 이후 블록은 `{PYTHON} {SCRIPTS}/<scope>_cli.py` 처럼 찾은 값을 재사용한다 (모범: `pro-launch/SKILL.md`).
6. **공유 로직이 부족하면 Layer 1에 추가**: 단일 skill 전용 로직만 cli에 두고, 2개 이상 skill이 쓸 가능성이 있으면 `scripts/common/<new>.py`로 분리.

### 골격이 제공하는 것

- cwd 무관 동작 (`__file__` 기준 sys.path 자동 조작)
- argparse 자동 `--help`
- `common.emit.emit()` 헬퍼로 MCP-style JSON 4필드 자동 보장 (ok/code/summary/next)
- Windows Git Bash + macOS/WSL 양쪽 동작 (실측 검증)

### 검증

- 신규 skill cli 작성 후 dry-run: `cd skills/pro-<new>/scripts && python <scope>_cli.py --help` → argparse usage 출력 확인
- 한 개 서브커맨드 실측 호출 → JSON 4필드 확인

CREATE Phase 6 보고 표준은 이 표준에 종속된다 — 신규 skill 생성 시 py 호출 항목은 위 절차로 자동 수행한다.
