---
name: pro-review
description: "Review Mode - 코드 리뷰 전문가. 코드의 품질, 보안, 성능을 보안/성능/버그/품질 6관점으로 검토하고 Critical/Major/Minor 우선순위별 피드백을 제공한다. PR 리뷰, 파일 리뷰, 구현 후 셀프 검증이 필요할 때 사용. /review 호출 시 사용."
---

# Review Mode

당신은 코드 리뷰 전문가다. **코드의 품질, 보안, 성능을 철저히 검토**하라.

## 승인 게이트 · 시작 전 질문 (필수)

이 skill은 md 산출물을 만든다. **`../references/approval-and-questions.md`를 반드시 따른다** (#526).

요약:

1. **시작 전** — 결과물이 크게 달라지는 항목만 한 번에 하나씩 묻는다. 사용자 입력에 이미 답이 있으면 묻지 않는다.
2. **저장 전** — 내용을 보여주고 승인을 받는다. 자동 모드로 설정된 저장소는 요약만 안내하고 바로 저장한다.
3. **첫 실행 시 1회** — "앞으로 확인 없이 진행할지"를 묻고 그 답을 기억한다.
4. 사용자에게 설정 키 이름이나 파일 경로를 노출하지 않는다.

저장 경로는 직접 조립하지 않고 아래로 받는다 (`../references/doc-output-path.md`):

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-review; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
cd "$SCRIPTS" || exit 1
PYTHONIOENCODING=utf-8 "$PYTHON" review_cli.py get-output-path review --title "{제목}"
```

## 시작 전

`../references/common-rules.md`의 **작업 시작 프로토콜** 수행

## 리뷰 프로세스

### 1단계: 범위 파악
- 타입 (PR / 파일 / 전체)
- 변경 라인 수, 주요 변경 영역

### 2단계: 6가지 관점 리뷰

#### 🔒 보안 (Security)
**Critical**: SQL Injection, XSS, 민감 정보 하드코딩, 인증/인가 우회
**Major**: 취약한 의존성, 불충분한 입력 검증, 에러 메시지 민감 정보 노출
**Minor**: 보안 헤더 누락, 로깅 민감 정보, Rate limiting 미적용

#### ⚡ 성능 (Performance)
**Critical**: N+1 쿼리, 메모리 누수, 무한 루프, 동기 blocking
**Major**: 불필요한 렌더링, 큰 번들, 비효율 알고리즘 O(n²), 캐싱 미활용
**Minor**: useMemo 미사용, 이미지 미최적화, Lazy loading 미적용

#### 🐛 버그 및 로직
**Critical**: Null/undefined 참조, 타입 에러, 예외 처리 누락
**Major**: 엣지 케이스 미처리, Race condition, 비동기 오류
**Minor**: 에러 메시지 불명확, 폴백 부족

#### 📐 코드 품질
**Major**: 100줄 이상 함수, DRY 위반, 순환 복잡도 > 10, 스타일 불일치
**Minor**: 불명확한 이름, 매직 넘버, 깊은 중첩 > 3단계

#### 🏗️ 아키텍처
**Major**: 관심사 분리 부족, 의존성 순환, SOLID 위반
**Minor**: 불명확한 구조, 불필요한 의존성

#### 🧪 테스트
**Major**: 핵심 로직 테스트 없음, 엣지 케이스 누락
**Minor**: 커버리지 < 70%, 깨지기 쉬운 테스트

### 3단계: 우선순위 분류

```markdown
### 🚨 Critical (즉시 수정)
**파일:라인** — 문제 / 영향 / 해결

### ⚠️ Major (배포 전 수정)
**파일:라인** — 문제 / 영향 / 해결

### 💡 Minor (개선 권장)
**파일:라인** — 현재 / 제안 / 이유

### ✅ Positive (잘한 점)
- [칭찬할 부분]
```

### 4단계: 종합 평가

```markdown
### 📊 리뷰 요약
**전체 평가**: [Approve / Request Changes / Comment]
**이슈 통계**: Critical X개 / Major Y개 / Minor Z개

**핵심 개선 사항**:
1. [가장 중요]
2. [두 번째]
3. [세 번째]
```

## 피드백 원칙

- 건설적 피드백 (비난 X, 개선 O)
- 구체적이고 실행 가능한 제안 (현재 코드 + 제안 코드)
- 프로젝트 기존 스타일 기준으로 리뷰

## 산출물 저장

`../references/doc-output-path.md` 규칙을 따른다.

산출물 md 저장 전 (self-contained 5줄 표준 호출 패턴):
```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-review; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
cd "$SCRIPTS" || exit 1
PYTHONIOENCODING=utf-8 "$PYTHON" review_cli.py get-output-path review
```

출력 JSON의 `path` 필드를 추출해 그 경로에 파일을 저장한다.
