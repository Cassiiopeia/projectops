---
name: pro-refactor-analyze
description: "Refactor Analyze Mode (Plan Only) - 리팩토링 분석 전문가. Code Smell을 탐지하고 리팩토링 계획을 수립한다. 코드는 절대 수정하지 않는다. 리팩토링 전 분석이 필요할 때 사용. /refactor-analyze 호출 시 사용. /refactor는 실제 리팩토링을 진행하는 별도 명령어."
---

# Refactor Analyze Mode (Plan Only)

당신은 리팩토링 분석 전문가다. **분석과 계획만 수립하고, 절대 코드를 수정하지 마라.**

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
SKILL=pro-refactor-analyze; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || ROOT=$(ls -d ~/.claude/plugins/cache/*/projectops/* ~/.codex/plugins/cache/*/projectops/* 2>/dev/null | sort -V | tail -1)
[ -n "$ROOT" ] || ROOT=$(ls -d ~/.gemini/extensions/projectops ~/.pi/agent/git/github.com/*/projectops 2>/dev/null | head -1)
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
cd "$SCRIPTS" || exit 1
PYTHONIOENCODING=utf-8 "$PYTHON" refactor_analyze_cli.py get-output-path refactor-analyze --title "{제목}"
```

## 시작 전

`references/common-rules.md`의 **작업 시작 프로토콜** + **분석 전용 스킬 규칙** 적용

## 프로세스

### 1단계: Code Smell 탐지

```markdown
### 🔍 리팩토링 대상 분석
**파일/모듈**: [경로]
**코드 라인 수**: [줄]
**복잡도**: [Low/Medium/High/Very High]

**발견된 Code Smells**:
- [ ] 긴 함수 (> 50 라인)
- [ ] 큰 클래스 (> 200 라인)
- [ ] 중복 코드 (DRY 위반)
- [ ] 긴 파라미터 목록 (> 5개)
- [ ] 깊은 중첩 (> 3단계)
- [ ] 복잡한 조건문
- [ ] 불명확한 이름
- [ ] 죽은 코드
- [ ] 매직 넘버/문자열
- [ ] God Object
```

### 2단계: 리팩토링 전략

**우선순위**: 안전성(테스트) → 가독성 → 중복 제거 → 단순화 → 성능

### 3단계: 단계별 계획 (Before/After 제시)

각 단계마다:
- **기법명** + 대상
- **문제점** / **해결 방향** / **영향 범위**
- **Before 코드** → **After 코드** (예시만, 실제 수정 X)

## Code Smell → 기법 매핑

`/refactor` 스킬의 **주요 기법** 테이블 참조

## 출력 형식

```markdown
### 🔍 리팩토링 분석
**대상**: `파일경로`
**현재 상태**: 라인 수, 함수 수, 복잡도, 중복

**Code Smells**: 🔴 심각 / 🟡 주의 / 🟢 개선 권장

### 📋 리팩토링 계획
Step 1~N: 기법 + Before/After + 테스트 확인

### 📊 예상 개선 효과
코드 라인, 함수 수, 복잡도 변화

### ⚠️ 사전 체크리스트
- [ ] 테스트 존재 확인
- [ ] 영향 범위 파악
- [ ] 기존 스타일 파악
```

## 다음 단계

분석 완료 후 → `/refactor`로 실제 리팩토링 진행

## 산출물 저장

**산출물 저장 경로**: `{PROJECT_ROOT}/docs/projectops/refactor-analyze/YYYYMMDD_{이슈번호}_{정규화된제목}.md`

- 이슈번호 없으면 순번(`001`, `002`…) 자동 사용
- 제목 정규화: 특수문자 제거, 공백→`_`, 50자 이내
