---
name: pro-commit
description: "브랜치명에서 이슈 번호를 자동 추출해 커밋 메시지를 완성하고 커밋한다. 이슈 연동 커밋, 커밋 메시지 자동 생성이 필요할 때 사용. /commit 호출 시 사용."
---

# Commit Mode

브랜치명에서 이슈 번호를 추출하고, GitHub API로 이슈 정보를 조회해 **커밋 컨벤션에 맞는 메시지를 자동 완성하고 커밋**한다.
`../references/common-rules.md`의 커밋 컨벤션 규칙을 따른다. 사용자 입력: $ARGUMENTS

## 무엇을 하려는가 → 명령 → 자세히

모든 명령은 `{PYTHON} {SCRIPTS}/commit_cli.py <명령>` 이다.

| 하려는 것 | 명령 | 자세히 |
|---|---|---|
| 이슈 제목·URL 조회 | `get-issue {owner} {repo} {번호}` | 3단계 |
| 현재 브랜치(cwd)의 이슈 번호 | `get-issue-number` | 3단계 |
| 이슈 제목 정제 · 메시지 틀 조립 | `normalize-title "<제목>"` · `get-commit-template "<제목>" "<URL>" [--type fix]` | `references/message-rules.md` |
| 커밋 직전 mention trailer 제거 | `sanitize-message "<메시지>"` | `references/message-rules.md` |
| 자동/수동 승인 판정 · 첫 실행 제안 | (config Read/Write) | `references/approval-gate.md` |

## 핵심 원칙

- **사용자 확인 없이 절대 커밋하지 않는다** — 메시지는 반드시 제안 후 승인받고 실행
- **이슈를 자동 생성하지 않는다** — 이슈 없으면 선택지 제시 후 사용자가 결정
- **`git add -A`·`git add .`로 일괄 스테이징하지 않는다** — 여러 세션이 같은 작업 트리를 쓰므로 일괄 스테이징하면 다른 세션의 미커밋 변경이 커밋에 섞인다. 변경 목록을 보여주고 **이번 작업에서 건드린 경로만** 명시해 `git add <경로...>` 한다. 의도를 모르는 변경은 건드리지 않고 그대로 둔다
- **`git push`는 절대 실행하지 않는다** — 커밋까지만 담당 (CLAUDE.md 규칙: push는 명시 허락 시에만)
- **커밋에 Claude/AI 흔적을 절대 남기지 않는다** — `Co-Authored-By`, `Generated with Claude`, `🤖`, `@claude` 등 AI 서명/푸터/GitHub @mention trailer 일절 금지. 변경설명·푸터 어디에도 `@username` GitHub mention을 포함하지 않는다(이슈 본문에서 가져온 mention도 제거). 사용자의 git 설정으로만 커밋되어 사용자가 직접 작성한 것처럼 보여야 한다. 커밋 메시지는 본문만 작성한다.
- **자동 모드(`auto_approve == true`)에서도 제안 메시지는 사용자에게 보여준 뒤 커밋한다** — 표시만 하고 즉시 진행. 응답을 기다리지 않는다.
- **사용자에게 config 키 이름·파일 경로를 노출하지 않는다** — 자동/수동 토글은 자연어 응답("자동으로 진행해줘" / "매번 확인받게 해줘")을 받아 agent가 직접 갱신한다.

## 시작 전 — 자동 승인 판정

`~/.projectops/config/config.json`(Windows: `C:\Users\<사용자>\.projectops\config\config.json`) 한 곳만 Read 로 읽어
`AUTO_APPROVE`·`CONFIG_HAS_KEY` 를 정한다. 우선순위(레포별 → 글로벌 → 기본 `false`)와 갱신 방법은 `references/approval-gate.md`.

## 스크립트 찾기 (1회)

**Bash 도구는 호출마다 상태가 초기화된다.** 한 번 찾은 뒤 **실제 경로를 이후 블록에 값으로 직접 써넣는다.**

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
# 이 레포에서 개발 중이면 로컬본이 캐시본보다 최신이므로 로컬 우선 (사용자 프로젝트는 설치본을 쓴다)
SKILL=pro-commit; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
echo "PYTHON=$PYTHON SCRIPTS=$SCRIPTS PROJECT_ROOT=$PROJECT_ROOT"
```

## 프로세스

### 1단계: 변경사항 확인 및 스테이징

```bash
git diff --cached --stat
git status --short
```

**staged 파일이 있으면** 그 목록을 보여주고 진행한다. 이번 작업과 무관해 보이는 파일이 섞여 있으면 커밋 전에 사용자에게 알린다 (임의로 unstage 하지 않는다).

**staged 파일이 없으면** 변경 목록을 두 묶음으로 나눠 보여주고, 첫 묶음만 경로를 명시해 스테이징한다:

| 묶음 | 판단 근거 | 처리 |
|------|-----------|------|
| 이번 작업에서 건드린 경로 | 이 세션에서 직접 수정·생성한 파일, 사용자가 지목한 파일 | `git add <경로...>` 로 명시 스테이징 |
| 의도를 모르는 변경 | 이 세션이 만들지 않았는데 작업 트리에 있는 파일 | **건드리지 않는다** — 다른 세션의 진행 중 작업일 수 있다 |

```bash
# 건드린 경로만 하나씩 명시한다. 공백·한글 경로는 따옴표로 감싼다.
git add -- "{경로1}" "{경로2}"
git diff --cached --stat
```

- `git add -A` / `git add .` / `git add -u` 는 쓰지 않는다. 무엇을 건드렸는지 판단이 서지 않으면 목록을 보여주고 사용자에게 고르게 한다.
- 스테이징할 경로가 하나도 없으면 커밋하지 않고 그 사실만 알린다.

### 2단계: 이슈 번호 추출

```bash
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
ISSUE_NUMBER=$(echo "$BRANCH" | grep -oE '#[0-9]+' | grep -oE '[0-9]+' | head -1)
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
OWNER=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/]([^/]+)/.*|\1|')
REPO=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/][^/]+/([^/.]+)(\.git)?$|\1|')
```

브랜치명 예: `20260422_#260_기능개선_제목` → `260`. (`{PYTHON} {SCRIPTS}/commit_cli.py get-issue-number` 도 같은 값을 준다.)

**이슈 번호가 없으면** 즉시 멈추고 묻는다:

```
브랜치명에서 이슈 번호를 찾을 수 없습니다. (현재 브랜치: {브랜치명})

어떻게 할까요?
1. 이슈 번호를 직접 입력할게요
2. 이슈 없이 자유 형식으로 커밋할게요
3. 취소
```

1 → 번호를 받아 3단계 / 2 → 메시지를 직접 받아 5단계(이슈 형식 없이) / 3 → 종료.

### 3단계: 이슈 조회 (인라인 Python 금지)

PAT는 commit_cli가 config.json에서 자동 로드한다(환경변수가 있으면 우선).

```bash
PYTHONIOENCODING=utf-8 "{PYTHON}" "{SCRIPTS}/commit_cli.py" get-issue {owner} {repo} {이슈번호}
```

출력의 `title`·`html_url`을 쓴다. 제목은 **agent가 요약/재작성하지 않고** 정제 규칙(태그 제거 → 앞 이모지 제거 → trim, 비면 원본)만 적용한다 — `references/message-rules.md`.

| 실패 | 다음 행동 |
|---|---|
| `github_api_401` | PAT 만료 안내 → `/pro-github`에서 재등록 유도. 제목은 사용자에게 직접 받는다 |
| `github_api_404` | 이슈 없음 안내 → 번호 재확인 또는 제목 직접 입력 |
| `bad_args` | 인자 순서(`owner repo number`) 확인 |

### 4단계: 메시지 구성

**형식**: `{clean_title} : {타입} : {변경설명} {html_url}`

- agent가 정하는 것은 **타입과 변경설명뿐**이다. 타입은 staged diff로 추천한다(feat/fix/refactor/docs/chore/test/style — 표는 `references/message-rules.md`).
- **호환성이 깨지는 변경에만 `!`** (`feat!` → 릴리스 major 승격, #546). 확신이 없으면 붙이지 말고 묻는다.
- `{변경설명}`에 `@username` mention을 넣지 않는다.

### 5단계: 승인 게이트

- `AUTO_APPROVE == true` → 메시지를 보여주기만 하고 바로 6단계.
- `false` → 제안 후 1(커밋)/2(타입 변경)/3(설명 수정)/4(취소)로 묻고 **응답 전 커밋 금지**.
- 첫 실행(`CONFIG_HAS_KEY == false`)에서 1을 고르면 커밋 직전 자동화 제안을 **한 번** 한다.

문구·분기·config 갱신 규칙 전문: `references/approval-gate.md`.

### 6단계: 커밋 실행

**AI 서명/푸터를 절대 추가하지 않는다.** `--author`·trailer 없이 사용자 git 설정 그대로 커밋한다.
메시지 끝 mention trailer는 `sanitize-message` 로 강제 제거한다(셸 `sed` 금지 — #523, 이유는 `references/message-rules.md`).

```bash
RAW_MSG="{최종 커밋 메시지}"
SANITIZED=$(PYTHONIOENCODING=utf-8 "{PYTHON}" "{SCRIPTS}/commit_cli.py" sanitize-message "$RAW_MSG") \
  || { echo "❌ 커밋 메시지 정리 실패 — 커밋을 중단합니다"; exit 1; }
CLEAN_MSG=$(SANITIZED="$SANITIZED" PYTHONIOENCODING=utf-8 "{PYTHON}" -c 'import json,os,sys; m=json.loads(os.environ["SANITIZED"])["message"]; sys.exit(1) if not m.strip() else print(m, end="")') \
  || { echo "❌ 커밋 메시지가 비었습니다 — 원문을 확인하세요"; exit 1; }
cd "{PROJECT_ROOT}" && git commit -m "$CLEAN_MSG"
```

- 정리 실패·빈 결과면 **커밋을 중단**한다. 정제 규칙을 문서에 fallback으로 복제하지 않는다.
- `removed: true` 면 mention이 들어간 경위를 4단계에서 되짚는다. 본문 중간 mention은 보존된다.

커밋 성공 후:

```
✅ 커밋 완료!
메시지: {커밋 메시지}
해시: {커밋 해시 앞 7자리}

push가 필요하면 직접 실행하세요:
git push origin {현재 브랜치명}
```
