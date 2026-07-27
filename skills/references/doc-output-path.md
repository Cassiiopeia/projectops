# 산출물 경로 규칙

이 reference는 `analyze`, `plan`, `design-analyze`, `refactor-analyze`, `troubleshoot`, `report`, `ppt`, `review` skill이 md 산출물을 저장할 때 반드시 따르는 규칙이다.

## 저장 전 경로 계산

산출물 md 저장 전 반드시 해당 skill의 `_cli.py` 의 `get-output-path` 서브커맨드를 호출해 경로를 받아라.
표준은 `common-rules.md` §"skill별 py 분산 호출" 참조.

skill별 호출 위치 매핑 — **8개 스킬 전부 자기 CLI를 갖는다** (#525):

| skill_id | 호출 cwd | cli 파일 |
|---|---|---|
| analyze | `skills/pro-analyze/scripts/` | `analyze_cli.py` |
| plan | `skills/pro-plan/scripts/` | `plan_cli.py` |
| design-analyze | `skills/pro-design-analyze/scripts/` | `design_analyze_cli.py` |
| refactor-analyze | `skills/pro-refactor-analyze/scripts/` | `refactor_analyze_cli.py` |
| ppt | `skills/pro-ppt/scripts/` | `ppt_cli.py` |
| review | `skills/pro-review/scripts/` | `review_cli.py` |
| troubleshoot | `skills/pro-troubleshoot/scripts/` | `troubleshoot_cli.py` |
| report | `skills/pro-report/scripts/` | `report_cli.py` |

> **agent가 경로를 직접 계산하지 않는다.** 과거에는 5개 스킬에 CLI가 없어 "직접 계산하거나 다른 스킬 것을 빌려 쓰라"는 상태였고, 그래서 스킬마다 파일명 규칙이 갈라져도 아무도 알아채지 못했다. 이제 규칙은 `scripts/common/paths.py`의 `resolve_output_path()` **한 곳**에만 있고 8개 CLI가 모두 그것을 호출한다.

예시 (review):

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-review; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || ROOT=$(ls -d ~/.claude/plugins/cache/*/projectops/* ~/.codex/plugins/cache/*/projectops/* 2>/dev/null | sort -V | tail -1)
[ -n "$ROOT" ] || ROOT=$(ls -d ~/.gemini/extensions/projectops ~/.pi/agent/git/github.com/*/projectops 2>/dev/null | head -1)
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
cd "$SCRIPTS" || exit 1
PYTHONIOENCODING=utf-8 "$PYTHON" review_cli.py get-output-path review
```

출력 JSON의 `path` 필드를 추출해 사용한다.

반환값 예시:
- `docs/projectops/plan/20260418_427_드롭다운_디자인_변경.md`
- `docs/projectops/analyze/20260418_001_초기_분석.md`

## 산출물 경로 우산 (기본 `docs/projectops/`)

모든 산출물은 하나의 우산 아래에 둔다. harness(`harness/WORKFLOW.md` §"산출물 경로 단일 규칙")와 skill이 동일한 위치를 공유한다.

| 종류 | 경로 | 비고 |
|------|------|------|
| skill 최종 산출물 | `<우산>/<skill>/` | plan·analyze·report·review·issue 등 |
| 작업중 지식 그래프 | `<우산>/hypercortex/` | harness SDLC의 TODO·REQUIREMENT·DESIGN·QUALITY 등 |
| 코드 작업 격리 | `<우산>/workspace/` | harness Phase 4 코드 산출물 격리 |

### 우산 위치는 사용자가 바꿀 수 있다 (#525)

기본값은 `docs/projectops/`이고, **설정을 건드리지 않으면 그대로 유지**된다.
팀 규약상 다른 위치를 써야 하거나 저장소에 문서를 남기고 싶지 않으면 config로 바꾼다.

```json
{
  "output": { "root": "docs/dev" }
}
```

| 값 | 결과 |
|---|---|
| 미설정 | `<repo>/docs/projectops/` — 기존과 동일 |
| 상대경로 (`docs/dev`) | `<repo>/docs/dev/` |
| 절대경로 (`/Users/me/notes`) | 그 경로 그대로 (저장소 밖에 모을 때) |

해석은 `scripts/common/paths.py`의 `resolve_output_root()`가 담당한다.
**skill이 경로 문자열을 직접 조립하지 않는다** — 반드시 `get-output-path`를 거친다.
사용자에게 안내할 때는 설정 키 이름이나 파일 경로를 노출하지 말고 자연어로만 말한다.

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
