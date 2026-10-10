# 스크립트 호출 표준 (상세)

`common-rules.md` §"skill별 py 분산 호출"·§"스크립트 탐색"의 근거와 상세다. 표준 블록 자체는
`common-rules.md` §"표준 호출 패턴"에 있다 — 형태를 바꿀 때만 이 문서를 읽는다.

## 3-layer 아키텍처

`config-get` / `init-config`는 제거되었다 — config는 agent가 Read/Write tool로 직접 처리한다 (`config-rules.md`).
`scripts/suh_template/` 단일 모듈도 제거되었다. 각 skill이 `skills/<skill>/scripts/<scope>_cli.py`를 보유하고,
공유 도메인 로직은 `scripts/common/`에서 import한다.

- **Layer 1** `scripts/common/`: GitHub HTTP·config 로드·경로/제목/이슈번호 등 도메인 순수 함수
- **Layer 2** `skills/<skill>/scripts/<scope>_cli.py`: skill 1개 = py 1개 = argparse 서브커맨드
- **Layer 3** `SKILL.md`: 사용자 대화·문서 작성·Python 호출

`github_cli.py`는 이슈 생성·조회·수정·검색·댓글·라벨·담당자·PR·secret·actions와
`normalize-title`·`create-branch-name`·`get-commit-template`를 흡수했다 (pro-issue 통합, #464).

## 스크립트 탐색: 로컬 → 하네스 설치 경로 폴백 (#524·#528·#542 — 이 형태를 바꾸지 말 것)

표준 블록은 **스킬명이 경로에 박히지 않도록 "플러그인 루트"만 해석**한다. 그래서 어느 스킬에서든
`SKILL=` 값 하나만 다르고 나머지는 문자 그대로 같다. 하네스가 늘어도 고칠 형태는 이 한 곳뿐이다.

| 위치 | 언제 | 버전 계층 |
|---|---|---|
| `$ROOT/skills/<skill>/scripts/` | **projectops 레포 자신** (여기서만 `skills/`가 실재) | 해당 없음 |
| `~/.claude/plugins/cache/{마켓}/projectops/{버전}/` | Claude Code | 있음 |
| `~/.codex/plugins/cache/{마켓}/projectops/{버전}/` | Codex | 있음 |
| `~/.gemini/extensions/projectops/` | Gemini | 없음 |
| `~/.pi/agent/git/github.com/{owner}/projectops/` | pi | 없음 |

**하네스를 한 줄에 나열하지 않고 `for`로 하나씩 검사한다 (#542 — 절대 되돌리지 말 것).**
여러 경로 패턴을 한 `ls`에 나열하면, zsh는 그중 하나라도 매치되지 않을 때 `no matches found`로
**명령 전체를 실행하지 않는다.** Claude Code의 실행 셸이 zsh이므로, Codex를 안 쓰는 사용자에게는
나란히 적힌 Claude 경로까지 함께 버려졌다. 실측에서 최신 캐시(4.2.44)가 있는데도 빈 값이 나왔고,
다른 설치본이 있으면 **구버전(4.2.19)이 조용히 실행**됐으며, Claude Code만 설치한 환경에서는
스킬이 아예 죽었다.

**`ls` + 나열 대신 `find`를 위치별로 쓴다.** `find`는 없는 경로를 만나도 그 경로만 건너뛴다.
우선순위는 `for` 목록 순서가 정하고, 같은 위치 안의 여러 버전은 `sort -V | tail -1`이 최신을 고른다.

마지막 `[ -d "$SCRIPTS" ] || { ...; exit 1; }` 가드도 빼지 말 것. `cd ""`는 실패하지 않고 현재
디렉터리에 머물기 때문에, 가드가 없으면 스크립트를 못 찾아도 조용히 통과해 엉뚱한 위치에서 실행된다.

`ROOT=...` 라인은 **로컬이 있으면 로컬, 없으면 하네스 설치본**으로 폴백한다. 두 환경 모두에서 옳다.

- 사용자 프로젝트에는 `skills/`가 없다(통합 시 제외) → 자동으로 하네스 설치본이 쓰인다.
- projectops 레포에는 `skills/`가 있다 → 자기 코드가 쓰인다. **수정 즉시 테스트 가능.**

과거에는 캐시를 먼저 봤는데(#386), 그러면 이 레포에서 스킬을 고쳐도 **릴리스로 캐시가 갱신되기
전까지 자기 변경분을 쓸 수 없었다.** 새 서브커맨드를 추가하자마자 "그런 커맨드 없음"으로 실패했다.

`_cli.py`는 `Path(__file__).parents[3]` 기준으로 `scripts/common`을 import하므로(cwd 무관),
스크립트 파일 위치만 맞으면 `cd` 위치와 무관하게 import가 풀린다.
config(`~/.projectops/config/config.json`)는 항상 user 홈 기준이라 프로젝트 위치와 무관하다.

## PYTHON 변수 설정 — 왜 이 형태인가

`command -v python3`만 쓰지 않고 `-c "import sys; sys.exit(0)"`로 실제 실행을 확인한다. Windows에서
`python3`가 Microsoft Store stub을 가리키면 존재는 하지만 실행이 `Exit code 49`로 실패하기 때문이다.
`python3 -c` 직접 호출도 같은 이유로 쓰지 않는다. 한글이 흐르는 호출은 `PYTHONIOENCODING=utf-8`을
붙인다 (#653 — Windows 기본 cp949로 한글이 깨진 채 커밋된 사고).

## OS 호환성 (실측 검증 완료)

- Windows Git Bash MINGW64 ⭕
- WSL Linux bash 5.2 ⭕
- macOS bash/zsh ⭕ (POSIX 호환)
- PowerShell 미지원 (Claude Code Bash tool = bash 강제)

## MCP-style JSON 출력 표준 (4필드 강제)

모든 `<scope>_cli.py` 서브커맨드 출력 = stdout JSON. `scripts/common/emit.py`의 `emit()`이 4필드를 보장한다.

| 필드 | 의미 | 예시 |
|---|---|---|
| `ok` | 성공 여부 | `true` / `false` |
| `code` | 식별자 (에러 시 디버깅용) | `ok`, `missing_pat`, `github_api_404` |
| `summary` | 사람 친화 한 줄 요약 | `"PR #123 생성 완료"` |
| `next` | 다음 행동 힌트 | `"deploy-status owner repo --pr 123"` 또는 null |

새 서브커맨드 설계는 `mcp-subcommand-rules.md`.

## GitHub 작업 원칙

GitHub API 작업은 **각 skill의 `<scope>_cli.py` 서브커맨드로 호출**한다. 스킬 문서에 curl 레시피,
Python heredoc, 임시 Python 파일을 새로 넣지 않는다.

- PAT는 cli가 `GITHUB_PAT` 환경변수 → `config.json` 순으로 자동 로드한다 (`scripts/common/config.py:get_github_pat`).
- 새 GitHub API 동작이 필요하면 `mcp-subcommand-rules.md`를 읽고 `scripts/common/gh_client.py` 헬퍼 + 해당 skill의 `_cli.py` 서브커맨드 + 테스트를 추가한다.
- `gh` CLI는 별도 설치 필요 및 Windows/macOS 환경 차이로 사용하지 않는다.
- curl 직접 호출은 아직 서브커맨드가 없는 긴급 조사에만 임시 허용한다. 반복 사용이 보이면 즉시 서브커맨드로 승격한다.

대표 호출: 표준 블록을 `SKILL=pro-github`로 찾은 뒤
`PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py get-issue {owner} {repo} {number} --with-comments`.

### GitHub API 공통 에러 대응

| HTTP 코드 | 원인 | 조치 |
|-----------|------|------|
| 401 | PAT 만료 또는 미전달 | `config-rules.md §2~5`로 PAT 재등록 안내 |
| 403 | 권한 부족 (repo/workflow 권한 없음) | PAT 권한 확인 요청 |
| 404 | owner/repo 오타 또는 비공개 저장소 접근 | `git remote get-url origin` 재확인 |
| 422 | 요청 값 오류 (라벨 없음, 중복 PR 등) | 오류 메시지 파싱 후 사용자에게 안내 |
| 35 (curl exit) | Windows 내부망 SSL 오류 | `--ssl-no-revoke` 추가 후 재시도 (아래) |

## Windows 내부망 환경

- curl이 `exit 35`(SSL 오류)로 실패하면 인증서 폐기 확인이 막힌 것이다 → curl에 `--ssl-no-revoke`를 붙여 재시도한다.
- 폐쇄망에서 `pip install`이 안 될 수 있다. 스크립트는 표준 라이브러리 우선이고, 외부 패키지가 꼭 필요하면
  설치 시도 후 실패 시 수동 설치 안내를 낸다 (`mcp-subcommand-rules.md` §5).
