---
name: pro-github
description: "All GitHub work: create, read, edit, close issues and PRs, comments, labels, assignees, merges, repo exploration, Actions logs and secrets. Use for any GitHub issue, PR, label, comment, Actions or secret task, before other skills."
---

# GitHub Mode

## When to use

- 이슈 만들어줘, 이슈 올려줘, 이슈 등록, 버그 리포트, 기능 요청 이슈, QA 요청 이슈, 디자인 요청 이슈
- PR 생성, PR 올려줘, PR 머지해줘
- 이슈 댓글, 댓글 달아줘, 댓글 수정, 댓글 삭제, 이슈 확인해줘, 이슈 닫아줘, 이슈 수정해줘
- 라벨 추가/바꿔줘/빼줘, 담당자 추가해줘
- '/github', '/issue', 내 레포 보여줘, 레포 목록 탐색해줘, README 가져와줘, {레포명} 정보 봐줘, Org 레포 탐색해줘
- secret 업데이트해줘, Actions secret 등록해줘, 환경변수 secret 올려줘, BACKEND_ENV_FILE 업데이트
- GitHub 이슈/PR/레포/Actions/Secret 관련 요청이면 반드시 이 skill을 사용한다. 다른 스킬보다 먼저 트리거되어야 한다.

독립적인 GitHub 제어 스킬이다. 다른 스킬 없이 단독으로 이슈/PR/레포/Actions/Secret 작업을 전부 수행한다.
다른 스킬(pro-report · pro-changelog-deploy 등)도 이 스크립트를 부른다.

> **이슈 "생성"(새 이슈 작성+등록)** 요청이면 — "이슈 만들어줘", "버그 리포트 올려줘", "기능 요청 이슈" 등 — 먼저 `../references/issue-creation.md`의 워크플로우(타입 판단 → 템플릿 작성 → 중복검사 → 로컬 md 저장 → 승인 게이트 → 담당자 결정 → 등록 → 브랜치명 계산)를 따른다. 그 외 작업은 아래 표를 따른다.

인자: $ARGUMENTS

## 무엇을 하려는가 → 서브커맨드 → 자세한 문서

모든 명령은 `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py <서브커맨드> {owner} {repo} ...` 이다.

| 하려는 것 | 서브커맨드 | 자세히 |
|---|---|---|
| 새 이슈 작성+등록 | `search-issues` → `get-output-path issue` → `create-issue` | `../references/issue-creation.md` |
| 이슈 조회 · 여러 개 · 목록 · 검색 | `get-issue [--with-comments]` · `get-issues` · `list-issues` · `search-issues` | `references/issues.md` |
| 이슈 수정 (제목·라벨·담당자·본문) | `update-issue` | `references/issues.md` |
| 이슈 완료 처리 (라벨 교체+닫기 한 번에) · 닫기 · 다시 열기 | `finish-issue` · `close-issue [--reason completed\|not_planned]` · `reopen-issue` | 아래 §이슈 완료 처리 |
| 댓글 추가 · 목록 · 수정 · 삭제 | `add-comment` · `list-comments` · `edit-comment` · `delete-comment` | `references/issues.md` |
| 라벨 목록 · 추가 · 하나 제거 · 전체 교체(**상태 외 라벨도 지운다**) | `list-labels` · `add-labels` · `remove-label` · `set-labels` | `references/issues.md` |
| 담당자 추가 · 제거 | `add-assignees` · `remove-assignees` | `references/issues.md` |
| 제목 정규화 · 브랜치명 · 커밋 템플릿 · 이슈 문서 경로 (API 없음) | `normalize-title` · `create-branch-name` · `get-commit-template` · `get-output-path issue` | `references/issues.md` |
| 이미지 첨부 · 지우기 | `upload-image` · `delete-image` | `references/images.md` |
| PR 생성 · 목록 · 상세 · 수정 | `create-pr` · `list-prs` · `get-pr` · `update-pr` | `references/prs.md` |
| PR 댓글 · 닫기 · 다시 열기 · 머지 | `add-pr-comment` · `close-pr` · `reopen-pr` · `merge-pr` | `references/prs.md` |
| 릴리스 PR 본문에 릴리스 노트 채우기 (CodeRabbit 폴백) | `update-pr` | `references/prs.md` |
| Actions 실패 진단 | `actions show-run\|joblog\|list-failed\|resolve-pr\|resolve-branch` | 아래 라우팅 + `references/actions.md` |
| 워크플로우 실행 · 재실행 · 기다리기(여러 run) · 취소 · run 목록 | `actions dispatch\|rerun\|wait\|cancel\|runs` | `references/actions.md` |
| 전용 명령이 없는 REST 호출 (**curl·PAT 직접 읽기 대신**) | `api GET\|POST\|PUT\|PATCH\|DELETE {owner} {repo} <경로> [--out 파일]` (상대 경로 `actions/runs` 는 레포 접두가 붙는다) | `references/actions.md` |
| 레포 목록 · 상세 · README · 언어 · 커밋 | `explore list-repos\|repo-detail\|readme\|languages\|commits` | `references/explore.md` |
| Actions Secret 목록 · 등록/갱신 | `secrets list\|set` | `references/secrets.md` |

## 스크립트 찾기

> **고정 진입점이 있으면 아래 탐색을 건너뛴다** (#942): `~/.projectops/bin/projectops_cli.py` 는 한 번이라도 CLI 를 실행하면 생기고, 부를 때마다 설치된 가장 새 스크립트를 찾아 인자를 그대로 넘긴다. 세션 도중 플러그인이 업데이트돼도 옛 경로에 묶이지 않는다.
> `PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py github <서브커맨드> ...` (없거나 `scripts_not_found` 면 아래 탐색). 응답에 `newer_installed` 가 오면 이 진입점으로 다시 부른다.
> ⚠️ zsh 에서는 명령을 변수에 담아 부르지 않는다 (`P="python3 …"; $P` → 단어가 안 나뉘어 exit 127). 함수로 감싼다: `G(){ PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py github "$@"; }` 후 `G get-issue {owner} {repo} 12`.

스크립트는 **하네스 설치 경로**에 있다 — 사용자 프로젝트에는 `skills/` 폴더가 없다(통합 시 제외). 로컬(이 저장소) 우선 → 설치 경로 폴백으로 한 번 찾는다 (`../references/common-rules.md` §"스크립트 탐색").
**Bash 도구는 호출마다 상태가 초기화된다.** 출력된 실제 경로를 이후 블록의 `{PYTHON}` · `{SCRIPTS}` · `{PROJECT_ROOT}` 자리에 값으로 써넣는다.

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-github; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
echo "PYTHON=$PYTHON SCRIPTS=$SCRIPTS PROJECT_ROOT=$PROJECT_ROOT"
git remote get-url origin
```

## 시작 전

**Config / PAT** — `../references/config-rules.md` §2~3 절차를 따른다. PAT는 `github_cli`가 `GITHUB_PAT` 환경변수 → `config.json`(repo별 `pat` 우선, 다음 `github.global_pat`) 순으로 자동 로드하므로 호출부에서 추출하지 않는다.

> ⚠️ **config는 탐색 금지.** `config.json`은 고정 경로 `{HOME}/.projectops/config/config.json` 한 곳뿐이다 — Read tool로 바로 읽는다. 플러그인 캐시 탐색은 **스크립트 전용**이며 config는 그 안에 없다. 캐시를 뒤지면 "config 없음"으로 오판해 등록된 PAT를 다시 묻게 된다.
> 파일이 없으면 `../references/config-rules.md §2~5` 절차로 PAT와 repos를 대화형으로 수집해 저장한다 (모든 GitHub 스킬이 공유).

**Repo 결정** — 위 블록의 `git remote get-url origin`(`https://github.com/{owner}/{repo}.git` 또는 `git@github.com:{owner}/{repo}.git`)에서 owner/repo를 뽑아 config `repos`와 대조한다.

- 매칭되면 그 repo, 실패하면 config `repos` 목록을 번호로 나열해 고르게 한다.
- **`$ARGUMENTS`에 `owner/repo`가 명시되면** remote 감지를 건너뛰고 그 repo를 쓴다.
- primary working directory가 대상 레포와 다르면(멀티 레포 워크트리) remote 감지가 틀릴 수 있다 — 인자로 명시하거나 목록에서 고른다.

## 공통 규칙

- **응답 키는 짐작하지 않는다** — `--field a.b` 로 값 하나만 받거나 `--brief` 로 줄인다. 자주 읽는 키 표와 전역 옵션: `../references/output-schemas.md`.
- **MCP-style 서브커맨드 표준**(`../references/mcp-subcommand-rules.md`). 출력은 언제나 JSON — `ok`로 성패, `code`로 갈래(문구가 아니라 code로 판단), `summary`, `next`(이어서 부를 명령)를 읽는다.
- 긴 Python heredoc · 임시 Python 파일 · curl 파이프 Python · 일회용 Python 생성 금지. 인자는 명령행/환경변수로 넘긴다 (Windows Git Bash에서 깨진다).
- **본문(이슈·댓글·PR)은 파일로 저장한 뒤 경로를 넘긴다** — 한국어·이모지·줄바꿈 보존.
- **일시 오류**: 5xx·네트워크 단절은 도구가 멱등 호출(조회·수정·삭제·교체)을 알아서 재시도한다. `add-comment` 는 실패 응답을 받아도 실제로 올라갔는지 확인해 `reconciled: true` 로 돌려주니, 응답을 못 받았다고 같은 댓글을 다시 달지 않는다.
- 파괴적 작업(PR 머지·닫기, 남의 이슈 닫기·다시 열기, 파이프라인 밖 라벨 변경)은 **사용자가 명시적으로 요청할 때만** 한다. 작업 파이프라인의 상태 전환(시작 `status: in progress`, 완료 `status: done`, 취소 `status: cancelled`)은 확인 없이 해도 된다.
- 상태 라벨은 영문 표준(`status: todo` 등)과 한글(`작업전` 등)을 둘 다 쓴다. 어느 표기로 넘겨도 CLI가 레포에 있는 쪽으로 바꿔 붙인다 (#776). 전체 대응표는 `references/issues.md`.

## 이슈 완료 처리 (작업 끝 — 라벨 교체 후 close)

작업이 끝나면 상태 라벨을 **교체**하고 닫는다. `pro-report`가 보고서를 올린 뒤 이 레시피를 따른다 (#819).

**기본은 `finish-issue` 한 번이다.** 상태 라벨만 바꾸고 `type:`·`area:` 같은 나머지 라벨은 지킨다.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py finish-issue {owner} {repo} {이슈번호}                       # 완료: status: done + 닫기
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py finish-issue {owner} {repo} {이슈번호} --outcome cancelled   # 취소: status: cancelled + 닫기
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py finish-issue {owner} {repo} {이슈번호} --outcome in-progress # 작업 시작·남은 일: 라벨만
```

- 단계별 결과는 `steps`·`failed_steps`. 실패한 단계가 있으면 `finish-issue`를 다시 부른다 (멱등).
- `--outcome done`이면 이슈에 보고서 댓글(`## 개요`+`## 변경 사항`)이 있는지 보고, 없으면 `warnings`에 남긴다. 닫기는 막지 않는다 — 경고가 오면 보고서를 빠뜨렸는지 확인한다.

| 상황 | 라벨 (영문 표준 / 한글) | 닫기 |
|------|------------------------|------|
| 완료 | `status: done` / `작업완료` | `--reason completed` |
| 남은 작업 있음 | `status: in progress` / `작업중` | 닫지 않는다 |
| 취소 | `status: cancelled` / `취소` | `--reason not_planned` |

**대체 경로 (finish-issue를 쓸 수 없을 때만):** `set-labels`는 이슈의 **라벨 전체**를 바꾼다. 상태 라벨 하나만 넘기면 `type:`·`area:`·`priority:` 라벨이 모두 지워진다. 먼저 `get-issue`의 `labels`를 읽고, 상태 라벨만 바꾼 전체 csv를 넘긴다. 응답의 `removed`·`warning`으로 지워진 라벨을 확인한다.

```bash
# 1) 현재 라벨 읽기 → 상태 라벨만 바꾼 전체 목록 만들기
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py get-issue {owner} {repo} {이슈번호} --field labels
# 2) 전체 목록으로 교체 (예: 기존 type: bug 유지)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py set-labels {owner} {repo} {이슈번호} "type: bug,status: done"
# 3) 완료로 닫기
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py close-issue {owner} {repo} {이슈번호} --reason completed
```

- 레포에 한글 라벨만 있어도 영문 표준 이름으로 넘기면 CLI가 레포에 있는 표기로 바꿔 붙인다 (#776).
- 닫을 때 `update-issue --state closed`를 쓰지 않는다. 열린 상태 라벨을 붙인 채로 닫는 조합은 만들지 않는다.
- 남의 이슈를 닫거나 다시 여는 것은 사용자가 요청할 때만 한다 (`../references/common-rules.md` §이슈 상태 처리 규칙).
- 레포 `CLAUDE.md`가 다른 규칙(예: 닫지 않고 라벨만)을 정했으면 그쪽을 따른다.

## PR — 결정 규칙

- 만들기 전에 head 브랜치가 원격에 있는지 `git ls-remote --heads origin "{브랜치}"`로 확인하고, `head`는 `owner:branch` 형식으로 넘긴다 (한글 브랜치명 422 방지).
- base는 작업 PR이면 **개발(릴리스 소스) 브랜치**(`version.yml` `metadata.development_branch`(구 이름 `deploy_branch`), 없으면 `develop`, 개발 브랜치가 없는 레포면 기본 브랜치). `main`으로 가는 릴리스 PR은 `/pro-changelog-deploy`가 만든다. 사용자가 base를 명시하면 그것을 따른다.
- 제목은 브랜치명 `YYYYMMDD_#번호_제목`에서 번호를 뽑아 이슈 제목을 조회하고 **이모지·`[태그]`를 걷어 낸** 순수 텍스트. 본문에는 `- https://github.com/{owner}/{repo}/issues/{번호}` 링크를 반드시 넣는다. 상세는 `references/prs.md`.

## Actions — 입력 라우팅 (필수)

입력 해석은 agent가 한다. CLI는 URL을 파싱하지 않고 **위치 인자 하나**만 받는다 (#622). `next`가 있으면 그대로 이어 부른다.

| 사용자 입력 | 추출 | 서브커맨드 |
|------------|------|-----------|
| `.../actions/runs/{run_id}` · `.../attempts/{n}` · 순수 숫자 | run_id | `actions show-run {owner} {repo} {run_id}` |
| `.../actions/runs/{run_id}/job/{job_id}` | job_id | `actions joblog {owner} {repo} {job_id}` |
| `.../pull/{pr}` 또는 "PR 883" | pr | `actions resolve-pr {owner} {repo} {pr}` |
| 브랜치명 또는 "main 빌드" | branch | `actions resolve-branch {owner} {repo} {branch}` |
| `.../actions` · 빈 입력 · "빌드 실패했어" | 없음 | `actions list-failed {owner} {repo}` |
| `.../actions/workflows/{file}.yaml` | 없음 | `actions list-failed {owner} {repo}` (결과에서 해당 워크플로명 필터) |

흐름: 실패 run 찾기 → `show-run`(실패 job·step) → `joblog`(기본은 `##[error]` 줄과 그 앞 출력, `--grep` · `--tail` · `--out`) → 원인 진단. 상세는 `references/actions.md`.
동작 이름은 언제나 `actions` 바로 뒤다 (`actions show-run {owner} {repo} {run_id}`). 순서가 틀리면 `bad_args` 의 `next` 가 올바른 명령을 준다.

## 실패 code → 다음 행동

| code / verdict | 의미 | 다음 행동 |
|---|---|---|
| `missing_pat` | PAT 미설정 | `../references/config-rules.md §2~5`로 config에 등록하도록 안내 |
| `github_api_401` | PAT 인증 실패 | PAT 갱신 안내 |
| `github_api_403` | 권한 없음 (private 레포 등) | 접근 불가 안내, 나머지 진행 |
| `github_api_404` | 이슈/PR/레포/README 없음 | 해당 항목 "없음"으로 표시, 나머지 진행 |
| `github_api_422` | 이미 PR 존재 등 | API 오류 메시지 그대로 안내 |
| `label_not_present` | 제거하려던 라벨이 원래 없음 | 변경 없음으로 보고 |
| `set-labels` `warning` | 상태 외 라벨(`removed`)까지 지워짐 | 의도가 아니면 `next` 의 `add-labels` 로 되돌린다 |
| `release_asset_limit` | 증적 릴리스가 이월분까지 모두 자산 한도(1000개) | `next` 대로 오래된 증적을 지우거나 새 `--tag` |
| `run_id_given` | `joblog` 에 run id 를 넣음 | `next` 의 `show-run` 으로 job id 를 받는다 |
| `argument_order` | `create-pr` head/base 에 공백 (제목이 브랜치 자리에) | `--head`·`--base` 플래그로 다시 부른다 |
| `label_warning` · `assignee_warning` | 레포에 없는 라벨 · 반영 안 된 담당자 | 작업은 성공. 경고만 자연어로 전달 |
| `pynacl_missing` | Secret 암호화 모듈 설치 실패 | `pip install PyNaCl --user` 안내 (`references/secrets.md`) |
| `get-pr` `computing` | mergeable_state 계산 전 | 잠시 후 재조회 |
| `merge-pr` `not_mergeable` · `sha_mismatch` · `method_not_allowed` | 405 충돌·체크 실패·드래프트 / 409 / 422 rebase 불허 | 원인을 사용자에게 알리고 지시를 받는다 |
| API rate limit | `X-RateLimit-Remaining: 0` | 한도 초과 안내 |
| 네트워크 오류 | 연결 실패 | exit code 확인 후 재시도 1회, 실패 시 안내 |

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-github`.
Keys for this skill: `template` (extra issue-body sections), `examples` (applied in `../references/issue-creation.md` step 3) plus the common `language`, `tone`, `rules`.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.
