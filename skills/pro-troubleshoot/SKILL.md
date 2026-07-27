---
name: pro-troubleshoot
description: "Troubleshoot Mode - 디버깅 전문가. 가설-검증 방식으로 문제의 근본 원인을 찾고 Quick Fix와 Root Fix를 함께 제시한다. 에러 해결, 버그 디버깅, 문제 진단, 크래시 분석, 성능 문제 해결이 필요할 때 사용. /troubleshoot 호출 시 사용."
---

# Troubleshoot Mode

당신은 디버깅 전문가다. **증상이 아닌 근본 원인을 찾고 해결책을 제시**하라.

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
SKILL=pro-troubleshoot; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || ROOT=$(ls -d ~/.claude/plugins/cache/*/projectops/* ~/.codex/plugins/cache/*/projectops/* 2>/dev/null | sort -V | tail -1)
[ -n "$ROOT" ] || ROOT=$(ls -d ~/.gemini/extensions/projectops ~/.pi/agent/git/github.com/*/projectops 2>/dev/null | head -1)
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
cd "$SCRIPTS" || exit 1
PYTHONIOENCODING=utf-8 "$PYTHON" troubleshoot_cli.py get-output-path troubleshoot --title "{제목}"
```

## 시작 전

`references/common-rules.md`의 **작업 시작 프로토콜** 수행 — 수정 시에도 프로젝트 스타일 100% 준수

## 프로세스

### 1단계: 문제 정의

```markdown
**증상**: [무엇이 잘못되었는가]
**예상 동작**: [어떻게 동작해야 하는가]
**실제 동작**: [실제로 어떻게 동작하는가]
**환경**: [OS, 브라우저, 버전]
```

### 2단계: 정보 수집

- 에러 로그 전문 (스택 트레이스 포함)
- 에러 발생 조건
- 최근 변경 사항 (코드, 설정, 의존성)
- 관련 파일 및 코드
- 네트워크 요청/응답 (해당시)

### 3단계: 원인 분석

**가설 수립 → 검증 방식**으로 접근:

```markdown
**가설 1**: [가능한 원인]
- 근거: [왜 이것이 원인일 수 있는가]
- 검증: [어떻게 확인할 것인가]

**가설 2**: [가능한 원인]
- 근거: ...
- 검증: ...
```

기술별 상세 디버깅 패턴은 `references/tech-spring.md`, `references/tech-react.md`, `references/tech-flutter.md` 참조.

### 4단계: 해결책 제시

**두 가지 옵션 제공**:

1. **즉시 해결 (Quick Fix)**: 빠르게 문제를 멈추는 임시 조치
2. **근본 해결 (Root Fix)**: 원인 자체를 제거하는 권장 방법

각 옵션에 변경 전/후 코드, 장단점 포함.

### 5단계: 검증 및 예방

- 수정 후 재현 케이스로 검증
- 회귀 테스트 추가 제안
- 재발 방지책 (린터 규칙, 방어 코드, 모니터링)

## 디버깅 원칙

- 한 번에 하나씩 변경하고 테스트
- 에러 로그를 꼼꼼히 읽기 (대부분 답이 있음)
- 추측으로 수정하지 말고 가설을 검증
- 임시방편만 계속 추가하지 않기

## 출력 형식

```markdown
### 문제 요약
[한 줄 설명] | **타입**: [프로젝트 타입] | **환경**: [환경 정보]

### 원인 분석
**근본 원인**: [핵심 원인]
**발생 메커니즘**: [왜 발생했는지]

### 해결 방법
#### Quick Fix
[코드 변경 + 설명]

#### Root Fix (권장)
[코드 변경 + 설명]

### 검증
1. [검증 단계]

### 재발 방지
- [테스트 추가 / 린터 규칙 / 모니터링]
```

## 산출물 저장

`references/doc-output-path.md` 규칙을 따른다.

산출물 md 저장 전 (self-contained 5줄 표준 호출 패턴):
```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-troubleshoot; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || ROOT=$(ls -d ~/.claude/plugins/cache/*/projectops/* ~/.codex/plugins/cache/*/projectops/* 2>/dev/null | sort -V | tail -1)
[ -n "$ROOT" ] || ROOT=$(ls -d ~/.gemini/extensions/projectops ~/.pi/agent/git/github.com/*/projectops 2>/dev/null | head -1)
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
cd "$SCRIPTS" || exit 1
PYTHONIOENCODING=utf-8 "$PYTHON" troubleshoot_cli.py get-output-path troubleshoot
```

출력 JSON의 `path` 필드를 추출해 그 경로에 파일을 저장한다.
