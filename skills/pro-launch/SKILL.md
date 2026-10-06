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
| `app shot` · `app launch` · `app type` | 앱 화면을 찍는다 · 앱을 띄운다 · **글자를 넣는다**(Android, 저장된 로그인 정보) |
| `web setup\|open\|goto\|click\|type\|shot\|assert\|console\|close` | 브라우저 조작 |
| `web viewport` · `web route` | 폭 바꾸기 · 응답 바꿔치기(빈 목록 · 500 · 지연) |
| `render snapshot` · `render run` | 코드로 상태를 그려 찍는다 — 실행 · 수집 · 청소 · **흔적 검사** |
| `http` | 단건 HTTP 요청 |
| `access show\|set\|unset` · `db` · `logs` | 서버에 붙는 법 기록 · SQL · 로그 |
| `cred list\|show\|set\|unset` · `ssh` | **이름 붙은 자격증명 저장**(다음 실행에서 다시 묻지 않는다) · 저장된 서버로 원격 명령 |
| `shrink` | 이슈 첨부용 축소 · WebP |
| `recall` · `learn` · `forget` | **이 컴퓨터에서 먹힌 조작 방식**을 꺼낸다 · 남긴다 · 지운다 |
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
  **iOS 시뮬레이터는 좌표로 누르지 않는다** (`cliclick` · AppleScript 금지) — 프로젝트의 E2E(Maestro 등)를 쓴다.
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
- 안전 계약(바꾸는 조작은 로컬만 · 로그인 정보는 저장된 것을 `--cred` 로, 새로 받으면 **저장해도 되는지 묻고** 저장)과 함정은 `references/web.md`. **반드시 읽는다.**

## 코드로 상태를 그려 찍는다 — render

실기기로 만들기 어려운 상태(빈 목록 · 실패 · 긴 글자 · 권한 거부)는 **코드로 그려서** 찍는다.
렌더 코드는 네가 `references/render.md` 의 스택별 레시피를 보고 대상 레포에 **임시로** 짠다.
스크립트는 실행 · 수집 · 청소 · 흔적 검사만 한다.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py render snapshot --root {대상 레포}     # ① 임시 파일을 만들기 **전에**
#   ② 임시 렌더 코드를 전용 폴더에 만든다 (예: client/test/_launch_render/)
{PYTHON} {SCRIPTS}/launch_cli.py render run --root {대상 레포} --cwd client \
  --cmd "flutter test test/_launch_render --update-goldens" \
  --collect "client/test/_launch_render/shots/*.png" --cleanup client/test/_launch_render
```

- 실패하면 **수집하지 않고 청소만** 한 뒤 `render_failed` 와 출력 끝 40줄을 준다.
- 끝난 뒤 레포에 처음에 없던 것이 남으면 `residue` 로 알린다. **지우지 않는다** — 다른 세션의
  변경일 수 있다. 네가 만든 것이면 네가 지운다.
- 캡처를 위해 AI 생성 API 를 부르지 않는다. 골든 기준 폴더에 쓰지 않는다.

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

접속 방법은 **네가 코드를 읽어 정하고 `access` 에 적는다.** `access.json` 에는 비밀을 적지 않는다
(값을 적으면 거절한다). 비밀은 아래 **자격증명 저장소**에 두고 `access` 에는 `{"cred":"이름"}` 만 적는다.
자세한 것은 `references/server.md`.

### 자격증명 — 한 번 저장하면 다음 실행에서 다시 묻지 않는다

`pro-ssh` · `pro-github` 가 `~/.projectops/config/config.json` 에 서버·PAT 를 두고 쓰는 것과 같은 방식이다.
`launch.credentials` 에 **이름 붙여** 값까지 저장하고(파일은 600), 목록·조회에서는 값이 `<저장됨>` 으로 가려진다.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py cred list                     # 작업 시작 때 한 번 — 무엇을 쓸 수 있나
{PYTHON} {SCRIPTS}/launch_cli.py cred show --name synology     # 값은 가려서 보여 준다
{PYTHON} {SCRIPTS}/launch_cli.py cred set --name synology --json '{"kind":"ssh","ssh_server":"synology-nas",
  "use_when":"서버 배포 QA","scope":"test-only","notes":"운영 컨테이너가 있으니 pops-qa- 접두사만"}'
{PYTHON} {SCRIPTS}/launch_cli.py ssh --cred synology --sudo --command 'SUDO docker ps'   # 비밀번호 sudo 도 된다
{PYTHON} {SCRIPTS}/launch_cli.py logs --cred synology --command 'sshpass -e ssh -p $CRED_PORT $CRED_USER@$CRED_HOST "docker logs --tail 100 app"'
{PYTHON} {SCRIPTS}/launch_cli.py db --cred pg --sql "select 1"   # host·user·password 를 채운다
{PYTHON} {SCRIPTS}/launch_cli.py http --cred api --url /me        # token 이면 Authorization: Bearer
```

| 항목 | 의미 |
|---|---|
| `kind` | `ssh` · `dockerhub` · `db` · `http` · `github-org` · `local` · `other` |
| `ssh_server` | `pro-ssh` 에 등록된 서버 이름. 있으면 host·port·user·password 를 거기서 가져온다 — **비밀번호는 한 곳에만** 둔다 |
| `use_when` | 이 자격증명을 **언제 써도 되는지**(근거). 사용자가 허용한 범위를 그대로 적는다 |
| 로그인 계정 | `kind: login` + `provider`(google · apple · naver · kakao · custom) · `surface` · `app` · `account` · `password` · `two_factor` — 소셜·앱 로그인과 개발자 콘솔 로그인. 화면에는 `web type --cred` · `app type --cred` 로 넣는다 |
| 이 맥 sudo | `kind: local` + `sudo_password` — **이 맥**에서 관리자 권한(`sudo installer -pkg …` 등)이 필요할 때. `local sudo --cred 이름 -- <명령>` 으로 쓴다 (아래) |
| `scope` | `test-only` · `test-ok` · `readonly` … 허용 범위 |
| `notes` | 지켜야 할 이름 규칙·포트 범위·서버에 있는 운영 서비스 등 알아둘 것 |

#### 이 맥의 sudo 비밀번호 (#784)

로컬 맥에서 관리자 권한이 필요한 작업(예: `sudo installer -pkg … -target /`)을 만나면, **"비밀번호는 못 넣는다"며 멈추지 말고** 저장된 자격증명부터 찾는다.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py cred list                      # kind 가 local 인 것이 있나
{PYTHON} {SCRIPTS}/launch_cli.py local sudo --cred mac -- installer -pkg /path/x.pkg -target /
```

- **첫 등록은 사용자가 터미널에서 직접 한다.** 입력은 화면에 보이지 않고, 비밀번호가 채팅·세션 기록에 들어가지 않는다.
  `! {PYTHON} {SCRIPTS}/launch_cli.py cred set --name mac --prompt` (Claude Code 에서는 `!` 접두사). `!` 로 TTY 를 못 받으면
  별도 터미널 창에서 같은 명령을 친다. 파이프·채팅으로는 받지 않는다(`no_tty` 로 거절).
- 비밀번호는 `sudo -S` 표준입력으로만 넘긴다. 명령줄·응답·로그에는 남지 않고 출력의 같은 문자열은 `***` 로 가려진다.
- `kind: local` 만 쓴다. 서버 ssh 비밀번호로 이 맥에 sudo 를 시도하지 않는다(`cred_not_local`).
- **시스템을 바꾸는 명령이다.** 실행 전에 무슨 명령인지 한 줄로 말한다. 한 번 저장했다고 아무 명령이나 돌리지 않고, `use_when` 범위 안에서 쓴다.
- 저장은 로컬 파일(`config.json`, 권한 600) 평문이다. 로컬 전용이라는 사용자 방침을 따랐고, 맥 로그인 비밀번호라는 점이 서버 키보다 민감하다는 것은 사용자가 알고 있다.
- ⚠️ **Claude Code 의 권한 분류기가 "저장된 비밀번호로 sudo" 호출을 거부할 수 있다.** 이 스킬로 우회할 수 없고 권한 설정을 바꾸지도 않는다.
  거부되면 그 사실과 사용자가 직접 칠 명령 한 줄을 알려 준다.

**agent 판단 규칙**
- 서버·DB·레지스트리를 만지기 전에 `cred list` 를 보고 **`use_when` 이 지금 하려는 일에 맞는 것만** 쓴다.
  맞는 것이 없으면 추측해서 다른 것을 쓰지 말고 사용자에게 묻는다.
- **"로그인이 필요해서 사용자가 직접 해야 한다"고 말하기 전에 `cred list` 를 먼저 본다.** 개발자 콘솔(Apple
  Developer 등)·소셜 로그인 계정이 `kind: login` 으로 저장돼 있을 수 있다. `use_when` 이 맞으면 "할 수 없다"가 아니라
  "저장된 계정으로 시도하겠다"고 제안한다. 인증서·프로필·Secret 처럼 **외부 상태를 바꾸는 실행은 무엇이 바뀌는지
  말하고 승인받은 뒤** 한다. 2FA 처럼 사람만 할 수 있는 지점만 따로 떼어 요청한다.
- `scope` · `notes` 를 읽고 그 안에서만 움직인다(예: 테스트 이름 접두사, 지우는 것은 내가 만든 것만).
- 사용자가 새 접속 정보를 주면 **저장해도 되는지 한 번 묻고**, 허락하면 `cred set` 으로 저장해 `use_when` · `scope` · `notes` 를
  사용자 말 그대로 채운다. 다음에 다시 묻지 않는 것이 목적이다. 거절하면 그 실행에만 쓰고 저장하지 않는다.
  (사용자가 "알아서 저장해 둬" 처럼 미리 허락한 범위 안에서는 묻지 않고 저장한다.)
- 저장된 정보가 **틀렸거나 바뀌어 보이면**(로그인 실패·접속 거부) 다시 시도하거나 덮어쓰기 전에 사용자에게 먼저 묻는다. 로그인은 자동 재시도하지 않는다.
- 접속·로그인이 **통과한 방식**(어느 브라우저 모드, 어느 순서)은 `learn` 으로 남긴다 — 값은 적지 않는다. 다음 `recall` 이 꺼내 준다.
- 결과·보고·이슈·커밋에 값을 옮기지 않는다. `cred show --reveal` 은 정말 필요할 때만.
- 명령 문자열에는 비밀을 적지 않고 `$CRED_HOST` · `$CRED_USER` · `$CRED_PASSWORD` · `$CRED_TOKEN` · `$SSHPASS` 환경변수를 쓴다.
  출력에 값이 섞이면 `***` 로 가려진다.

## 줄이기

```bash
{PYTHON} {SCRIPTS}/launch_cli.py shrink "$SHOT_DIR"/*.png           # 긴 변 1200 + WebP
```

파일 크기는 WebP 가, 세션 토큰은 해상도가 줄인다. 둘을 함께 해야 한다.

## 이 컴퓨터에서 먹힌 방식을 기억한다 (쓸수록 정확해진다)

사람마다 컴퓨터마다 잘 되는 방식이 다르다(iOS 는 Maestro 가 깔린 곳에서만, Google 로그인은 `--headed` 여야 하는 곳 등).
같은 실패를 반복하지 않고 토큰을 아끼려고 **먹힌 방식을 홈에 적어 둔다.**

1. **앱·웹 작업을 시작할 때 `recall` 을 한 번 부른다.** 상위 5건, 항목당 200자 이내라 짧다.
   `verify:true` 는 실패가 앞서거나 오래된 것이니 **한 번 확인하고** 쓴다.
2. **끝나면 `learn` 으로 결과만 남긴다** — 처음 알게 된 방식이거나, 기억이 맞았는지/틀렸는지.
   맞았으면 `--result ok`, 틀렸으면 `--result fail`. 쌓일수록 순서가 정확해진다.
3. 잘못 배운 것은 `forget`.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py recall --area ios
{PYTHON} {SCRIPTS}/launch_cli.py learn --area ios --key ios.tap \
    --how "client/tool/e2e_shot.sh (Maestro) 로 위젯 텍스트를 누른다" --result ok
# 이 컴퓨터 전체에 해당하면 --scope machine (기본은 이 레포)
```

- **안전 규칙이 기억보다 위다.** 호스트 마우스로 좌표를 누르는 방법(`cliclick` 등)은 저장도, 꺼내기도 막힌다.
- 비밀번호·토큰·이메일 같은 비밀값은 저장을 거절한다.
- **앱 화면·좌표·함정은 여기가 아니다** — `pro-agent-test` 의 `note` 가 맡는다. 여기는 **도구·방식**만.
- 설명이 필요한 긴 사례(왜 막혔고 어떻게 풀었나)는 `pro-note` 로 남긴다. 여기에는 결론만.

## 토큰을 아낀다

- 화면 이미지를 읽는 것이 가장 비싸다. **텍스트로 확인되면(`assert` · 로그 · E2E 의 assertVisible) 스크린샷을 읽지 않는다.**
- 한 번 만든 E2E 플로우는 경로를 `learn` 으로 남겨 다시 짜지 않는다.
- 캡처는 기본 축소본(긴 변 1200px WebP)을 쓰고, 원본은 픽셀 대조처럼 꼭 필요할 때만.

## 저장 위치

| 자리 | 담는 것 |
|---|---|
| `~/.projectops/launch/<owner__repo>/` | devices.json · browser.json · access.json(**비밀 없음**) · knowledge.json · `.browser-profile/` · `shots/` |
| `~/.projectops/config/config.json` → `launch.credentials` | **자격증명**(값 포함, 파일 600). `pro-ssh`·`pro-github` 와 같은 파일 |
| `~/.projectops/launch/_machine/` | knowledge.json — 이 컴퓨터 전체에 해당하는 방식 |
| `~/.projectops/launch/.venv` | Playwright · Pillow (옛 `agent-test/.venv` 가 있으면 그것을 쓴다) |

예전에는 `~/.projectops/agent-test/` 에 섞여 있었다. 처음 부를 때 launch 몫을 옮기고
결과에 `migrated` 로 알린다. 두 번째부터는 아무 일도 없다. 브라우저가 떠 있으면 브라우저
관련은 닫은 뒤로 미룬다.

## 하지 않는 것

- 프로젝트 구조 추측 — 무엇을 찍을지는 agent 가 코드를 읽고 정한다
- 캡처를 위한 AI 생성 API 호출 — 가짜 데이터로 채운다(돈이 든다)
- 탭·스와이프 추상화 — `adb shell input` 을 직접 쓴다
- 상태 관리 방식 추측 — render 의 가짜 값 주입은 레시피를 보고 네가 짠다
