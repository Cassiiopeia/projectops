# fix 모드 — 단계별 명령과 문구

> 언제 읽나: automerge가 실패해 기존 deploy PR을 닫고 새로 열어 재트리거할 때 ("머지 안 됐어", "changelogfix", "다시 해줘", "PR 재시도"). 단계 순서와 안전 규칙은 SKILL.md에 있다.

**Bash는 stateless다.** `{PAT}` · `{OWNER}` · `{REPO}` · `{PYTHON}` · `{SCRIPTS}` · `{HEAD_BRANCH}` · `{BASE_BRANCH}`는 [시작 전]에서 구한 **실제 값으로 써넣는다** (브랜치는 [시작 전 §5] 확정값, 폴백 develop/main).

## fix 1단계: 현재 deploy PR 상태 확인 (deploy-status)

curl 즉석 파싱 대신 `deploy-status`로 종합 조회한다. `--pr` 없이 부르면 open deploy PR을 자동 탐색한다.

```bash
GITHUB_PAT="{PAT}" PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/changelog_cli.py \
  deploy-status "{OWNER}" "{REPO}" --base "{BASE_BRANCH}"
```

`verdict`로 분기한다:

- `no_pr` → open PR 없음. fix 3단계(새 PR 생성 준비)로 이동
- `merged` → 이미 머지됨. 재시도 불필요, 안내 후 종료
- 그 외(`waiting_for_automerge`/`missing_coderabbit_summary`/`workflow_failed`/`conflict`) → `pr.number`를 `EXISTING_PR`로 기억하고 fix 2단계로

## fix 2단계: 기존 PR 닫기 (사용자 확인 후)

```
현재 open된 deploy PR #NNN이 있습니다.
이 PR을 닫고 새로 열어서 워크플로우를 재트리거할까요?

1. 네, 닫고 새로 생성합니다
2. 취소
```

확인 후 실행:

```bash
GITHUB_PAT="{PAT}" PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/changelog_cli.py \
  update-pr "{OWNER}" "{REPO}" "{EXISTING_PR}" "-" --state closed
```

## fix 3단계: 커밋 분석

> fix 모드로 곧장 진입해 `APP_RELEASE == unset`이면, 이 단계 **전에** deploy 1.5단계(`deploy-steps.md`)의 신호 수집·확인 절차를 한 번 수행해 값을 정한다.

```bash
git fetch origin "{BASE_BRANCH}" "{HEAD_BRANCH}" 2>/dev/null || true
# 분석 base는 origin/{HEAD_BRANCH} (deploy 4단계와 동일 이유 — HEAD가 origin/{HEAD_BRANCH}보다 뒤일 수 있음).
git log "origin/{BASE_BRANCH}..origin/{HEAD_BRANCH}" --pretty=format:"%s" | grep -v "\[skip ci\]" | head -60
```

deploy 4·5단계와 **완전히 동일한 기준**으로 분류·재작성한다 (`release-notes.md`). 앱스토어 업데이트 노트처럼 — 파일명·기술 prefix·구현 방식·이슈 번호·URL 모두 금지, 사용자가 직접 느끼는 변화만 40자 이내로.

## fix 4단계: 릴리스 노트 작성

deploy 5단계와 **같은 위치·파일명 규칙·고정 구조**(`Summary by CodeRabbit` 포함)로 Write한다 — `~/.projectops/tmp/{OWNER}__{REPO}__release_notes.md`, tmp 폴더 없으면 먼저 생성 (`release-notes.md`).

> **⚠️ AGENT 필독: 노트 파일을 만든 뒤 fix 5단계(PR 생성)로 곧바로 가지 않고 fix 4.5단계(승인 게이트)부터 거친다.**

## fix 4.5단계: 사용자 승인 게이트

deploy 5.5단계와 **동일한 로직·문구**를 쓴다 ([시작 전 §3]의 `AUTO_APPROVE` / `CONFIG_HAS_KEY` 그대로).

- `APP_RELEASE == true`면 본문 위에 심사 경고 배너를 먼저 출력하고 **`AUTO_APPROVE`와 무관하게 수동 승인**을 받는다. fix 모드는 보통 1.5단계를 이미 거친 재시도이므로 값이 정해져 있다.
- 자동 모드(`AUTO_APPROVE == true` 이고 `APP_RELEASE != true`): 본문 표시만 하고 즉시 fix 5단계. "수동으로 바꿔줘"라고 하면 config 갱신 후 수동 분기로 전환
- 수동 모드(`AUTO_APPROVE == false` 또는 `APP_RELEASE == true`): 본문 표시 + 승인/수정 분기. 수정 요청 시 fix 4단계로 돌아가 재작성 후 fix 4.5단계 재진입
- 첫 실행(`CONFIG_HAS_KEY == false`, `APP_RELEASE != true`): 수동 모드 승인 직후 한 번만 자동화 제안(이 레포만 / 모든 레포 / 매번 확인) → 응답에 따라 config 갱신

## fix 5단계: 새 deploy PR 생성 (릴리스 노트 본문 포함)

PR이 처음부터 `Summary by CodeRabbit`을 담고 태어나야 워크플로우가 본문을 초기화하지 않는다.

```bash
# 릴리스 노트 임시 파일 — fix 4단계에서 Write한 그 절대경로와 동일해야 한다.
NOTES_FILE="$HOME/.projectops/tmp/{OWNER}__{REPO}__release_notes.md"
# commit provider "맡기기"로 노트 파일이 없으면 빈 문자열 → 빈 본문 PR (워크플로우가 채움).
[ -f "$NOTES_FILE" ] || NOTES_FILE=""

# create-pr의 body_file에 릴리스 노트 절대경로를 넘겨 본문 포함 PR 생성 (deploy 6-2b와 동일 패턴).
GITHUB_PAT="{PAT}" PYTHONIOENCODING=utf-8 "{PYTHON}" "{SCRIPTS}/changelog_cli.py" \
  create-pr "{OWNER}" "{REPO}" "🚀 Deploy $(date '+%Y%m%d') (재시도)" "$NOTES_FILE" "{HEAD_BRANCH}" "{BASE_BRANCH}"
rm -f "$NOTES_FILE"
```

출력 JSON의 `number`를 새 PR 번호로 읽는다. 없으면 "❌ PR 생성 실패"와 응답 JSON을 보여주고 멈춘다.
있으면 deploy 7단계처럼 `deploy-status --pr {number}`로 검증한다.

## fix 6단계: 결과 안내

```
✅ 새 deploy PR #NNN 생성 완료!

워크플로우가 본문의 릴리스 노트를 그대로 사용해 automerge를 진행합니다.
진행 상황: https://github.com/{owner}/{repo}/actions
```
