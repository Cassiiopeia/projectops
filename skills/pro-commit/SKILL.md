---
name: pro-commit
description: "브랜치명에서 이슈 번호를 자동 추출해 커밋 메시지를 완성하고 커밋한다. 이슈 연동 커밋, 커밋 메시지 자동 생성이 필요할 때 사용. /commit 호출 시 사용."
---

# Commit Mode

브랜치명에서 이슈 번호를 추출하고, GitHub API로 이슈 정보를 조회해 **커밋 컨벤션에 맞는 메시지를 자동 완성하고 커밋**한다.

## 핵심 원칙

- **사용자 확인 없이 절대 커밋하지 않는다** — 메시지는 반드시 제안 후 승인받고 실행
- **이슈를 자동 생성하지 않는다** — 이슈 없으면 선택지 제시 후 사용자가 결정
- **staged 파일이 없으면 변경 파일을 자동으로 `git add`한다** — 사용자가 멈춰서 직접 스테이징할 필요 없음
- **`git push`는 절대 실행하지 않는다** — 커밋까지만 담당 (CLAUDE.md 규칙: push는 명시 허락 시에만)
- **커밋에 Claude/AI 흔적을 절대 남기지 않는다** — `Co-Authored-By`, `Generated with Claude`, `🤖`, `@claude` 등 AI 서명/푸터/GitHub @mention trailer 일절 금지. 변경설명·푸터 어디에도 `@username` GitHub mention을 포함하지 않는다(이슈 본문에서 가져온 mention도 제거). 사용자의 git 설정으로만 커밋되어 사용자가 직접 작성한 것처럼 보여야 한다. 커밋 메시지는 본문만 작성한다.
- **자동 모드(`auto_approve == true`)에서도 제안 메시지는 사용자에게 보여준 뒤 커밋한다** — 표시만 하고 즉시 진행. 응답을 기다리지 않는다.
- **사용자에게 config 키 이름·파일 경로를 노출하지 않는다** — 자동/수동 토글은 자연어 응답("자동으로 진행해줘" / "매번 확인받게 해줘")을 받아 agent가 직접 갱신한다.

## 시작 전

`references/common-rules.md`의 커밋 컨벤션 규칙을 숙지한다.

### 자동 승인 모드 판정 — Read 도구로 config에서 직접 추출

`Read` 도구로 config 파일을 읽는다. **이 고정 경로 한 곳만 본다 — `ls`·glob으로 탐색하거나 플러그인 캐시(`~/.claude/plugins/cache/...`)를 뒤지지 마라.**
- Windows: `C:\Users\<사용자>\.projectops\config\config.json`
- macOS/Linux: `~/.projectops/config/config.json`

`github` 섹션에서 `auto_approve` 값을 결정한다. 해석 우선순위 (위→아래로 검사, 먼저 발견되는 값 채택):

1. `github.repos[]` 중 `owner == 현 OWNER && repo == 현 REPO`인 항목의 `commit.auto_approve`
2. `github.commit.auto_approve` (글로벌 기본값)
3. 어디에도 없으면 `false` (안전 default — 수동 승인)

판정 결과를 두 값으로 **기억**한다:

- `AUTO_APPROVE` — boolean (`true` / `false`)
- `CONFIG_HAS_KEY` — boolean (`true`면 위 우선순위 1 또는 2에서 키 발견. `false`면 둘 다 없어 첫 실행 케이스)

`CONFIG_HAS_KEY=false`인 경우는 5.5단계의 **첫 실행 안내 분기** 트리거로 사용한다.

> **사용자에게 노출하는 안내는 자연어로만 한다.** "auto_approve", "config.json", "commit 섹션" 같은 키 이름·파일 경로를 사용자 메시지에 절대 쓰지 않는다. 사용자는 "자동으로 진행" / "매번 확인" 같은 자연어로 의사 표시하며 agent가 config를 직접 갱신한다.

## 사용자 입력

$ARGUMENTS

## 프로세스

### 1단계: 환경 준비

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
```

### 2단계: 변경사항 확인 및 스테이징

```bash
git diff --cached --stat
git status --short
```

**staged 파일이 있으면** 그대로 진행한다.

**staged 파일이 없으면** 변경된(추적/미추적) 파일을 자동으로 스테이징한다:

```bash
git add -A
```

스테이징 후 다시 확인하고 진행한다:

```bash
git diff --cached --stat
```

> 이슈별로 따로 커밋하려는 경우(사용자가 명시), 해당 이슈 관련 파일만 골라서 `git add <파일들>` 한다. 그 외엔 `git add -A`로 일괄 스테이징한다.

### 3단계: 이슈 번호 자동 추출

브랜치명에서 이슈 번호를 추출한다:

```bash
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
ISSUE_NUMBER=$(echo "$BRANCH" | grep -oE '#[0-9]+' | grep -oE '[0-9]+' | head -1)
```

브랜치명 형식 예시: `20260422_#260_기능개선_제목` → 이슈 번호 `260` 추출

**이슈 번호가 추출된 경우** — GitHub API로 이슈 정보 조회:

```bash
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
OWNER=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/]([^/]+)/.*|\1|')
REPO=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/][^/]+/([^/.]+)(\.git)?$|\1|')
```

**이슈 조회는 인라인 Python으로 하지 않는다.** `skills/pro-commit/scripts/commit_cli.py`의 `get-issue` 서브커맨드로 이슈 정보를 가져온다. PAT는 commit_cli가 config.json에서 자동 로드하므로 직접 추출할 필요가 없다(환경변수가 있으면 우선 사용).

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SCRIPTS="$PROJECT_ROOT/skills/pro-commit/scripts"; [ -d "$SCRIPTS" ] || SCRIPTS=$(ls -d ~/.claude/plugins/cache/*/projectops/*/skills/pro-commit/scripts 2>/dev/null | sort -V | tail -1); cd "$SCRIPTS" || exit 1
PYTHONIOENCODING=utf-8 "$PYTHON" commit_cli.py get-issue {owner} {repo} {추출된 이슈번호}
```

출력 JSON에서 `title`(원본 제목)과 `html_url`을 얻는다. **이슈 제목은 agent가 임의 요약/재작성하지 않고**, 아래 규칙으로 결정적으로 정제해 커밋 메시지에 쓴다 (SUH-ISSUE-HELPER의 `extractIssueTitle`과 동일):

1. `[태그]` 형식(`[버그]`, `[기능개선]` 등)을 모두 제거
2. 앞에 붙은 이모지·제어문자(So/VS16/ZWJ)를 제거
3. 앞뒤 공백 trim — 결과가 비면 원본 제목을 그대로 사용

`get-issue`가 `[ERROR] ... github_api_401`(PAT 만료) 또는 `github_api_404`(이슈 없음)을 stderr로 내면, 그 사유를 안내하고 사용자에게 제목을 직접 입력받는다. → 4단계로 진행

**이슈 번호가 없는 경우** — 즉시 멈추고 선택지 제시:

```
브랜치명에서 이슈 번호를 찾을 수 없습니다. (현재 브랜치: {브랜치명})

어떻게 할까요?
1. 이슈 번호를 직접 입력할게요
2. 이슈 없이 자유 형식으로 커밋할게요
3. 취소
```

- **1 선택**: 이슈 번호 입력받아 GitHub API 조회 후 4단계 진행
- **2 선택**: 커밋 메시지 직접 입력받아 5단계로 진행 (이슈 형식 없이)
- **3 선택**: 종료

### 4단계: 변경사항 분석

staged 파일 목록과 diff를 분석하여 적절한 타입 추천:

| 변경 내용 | 추천 타입 |
|-----------|-----------|
| 새 기능, 새 파일 추가 | `feat` |
| 버그 수정, 에러 처리 | `fix` |
| 코드 구조 변경 (로직 유지) | `refactor` |
| 문서, 주석, README | `docs` |
| 설정 파일, 빌드 관련 | `chore` |
| 테스트 추가/수정 | `test` |
| 스타일, 포맷 | `style` |

### 5단계: 커밋 메시지 제안 후 사용자 확인

`references/common-rules.md` 커밋 컨벤션에 따라 메시지를 구성한 뒤 **제안만** 한다.

**형식**: `{clean_title} : {타입} : {변경설명} {html_url}`

| 부분 | 결정 방식 |
|------|-----------|
| `clean_title` | 3단계 정적 추출 스크립트의 `clean_title` **그대로** — agent가 다시 요약/재작성하지 않는다 |
| `html_url` | 3단계 스크립트의 `html_url` **그대로** |
| `{타입}` | 4단계 diff 분석으로 agent 추천 (사용자 승인) |
| `{변경설명}` | staged diff 분석으로 agent 작성 (사용자 승인) |

- agent가 자유 판단하는 부분은 **타입과 변경설명뿐**이다. 제목·URL은 이슈 원본에서 정규식으로 정리한 값을 손대지 않고 사용한다.
- `{변경설명}`에 `@username` GitHub mention(`@claude` 등)을 절대 포함하지 않는다. 이슈 본문·제목에서 따온 문구에 mention이 있으면 제거 후 사용한다.
- 이슈 없이 자유 형식으로 커밋하는 경우(3단계 2선택)에만 제목을 직접 입력받는다.

[시작 전]에서 판정한 `AUTO_APPROVE` / `CONFIG_HAS_KEY` 값에 따라 5.5단계로 분기한다.

### 5.5단계: 사용자 승인 게이트

#### A. 자동 모드 (`AUTO_APPROVE == true`)

메시지를 사용자에게 표시만 하고 즉시 6단계로 진행한다. 응답을 기다리지 않는다.

```
🤖 이 레포는 확인 없이 바로 커밋되도록 설정돼 있어 메시지만 안내드리고 커밋합니다.
   (다시 매번 확인받고 싶으시면 "확인받게 해줘"라고 말씀해주세요.)

📝 커밋 메시지:
{완성된 커밋 메시지}

커밋을 실행합니다.
```

이후 6단계 진행.

> 사용자가 메시지를 보고 "확인받게 해줘", "수동으로 바꿔줘", "다음부턴 확인받아줘" 같은 자연어로 응답하면, 6단계를 진행하기 **전에** Read/Write 도구로 `config.json`을 갱신한다. 우선순위 1(레포별)에 키가 있었다면 그 값을 `false`로, 없었다면 우선순위 2(글로벌)를 `false`로 설정한다. 갱신 후 메시지는 그대로 두고 다시 사용자 승인을 받는다(B 분기로 전환).

#### B. 수동 모드 (`AUTO_APPROVE == false`)

```
📝 제안 커밋 메시지:

{완성된 커밋 메시지}

이 메시지로 커밋할까요?
1. 네, 커밋합니다
2. 타입을 바꾸고 싶어요 (feat/fix/refactor/docs/chore/test/style)
3. 설명을 직접 수정할게요
4. 취소
```

사용자 응답을 기다린다. **응답 전까지 커밋을 절대 실행하지 않는다.**

응답 분기:

- **1 선택** → 6단계 진행. 단, `CONFIG_HAS_KEY == false`(첫 실행)이면 6단계 **직전**에 아래 [C. 첫 실행 자동화 제안]을 한 번만 실행한다
- **2 선택** → 타입 목록 출력 후 입력받아 메시지 재구성 → 5.5단계 처음으로
- **3 선택** → 설명 부분만 입력받아 메시지 재구성 → 5.5단계 처음으로
- **4 선택** → 종료

#### C. 첫 실행 자동화 제안 (B에서 1 선택 + `CONFIG_HAS_KEY == false`일 때만, 한 번)

```
💡 다음 커밋부터 어떻게 진행할까요?

매번 커밋 직전에 메시지를 보여드리고 확인받는 방식이 기본입니다.
원하시면 이 확인 단계를 건너뛰고 곧바로 커밋이 진행되도록 바꿀 수 있습니다.

1. 이 레포 커밋은 앞으로 확인 없이 바로 진행해주세요
2. 모든 레포 커밋을 앞으로 확인 없이 바로 진행해주세요
3. 지금처럼 매번 커밋 메시지 확인받겠습니다

(언제든 "다시 확인받게 해줘" / "자동으로 바꿔줘"라고 말씀하시면 바꿀 수 있습니다)
```

응답에 따라 agent가 Read/Write 도구로 `config.json`을 갱신한다:

- **1 선택** → `github.repos[]`에서 현 OWNER/REPO 매칭 항목에 `commit.auto_approve: true` 추가
- **2 선택** → `github.commit.auto_approve: true` 추가 (객체 없으면 생성)
- **3 선택** → `github.commit.auto_approve: false` 추가 (다음 실행부터 묻지 않도록 키 자체는 남긴다)

갱신 후 안내:

- 1: "✅ 이 레포는 다음 커밋부터 확인 없이 바로 진행합니다."
- 2: "✅ 모든 레포에서 다음 커밋부터 확인 없이 바로 진행합니다."
- 3: "✅ 앞으로도 매번 커밋 메시지 확인받습니다."

이후 6단계 진행.

> **갱신 시 주의**: `references/config-rules.md §4` 규칙대로 전체 파일을 Read로 먼저 읽고 다른 섹션을 보존한 채 해당 키만 추가/수정해 Write한다. PAT·다른 repos 항목을 절대 날리지 않는다.

### 6단계: 커밋 실행

사용자가 1번(확인)을 선택했거나 자동 모드인 경우에만 실행한다.

**커밋 메시지에 AI 서명/푸터를 절대 추가하지 않는다.** `Co-Authored-By`, `Generated with Claude`, `🤖`, `@claude` 등 GitHub @mention trailer 금지. 아래 명령 외에 `--author` 옵션이나 추가 trailer를 붙이지 않는다 — 사용자 git 설정 그대로 커밋한다.

커밋 직전, 메시지 끝의 `@username` mention trailer를 무조건 자동 제거한다(skill 차원 강제 sanitize). 5단계 검열을 우회한 경우의 마지막 방어선이다.

> ⚠️ **셸 `sed`로 하지 않는다 (#523).** 과거 `sed -E ':a;$!N;$!ba;...'` 한 줄로 처리했는데 이 라벨 구문이 **GNU sed 전용**이라 macOS(BSD sed)에서는 **종료 코드 0으로 조용히 통과하며 입력을 그대로 흘려보냈다.** 안전망이 켜져 있다고 믿는 상태에서 실제로는 꺼져 있었다. OS별 도구 차이를 타지 않도록 `commit_cli.py`로 옮겼다.

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "❌ Python을 찾을 수 없습니다"; exit 1; }

RAW_MSG="{최종 커밋 메시지}"

# 스크립트 탐색: 이 레포에서 개발 중이면 로컬본이 캐시본보다 최신이므로 로컬 우선.
# (사용자 프로젝트에는 skills/ 가 없어 자동으로 캐시본이 쓰인다)
SCRIPTS="$PROJECT_ROOT/skills/pro-commit/scripts"
[ -f "$SCRIPTS/commit_cli.py" ] || SCRIPTS=$(ls -d ~/.claude/plugins/cache/*/projectops/*/skills/pro-commit/scripts 2>/dev/null | sort -V | tail -1)

CLEAN_MSG=$(RAW_MSG="$RAW_MSG" SCRIPTS="$SCRIPTS" PYTHONIOENCODING=utf-8 "$PYTHON" - <<'EOF'
import json, os, re, subprocess, sys

raw = os.environ["RAW_MSG"]
script = os.path.join(os.environ.get("SCRIPTS", ""), "commit_cli.py")

# 1순위: 재사용 스크립트의 sanitize-message
try:
    out = subprocess.run([sys.executable, script, "sanitize-message", raw],
                         capture_output=True, text=True, timeout=20)
    msg = json.loads(out.stdout)["message"]
except Exception:
    # 2순위: 구버전 캐시라 서브커맨드가 없을 수 있다 — 동일 규칙을 인라인으로 적용.
    #        여기서 절대 빈 문자열을 반환하지 않는다 (git commit -m "" 로 깨진다).
    msg = re.sub(r"\s*(@[A-Za-z0-9_-]+(?:\s+@[A-Za-z0-9_-]+)*)\s*$", "", raw).rstrip()

if not msg.strip():
    print("❌ 커밋 메시지가 비었습니다 — 원문을 확인하세요", file=sys.stderr)
    sys.exit(1)
print(msg, end="")
EOF
) || { echo "❌ 커밋 메시지 정리 실패 — 커밋을 중단합니다"; exit 1; }

cd "$PROJECT_ROOT" && git commit -m "$CLEAN_MSG"
```

`sanitize-message` 출력 JSON: `{"message": "정리된 메시지", "removed": true|false, "summary": "..."}`.
`removed`가 `true`면 mention이 실제로 제거된 것이므로, 왜 들어갔는지 5단계를 되짚어본다.

> **실패해도 빈 메시지를 만들지 않는다.** 스크립트를 못 찾거나 구버전이라 서브커맨드가 없어도 동일 규칙을 인라인으로 적용하고, 그래도 결과가 비면 **커밋을 중단**한다. 과거 sed 방식은 실패를 성공으로 보고했지만 이제는 드러난다.

> **본문 중간의 mention은 보존한다.** `@projectops build app 관련 수정`처럼 의미 있게 등장한 mention은 지우지 않고, **끝에 붙은 trailer만** 제거한다.

커밋 성공 후 결과 출력:

```
✅ 커밋 완료!
메시지: {커밋 메시지}
해시: {커밋 해시 앞 7자리}

push가 필요하면 직접 실행하세요:
git push origin {현재 브랜치명}
```
