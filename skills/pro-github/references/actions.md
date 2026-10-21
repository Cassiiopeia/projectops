# GitHub Actions 로그 조회

> 언제 읽나: 빌드·워크플로우 실패 원인을 진단할 때 ("빌드 실패 확인해줘", "Actions 로그 봐줘", "이 PR 왜 빌드 실패?", run/job/PR URL, "main 빌드 됐어?"). 입력 → 서브커맨드 라우팅 표는 SKILL.md에 있다.

명령은 `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions <sub> ...` 형태다 (SKILL.md "스크립트 찾기").

## 핵심 원리

- 모든 로직은 `github_cli.py`의 `actions` 서브커맨드에 있다. **인라인 Python 작성 금지.**
- **입력 해석은 agent의 책임**이다. URL·PR번호·브랜치명·빈 입력을 보고 SKILL.md 라우팅 표에 따라 서브커맨드와 인자를 결정한다.
- `github_cli`는 **명확한 인자만** 받는다 (URL을 파싱하지 않는다). 위치 인자는 **하나**(`arg`)이고 서브커맨드가 run_id · job_id · pr_number · branch 로 해석한다 (#622). 예외: `wait` 는 run id 를 여러 개 받는다.
- 동작 이름은 `actions` 바로 뒤에 둔다. `actions {owner} {repo} show-run …` 처럼 순서가 틀리면 `bad_args` 의 `next` 가 올바른 명령을 준다.
- 출력은 **언제나 JSON**이며 `ok`·데이터·`next`(이어서 호출할 다음 서브커맨드 힌트)를 담는다. `next`가 비어있지 않으면 그 값을 그대로 다음 명령으로 실행해 체인을 잇는다 (예: `show-run`의 `next` → `joblog`).
- PAT는 config.json에서 자동 로드하므로 `export GITHUB_PAT`는 생략 가능하다(환경변수가 있으면 우선). `PYTHONIOENCODING=utf-8` 필수(한글 출력 보호).

## 전형적 진단 흐름

1. 입력에 run_id 없음(PR/브랜치/빈입력) → `resolve-pr`·`resolve-branch`·`list-failed`로 실패 run 찾기
   `resolve-pr`가 run을 여러 개 주면 `conclusion`이 `failure`인 것 중 **가장 최근** run을 고른다.
2. 실패 run의 `next`(=`show-run ...`) 실행 → 실패 job_id + 실패 step 확인
3. `show-run`의 `next`(=`joblog ...`) 실행 → 실제 에러 로그 라인 확인
   기본(`--grep` 없음)은 `##[error]` 줄과 그 앞 출력 줄이다 (`mode: error_markers`). `##[group]Run` 스크립트 원문 구간은 빼고 본다 — 원문의 `error` 글자·브랜치명이 걸리지 않는다. `##[error]` 가 없으면 `error|failed` 로 대신 찾는다.
   더 넓히려면 `--grep "exception|exit code"` (정규식, 대소문자 무시). `--grep "" --tail 80`이면 로그 끝 80줄 전체.
   job id 자리에 run id 를 넣으면 `run_id_given` 과 `next: show-run` 이 온다.
4. 로그 라인을 읽고 사용자에게 원인 진단 제시

## 호출법

```bash
# run 메타 + job 목록 + 실패 step
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions show-run {owner} {repo} {run_id}
# 실패 job 로그 (error 라인 필터, Azure redirect 자동 처리)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions joblog {owner} {repo} {job_id}
#   --grep "\.dart" : 정규식으로 찾는다 (대소문자 무시). 생략하면 ##[error] 줄 + 그 앞 출력 (스크립트 원문 제외)
#   --tail 30       : 매칭 라인 끝 N개 (기본 30)
#   --out log.txt   : 전체 로그를 파일로
# 최근 실패 run 목록
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions list-failed {owner} {repo} --limit 10
# 특정 run 의 실패 job 만 (run id 를 주면)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions list-failed {owner} {repo} {run_id}
# PR → 연결된 run 추적
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions resolve-pr {owner} {repo} {pr_number}
# 브랜치 → 최근 run 목록
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions resolve-branch {owner} {repo} "{branch}" --limit 10
```

> **Windows 주의**: 임시 파일 파싱·curl 파이프 Python·heredoc 보간은 사용하지 않는다 (Windows Git Bash에서 깨짐). 인자는 모두 명령행/환경변수로 전달한다.

## 출력 예시

```json
{"run_id": 26554093214, "name": "프로젝트 빌드 테스트", "conclusion": "failure",
 "jobs": [{"job_id": 78222159478, "name": "프로젝트 빌드 테스트", "conclusion": "failure", "failed_steps": ["코드 분석 실행"]}],
 "failed_job_ids": [78222159478],
 "ok": true, "next": "actions joblog acme-org acme-app 78222159478"}
```


## 실행 · 재실행 · 대기 · 목록 (#939)

워크플로우를 돌리거나 끝날 때까지 기다리려고 curl 을 쓰지 않는다. PAT 를 설정 파일에서 읽어 오는 것이 세션 기록에 남는 가장 큰 이유였다.

```bash
# 실행 (workflow_dispatch). run id 는 돌려주지 않으니 runs 로 새 run 을 찾는다
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions dispatch {owner} {repo} build.yaml --ref develop --input env=test
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions runs {owner} {repo} build.yaml --on-branch develop --limit 3   # --branch 도 같다
# 끝날 때까지 도구 안에서 기다린다 (최대 540초, 못 끝나면 finished: false 와 같은 명령을 next 로). sleep·폴링 루프를 쓰지 않는다
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions wait {owner} {repo} {run_id} --timeout 300
# 여러 run 을 모두 끝날 때까지 (runs[]·pending_run_ids·failed_job_ids)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions wait {owner} {repo} {run_id} {run_id2} {run_id3}
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions rerun {owner} {repo} {run_id} --failed-only
# 취소 (사용자가 요청할 때만). --force 는 always() step 까지 멈추는 강제 취소
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions cancel {owner} {repo} {run_id} [--force]
```

- `joblog --grep` 은 정규식이다 (`'error|failed'`, 대소문자 무시). 틀린 정규식은 글자 그대로 찾는다. 응답의 `regex` 로 어느 쪽으로 해석됐는지 본다.
  전체 로그가 필요하면 `--out 파일` 로 저장해 직접 본다. 보존 기간이 지난 로그는 `log_expired`.
- `list-failed --workflow build.yaml` 은 그 워크플로우의 실패 run 만 남긴다.
- 위 명령으로 안 되는 REST 호출은 `api` 로: `api GET {owner} {repo} releases/latest` (상대 경로는 `/repos/{owner}/{repo}/` 가 붙는다. 절대 경로 `/repos/{owner}/{repo}/...` 도 된다).
  이 레포 경로만 받는다. 레포 밖 예외는 읽기 전용 `GET /rate_limit` 하나다. 상태를 바꾸는 메서드(POST·PUT·PATCH·DELETE)는 사용자가 요청한 작업일 때만 `--write` 를 붙인다.
  응답이 2만 자를 넘으면 목록의 뒤 항목을 빼 **유효한 JSON** 으로 준다 (`truncated: true`, `truncated_items`). 전체가 필요하면 `--out 파일` (응답의 `saved_to`), 아니면 `?per_page=10` 으로 줄인다.
- Secret 값이 여러 줄이면 `secrets set {owner} {repo} {이름} --value-file 파일` 로 넘긴다 (`SECRET_VALUE` 환경변수도 된다).
