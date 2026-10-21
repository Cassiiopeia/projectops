# 출력 형태와 전역 옵션 (모든 skill CLI 공통)

응답은 항상 JSON 한 줄이고 **`ok` · `code` · `summary` · `next` 가 맨 앞**에 온다 (#940). `summary` 는 언제나 문자열이다 (비면 실패는 `error`·`code`, 성공은 `완료`). 키를 짐작해 인라인 파이썬으로 파싱하지 않는다.

## 전역 옵션

| 옵션 | 효과 |
|---|---|
| `--field a.b.0` | 성공 응답의 그 값만 글자로 준다 (`--field issue.title`, `--field runs.0.run_id`). 없는 경로면 `field_not_found` 와 `did_you_mean`(중첩 경로 후보, 예: `issue.labels`) · `available_keys`. 오류 응답에는 적용되지 않는다 |
| `--fields a,b` | `--field` 와 같은 옵션의 다른 표기. 경로가 여럿이면 `{경로: 값}` JSON 하나로 준다 |
| `--brief` | `ok · code · summary · next · error · hint · usage · example · count · warning(s)` 와, 목록 값은 행마다 식별 키(`number · id · run_id · job_id · title · name · state · status · conclusion`)만 남긴다. 목록 응답을 다시 부르지 않아도 된다 |

`bad_args` 응답에는 `usage`(그 서브커맨드의 사용법)와 `did_you_mean`(비슷한 서브커맨드)이 들어 있다 — `--help` 를 따로 부르지 않는다.

## 자주 읽는 응답의 키

| 명령 | 읽을 키 |
|---|---|
| `github_cli get-issue` | 최상위 `number` · `title` · `url` · `state` · `labels[]` · `assignees[]` · `body`, 원본 `issue.{…,created_at,updated_at,comments_count}`, 별칭 `html_url` |
| `github_cli create-issue` | `number`, `url`, `title`, `branch`, `commit_template`, `next` (+ `body_file_renamed_to` · `rename_warning` · `label_warning` · `assignee_warning`) |
| `github_cli list-comments` | `comments[].{id,url,author,body,created_at}` — `id` 를 `edit-comment`·`delete-comment` 에 넘긴다 |
| `github_cli list-labels` | `labels[]` (이름 문자열 목록) |
| `github_cli set-labels` | `labels[]`(교체 후), `removed[]`(지워진 라벨), `warning`(상태 외 라벨이 지워짐) |
| `github_cli finish-issue` | `steps[].{step,ok}`, `failed_steps[]`, `warnings[]`(보고서 댓글 없음 등) |
| `github_cli create-branch-name` | `branch`, `issue_number` |
| `github_cli upload-image` | `markdown`, `tag`(실제로 쓴 증적 릴리스), `images[].{name,url,asset_id,renderable,tag,file}` (`file` 은 올린 로컬 파일의 절대경로), 1개면 최상위 `url` |
| `github_cli list-prs` | `prs[].{number,title,url,state,head,base,merged_at}` |
| `github_cli create-pr` · `changelog_cli create-pr` | `number`, `url` (+ `notes_wrapped` · `body_guard`) |
| `github_cli explore repo-detail` | `repo.{name,default_branch,private,visibility,url,…}` |
| `github_cli api` | `data`(유효한 JSON), `truncated`, `truncated_items`, `saved_to`(`--out`) |
| `github_cli actions runs\|list-failed` | `runs[].{run_id,name,path,branch,event,status,conclusion,created_at,url}` (`list-failed {run_id}` 는 그 run 의 `jobs[]`) |
| `github_cli actions show-run` | run 요약 + `jobs[].{job_id,name,conclusion,failed_steps[]}` + `failed_job_ids[]` |
| `github_cli actions joblog` | `lines[]`, `matched_count`, `mode`(`error_markers`·`grep`), `saved_to` |
| `github_cli actions wait` (run 여러 개) | `runs[]`, `finished`, `pending_run_ids[]`, `failed_job_ids[]` |
| `github_cli add-comment` | `id`, `url` (+ `reconciled`) |
| `changelog_cli deploy-status` | `verdict`, `stuck_reason`, `pr.{number,state,merged,mergeable_state,age_seconds,head_sha,url}`, `workflow.{status,conclusion,run_url}` |

위 표는 코드에서 옮긴 것이다. 새 서브커맨드를 만들면 여기에 읽을 키를 한 줄 더한다.
