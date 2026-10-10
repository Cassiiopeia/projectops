# deploy 모드 — 단계별 명령과 문구

> 언제 읽나: deploy 모드를 실제로 실행할 때. 각 단계의 판단 규칙 요약은 SKILL.md에 있고, 여기는 그대로 실행할 bash와 사용자에게 보여줄 문구다.

**Bash는 stateless다.** 아래 `{PAT}` · `{OWNER}` · `{REPO}` · `{PYTHON}` · `{SCRIPTS}` · `{PROJECT_ROOT}` · `{HEAD_BRANCH}` · `{BASE_BRANCH}`는 [시작 전]에서 구한 **실제 값으로 써넣는다**. 이전 Bash 호출의 변수가 살아 있다고 가정하지 않는다. `{HEAD_BRANCH}`/`{BASE_BRANCH}`는 [시작 전 §5]에서 확정한 값(폴백 develop/main) — 하드코딩하지 않는다.

## 1단계: 커밋 상태 확인

아래 명령을 **각각 별도로** 실행한다. 절대 한 줄로 합치지 않는다.

```bash
git status --short
```

```bash
git fetch origin
```

```bash
# 현재 브랜치가 릴리스 head 인지 확인 — 다른 브랜치에서 merge·push 하면 엉뚱한 곳이 바뀐다
git rev-parse --abbrev-ref HEAD
```

```bash
# base(프로덕션) 대비 미반영 커밋 목록 (이게 핵심 — head→base PR이 목적이므로)
git log "origin/{BASE_BRANCH}..HEAD" --oneline 2>/dev/null
```

```bash
# 위 결과가 비어 있을 경우 대비용 — head remote 대비도 함께 확인
git log "origin/{HEAD_BRANCH}..HEAD" --oneline 2>/dev/null
```

미커밋 변경이 있을 때 안내 문구:
```
커밋되지 않은 변경사항이 있습니다. 먼저 커밋 후 다시 실행해주세요.
/pro-commit 으로 커밋할 수 있습니다.
```

## 1-1. base 최신화 (역방향 차이 병합 — 생략 금지)

> **왜 필요한가**: RELEASE-CHANGELOG는 버전 확정 커밋을 **base(main)에만** 남긴다. head(develop)가 그 커밋을 받지 않은 채 다음 릴리스 PR을 열면 버전 파일이 충돌해 워크플로우가 실패한다.

```bash
# head 를 원격과 먼저 맞춘다. merge 커밋을 만든 뒤에 pull --rebase 하면 merge 가 풀려 base 커밋이 재작성된다.
git pull --rebase origin "{HEAD_BRANCH}"
# base 에는 있는데 head 에는 없는 커밋 (역방향 차이)
git log "origin/{HEAD_BRANCH}..origin/{BASE_BRANCH}" --oneline
```

결과가 있으면 목록을 사용자에게 보여주고 병합한다:

```bash
git merge --no-edit "origin/{BASE_BRANCH}"
```

- 병합 커밋은 2단계의 push 목록에 함께 표시되고 3단계에서 push된다.
- **충돌이 나면 멈추고** 충돌 파일을 사용자에게 알린다. 임의로 한쪽을 버리거나 `git merge --abort`·`reset`을 실행하지 않는다 — 양쪽 의도를 살리는 해소 방향을 사용자와 정한다.

## 1.5단계: 릴리스 컨텍스트 인지 (앱 심사 연관 레포 판단)

> **왜 필요한가**: 앱스토어/플레이스토어 심사 자동 제출이 켜진 레포에서는 `main` 릴리스가 "내부 배포"가 아니라 **사용자 대면 출시**가 된다. 릴리스 노트가 그대로 스토어 "이번 업데이트" 출시노트가 되어 심사에 들어간다. **백엔드 레포(spring/python 등)는 아무 영향 없이 조용히 통과한다.**

신호 수집 (PAT 불필요, 로컬 파일만 스캔):

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/changelog_cli.py detect-release-context --project-root "{PROJECT_ROOT}"
```

반환 JSON의 `signals`(사실)와 `hint`(약한 힌트)를 얻는다. **`hint`는 참고일 뿐, 최종 판단은 agent가 한다.** 분기 표는 SKILL.md 1.5단계.

확인 메시지 (`APP_RELEASE == unset`이고 앱 심사 감지 시 **한 번**, 자연어만 — config 키·파일 경로 노출 금지):

```
📱 이 저장소는 앱스토어/플레이스토어 심사로 이어지는 배포로 보입니다.
   그렇다면 지금 작성하는 릴리스 노트가 그대로 스토어 "이번 업데이트"
   출시노트가 되어 심사에 들어갑니다.

이 저장소를 앞으로 "앱 심사 배포"로 보고, 릴리스 노트를 더 신중히 다룰까요?
1. 네 (앱 심사 배포가 맞습니다)
2. 아니요 (일반 배포입니다)
```

응답별 config 갱신은 `config.md` §4. 이후 2단계로 진행한다.

## 2단계: push 전 확인

```
📋 push할 커밋 ({HEAD_BRANCH} → {BASE_BRANCH} 미반영):
  - {커밋 메시지 1}
  - {커밋 메시지 2}

{HEAD_BRANCH} 브랜치에 push할까요?
1. 네, push합니다
2. 취소
```

## 3단계: push

```bash
# 원격 동기화는 1-1단계에서 이미 했다. 여기서 pull --rebase 를 다시 하면 1-1의 merge 커밋이 풀린다.
git push origin "{HEAD_BRANCH}"
```

- non-fast-forward로 거부되면 **강제 푸시하지 않는다.** `git pull --rebase=merges origin "{HEAD_BRANCH}"`로 merge 커밋을 보존한 채 통합한 뒤 다시 push한다.
- push 후 버전은 증가하지 않는다 — 버전은 릴리스 PR에서 RELEASE-CHANGELOG가 머지 직전 확정한다(릴리스당 +1).

## 4단계: 커밋 분석

PR을 만들기 **전에** head → base 변경분을 분석한다:

```bash
git fetch origin "{BASE_BRANCH}" "{HEAD_BRANCH}" 2>/dev/null || true
# 분석 base는 HEAD가 아닌 origin/{HEAD_BRANCH} — README 버전 워크플로우 등이 원격을 앞서게 할 수 있다
git log "origin/{BASE_BRANCH}..origin/{HEAD_BRANCH}" --pretty=format:"%s" | grep -v "\[skip ci\]" | head -60
```

분류·재작성 기준은 `release-notes.md`.

## 5단계 · 5.5단계

노트 작성·파일 위치·고정 구조·승인 문구는 `release-notes.md`. 분기 조건은 SKILL.md.

## 6단계: deploy PR 생성 (릴리스 노트 본문 포함)

VERSION-CONTROL 워크플로우 완료를 기다리지 않고 deploy PR을 생성한다. **5단계에서 만든 릴리스 노트 파일을 본문으로 담아 생성**하는 것이 핵심이다 — PR이 처음부터 `Summary by CodeRabbit`을 담고 있어야 RELEASE-CHANGELOG가 본문을 초기화하지 않는다.

```bash
GITHUB_PAT="{PAT}"; OWNER="{OWNER}"; REPO="{REPO}"; PYTHON="{PYTHON}"; SCRIPTS="{SCRIPTS}"; HEAD_BRANCH="{HEAD_BRANCH}"; BASE_BRANCH="{BASE_BRANCH}"

# 릴리스 노트 임시 파일 — 5단계에서 Write한 그 절대경로와 동일해야 한다.
# 홈 디렉토리 + {OWNER}__{REPO} prefix → cwd 무관·레포별 격리. (Windows Git Bash도 $HOME 정상 동작)
NOTES_FILE="$HOME/.projectops/tmp/${OWNER}__${REPO}__release_notes.md"
# commit provider에서 "맡기기" 선택 시 5단계가 노트 파일을 만들지 않는다.
# 파일이 없으면 빈 문자열로 넘겨 빈 본문 PR 생성 → 워크플로우 fallback job이 커밋 분석으로 채운다.
[ -f "$NOTES_FILE" ] || NOTES_FILE=""

TODAY=$(date '+%Y%m%d')
TITLE="🚀 Deploy ${TODAY}"

DEPLOY_STATUS=$(GITHUB_PAT="$GITHUB_PAT" PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPTS/changelog_cli.py" \
  deploy-status "$OWNER" "$REPO" --base "$BASE_BRANCH" --head "$HEAD_BRANCH")
EXISTING_PR=$(DEPLOY_STATUS="$DEPLOY_STATUS" "$PYTHON" -c "import os,json; d=json.loads(os.environ['DEPLOY_STATUS']); print((d.get('pr') or {}).get('number',''))")

# 기존 open deploy PR이 있으면 재사용 — 닫지 않는다 (새로 열면 워크플로우 재트리거되어 본문 초기화 위험)
if [ -n "$EXISTING_PR" ]; then
  # 재사용: 이미 PR이 있으므로 update-pr로 릴리스 노트 본문만 갱신한다.
  PR_NUMBER=$EXISTING_PR
  echo "기존 deploy PR #$PR_NUMBER 재사용 → 본문 업데이트"
  RESULT_OUT=$(GITHUB_PAT="$GITHUB_PAT" PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPTS/changelog_cli.py" \
    update-pr "$OWNER" "$REPO" "$PR_NUMBER" "$NOTES_FILE")
else
  # 신규: create-pr의 body_file에 릴리스 노트 절대경로를 넘겨 본문 포함 PR 생성.
  # NOTES_FILE이 빈 문자열(commit 맡기기)이면 빈 본문 PR → 워크플로우가 채운다.
  RESULT_OUT=$(GITHUB_PAT="$GITHUB_PAT" PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPTS/changelog_cli.py" \
    create-pr "$OWNER" "$REPO" "$TITLE" "$NOTES_FILE" "$HEAD_BRANCH" "$BASE_BRANCH")
  PR_NUMBER=$(RESULT_OUT="$RESULT_OUT" "$PYTHON" -c "import os,json; print(json.loads(os.environ['RESULT_OUT']).get('number',''))")
  echo "새 deploy PR #$PR_NUMBER 생성 (릴리스 노트 본문 포함)"
fi
rm -f "$NOTES_FILE"

if [ -z "$PR_NUMBER" ]; then
  echo "❌ PR 생성/업데이트 실패. GitHub API 응답을 확인하세요. ($RESULT_OUT)"
  exit 1
fi
```

출력 JSON(`{"number","url"}`)으로 성공을 확인한다.

## 7단계: automerge 검증 (deploy-status)

PR 생성 직후 **`/tmp`에 즉석 Python을 만들지 말고** 이 재사용 커맨드 한 번으로 확인한다. PR 머지·CodeRabbit 본문·워크플로우 run·deploy HEAD를 한 번에 조회해 `verdict`로 판정한 JSON을 반환한다. verdict별 행동은 SKILL.md 표.

```bash
GITHUB_PAT="{PAT}" PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/changelog_cli.py \
  deploy-status "{OWNER}" "{REPO}" --pr "{PR_NUMBER}" --base "{BASE_BRANCH}"
```

> **재확인 시 sleep을 쓰지 않는다.** Claude Code Bash는 `sleep 120`을 차단한다. 대기가 필요하면 `ScheduleWakeup`으로 자기 페이스를 잡고, 깨어나면 `next` 힌트의 `deploy-status` 커맨드를 다시 호출한다.
>
> **재확인 주기 (실측 기반)**: 릴리스 노트를 본문에 담아 PR을 만들면 CodeRabbit 10분 대기가 없으므로 automerge는 **보통 60초 안에** 끝난다 (VERSION-CONTROL → CHANGELOG → automerge 한 사이클, 실측 #317·#318 모두 60초 내 머지). 그래서 `ScheduleWakeup(delaySeconds=60)`으로 재확인하고 `merged`가 될 때까지 60초 간격으로 반복한다. **`ScheduleWakeup`의 최소 허용값이 60초**라 45·30초를 줘도 60초로 클램프된다 — 60초가 사실상 최단 주기다. 90초 같은 긴 값은 이미 끝난 배포를 늦게 확인해 시간을 낭비하므로 쓰지 않는다. (60초는 캐시 유지 구간 270초 이내라 비용 페널티 없음.)

## 8단계: 결과 안내

```
✅ 완료!

📋 요약:
  • push: origin/{HEAD_BRANCH}
  • deploy PR: #NNN
  • 릴리스 노트: 작성 완료

RELEASE-CHANGELOG 워크플로우가 본문의 릴리스 노트("Summary by CodeRabbit" 형식)를
그대로 사용해 CHANGELOG 업데이트 후 {BASE_BRANCH} automerge를 진행합니다.

진행 상황: https://github.com/{owner}/{repo}/actions
```
