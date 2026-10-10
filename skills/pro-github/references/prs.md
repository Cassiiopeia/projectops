# PR 생성 · 조회 · 머지 · 릴리스 노트 폴백

> 언제 읽나: PR을 만들거나 조회·댓글·닫기·머지할 때, 릴리스 PR 본문에 릴리스 노트를 직접 채울 때.

명령은 `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py ...` 형태다 (SKILL.md "스크립트 찾기").

## PR 생성

현재 브랜치 이름을 자동 감지하여 PR을 생성한다.

**PR 생성 전 반드시 remote 브랜치 존재 여부를 확인한다 (한글 브랜치명 422 오류 방지):**

```bash
HEAD_BRANCH=$(git rev-parse --abbrev-ref HEAD)
git ls-remote --heads origin "$HEAD_BRANCH" | grep -q "$HEAD_BRANCH" || echo "브랜치가 remote에 없습니다. git push 먼저 실행하세요."
```

`head`는 반드시 `owner:branch` 형식으로 지정한다 (한글 포함 브랜치명의 422 오류 방지):

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py create-pr {owner} {repo} "{제목}" "{PR 본문 파일 경로}" "{owner}:{head_branch}" {base_branch}
```

`{base_branch}`는 작업 PR이면 **개발(릴리스 소스) 브랜치**다 — `version.yml`의 `metadata.deploy_branch`, 없으면 `develop` (원격에 개발 브랜치가 아예 없는 단일 브랜치 레포면 기본 브랜치). 기본(배포) 브랜치(`main`)로 가는 릴리스 PR은 이 레시피가 아니라 `/pro-changelog-deploy`가 만든다. 사용자가 base를 명시하면 그것을 따른다.

### PR 제목 규칙 (필수)

브랜치명이 `YYYYMMDD_#번호_제목` 형식이면 번호를 추출해 이슈 API(`get-issue`)로 제목을 조회한다. 조회한 이슈 제목에서 **앞에 붙은 이모지와 `[태그]` 형식을 모두 제거**한 순수 텍스트만 PR 제목으로 사용한다.

예) 이슈 제목이 `❗[버그][개발자도구] SSE 서버 로그 스트리밍 연결 즉시 종료 및 구독자 누적 문제`이면
→ PR 제목: `SSE 서버 로그 스트리밍 연결 즉시 종료 및 구독자 누적 문제`

### PR 본문 규칙 (필수)

PR 본문에는 반드시 관련 이슈 링크를 포함한다. 이슈 번호는 브랜치명(`YYYYMMDD_#번호_...`)에서 자동 추출한다.

```
- https://github.com/{owner}/{repo}/issues/{이슈번호}
```

## PR 목록 조회

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py list-prs {owner} {repo} --state open
# 닫힌 PR 포함: --state closed 또는 --state all
```

## PR 상세 / 댓글 / 상태 / 머지

`get-pr`는 `verdict`(mergeable/blocked/computing/merged/closed)를 반환하니 머지 전 상태 확인에 쓴다.

```bash
# PR 상세 (mergeable_state 등) — verdict로 머지 가능 판단
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py get-pr {owner} {repo} {PR번호}
# PR에 댓글 추가 (본문 파일)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py add-pr-comment {owner} {repo} {PR번호} "{댓글 본문 파일}"
# PR 본문·제목·상태 수정 (본문 파일은 선택)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py update-pr {owner} {repo} {PR번호} "{본문 파일}" --title "새 제목"
# PR 닫기 / 다시 열기
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py close-pr {owner} {repo} {PR번호}
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py reopen-pr {owner} {repo} {PR번호}
# PR 머지 (merge|squash|rebase, 기본 merge). --message 로 머지 커밋 본문
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py merge-pr {owner} {repo} {PR번호} --method squash --title "머지 제목"
```

`get-pr`의 `verdict`가 `computing`(mergeable_state 계산 전)이면 잠시 후 재조회한다. `merge-pr` 실패 시 `verdict`로 원인을 구분한다 (SKILL.md 실패 code 표). **PR 머지·닫기는 파괴적 작업이므로 사용자가 명시적으로 요청할 때만 실행한다.**

## PR 릴리스 노트 업데이트 (CodeRabbit 폴백)

릴리스 PR(develop→main)에 CodeRabbit Summary가 없을 때 직접 커밋을 분석하여 한국어 릴리스 노트를 작성하고 PR 본문에 업데이트한다. "릴리스 노트 업데이트해줘", "changelog 폴백", "PR 본문 업데이트" 등의 요청 시 실행.

1. PR 번호 확인 (사용자 입력 또는 `list-prs`로 최근 릴리스 PR 조회)
2. main(프로덕션) 대비 커밋 목록 수집

   ```bash
   git fetch origin main 2>/dev/null || true
   git log origin/main..HEAD --pretty=format:"%H %s" | grep -v "\[skip ci\]" | head -60
   ```

3. 커밋 메시지를 분석하여 한국어 릴리스 노트 작성
   - `feat:` → 새 기능 / `fix:` → 버그 수정 / `refactor:`·`perf:`·`style:` → 개선 / `docs:` → 문서 / 나머지 → 기타
   - 커밋 메시지를 그대로 쓰지 말고 사용자가 이해하기 쉬운 한국어 문장으로 재작성
4. 릴리스 노트 본문을 파일로 저장한 뒤 `update-pr`로 PATCH 전송:

   ```bash
   PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py update-pr {owner} {repo} {pr_number} "{릴리스 노트 파일 경로}"
   ```
