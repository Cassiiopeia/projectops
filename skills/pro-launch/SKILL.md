---
name: pro-launch
description: "앱·웹·서버를 띄우고, 조작하고, 찍는 능력 스킬이다. Android 에뮬레이터·iOS 시뮬레이터 화면을 찍고(상태바 고정 포함) 앱을 띄우며, 브라우저를 열어 이동·클릭·입력·캡처하고, 폭을 바꾸거나 API 응답을 바꿔치기해 빈 목록·실패·로딩 상태를 서버를 건드리지 않고 연출한다. 자동화 표식을 가려 Google·Apple 로그인 화면이 자동화 브라우저를 막는 것을 줄인다. 단건 HTTP 요청·DB 조회·서버 로그도 적어 둔 접속 방법대로 실행한다. 무엇을 왜 찍을지는 정하지 않는다 — 그건 부르는 작업 스킬(pro-agent-test · pro-design-brief · pro-figma-verify)의 일이다. '에뮬레이터 띄워서 찍어줘', '시뮬레이터 스크린샷', '브라우저로 이 화면 캡처해줘', '모바일 폭으로 찍어줘', '빈 목록 화면 찍어줘', '500 났을 때 화면 보여줘', '이 API 한 번 불러줘' 같은 요청에 사용한다. 버그를 찾으며 끝까지 밟는 QA 는 pro-agent-test 다."
---

# pro-launch — 띄우고, 조작하고, 찍는다

**능력 스킬이다. 절차를 강요하지 않는다.** 무엇을 부르면 무엇이 나오는지와 함정만 적는다.
무엇을 찍을지, 왜 찍을지는 부르는 쪽이 정한다.

```
작업 스킬   pro-agent-test · pro-design-brief · pro-figma-verify · pro-report
              │ (스크립트로 부른다 — Skill 호출이 아니다)
능력 스킬   pro-launch · pro-github · pro-ssh
```

원칙: **판단은 agent, 스크립트는 실행과 기록만 한다.** 스크립트는 프로젝트 구조를
알아맞히지 않는다(라우트·화면 목록을 스캔하지 않는다). 코드는 네가 읽는다.

## 시작 전

`../references/common-rules.md`의 **절대 규칙** 적용 (Git 커밋 금지, 민감 정보 보호).

인자: $ARGUMENTS

## 스크립트 찾기

**Bash 도구는 호출마다 상태가 초기화된다.** 아래 블록으로 `SCRIPTS`를 한 번 찾은 뒤
**그 실제 경로를 기억해 두고 이후 모든 블록에 값으로 직접 써넣는다.**

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

다른 스킬에서 부를 때도 이 블록을 `SKILL=pro-launch` 그대로 쓴다.

## 산출물 자리 — 먼저 받는다. 경로를 지어내지 않는다 ⚠️

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py get-output-path --title "{무엇을 찍는지}"
#   --skill design-brief   # 부르는 작업 스킬이 자기 폴더에 받고 싶을 때
#   --package {패키지명}   # env.sh 에 PKG 로 넣는다
```

돌려준 `env_file` 을 **이후 블록 첫 줄에서 source 한다.** `$RUN_DIR`·`$SHOT_DIR`·`$DEV`·`$PKG` 가 들어온다.
`--skill` 은 **증거 스킬로 등록된 것만** 받는다(`scripts/common/paths.py` 의 `EVIDENCE_SKILLS`) —
문서 스킬 폴더에 캡처를 쌓으면 추적 제외가 없어 커밋된다.

| 변수 | 무엇 |
|---|---|
| `LAUNCH_RUN` (스킬별 `{스킬}_RUN`) | 이번 실행 이름 |
| `RUN_DIR` · `SHOT_DIR` | 실행 폴더 · 캡처 폴더 |
| `DEV` · `DEVn` · `ROLEn` | 기기 (역할을 묶었으면 번호별) |
| `PKG` | 앱 패키지명 |

## 명령 한눈에

모두 JSON 을 돌려준다. `ok`·`code`·`summary`·`next`를 보고 다음 수를 정한다.

| 명령 | 하는 일 |
|---|---|
| `doctor` | 도구(adb · simctl · Chromium · Pillow · cwebp · ffmpeg) 설치 여부 · 저장 위치 |
| `detect --path` | 무엇을 띄울 수 있는지(app · web · server) · 패키지명 · 번들 ID · 기기 · 브라우저 준비 |
| `devices` | 붙은 기기 · 부팅된 시뮬레이터 · AVD |
| `device list\|bind\|unbind\|show` | 역할을 기기에 묶는다 — 참가자가 둘 이상일 때 |
| `app shot` · `app launch` | 앱 화면을 찍는다 · 앱을 띄운다 |
| `web setup\|open\|goto\|click\|type\|shot\|assert\|console\|close` | 브라우저 조작 |
| `web viewport` · `web route` | 폭 바꾸기 · 응답 바꿔치기(빈 목록 · 500 · 지연) |
| `http` | 단건 HTTP 요청 |
| `access show\|set\|unset` · `db` · `logs` | 서버에 붙는 법 기록 · SQL · 로그 |
| `shrink` | 이슈 첨부용 축소 · WebP |
| `get-output-path` | 이번 실행 자리 + `env.sh` |

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py doctor
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py detect --path {PROJECT_ROOT}
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py devices
```

## 앱 — 찍고 띄운다

```bash
source "{env_file 값}"
{PYTHON} {SCRIPTS}/launch_cli.py app launch --device "$DEV" --pkg "$PKG"
{PYTHON} {SCRIPTS}/launch_cli.py app shot --device "$DEV" --out 01_로그인 --clean-status
```

- `--device` 는 Android 시리얼이나 iOS UDID. 없으면 `$DEV` → 붙은 기기가 한 대뿐이면 그것.
  **여러 대인데 안 고르면 `no_device` 로 멈춘다** — 엉뚱한 기기를 찍지 않게 하려는 것이다.
- `--clean-status` 는 상태바를 9:41 · 배터리 100% 로 고정해 찍고 **찍은 뒤 되돌린다**
  (iOS `simctl status_bar`, Android 데모 모드 + 허용 설정 원복). 캡처끼리 시각이 달라 보이지 않게 한다.
- 기본은 긴 변 1200px WebP 다. **픽셀 대조처럼 원본이 필요하면** `--keep-format`
  (또는 `--out` 에 경로를 직접 주면 그대로 저장한다).
- 탭·스와이프는 감싸지 않는다 — `adb -s "$DEV" shell input tap x y` 를 직접 쓴다.
  붙는 법·함정은 `references/app.md`.

## 웹 — 브라우저를 몬다

```bash
{PYTHON} {SCRIPTS}/launch_cli.py web open --url {주소}        # 처음 한 번
{PYTHON} {SCRIPTS}/launch_cli.py web shot --out 01_홈
{PYTHON} {SCRIPTS}/launch_cli.py web click --selector "text=로그인"
{PYTHON} {SCRIPTS}/launch_cli.py web console                  # 로드 중 오류까지
{PYTHON} {SCRIPTS}/launch_cli.py web close
```

**상태를 연출한다 — 서버를 건드리지 않는다.**

```bash
{PYTHON} {SCRIPTS}/launch_cli.py web viewport --preset mobile          # tablet · desktop · 390x844
{PYTHON} {SCRIPTS}/launch_cli.py web route --match "**/api/items*" --status 200 --body "[]"
{PYTHON} {SCRIPTS}/launch_cli.py web goto --url {그 화면}              # 규칙은 이동할 때 걸린다
{PYTHON} {SCRIPTS}/launch_cli.py web shot --out 02_빈목록
{PYTHON} {SCRIPTS}/launch_cli.py web route --match "**/api/items*" --status 500 --body '{"error":"x"}'
{PYTHON} {SCRIPTS}/launch_cli.py web route --match "**/api/items*" --delay 5000   # 로딩 상태
{PYTHON} {SCRIPTS}/launch_cli.py web route --clear
```

- **Google·Apple 로그인이 막히면 먼저 `web open --headed`** 다(#604 실측 — 통과를 가른 것은
  headed 여부였다). 기본으로 자동화 표식 가리기(stealth)가 켜져 있어 headless 에서도 덜 막힌다.
  사이트가 이상하게 굴면 `--no-stealth` 로 비교한다.
- 요소 하나만 찍으려면 `web shot --selector "#card"`.
- 안전 계약(바꾸는 조작은 로컬만 · 자격증명은 사용자에게)과 함정은 `references/web.md`. **반드시 읽는다.**

## 서버 — 요청 · DB · 로그

```bash
{PYTHON} {SCRIPTS}/launch_cli.py http --url /api/health --expect-status 200
{PYTHON} {SCRIPTS}/launch_cli.py http --method POST --url /api/items --data '{"name":"x"}' \
  --header "Authorization: Bearer $TOKEN" --save create.json
{PYTHON} {SCRIPTS}/launch_cli.py access set --key base_url --json '{"url":"http://localhost:8080"}'
{PYTHON} {SCRIPTS}/launch_cli.py access show
{PYTHON} {SCRIPTS}/launch_cli.py db --profile db --sql "select count(*) from item"
{PYTHON} {SCRIPTS}/launch_cli.py logs --tail 100 --grep ERROR
```

접속 방법은 **네가 코드를 읽어 정하고 `access` 에 적는다.** 비밀번호는 값이 아니라
`password_env` 로 어디서 읽을지만 적는다(값을 적으면 거절한다). 자세한 것은 `references/server.md`.

## 줄이기

```bash
{PYTHON} {SCRIPTS}/launch_cli.py shrink "$SHOT_DIR"/*.png           # 긴 변 1200 + WebP
```

파일 크기는 WebP 가, 세션 토큰은 해상도가 줄인다. 둘을 함께 해야 한다.

## 저장 위치

| 자리 | 담는 것 |
|---|---|
| `~/.projectops/launch/<owner__repo>/` | devices.json · browser.json · access.json · `.browser-profile/` · `shots/` |
| `~/.projectops/launch/.venv` | Playwright · Pillow (옛 `agent-test/.venv` 가 있으면 그것을 쓴다) |

예전에는 `~/.projectops/agent-test/` 에 섞여 있었다. 처음 부를 때 launch 몫을 옮기고
결과에 `migrated` 로 알린다. 두 번째부터는 아무 일도 없다. 브라우저가 떠 있으면 브라우저
관련은 닫은 뒤로 미룬다.

## 하지 않는 것

- 프로젝트 구조 추측 — 무엇을 찍을지는 agent 가 코드를 읽고 정한다
- 캡처를 위한 AI 생성 API 호출 — 가짜 데이터로 채운다(돈이 든다)
- 탭·스와이프 추상화 — `adb shell input` 을 직접 쓴다
