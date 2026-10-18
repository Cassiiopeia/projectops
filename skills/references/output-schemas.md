# 출력 형태와 전역 옵션 (모든 skill CLI 공통)

응답은 항상 JSON 한 줄이고 **`ok` · `code` · `summary` · `next` 가 맨 앞**에 온다 (#940). 키를 짐작해 인라인 파이썬으로 파싱하지 않는다.

## 전역 옵션

| 옵션 | 효과 |
|---|---|
| `--field a.b.0` | 성공 응답의 그 값만 글자로 준다 (`--field issue.title`, `--field runs.0.run_id`). 없는 경로면 `field_not_found` 와 `available_keys`. 오류 응답에는 적용되지 않는다 |
| `--brief` | `ok · code · summary · next · error · hint · usage · example` 만 남긴다 |

`bad_args` 응답에는 `usage`(그 서브커맨드의 사용법)와 `did_you_mean`(비슷한 서브커맨드)이 들어 있다 — `--help` 를 따로 부르지 않는다.

## 자주 읽는 응답의 키

| 명령 | 읽을 키 |
|---|---|
| `github_cli get-issue` | `issue.{number,title,url,state,body,labels[],assignees[],created_at,updated_at,comments_count}`, 편의 별칭 `title` · `url` · `html_url` |
| `github_cli list-labels` | `labels[]` (이름 문자열 목록) |
| `github_cli list-prs` | `prs[].{number,title,url,state}` |
| `github_cli create-pr` · `changelog_cli create-pr` | `number`, `url` (+ `notes_wrapped` · `body_guard`) |
| `github_cli actions runs\|list-failed` | `runs[].{run_id,name,path,branch,event,status,conclusion,created_at,url}` |
| `github_cli actions show-run` | run 요약 + `jobs[].{job_id,name,conclusion,failed_steps[]}` + `failed_job_ids[]` |
| `github_cli add-comment` | `id`, `url` (+ `reconciled`) |
| `changelog_cli deploy-status` | `verdict`, `stuck_reason`, `pr.{number,state,merged,mergeable_state,age_seconds,head_sha,url}`, `workflow.{status,conclusion,run_url}` |

위 표는 코드에서 옮긴 것이다. 새 서브커맨드를 만들면 여기에 읽을 키를 한 줄 더한다.
