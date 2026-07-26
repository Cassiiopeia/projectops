# 산출물 경로 규칙

이 reference는 `analyze`, `plan`, `design-analyze`, `refactor-analyze`, `troubleshoot`, `report`, `ppt`, `review` skill이 md 산출물을 저장할 때 반드시 따르는 규칙이다.

## 저장 전 경로 계산

산출물 md 저장 전 반드시 해당 skill의 `_cli.py` 의 `get-output-path` 서브커맨드를 호출해 경로를 받아라.
표준은 `common-rules.md` §"skill별 py 분산 호출" 참조.

skill별 호출 위치 매핑:

| skill_id | 호출 cwd | cli 파일 |
|---|---|---|
| review | `skills/pro-review/scripts/` | `review_cli.py` |
| troubleshoot | `skills/pro-troubleshoot/scripts/` | `troubleshoot_cli.py` |
| report | `skills/pro-report/scripts/` | `report_cli.py` |
| 나머지 (analyze, plan, design-analyze, refactor-analyze, ppt) | (해당 skill 자체 cli 없음 — agent가 직접 경로 계산하거나 report_cli 임시 사용) | — |

예시 (review):

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SCRIPTS=$(ls -d ~/.claude/plugins/cache/*/projectops/*/skills/pro-review/scripts 2>/dev/null | sort -V | tail -1); [ -z "$SCRIPTS" ] && SCRIPTS="$PROJECT_ROOT/skills/pro-review/scripts"; cd "$SCRIPTS" || exit 1
PYTHONIOENCODING=utf-8 "$PYTHON" review_cli.py get-output-path review
```

출력 JSON의 `path` 필드를 추출해 사용한다.

반환값 예시:
- `docs/projectops/plan/20260418_427_드롭다운_디자인_변경.md`
- `docs/projectops/analyze/20260418_001_초기_분석.md`

## 산출물 경로 우산 (`docs/projectops/`)

모든 산출물은 `docs/projectops/` 우산 아래에 둔다. harness(`harness/WORKFLOW.md` §"산출물 경로 단일 규칙")와 skill이 동일한 위치를 공유한다.

| 종류 | 경로 | 비고 |
|------|------|------|
| skill 최종 산출물 | `docs/projectops/<skill>/` | plan·analyze·report·review·issue 등 |
| 작업중 지식 그래프 | `docs/projectops/hypercortex/` | harness SDLC의 TODO·REQUIREMENT·DESIGN·QUALITY 등 |
| 코드 작업 격리 | `docs/projectops/workspace/` | harness Phase 4 코드 산출물 격리 |

## 실패 시 대응

| 상황 | 대응 |
|------|------|
| `[WARN] title_not_found` (exit 0) | AI가 작업 컨텍스트로 제목 생성 후 `--title "제목"` 옵션으로 재호출 |
| `[WARN] issue_number_not_found` (exit 0) | fallback 경로 그대로 사용, 사용자에게 "이슈번호 없어서 순번 사용" 안내 |
| `[WARN] issue_number_mismatch` (exit 0) | fallback 경로 그대로 사용, 사용자에게 불일치 안내 |
| `[ERROR] git_not_found` (exit 1) | 사용자에게 "git 저장소가 아닙니다" 알리고 중단 |

## 디렉토리 자동 생성

경로를 받은 뒤 파일 쓰기 전 디렉토리를 생성한다:

**Mac/Linux:**
```bash
mkdir -p "$(dirname "<받은 경로>")"
```

**Windows (PowerShell):**
```powershell
New-Item -ItemType Directory -Force -Path (Split-Path "<받은 경로>")
```
