---
name: pro-launch
description: "앱·웹·서버를 띄우고, 조작하고, 찍는 능력 스킬이다. Android 에뮬레이터·iOS 시뮬레이터 화면을 찍고(상태바 고정 포함) 앱을 띄우며, 브라우저를 열어 이동·클릭·입력·캡처하고, 폭을 바꾸거나 API 응답을 바꿔치기해 빈 목록·실패·로딩 상태를 서버를 건드리지 않고 연출한다. 자동화 표식을 가려 Google·Apple 로그인 화면이 자동화 브라우저를 막는 것을 줄인다. 단건 HTTP 요청·DB 조회·서버 로그도 적어 둔 접속 방법대로 실행한다. 무엇을 왜 찍을지는 정하지 않는다 — 그건 부르는 작업 스킬(pro-agent-test · pro-design-brief · pro-figma-verify)의 일이다. '에뮬레이터 띄워서 찍어줘', '시뮬레이터 스크린샷', '브라우저로 이 화면 캡처해줘', '모바일 폭으로 찍어줘', '빈 목록 화면 찍어줘', '500 났을 때 화면 보여줘', '이 API 한 번 불러줘' 같은 요청에 사용한다. 버그를 찾으며 끝까지 밟는 QA 는 pro-agent-test 다."
---

# pro-launch — 띄우고, 조작하고, 찍는다

**능력 스킬이다.** 무엇을 부르면 무엇이 나오는지만 적는다. 무엇을 왜 찍을지는 부르는 작업 스킬
(pro-agent-test · pro-design-brief · pro-figma-verify · pro-report)이 정하고, 이 스크립트를 **Skill 호출이 아니라 스크립트로** 부른다(같은 층의 능력 스킬: pro-github · pro-ssh).
판단은 agent, 스크립트는 실행과 기록만 한다 — 라우트·화면 목록을 스캔해 프로젝트 구조를 알아맞히지 않는다.

`../references/common-rules.md` 의 **절대 규칙** 적용 (Git 커밋 금지, 민감 정보 보호). 인자: $ARGUMENTS

## 무엇을 하려는가 → 명령 → 자세한 문서

모든 명령은 `{PYTHON} {SCRIPTS}/launch_cli.py <명령>` 이다.

| 하려는 것 | 명령 | 자세히 |
|---|---|---|
| 도구(adb · simctl · Chromium · Pillow · cwebp · ffmpeg) · 무엇을 띄울 수 있나(app · web · server, 패키지명 · 번들 ID) · 붙은 기기 · 부팅된 시뮬레이터 · AVD | `doctor` · `detect --path .` · `devices` | — |
| 참가자가 둘 이상 — 역할을 기기에 묶기 | `device list\|bind\|unbind\|show` | `references/app.md` |
| 앱 띄우기 · 찍기 | `app launch` · `app shot [--clean-status]` | `references/app.md` |
| 앱 화면 구조 · 누르기 · 밀기 | `app tree` · `app tap` · `app swipe` | `references/app.md` |
| 앱에 글자 넣기(Android, 저장된 로그인) | `app type --cred 이름` | `references/app.md` |
| 브라우저 열기 · 이동 · 클릭 · 입력 · 캡처 · 확인 | `web setup\|open\|goto\|click\|type\|shot\|assert\|console\|close` | `references/web.md` |
| 폭 바꾸기 · 응답 바꿔치기(빈 목록 · 500 · 지연) | `web viewport` · `web route` | `references/web.md` |
| 코드로 상태를 그려 찍기 | `render snapshot` → `render run` | `references/render.md` |
| 단건 HTTP · 붙는 법 기록 · SQL · 로그 | `http` · `access show\|set\|unset` · `db` · `logs` | `references/server.md` |
| 자격증명 저장 · 원격 명령 · 이 맥 sudo | `cred list\|show\|set\|unset` · `ssh` · `local sudo` | `references/credentials.md` |
| 이슈 첨부용 축소 | `shrink` | `references/memory.md` |
| 이 컴퓨터에서 먹힌 방식 꺼내기 · 남기기 · 지우기 | `recall` · `learn` · `forget` | `references/memory.md` |
| 이번 실행 자리 + `env.sh` | `get-output-path` | 아래 |
| 새 플랫폼 · 새 동작 추가(기여자) | — | `references/extending.md` |

## 스크립트 찾기

**Bash 도구는 호출마다 상태가 초기화된다.** 한 번 찾은 뒤 **실제 경로를 이후 블록에 값으로 직접 써넣는다.**
다른 스킬에서 부를 때도 `SKILL=pro-launch` 그대로 쓴다.

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-launch; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
echo "PYTHON=$PYTHON SCRIPTS=$SCRIPTS PROJECT_ROOT=$PROJECT_ROOT"
```

## 산출물 자리 — 먼저 받는다. 경로를 지어내지 않는다 ⚠️

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py get-output-path --title "{무엇을 찍는지}"
#   --skill design-brief   # 부르는 작업 스킬이 자기 폴더에 받고 싶을 때 (증거 스킬만 — 아니면 not_evidence_skill)
#   --package {패키지명}   # env.sh 에 PKG 로 넣는다
```

돌려준 `env_file` 을 **이후 블록 첫 줄에서 source 한다.** `LAUNCH_RUN`(스킬별 `{스킬}_RUN`) · `$RUN_DIR` · `$SHOT_DIR` ·
`$DEV`(역할을 묶었으면 `DEVn` · `ROLEn`) · `$PKG` 가 들어온다. `--skill` 은 `scripts/common/paths.py` 의 `EVIDENCE_SKILLS` 만
받는다 — 문서 스킬 폴더에 캡처를 쌓으면 추적 제외가 없어 커밋된다.

## 공통 규칙

- **기기는 `--device` 로 고른다.** 없으면 `$DEV` → 붙은 기기가 한 대뿐이면 그것. 여러 대인데 안 고르면 `no_device` 로 멈춘다.
- **JSON 하나를 돌려준다.** `ok` 로 성패, `code` 로 갈래(문구가 아니라 code 로 판단), `next` 를 다음 명령 후보로 읽는다.
  요소를 못 찾으면 `candidates`(화면에 실제로 있는 값)와 `locale` 이 온다 — **추측을 반복하지 말고 거기서 고른다.**
- 캡처는 기본 긴 변 1200px WebP. 픽셀 대조처럼 원본이 필요할 때만 `--keep-format`. **찍은 것은 Read 로 열어 본다.**
  텍스트로 확인되면(`web assert` · `app tree` · 로그) 이미지를 읽지 않는다 — 가장 비싼 것이 이미지다.
- **호스트 마우스로 좌표를 누르지 않는다**(`cliclick` · AppleScript · CGEvent) — 사용자 커서를 빼앗는다. 앱은 `app tap`, 웹은 셀렉터.
- **자격증명을 평문으로 다루지 않는다.** 명령줄 `--text` 대신 `--cred`(저장된 것) · `--text-env`(일회용),
  명령 문자열에는 `$CRED_*` 환경변수. 결과·보고·이슈·커밋에 값을 옮기지 않는다. `access` 에는 비밀을 적지 않는다.
- 바꾸는 조작(제출 · 삭제 · 결제 · 발송)은 **로컬만 그냥** 한다. 그 밖은 멈추고 묻는다 (`references/web.md` 안전 계약).
- 캡처를 위해 AI 생성 API 를 부르지 않는다. 상태 관리 방식·프로젝트 구조를 추측하지 않는다.

## 앱 — 이럴 땐 이것

```bash
source "{env_file 값}"
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app launch --device "$DEV" --pkg "$PKG"
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app shot   --device "$DEV" --out 01_로그인 --clean-status
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app tree   --device "$DEV"
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app tap    --device "$DEV" --text "로그인" --shot after_login
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app swipe  --device "$DEV" --dir up --shot list_scrolled
```

- 누를 대상은 **요소로** 찾는다: `--text`(화면 언어 그대로) · `--id`(resource-id · accessibilityIdentifier) · `--desc`(접근성 설명),
  여러 개면 `--index N`(0부터). 문구를 모르면 `app tree` 의 `elements` · `locale` 을 먼저 본다.
- 캔버스·지도처럼 요소가 없을 때만 `--at 0.5,0.8` **비율(0~1)** 좌표. 픽셀은 거절한다(`bad_ratio`).
- 밀기는 `--dir up|down|left|right`, 정확한 궤적이면 `--from 0.5,0.8 --to 0.5,0.2 --ms 300`.
- `--shot 이름` 을 붙이면 화면이 멈춘 뒤 찍어 준다. `screen_changed: false` 면 반응이 없었다 — 다른 요소를 고른다.
- iOS 조작은 Maestro 가 필요하다(호출당 10~40초). 긴 시나리오는 프로젝트의 E2E flow 로 한 번에 돌린다.

| code | 다음 행동 |
|---|---|
| `no_device` | `devices` 로 보고 `--device` 를 준다 |
| `not_found` | `candidates` 에서 고른다 |
| `ios_tool_missing` · `android_tool_missing` · `adb_missing` | 결과의 설치 안내를 사용자에게 제안한다 |
| `non_ascii_unsupported` · `ios_text_unsupported` | `app type` 이 못 넣는다. 영문 대체 또는 사용자에게 맡긴다 |
| `build_mismatch` | 기기마다 설치된 빌드가 다르다. 멈추고 양쪽을 맞춘다 |

## 웹 — 이럴 땐 이것

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web open --url {주소}              # 처음 한 번
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web click --selector "text=로그인"
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web viewport --preset mobile
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web route --match "**/api/items*" --status 200 --body "[]"
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web goto --url {그 화면}            # 규칙은 이동할 때 걸린다
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web shot --out 02_빈목록
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web route --clear
```

- 빈 목록 · 실패 · 로딩은 **서버를 건드리지 않고** `route` 로 연출한다(`--status 500` · `--delay 5000`). 끝나면 `--clear`.
- Google·Apple 로그인이 막히면 먼저 `web open --headed`. 사이트가 이상하면 `--no-stealth` 로 비교한다.
- `playwright_missing` 이면 사용자에게 묻고 `web setup`. `browser_not_open` · `browser_gone` 이면 `web open` 을 다시.
- **처음 웹을 몰기 전에 `references/web.md` 의 안전 계약을 읽는다.**

## render · 서버 · 자격증명 · 기억 — 이럴 땐 이것

- 실기기로 만들기 어려운 상태(빈 목록 · 긴 글자 · 권한 거부)는 `render snapshot` → 임시 렌더 코드 → `render run`.
  `render_failed` 는 `output_tail` 로 고치고, `residue` 는 **네가 만든 것만** 지운다(`references/render.md`).
- 서버에 붙는 법은 코드를 읽어 정하고 `access set` 에 적는다. `http --url /경로` · `db --profile db --sql …` · `logs --tail 100`.
- 서버·DB·로그인 화면을 만지기 전, "사용자가 직접 로그인해야 한다"고 말하기 전에 **`cred list` 를 먼저 본다.**
  `use_when` 이 맞는 것만 쓰고, 새 정보는 저장해도 되는지 묻고 `cred set`. 원격은 `ssh --cred 이름 --command '…'`,
  이 맥 관리자 권한은 `local sudo --cred 이름 -- <명령>`(첫 등록은 사용자가 `cred set --prompt` 로 직접). 상세는 `references/credentials.md`.
- 앱·웹 작업 시작 때 `recall --area ios|android|web|server` 를 한 번, 끝나면 먹힌 방식을 `learn --result ok|fail`.
  비밀값과 호스트 마우스 방식은 저장되지 않는다. 캡처는 이슈에 붙이기 전에 `shrink`. 상세는 `references/memory.md`.
