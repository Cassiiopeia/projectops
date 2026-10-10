# 이슈 조회 · 수정 · 댓글 · 라벨 · 담당자 · 헬퍼

> 언제 읽나: 이슈를 조회·수정하거나 댓글·라벨·담당자를 다룰 때, 이슈 헬퍼(제목 정규화·브랜치명·커밋 템플릿·문서 경로) 출력 형식이 필요할 때.

명령은 모두 `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py <서브커맨드> ...` 형태다. `{PYTHON}`·`{SCRIPTS}`는 SKILL.md "스크립트 찾기"에서 얻은 실제 경로로 써넣는다.
새 이슈 **생성**(작성+등록)은 이 문서가 아니라 `../../references/issue-creation.md` 워크플로우를 따른다.

## 이슈 조회

`#번호` 형식이나 "이슈 427 확인해줘"처럼 번호를 명시하면 해당 이슈를 조회한다. 본문과 댓글이 모두 필요하면 `--with-comments`를 붙인다.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py get-issue {owner} {repo} {이슈번호}
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py get-issue {owner} {repo} {이슈번호} --with-comments
```

출력 JSON: `{"ok":true,"issue":{number,title,url,state,body,labels,assignees,created_at,updated_at,comments_count},"comments":...,"summary","next":null}`.

여러 이슈를 한 번에 조회:

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py get-issues {owner} {repo} 712 707 715
```

일부 이슈가 404여도 해당 항목만 `{number,error,code}`로 들어오며 전체 조회는 계속된다.

이슈 목록:

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py list-issues {owner} {repo} --state open
# --state open|closed|all (기본 open)
```

출력 JSON: `{"count":N,"issues":[{number,title,url,state,labels}]}`. PR은 제외된다. 라벨로 좁히려면 `--labels "a,b"`(모두 가진 이슈만), 전부 보려면 `--limit 0`(기본 50개). 담당자로 좁히려면 결과에서 agent가 직접 필터링한다.

키워드 검색(중복 검사에도 쓴다):

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py search-issues {owner} {repo} "{핵심 키워드}"
```

출력 JSON `{"count":N,"items":[{number,title,url,state,labels}]}`. keyword는 마지막 인자로 그대로 넘기며(공백 포함 가능) 내부에서 URL 인코딩한다.

## 이슈 등록 (create-issue)

생성 워크플로우의 등록 단계에서 쓴다:

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py create-issue {owner} {repo} "{제목}" "{본문 .md 절대경로}" "{라벨 csv}" --assignees "{담당자}"
```

출력 JSON: `{"number":...,"url":...,"title":...,"assignees":[...]}`. 존재하지 않는 라벨은 자동 필터링된다. `assignee_warning`이 있으면 이슈는 정상 생성된 것이므로 그 경고만 자연어로 전달한다.

## 이슈 상태 변경 (닫기 / 다시 열기)

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py close-issue {owner} {repo} {번호}                         # 완료 (기본 --reason completed)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py close-issue {owner} {repo} {번호} --reason not_planned    # 취소
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py reopen-issue {owner} {repo} {번호}
```

출력 JSON: `{"number":...,"url":...,"title":...,"state_reason":"completed"}`.
작업 파이프라인의 완료·취소 처리(SKILL.md §이슈 완료 처리)는 확인 없이 해도 된다. 그 밖에 남의 이슈를 닫거나 다시 여는 것은 사용자가 요청할 때만 한다 (`../../references/common-rules.md` §이슈 상태 처리 규칙).

## 이슈 수정

제목, 상태(open/closed), 라벨, 담당자, 본문 변경 가능. 변경할 옵션만 넘기면 나머지는 기존 값 유지.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py update-issue {owner} {repo} {이슈번호} \
  --title "새 제목" --labels "status: in progress" --assignees "Cassiiopeia"
# --body-file "{본문 파일 경로}" 로 본문 교체, --state open|closed
```

> 닫을 때는 `update-issue --state closed` 대신 SKILL.md §이슈 완료 처리 레시피(`set-labels` → `close-issue --reason`)를 쓴다. 열린 상태 라벨을 붙인 채로 닫는 조합은 만들지 않는다.

## 댓글 추가 / 목록 / 수정 / 삭제

본문에 한국어·이모지·줄바꿈이 포함될 수 있으므로 댓글 본문을 **파일로 저장한 뒤** 넘긴다.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py add-comment {owner} {repo} {이슈번호} "{댓글 본문 파일 경로}"
```

댓글 수정·삭제는 이슈 번호가 아니라 **댓글 ID(comment_id)** 로 지정한다 (이슈·PR 공용). 댓글 ID는 `list-comments`나 이전 `add-comment` 응답의 `id`에서 얻는다.

```bash
# 댓글 목록 (id 확인용)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py list-comments {owner} {repo} {이슈번호}
# 댓글 본문 수정 (본문은 파일로 전달 — 한글·줄바꿈 보존)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py edit-comment {owner} {repo} {comment_id} "{새 본문 파일 경로}"
# 댓글 삭제
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py delete-comment {owner} {repo} {comment_id}
```

`list-comments`는 `{count,comments:[{author,body,created_at}]}`를 반환한다(현재 API 응답에 id가 필요하면 `add-comment`/`edit-comment` 응답의 `id`를 재사용). `edit-comment`는 `{id,url}`, `delete-comment`는 `{comment_id,status:"deleted"}`.

## 라벨 (추가 / 제거 / 전체 교체)

기존 라벨을 유지하며 다루려면 `add-labels`/`remove-label`을, 통째로 갈아끼우려면 `set-labels`를 쓴다.

```bash
# 레포에 정의된 라벨 목록
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py list-labels {owner} {repo}
# 기존 라벨 유지하며 추가 (csv)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py add-labels {owner} {repo} {이슈번호} "priority: urgent"
# 라벨 하나만 제거 (나머지 유지, 없으면 멱등 처리)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py remove-label {owner} {repo} {이슈번호} "status: todo"
# 라벨 전체 교체 (빈 문자열이면 전부 제거) — 상태 라벨을 바꿀 때는 이것을 쓴다
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py set-labels {owner} {repo} {이슈번호} "status: in progress"
```

상태 라벨은 영문 표준과 한글을 둘 다 쓴다: `status: todo`(`작업전`) · `status: in progress`(`작업중`) · `status: needs review`(`담당자확인`) · `status: feedback`(`피드백`) · `status: done`(`작업완료`) · `status: on hold`(`보류`) · `status: cancelled`(`취소`), 그 밖에 `priority: urgent`(`긴급`) · `documentation`(`문서`). 어느 표기로 넘겨도 CLI가 레포에 있는 쪽으로 바꿔 붙인다 (#776).

`add-labels`는 레포에 없는 라벨은 무시하고 `label_warning`으로 알린다. `remove-label`은 이슈에 그 라벨이 원래 없으면 `code:"label_not_present"`(변경 없음)를 반환한다. 한글 라벨도 URL 인코딩되어 정상 처리된다.

## 담당자 (추가 / 제거)

담당자도 기존을 유지하며 다룬다. 전체 교체가 필요하면 `update-issue --assignees`(전체 교체)를 쓴다.

```bash
# 기존 담당자 유지하며 추가 (csv, 최대 10명)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py add-assignees {owner} {repo} {이슈번호} "Cassiiopeia"
# 지정한 담당자만 제거 (나머지 유지)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py remove-assignees {owner} {repo} {이슈번호} "Cassiiopeia"
```

출력 JSON: `{"number":...,"url":...,"assignees":[...]}`. 권한 없는/협업자 아닌 유저는 GitHub이 조용히 누락시키므로 `add-assignees`는 `assignee_warning`으로 알린다.

## 이슈 헬퍼 (제목 정규화 / 브랜치명 / 커밋 템플릿 / 문서 경로)

이슈 생성 워크플로우와 `/pro-commit`이 쓰는 순수 계산 헬퍼다 (API 호출 없음):

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py normalize-title "❗[버그] 한글 제목!"
# → {"normalized":"버그_한글_제목", ...}
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py create-branch-name "이슈 제목" 235 --date 20260710
# → {"branch":"20260710_#235_이슈_제목", ...}
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py get-commit-template "❗[Bug][Skills] 이슈 제목" "https://github.com/o/r/issues/235"
# → {"template":"이슈 제목 : fix : {설명} https://...", ...}   타입은 제목 태그에서 추론 (버그→fix, 기능→feat)
#   태그와 실제 작업이 다를 때만 --type fix|docs|chore 등으로 직접 지정한다
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py get-output-path issue --title "❗[Bug][Skills] 이슈 제목"
# → {"path":".../issue/20260710_001_이슈_제목.md", ...}   이슈 문서 저장 경로 (등록 전 일련번호)
```

- 커밋 템플릿은 `template` 값을 그대로 쓴다. 타입을 `feat`로 고쳐 쓰지 않는다 — `semver_auto` 레포에서 버그 수정이 minor로 오른다.
- 이슈 문서 경로는 직접 조립하지 않고 `get-output-path issue`의 `path`를 쓴다 (산출물 루트는 설정으로 바뀐다). 현재 레포 기준으로 계산되므로 프로젝트 루트에서 부른다.
