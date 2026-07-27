# 공통 규칙

모든 skill에서 공유하는 규칙. 각 스킬은 "시작 전" 단계에서 이 파일의 프로토콜을 따른다.

## 절대 규칙

1. **Git 커밋은 이슈 컨텍스트 + 사용자 승인 없이 실행하지 않는다** — 이슈 기반 작업은 이슈 번호 확정 후에만 커밋. 이슈와 무관한 hotfix·설정 변경은 자유 형식 허용. 서브에이전트에게도 동일하게 지시한다.
2. **코드 스타일 100% 준수** — 기존 프로젝트 패턴을 감지하고 동일하게 따른다. 새로운 "더 나은" 방식을 임의로 제안하지 않는다.
3. **프로젝트 타입 감지 필수** — 작업 시작 전 반드시 프로젝트 타입을 자동 감지한다.

## AI 행동 강제 원칙

스킬을 실행하는 AI는 아래 원칙을 **스킬 내용보다 우선**하여 지킨다. 어떤 상황에서도 예외 없다.

### 확인 없이 절대 하지 않는 것

| 행동 | 이유 |
|------|------|
| 커밋 실행 | 메시지 제안 → 사용자 승인 → 실행 순서 필수 |
| GitHub 이슈/PR 생성 | 내용 확인 → 사용자 승인 → 생성 순서 필수 |
| **이슈 close** | **이 프로젝트는 완료 시 이슈를 닫지 않고 라벨을 `작업완료`로 변경한다.** 작업·보고서가 끝났다는 이유로 임의로 close 금지 — 사용자가 명시적으로 "닫아줘"라고 요청할 때만 close (라벨이 Projects 보드 상태와 동기화되므로 close는 이 흐름을 깨뜨린다) |
| 파일 삭제 | 삭제 전 반드시 사용자 허락 |
| push | 대상/내용 명시 후 사용자 승인 필수 |

### 전용 스킬 경유 강제 (우회 금지)

아래 작업은 **반드시 해당 전용 스킬을 거쳐서** 수행한다. 스킬을 건너뛰고 `curl`·GitHub API로 직접 처리하는 것은 금지한다 — 템플릿 규격·제목 prefix·중복검사·로컬 파일 저장 등 스킬이 보장하는 절차를 우회하기 때문이다.

| 작업 | 반드시 경유할 스킬 |
|------|------------------|
| GitHub 이슈 **생성** | `issue` |
| GitHub PR 생성, 이슈 조회/수정/댓글, Actions Secret | `github` |
| 이슈 기반 커밋 | `commit` |
| 구현 보고서 작성·PR 댓글 | `report` |

**복합 요청 처리 원칙**: "이슈 만들고 커밋하고 보고서까지"처럼 여러 작업이 한 번에 요청되어도, **각 단계를 빠르게 직접 처리하지 말고** 해당 단계의 전용 스킬을 순서대로 호출한다. "한 번에 끝내는 게 빠르다"는 판단으로 스킬을 우회하지 않는다.

**예외**: 이미 생성된 이슈의 제목·본문을 규격에 맞게 **보정**하거나, 스킬이 명시적으로 위임한 curl 호출(스킬 내부 절차)은 직접 호출을 허용한다.

### 이슈 기반 커밋 원칙

이슈 기반 작업 시 커밋 전 반드시 이슈 컨텍스트(`current-issue.json`)가 존재해야 한다.
없으면 **즉시 멈추고** 선택지 제시 — 절대 임의로 커밋 메시지를 만들어 커밋하지 않는다.
(이슈와 무관한 hotfix·설정 변경은 자유 형식 커밋 허용 — 절대 규칙 §1 참조)

### 이슈 작성 컨벤션 (반드시 준수)

이슈 제목 형식:
```
[이모지+태그][카테고리] 제목
```

허용 이모지+태그 (이 외 사용 금지):

| 이모지+태그 | 용도 |
|-------------|------|
| `❗[버그]` | 버그 리포트 |
| `🎨[디자인]` | 디자인/UI 요청 |
| `🔧[기능요청]` | 기능 요청 |
| `⚙️[기능추가]` | 새 기능 추가 |
| `🚀[기능개선]` | 기존 기능 개선 |
| `🔍[시험요청]` | QA/테스트 요청 |
| `📄[문서]` | 문서 관련 |
| `🔥[긴급]` | 긴급 (사용자가 명시할 때만) |

**규칙**:
- 이모지와 `[` 사이 공백 없음: `⚙️[기능추가]` (O), `⚙️ [기능추가]` (X)
- `·` 등 구분자 이모지 사용 금지
- 허용 목록 외 이모지 사용 금지
- 이슈 파일 저장 위치: `docs/projectops/issue/` (agent가 직접 경로 계산)
- `.issue/` 폴더에 저장하는 것 금지

### 이슈 MD 파일명 규칙

- **등록 전**: `YYYYMMDD_001_제목.md` — seq 번호 사용, 이모지 없는 순수 제목
- **등록 후**: `YYYYMMDD_245_제목.md` — 실제 이슈 번호로 rename (선택)
- **금지**: 파일명에 이모지 포함, `TMP` 접두사 사용

### 이슈 등록 순서 (이슈 기반 작업 시)

1. 이슈 파일 로컬 저장 (`YYYYMMDD_001_제목.md`)
2. 사용자에게 내용 확인 요청
3. 승인 후 GitHub 등록
4. 반환된 실제 이슈 번호 확인
5. 이슈 번호 확정 후 파일명 rename (`YYYYMMDD_245_제목.md`) — 선택
6. 이슈 번호가 확정된 후에만 커밋 가능

이슈 기반 작업에서 이슈 번호 없이 커밋하는 것은 절대 금지다.

## 작업 시작 프로토콜

모든 코드 관련 skill은 다음 순서로 시작한다:

0. **페르소나 로드** — `references/personas.md`에서 공통 마인드셋 6종 + 본 skill의 페르소나 카드(매핑표 참조)를 명시적으로 장착한다. 페르소나는 장식이 아니라 행동 강제 레이어다.
1. `references/project-detection.md`에 따라 프로젝트 타입 감지
2. `references/code-style-detection.md`에 따라 코드 스타일 감지 (기존 코드 3-5개 샘플링)
3. 프로젝트 타입에 맞는 기술 가이드 참조:
   - Spring Boot → `references/tech-spring.md`
   - React / React Native / Expo → `references/tech-react.md`
   - Flutter → `references/tech-flutter.md`
   - Next.js → `references/tech-react.md` (React 기반)
   - Node.js / Python → 기술 가이드 없음, 코드베이스 직접 분석
4. **Git 컨텍스트 확인** (코드 수정이 수반되는 작업 시 필수) — 아래 §Git 컨텍스트 확인 프로토콜 수행
5. 본 skill의 작업 수행

## Git 컨텍스트 확인 프로토콜

코드 수정이 수반되는 모든 작업(구현, 버그 수정, 리팩토링 등) 시작 전에 반드시 수행한다.
분석·계획·문서 전용 스킬(`/plan`, `/analyze`, `/design-analyze`, `/refactor-analyze`)은 제외.

### 1단계: 현재 브랜치 확인

```bash
git rev-parse --abbrev-ref HEAD
```

현재 브랜치가 **main(프로덕션, 직접 커밋·push 금지, 레포에 따라 master 등으로 불릴 수 있는 default branch)이거나 develop이면 즉시 멈추고** 사용자에게 확인한다. main인 경우 특히 더 강하게 경고한다 — main은 릴리스(develop→main PR)로만 갱신되어야 하는 배포 브랜치다.
feature 브랜치이면 이슈 번호 추출로 넘어간다.

### 2단계: 이슈 번호 확인

현재 브랜치명이 `YYYYMMDD_#번호_제목` 형식인지 확인한다.

- **이슈 번호 있음** → 해당 이슈를 GitHub API로 조회해 제목·상태 출력 후 작업 진행
- **이슈 번호 없음** → 사용자에게 확인 (아래 §사용자 확인 메시지 참조)

### 3단계: 사용자 확인 메시지

브랜치가 main·develop이거나 이슈 번호가 없을 때 **반드시** 아래 형식으로 묻는다.
한 번에 한 질문. 사용자가 답하면 그에 따라 진행한다.

**main 브랜치인 경우 (⚠️ main은 프로덕션 — 직접 커밋·push 금지):**
```
현재 main(프로덕션) 브랜치에서 작업하려고 합니다. main은 직접 커밋·push 대상이 아니며, develop→main 릴리스 PR로만 갱신되어야 합니다.
이 작업에 연결된 이슈가 있나요?

1. 이슈 번호 알려주세요 → 브랜치명 자동 계산 후 안내
2. 이슈 없음 → 새로 생성할까요? (`/pro-github`의 이슈 생성 워크플로우로 이동)
3. 그래도 main에서 바로 작업 (hotfix 등 예외 상황 — 신중히 확인 후 진행)
```

**develop 브랜치인 경우 (기본 개발 브랜치):**
```
현재 develop 브랜치에서 작업하려고 합니다.
이 작업에 연결된 이슈가 있나요?

1. 이슈 번호 알려주세요 → 브랜치명 자동 계산 후 안내
2. 이슈 없음 → 새로 생성할까요? (`/pro-github`의 이슈 생성 워크플로우로 이동)
3. 이슈 없이 develop에서 바로 작업 (경미한 수정 등)
```

**feature 브랜치이지만 이슈 번호가 없는 경우:**
```
현재 브랜치 [{브랜치명}]에 이슈 번호가 없습니다.
연결된 이슈가 있나요?

1. 이슈 번호 알려주세요
2. 이슈 없이 현재 브랜치에서 바로 작업
```

### 4단계: 사용자 선택에 따른 처리

| 선택 | 처리 |
|------|------|
| 이슈 번호 제공 | GitHub API로 이슈 조회 → 브랜치명 계산(`YYYYMMDD_#번호_제목`) → worktree 여부 확인 → 작업 진행 |
| 이슈 새로 생성 | `/pro-github`의 이슈 생성 워크플로우로 이동 (이슈 생성 후 돌아와서 작업) |
| main에서 바로 작업 | 사용자가 명시적으로 선택한 것이므로 허용 — 커밋은 자유 형식 |
| 현재 브랜치에서 바로 작업 | 허용 — 진행 |

### worktree 여부 확인

이슈 번호가 확정되어 새 브랜치가 필요한 경우 반드시 묻는다:

```
worktree로 격리된 환경에서 작업할까요, 아니면 현재 디렉토리에서 브랜치만 생성할까요?

1. worktree 생성 (/init-worktree 실행)
2. 현재 디렉토리에서 브랜치만 생성
```

## 분석 전용 스킬 규칙

`/plan`, `/analyze`, `/design-analyze`, `/refactor-analyze`에 적용:

- **금지**: Edit/Write 도구 사용, 파일 생성/수정/삭제, 코드 작성
- **허용**: 코드 읽기(Read), 검색(Glob, Grep), 분석, 계획 수립, 사용자 질문

## 워크플로우 체인

**기본**: `/plan` → `/analyze` → `/implement` → `/review` → `/test`
**설계**: `/design-analyze` → `/design` → `/implement` → `/review` → `/test`
**리팩토링**: `/refactor-analyze` → `/refactor` → `/review` → `/test`

각 skill은 이전 단계의 결과를 참조하고, 다음 단계를 안내한다.

## skill별 py 분산 호출 (3-layer 아키텍처 표준)

`config-get` / `init-config`는 제거되었다 — config는 agent가 Read/Write tool로 직접 처리한다 (`references/config-rules.md` 참조).

`scripts/suh_template/` 단일 모듈은 제거되었다. 7개 skill이 각자 `skills/<skill>/scripts/<scope>_cli.py`를 보유하고, 공유 도메인 로직은 `scripts/common/`에서 import한다.

### 3-layer 아키텍처

- **Layer 1** `scripts/common/`: GitHub HTTP·config 로드·경로/제목/이슈번호 등 도메인 순수 함수
- **Layer 2** `skills/<skill>/scripts/<scope>_cli.py`: skill 1개 = py 1개 = argparse 서브커맨드
- **Layer 3** `SKILL.md`: 사용자 대화·문서 작성·Python 호출 = self-contained 5줄

| skill | py 파일 |
|---|---|
| github | `skills/pro-github/scripts/github_cli.py` (이슈 생성·조회·수정·검색·댓글·라벨·담당자·PR·secret·actions + normalize-title·create-branch-name·get-commit-template 흡수) |
| commit | `skills/pro-commit/scripts/commit_cli.py` |
| report | `skills/pro-report/scripts/report_cli.py` |
| review | `skills/pro-review/scripts/review_cli.py` |
| troubleshoot | `skills/pro-troubleshoot/scripts/troubleshoot_cli.py` |
| changelog-deploy | `skills/pro-changelog-deploy/scripts/changelog_cli.py` |

### 표준 호출 패턴 (self-contained 6줄)

모든 Bash 코드블록은 self-contained — agent가 어느 블록부터 시작해도 100% 동작.

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=<skill>; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || ROOT=$(ls -d ~/.claude/plugins/cache/*/projectops/* ~/.codex/plugins/cache/*/projectops/* 2>/dev/null | sort -V | tail -1)
[ -n "$ROOT" ] || ROOT=$(ls -d ~/.gemini/extensions/projectops ~/.pi/agent/git/github.com/*/projectops 2>/dev/null | head -1)
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
cd "$SCRIPTS" || exit 1
PYTHONIOENCODING=utf-8 "$PYTHON" <scope>_cli.py <subcommand> [args]
```

> **⚠️ 스크립트 탐색: 로컬 → 하네스 설치 경로 폴백 (#524·#528 — 이 순서를 뒤집지 말 것)**
>
> 위 3줄은 **스킬명이 경로에 박히지 않도록 "플러그인 루트"만 해석**한다. 그래서 어느 스킬에서든 `SKILL=` 값 하나만 다르고 나머지는 문자 그대로 같다. 하네스가 늘어도 고칠 형태는 이 한 곳뿐이다.
>
> | 위치 | 언제 | 버전 계층 |
> |---|---|---|
> | `$ROOT/skills/<skill>/scripts/` | **projectops 레포 자신** (여기서만 `skills/`가 실재) | 해당 없음 |
> | `~/.claude/plugins/cache/{마켓}/projectops/{버전}/` | Claude Code | 있음 |
> | `~/.codex/plugins/cache/{마켓}/projectops/{버전}/` | Codex | 있음 |
> | `~/.gemini/extensions/projectops/` | Gemini | 없음 |
> | `~/.pi/agent/git/github.com/{owner}/projectops/` | pi | 없음 |
>
> **버전 계층이 있는 두 하네스를 `sort -V`로 먼저 조회하고, 결과가 없을 때만 무버전 하네스로 넘어간다.** 네 경로를 한 번에 `sort -V`하면 하네스 루트 이름(`.claude` vs `.pi`)이 버전보다 먼저 비교되어 버전과 무관한 항목이 선택된다. 이 2단계를 하나로 합치지 말 것.
>
> 마지막 `[ -d "$SCRIPTS" ] || { ...; exit 1; }` 가드도 빼지 말 것. `cd ""`는 실패하지 않고 현재 디렉터리에 머물기 때문에, 가드가 없으면 스크립트를 못 찾아도 조용히 통과해 엉뚱한 위치에서 실행된다.
>
> 위 `ROOT=...` 라인은 **로컬이 있으면 로컬, 없으면 하네스 설치본**으로 폴백한다. 두 환경 모두에서 옳다:
>
> - 사용자 프로젝트에는 `skills/`가 없다(통합 시 제외) → 자동으로 하네스 설치본이 쓰인다. **기존과 동일한 동작.**
> - projectops 레포에는 `skills/`가 있다 → 자기 코드가 쓰인다. **수정 즉시 테스트 가능.**
>
> 과거에는 캐시를 먼저 봤는데(#386 해결 과정에서 도입), 그러면 이 레포에서 스킬을 고쳐도 **릴리스로 캐시가 갱신되기 전까지 자기 변경분을 쓸 수 없었다.** 새 서브커맨드를 추가하자마자 "그런 커맨드 없음"으로 실패하는 문제가 실제로 발생했다.
>
> `_cli.py`는 `Path(__file__).parents[3]` 기준으로 `scripts/common`을 import하므로(cwd 무관), 스크립트 파일 위치만 맞으면 `cd` 위치와 무관하게 import가 풀린다.
> config(`~/.projectops/config/config.json`)는 항상 user 홈 기준이라 프로젝트 위치와 무관하다.

### OS 호환성 (실측 검증 완료)

- Windows Git Bash MINGW64 ⭕
- WSL Linux bash 5.2 ⭕
- macOS bash/zsh ⭕ (POSIX 호환)
- PowerShell 미지원 (Claude Code Bash tool = bash 강제)

### MCP-style JSON 출력 표준 (4필드 강제)

모든 `<scope>_cli.py` 서브커맨드 출력 = stdout JSON. `scripts/common/emit.py`의 `emit()` 헬퍼가 4필드 자동 보장:

| 필드 | 의미 | 예시 |
|---|---|---|
| `ok` | 성공 여부 | `true` / `false` |
| `code` | 식별자 (에러 시 디버깅용) | `ok`, `missing_pat`, `github_api_404` |
| `summary` | 사람 친화 한 줄 요약 | `"PR #123 생성 완료"` |
| `next` | 다음 행동 힌트 (agent 자율 워크플로우용) | `"deploy-status owner repo --pr 123"` 또는 null |

## GitHub 작업 원칙

GitHub API 작업은 **각 skill의 `<scope>_cli.py` 서브커맨드로 호출**한다. 스킬 문서에 curl 레시피, Python heredoc, 임시 Python 파일을 새로 넣지 않는다.

- PAT는 cli가 `GITHUB_PAT` 환경변수 → `config.json` 순으로 자동 로드한다 (`scripts/common/config.py:get_github_pat`).
- 새 GitHub API 동작이 필요하면 먼저 `references/mcp-subcommand-rules.md`를 읽고 `scripts/common/gh_client.py` 헬퍼 + 해당 skill의 `_cli.py` 서브커맨드 + 테스트를 추가한다.
- `gh` CLI는 별도 설치 필요 및 Windows/macOS 환경 차이로 사용하지 않는다.
- curl 직접 호출은 아직 서브커맨드가 없는 긴급 조사에만 임시 허용한다. 반복 사용이 보이면 즉시 `<scope>_cli.py` 서브커맨드로 승격한다.

대표 호출 (github get-issue):

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-github; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || ROOT=$(ls -d ~/.claude/plugins/cache/*/projectops/* ~/.codex/plugins/cache/*/projectops/* 2>/dev/null | sort -V | tail -1)
[ -n "$ROOT" ] || ROOT=$(ls -d ~/.gemini/extensions/projectops ~/.pi/agent/git/github.com/*/projectops 2>/dev/null | head -1)
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
cd "$SCRIPTS" || exit 1
PYTHONIOENCODING=utf-8 "$PYTHON" github_cli.py get-issue {owner} {repo} {number} --with-comments
```

### GitHub API 공통 에러 대응

| HTTP 코드 | 원인 | 조치 |
|-----------|------|------|
| 401 | PAT 만료 또는 미전달 | `references/config-rules.md §2~5`로 PAT 재등록 안내 |
| 403 | 권한 부족 (repo/workflow 권한 없음) | PAT 권한 확인 요청 |
| 404 | owner/repo 오타 또는 비공개 저장소 접근 | `git remote get-url origin` 재확인 |
| 422 | 요청 값 오류 (라벨 없음, 중복 PR 등) | 오류 메시지 파싱 후 사용자에게 안내 |
| 35 (curl exit) | Windows 내부망 SSL 오류 | `--ssl-no-revoke` 추가 후 재시도 |

## Git Push 실행 시 동작 규칙

스킬이 `git push`를 실행해야 하는 경우 (사용자가 push를 요청하거나 스킬 플로우상 push가 필요한 경우):

1. `git pull --rebase origin main` 먼저 실행
2. rebase 성공 후 `git push origin main` 실행
3. 사용자에게는 결과만 친근하게 안내 (rebase 과정은 내부적으로 처리, 별도 설명 불필요)

> 이 프로젝트는 main 푸시 시 버전 자동 증가 워크플로우가 실행되어 리모트에 커밋이 추가된다. rebase 없이 push하면 rejected된다.

## 커밋 메시지 컨벤션

이 프로젝트의 커밋 메시지 형식은 다음과 같다:

```
{이슈제목} : {타입} : {변경사항 설명} {이슈URL}
```

**타입 목록**:

| 타입 | 용도 |
|------|------|
| `feat` | 새 기능 추가 |
| `fix` | 버그 수정 |
| `refactor` | 리팩토링 (기능 변경 없음) |
| `docs` | 문서/주석 변경 |
| `chore` | 빌드, 설정, 기타 |
| `style` | 코드 스타일 (로직 변경 없음) |
| `test` | 테스트 추가/수정 |

**예시**:

이슈 제목이 `⚙️[기능추가][Skills] commit 스킬 신규 추가`인 경우, SUH-ISSUE-HELPER가 생성하는 커밋 템플릿은 이모지+태그를 제거한 순수 내용만 사용한다:

```
commit 스킬 신규 추가 : feat : 이슈 컨텍스트 기반 커밋 메시지 자동 생성 https://github.com/Cassiiopeia/projectops/issues/224
commit 스킬 신규 추가 : docs : common-rules 커밋 컨벤션 예시 수정 https://github.com/Cassiiopeia/projectops/issues/224
commit 스킬 신규 추가 : fix : owner/repo 추출 로직 버그 수정 https://github.com/Cassiiopeia/projectops/issues/224
```

**핵심 규칙**:
- `{이슈제목}`은 SUH-ISSUE-HELPER가 생성한 커밋 템플릿의 앞부분을 **그대로** 사용한다 — 이모지+태그(`⚙️[기능추가][Skills]`)는 포함하지 않는다
- `{타입}`은 **이번 커밋의 변경 내용**에 따라 결정한다 — `feat`가 기본값이지만 항상 feat가 아니다
- 같은 이슈에 여러 커밋을 할 때 타입이 달라질 수 있다 (feat → fix → docs 순서로 커밋 가능)
- 이슈 컨텍스트가 있을 때만 이 형식을 사용한다
- 이슈와 무관한 커밋(hotfix, 설정 변경 등)은 자유 형식 허용
- 사용자가 `/commit` 스킬을 호출하면 이 형식으로 자동 완성

커밋 템플릿 계산 (agent가 직접 생성):
```
형식: {이슈제목에서 이모지·태그 제거한 순수 내용} : {타입} : {설명} {이슈URL}
```

## 민감 정보 보호

`docs/projectops/` 폴더는 Git에 공개 커밋된다. 이슈/보고서/플랜 등 모든 산출물 파일에 민감 정보가 포함되지 않도록 반드시 아래 규칙을 따른다.

### 절대 포함 금지 항목

- GitHub PAT, API Key, Secret, Token, Password 실제 값
- 서버 IP, 내부 도메인, SSH 접속 정보
- 개인 이메일, 전화번호 등 개인정보
- `.env` 파일 내용, DB 접속 정보

### 마스킹 규칙

실제 값이 아닌 플레이스홀더로 표기:

| 종류 | 표기 방식 |
|------|-----------|
| API Key / PAT / Token | `{API_KEY}`, `{PAT}`, `{TOKEN}` |
| Password / Secret | `{PASSWORD}`, `{SECRET}` |
| DB 유저명 / 계정명 | `{DB_USERNAME}`, `{ADMIN_ID}` |
| 서버 주소 | `{SERVER_HOST}` |
| 개인정보 | `{EMAIL}`, `{PHONE}` |

### 보고서/이슈 작성 시 추가 주의

- 에러 로그에 토큰/키가 포함된 경우 반드시 마스킹 후 기재
- 재현 방법에 실제 서버 정보 대신 `{SERVER_HOST}` 등 플레이스홀더 사용
- 스크린샷/로그 인용 시 민감 값은 플레이스홀더로 대체 (`***` 같은 익명 별표 금지 — 종류를 알 수 없어 의미 전달 불가)

### 파일 저장 직전 자체검토 프로토콜

산출물 파일(보고서, 이슈 등)을 저장하기 **직전**, AI는 작성한 내용 전체를 스스로 아래 체크리스트로 검토한다.

**검토 항목**:

| 항목 | 위험 예시 | 안전 예시 |
|------|-----------|-----------|
| 비밀번호 실제값 | `password: abc123`, `비번: qwer1234` | `password: {PASSWORD}` |
| ID/계정/DB유저명 실제값 | `admin/mypassword`, `아이디: hong123`, `username: kimchi` | `{ADMIN_ID}/{PASSWORD}`, `{DB_USERNAME}` |
| API Key / Token 실제값 | `sk-abc123xyz`, `AIza...` | `{API_KEY}` |
| GitHub PAT 실제값 | `ghp_abc123...` (실제 유효한 긴 문자열) | `{PAT}` |
| DB 접속 정보 실제값 | `mysql://user:pass@192.168.0.1` | `mysql://{DB_USER}:{DB_PASS}@{DB_HOST}` |
| 개인정보 | 전화번호, 주민번호, 실명+계좌 조합 | `{PHONE}`, `{SSN}` |

**판단 기준**:
- `${{ secrets.XXX }}` 형태 — **안전** (키 이름이며 실제값 아님)
- `{DB_USERNAME}`, `{PASSWORD}` 형태 — **안전** (명명된 플레이스홀더)
- `ghp_ru0dCYe...` 처럼 실제로 유효해 보이는 긴 문자열 — **위험**
- `password: admin123` 처럼 실제 값이 평문 노출 — **위험**
- `username: kimchi`, `user: hong123` 처럼 실제 계정명 노출 — **위험**
- `********` 같은 익명 별표 — **금지** (플레이스홀더로 교체할 것)

**처리 방식**:
1. 위험 항목 발견 시 → 해당 값을 플레이스홀더로 교체 후 저장
2. 마스킹한 항목이 있으면 저장 후 사용자에게 고지:
   ```
   ⚠️ 민감 정보 마스킹 처리됨:
   - [항목 종류]: 실제값 → {플레이스홀더}
   ```
3. 위험 항목 없으면 → 그대로 저장 진행 (별도 메시지 불필요)
