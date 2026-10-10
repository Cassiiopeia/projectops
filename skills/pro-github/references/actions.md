# GitHub Actions 로그 조회

> 언제 읽나: 빌드·워크플로우 실패 원인을 진단할 때 ("빌드 실패 확인해줘", "Actions 로그 봐줘", "이 PR 왜 빌드 실패?", run/job/PR URL, "main 빌드 됐어?"). 입력 → 서브커맨드 라우팅 표는 SKILL.md에 있다.

명령은 `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions <sub> ...` 형태다 (SKILL.md "스크립트 찾기").

## 핵심 원리

- 모든 로직은 `github_cli.py`의 `actions` 서브커맨드에 있다. **인라인 Python 작성 금지.**
- **입력 해석은 agent의 책임**이다. URL·PR번호·브랜치명·빈 입력을 보고 SKILL.md 라우팅 표에 따라 서브커맨드와 인자를 결정한다.
- `github_cli`는 **명확한 인자만** 받는다 (URL을 파싱하지 않는다). 위치 인자는 **하나**(`arg`)이고 서브커맨드가 run_id · job_id · pr_number · branch 로 해석한다 (#622).
- 출력은 **언제나 JSON**이며 `ok`·데이터·`next`(이어서 호출할 다음 서브커맨드 힌트)를 담는다. `next`가 비어있지 않으면 그 값을 그대로 다음 명령으로 실행해 체인을 잇는다 (예: `show-run`의 `next` → `joblog`).
- PAT는 config.json에서 자동 로드하므로 `export GITHUB_PAT`는 생략 가능하다(환경변수가 있으면 우선). `PYTHONIOENCODING=utf-8` 필수(한글 출력 보호).

## 전형적 진단 흐름

1. 입력에 run_id 없음(PR/브랜치/빈입력) → `resolve-pr`·`resolve-branch`·`list-failed`로 실패 run 찾기
   `resolve-pr`가 run을 여러 개 주면 `conclusion`이 `failure`인 것 중 **가장 최근** run을 고른다.
2. 실패 run의 `next`(=`show-run ...`) 실행 → 실패 job_id + 실패 step 확인
3. `show-run`의 `next`(=`joblog ...`) 실행 → 실제 에러 로그 라인 확인
   기본 필터 `error`로 못 찾으면 `--grep "failed"` · `--grep "exception"` · `--grep "exit code"`로 넓힌다.
   `--grep`은 정규식이 아니라 **대소문자 무시 부분 문자열**이라 `A|B`는 통하지 않는다 — 하나씩 부른다. `--grep "" --tail 80`이면 로그 끝 80줄 전체.
4. 로그 라인을 읽고 사용자에게 원인 진단 제시

## 호출법

```bash
# run 메타 + job 목록 + 실패 step
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions show-run {owner} {repo} {run_id}
# 실패 job 로그 (error 라인 필터, Azure redirect 자동 처리)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions joblog {owner} {repo} {job_id}
#   --grep ".dart"  : 그 문자열이 든 라인만 (부분 문자열·대소문자 무시, 정규식 아님. 기본 "error")
#   --tail 30       : 매칭 라인 끝 N개 (기본 30)
# 최근 실패 run 목록
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions list-failed {owner} {repo} --limit 10
# PR → 연결된 run 추적
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions resolve-pr {owner} {repo} {pr_number}
# 브랜치 → 최근 run 목록
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py actions resolve-branch {owner} {repo} "{branch}" --limit 10
```

> `show-run`(실패 시)·`joblog` 응답에 `note_hits`(제목·경로·요약, 최대 2건)가 있으면 `pro-note` 과거 기록이 맞은 것이다 — 조사 전에 그 문서부터 읽는다. 없으면 필드 자체가 없다.

> **Windows 주의**: 임시 파일 파싱·curl 파이프 Python·heredoc 보간은 사용하지 않는다 (Windows Git Bash에서 깨짐). 인자는 모두 명령행/환경변수로 전달한다.

## 출력 예시

```json
{"run_id": 26554093214, "name": "프로젝트 빌드 테스트", "conclusion": "failure",
 "jobs": [{"job_id": 78222159478, "name": "프로젝트 빌드 테스트", "conclusion": "failure", "failed_steps": ["코드 분석 실행"]}],
 "failed_job_ids": [78222159478],
 "ok": true, "next": "actions joblog acme-org acme-app 78222159478"}
```
