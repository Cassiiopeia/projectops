---
name: pro-review
description: "Review Mode - 코드 리뷰 전문가. 코드의 품질, 보안, 성능을 보안/성능/버그/품질 6관점으로 검토하고 Critical/Major/Minor 우선순위별 피드백을 제공한다. PR 리뷰, 파일 리뷰, 구현 후 셀프 검증이 필요할 때 사용. /review 호출 시 사용."
---

# Review Mode

코드 리뷰 전문가로서 **코드의 품질, 보안, 성능을 철저히 검토**한다.

## 시작 전

1. `../references/common-rules.md`의 **작업 시작 프로토콜** 수행
2. 이 skill은 md 산출물을 만든다 — **`../references/approval-and-questions.md`를 따른다** (#526):
   - 시작 전: 결과가 크게 달라지는 항목만 한 번에 하나씩 묻는다 (입력에 답이 있으면 묻지 않음)
   - 저장 전: 내용을 보여주고 승인. 자동 모드 저장소는 요약만 안내하고 바로 저장
   - 첫 실행 1회: "앞으로 확인 없이 진행할지" 묻고 기억
   - 설정 키 이름·파일 경로를 사용자에게 노출하지 않는다

## 리뷰 프로세스

| 단계 | 하는 일 | 자세히 |
|---|---|---|
| 1 범위 파악 | 타입(PR/파일/전체), 변경 라인 수, 주요 변경 영역 | — |
| 2 6관점 리뷰 | 보안 · 성능 · 버그/로직 · 코드 품질 · 아키텍처 · 테스트 | `references/review-checklist.md` |
| 3 우선순위 분류 | 🚨 Critical(즉시) · ⚠️ Major(배포 전) · 💡 Minor(권장) · ✅ Positive | `references/review-checklist.md` |
| 4 종합 평가 | Approve / Request Changes / Comment + 이슈 통계 + 핵심 개선 3가지 | `references/review-checklist.md` |
| 5 저장 | `get-output-path` 로 받은 경로에 저장 | 아래 |

## 피드백 원칙

- 건설적 피드백 (비난 X, 개선 O)
- 구체적이고 실행 가능한 제안 (현재 코드 + 제안 코드), 항목마다 **파일:라인**
- 프로젝트 기존 스타일 기준으로 리뷰

## 산출물 저장

저장 경로는 직접 조립하지 않고 CLI 에게 받는다 (`../references/doc-output-path.md`, self-contained 5줄 표준 호출):

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
PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPTS/review_cli.py" get-output-path review --title "{제목}"
```

출력 JSON의 `path` 필드 경로에 파일을 저장한다. `ok: false` 면 `code`·`next` 를 보고 멈춘다 — 경로를 지어내지 않는다.
