# 공통 규칙

모든 skill이 시작할 때 읽는 절대 규칙이다. 특정 상황의 상세는 각 절의 링크 문서에 있다 — 필요할 때만 읽는다.
스킬 문서를 쓰거나 고칠 때(참조 경로 `../references/` 규칙 등)는 `skill-authoring.md`.
"다음에도 쓸 지식"을 저장·회수하는 기능을 만들거나 고칠 때는 `memory-principles.md`.

## 절대 규칙

1. **Git 커밋은 이슈 컨텍스트 + 사용자 승인 없이 실행하지 않는다** — 이슈 기반 작업은 이슈 번호 확정 후에만 커밋. 이슈와 무관한 hotfix·설정 변경은 자유 형식 허용. 서브에이전트에게도 동일하게 지시한다. 번호는 브랜치명(`commit_cli.py get-issue-number`) 또는 사용자에게 받고, 확인하지 못하면 **즉시 멈추고** 선택지를 제시한다 (`commit-convention.md` §이슈 기반 커밋 원칙).
2. **코드 스타일 100% 준수** — 기존 프로젝트 패턴을 감지하고 동일하게 따른다. 새로운 "더 나은" 방식을 임의로 제안하지 않는다.
3. **프로젝트 타입 감지 필수** — 작업 시작 전 반드시 프로젝트 타입을 자동 감지한다.
4. **민감 정보 보호** — 산출물·댓글에 실제 비밀값을 넣지 않는다 (아래 §민감 정보 보호).
5. 레포 `CLAUDE.md`·`AGENTS.md`가 다른 규칙을 정했으면 그쪽이 우선한다.

## AI 행동 강제 원칙

아래 원칙은 **스킬 내용보다 우선**한다.

### 확인 없이 절대 하지 않는 것

| 행동 | 이유 |
|------|------|
| 커밋 실행 | 메시지 제안 → 사용자 승인 → 실행 순서 필수 |
| GitHub 이슈/PR 생성 | 내용 확인 → 사용자 승인 → 생성 순서 필수 |
| **이슈 상태·라벨 변경** | 아래 §이슈 상태 처리 규칙의 **파이프라인 단계는 확인 없이 해도 된다** (작업 시작 → `status: in progress`, 작업 완료 → `status: done` 교체 후 close). 그 밖의 임의 변경(다른 사람 이슈 닫기, 상관없는 라벨 바꾸기)은 사용자 요청이 있을 때만 |
| 파일 삭제 | 삭제 전 반드시 사용자 허락 |
| push | 대상/내용 명시 후 사용자 승인 필수 |
| **외부 계정·인증서·Secret을 바꾸는 실행** | 인증서 재발급, 프로비저닝 프로필 갱신, Actions Secret 교체, 외부 저장소 push. 무엇이 바뀌는지 말하고 승인받은 뒤 실행한다 (조회·읽기 전용 확인은 승인 불필요) |
| **사용자 환경을 바꾸는 설치** | 패키지·런타임·브라우저·CLI를 까는 일은 **무엇을 왜 얼마나 받는지 말하고 물어본 뒤** 실행한다. 스킬이 돌아가려면 필요하다는 것은 이유가 되지만 승인은 아니다 |

### 이슈 상태 처리 규칙

상태 라벨은 영문 표준과 한글 표기를 둘 다 쓴다 (#776). 스킬 CLI가 두 표기를 서로 바꿔 인식하므로
레포에 있는 쪽으로 자동 치환된다. 문서·예시는 영문을 먼저 쓰고 한글을 병기한다.

| 시점 | 처리 | 명령 |
|------|------|------|
| 작업 시작 | 라벨을 `status: in progress`(`작업중`)로 교체 | `github_cli.py set-labels {owner} {repo} {번호} "status: in progress"` |
| 작업 완료 | 라벨을 `status: done`(`작업완료`)로 **교체** 후 close | `set-labels ... "status: done"` → `close-issue ... --reason completed` |
| 남은 작업 있음 | 닫지 않고 `status: in progress` 유지 | — |
| 작업 취소 | 라벨을 `status: cancelled`(`취소`)로 교체 후 close | `set-labels ... "status: cancelled"` → `close-issue ... --reason not_planned` |

- **`add-labels`가 아니라 `set-labels`로 교체한다** — 더하기만 하면 `status: todo`가 남아 상태가 두 개가 된다.
  상태 외 라벨(`priority: urgent` 등)을 지키려면 `get-issue`로 기존 라벨을 읽어 상태 라벨만 바꾼 목록을 넘긴다.
- 완료 처리 레시피는 `pro-github/SKILL.md` §"이슈 완료 처리"에 있다. `pro-report`가 보고서를 올린 뒤 이 레시피를 따른다.
- 릴리스 워크플로우(`close_on_release`)도 완료 라벨 이슈를 닫지만, 이미 닫힌 이슈는 건너뛰므로 먼저 닫아도 충돌하지 않는다.
- **취소 이슈는 `close_on_release`가 닫지 않는다**(완료 라벨만 대상). 그래서 취소는 agent가 직접 `close-issue --reason not_planned` 까지 한다.

### 필요한 것이 없을 때

도구가 없으면 ① 무엇이 왜 필요한지·얼마나 받는지 말하고 ② 물어본 뒤 ③ 승인받으면 **스킬이 직접 깐다**
(명령만 알려주고 멈추지 않는다). 격리된 경로에 멱등으로 설치한다.
**안 된다고 말하기 전에** 레포의 CLI·자동화 수단과 저장된 자격증명(`launch_cli.py cred list`)으로 되는지 먼저 **조회**한다.
조회는 바로, 바꾸는 실행은 승인 후. 막히는 지점과 할 수 있는 부분을 나눠 제안한다. 상세: `agent-conduct.md`.

### 전용 스킬 경유 강제 (우회 금지)

`curl`·GitHub API로 직접 처리하면 템플릿 규격·중복검사·로컬 저장 등 스킬이 보장하는 절차를 우회하게 된다.

| 작업 | 반드시 경유할 스킬 |
|------|------------------|
| GitHub 이슈 **생성** | `pro-github` (`issue-creation.md` 워크플로우) |
| GitHub PR 생성, 이슈 조회/수정/댓글/라벨/닫기, Actions Secret | `pro-github` |
| 이슈 기반 커밋 | `pro-commit` |
| 구현 보고서 작성·PR 댓글 | `pro-report` |

한 번에 여러 작업을 요청받아도 각 단계의 전용 스킬을 순서대로 호출한다. **예외**: 이미 생성된 이슈의 제목·본문 **보정**, 스킬이 명시적으로 위임한 호출.

### 이슈 작성 컨벤션 (반드시 준수)

제목 형식 `[이모지+태그][카테고리] 제목`. 허용 태그는 아래뿐이다. 대상 레포 템플릿의 언어를 따르고, 템플릿이
없으면 영문을 쓴다. 두 언어의 태그는 같은 커밋 타입으로 매핑된다 (대소문자 무시).

| 영문 (기본) | 한글 | 용도 |
|-------------|------|------|
| `❗[Bug]` | `❗[버그]` | 버그 리포트 |
| `🎨[Design]` | `🎨[디자인]` | 디자인/UI 요청 |
| `🔧[Feature Request]` | `🔧[기능요청]` | 기능 요청 |
| `⚙️[Feature]` | `⚙️[기능추가]` | 새 기능 추가 |
| `🚀[Improvement]` | `🚀[기능개선]` | 기존 기능 개선 |
| `🔍[QA]` | `🔍[시험요청]` | QA/테스트 요청 |
| `📄[Docs]` | `📄[문서]` | 문서 관련 |
| `🔥[Urgent]` | `🔥[긴급]` | 긴급 (사용자가 명시할 때만) |

- 이모지와 `[` 사이 공백 없음: `⚙️[Feature]` (O), `⚙️ [Feature]` (X). 템플릿 주석의 복사용 예시(`❗ [Bug]`)에 공백이 있어도 **제목에는 붙여 쓴다** — 실제 등록된 이슈 제목이 전부 붙여 쓴 형태다
- `·` 등 구분자 이모지, 허용 목록 외 이모지 사용 금지. 이슈 파일은 `github_cli.py get-output-path issue --title "{제목}"`이 돌려준 `path`에 저장한다 (직접 조립 금지, `.issue/` 폴더 금지)

### 이슈 MD 파일명 규칙

등록 전 `YYYYMMDD_001_제목.md`(`get-output-path issue`가 그날 일련번호·태그 뺀 제목으로 만든다) → 등록 후 실제 번호로
rename `YYYYMMDD_245_제목.md`(권장). 파일명에 이모지·`TMP` 접두사 금지. 등록 순서: `work-start-protocol.md` §이슈 등록 순서.

## 작업 시작 프로토콜

모든 코드 관련 skill은 다음 순서로 시작한다.

1. `project-detection.md`로 프로젝트 타입 감지
2. `code-style-detection.md`로 코드 스타일 감지 (기존 코드 3-5개 샘플링)
3. 기술 가이드: Spring Boot → `tech-spring.md` · React / React Native / Expo / Next.js → `tech-react.md` · Flutter → `tech-flutter.md` · Node.js / Python → 가이드 없음, 코드베이스 직접 분석
4. **Git 컨텍스트 확인** (코드 수정이 수반될 때) — 아래 §Git 컨텍스트 확인 프로토콜
5. 본 skill의 작업 수행

설계·계획·구현 흐름은 `superpowers:brainstorming` → `writing-plans` → `executing-plans` → `/pro-review`.

## Git 컨텍스트 확인 프로토콜

코드 수정 작업 전에 수행한다. 질문 문구·선택지별 처리: `work-start-protocol.md`.

- **main**(프로덕션) → 즉시 멈추고 사용자에게 확인. main은 릴리스 PR로만 갱신된다.
- **개발 브랜치**(`version.yml` `metadata.deploy_branch`, 없으면 `develop`) → 레포 `CLAUDE.md`·`AGENTS.md`가 직행을 선언했으면 통과, 아니면 이슈 연결 여부를 묻는다.
- **feature 브랜치** → `YYYYMMDD_#번호_제목`에서 번호를 뽑아 이슈 조회, 없으면 묻는다. 새 브랜치가 필요하면 worktree(`/pro-init-worktree`) 여부를 묻는다.

## skill별 py 분산 호출

각 skill이 `skills/<skill>/scripts/<scope>_cli.py`를 보유하고(argparse 서브커맨드), 공유 로직은 `scripts/common/`에
있다. SKILL.md는 아래 표준 블록으로 Python을 호출한다 (self-contained 5줄 원칙 — 어느 블록부터 시작해도 동작).
config는 CLI가 아니라 agent가 Read/Write로 직접 다룬다 (`config-rules.md`).

예: `pro-github/scripts/github_cli.py` · `pro-commit/scripts/commit_cli.py` · `pro-report/scripts/report_cli.py` ·
`pro-review/scripts/review_cli.py` · `pro-note/scripts/note_cli.py` · `pro-changelog-deploy/scripts/changelog_cli.py` (다른 스킬도 같은 규칙).
3-layer 구조·JSON 출력(`ok`/`code`/`summary`/`next`)·GitHub API 에러 대응·OS 호환성: `script-invocation.md`.

**GitHub 작업**도 이 서브커맨드로만 한다. `gh` CLI 금지, 스킬 문서에 curl 레시피·Python heredoc·임시 Python 파일을 넣지 않는다.
PAT는 CLI가 자동 로드한다.

### 표준 호출 패턴

**Bash 도구는 호출마다 상태가 초기화된다.** 스크립트는 스킬 실행당 **한 번** 찾고, 출력된 실제 경로를 이후 블록에
값으로 써넣는다 — `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/<scope>_cli.py <subcommand> [args]` (모범: `pro-launch/SKILL.md`).
다른 스킬의 스크립트를 부를 때도 `SKILL=` 값만 그 스킬로 바꾼다.

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=<skill>; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
echo "PYTHON=$PYTHON SCRIPTS=$SCRIPTS PROJECT_ROOT=$PROJECT_ROOT"
```

한 블록에서 찾기와 호출을 함께 하려면(self-contained) `echo` 줄 대신
`cd "$SCRIPTS" || exit 1` 다음 줄에 `PYTHONIOENCODING=utf-8 "$PYTHON" <scope>_cli.py <subcommand> [args]`를 둔다.

### 스크립트 탐색

위 블록은 **로컬(projectops 레포의 `skills/`) → 하네스 설치 경로(Claude Code·Codex·Gemini·pi)** 순으로 플러그인 루트를 찾는다.
**형태를 바꾸지 않는다** — 하네스를 `for`로 하나씩 `find`하는 것(zsh `no matches found` 회피, #542)과 마지막 `[ -d "$SCRIPTS" ]`
가드는 실사고로 생긴 것이다. 근거: `script-invocation.md` §스크립트 탐색.

### PYTHON 변수 설정 (크로스 플랫폼 필수)

위 블록의 `PYTHON=` 줄을 그대로 쓴다. `python3 -c` 직접 호출 금지(Windows Store stub → `Exit code 49`), 한글이 흐르는 호출은
`PYTHONIOENCODING=utf-8` 필수. 근거: `script-invocation.md` §PYTHON 변수 설정.

### Windows 내부망 환경

curl `exit 35`(SSL) → `--ssl-no-revoke` 추가 후 재시도. 상세: `script-invocation.md` §Windows 내부망 환경.

## 출력 경로

산출물 저장 위치는 각 스킬 CLI의 `get-output-path`가 돌려준 `path`를 그대로 쓴다. 경로를 직접 조립하지 않는다
(산출물 루트는 설정 `output.root`로 바뀐다). 상세: `doc-output-path.md`.

## Git Push 실행 시 동작 규칙

1. **main(기본·배포 브랜치)이면 push하지 않는다** — main은 릴리스 PR(`/pro-changelog-deploy`)로만 갱신된다
2. `git pull --rebase origin {현재 브랜치}` 먼저 (릴리스 때 버전 확정 커밋이 개발 브랜치에도 추가되어 로컬이 뒤처지기 쉽다)
3. `git push origin {현재 브랜치}`. non-fast-forward면 다시 rebase로 통합 (강제 push 금지). 사용자에게는 결과만 안내

## 커밋 메시지 컨벤션

형식 `{이슈제목} : {타입} : {변경사항 설명} {이슈URL}` — 이슈제목은 이모지·태그를 뺀 순수 내용,
타입(`feat`/`fix`/`refactor`/`docs`/`chore`/`style`/`test`)은 **이번 커밋의 변경 내용**으로 정한다. 템플릿은
`github_cli.py get-commit-template`의 `template`을 그대로 쓴다. `semver_auto` 레포에서는 타입이 릴리스 버전을 정한다
(`feat!` major · `feat` minor · 나머지 patch — `!`는 호환성이 깨질 때만). 이슈와 무관한 커밋은 자유 형식.
상세·예시: `commit-convention.md`.

## 민감 정보 보호

`docs/projectops/` 산출물은 Git에 공개 커밋된다. PAT·API Key·Secret·Token·Password 실제 값, 서버 IP·내부 도메인·SSH 정보,
개인정보, `.env`·DB 접속 정보를 넣지 않는다.

### 마스킹 규칙

실제 값 대신 명명된 플레이스홀더(`{PAT}`, `{API_KEY}`, `{PASSWORD}`, `{DB_USERNAME}`, `{SERVER_HOST}`, `{EMAIL}` 등)를 쓴다.
`***` 같은 익명 별표는 금지. 표: `sensitive-info.md` §마스킹 규칙.

### 파일 저장 직전 자체검토 프로토콜

산출물을 저장하기 **직전** 내용 전체를 검토해 위험 값을 플레이스홀더로 바꾸고, 바꾼 것이 있으면 저장 후 사용자에게 알린다.
체크리스트·판단 기준·고지 형식: `sensitive-info.md` §파일 저장 직전 자체검토 프로토콜.
