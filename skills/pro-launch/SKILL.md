---
name: pro-launch
description: "Capability skill that launches and drives apps, web and servers: emulator/simulator screenshots, browser navigation and capture, API mocking for empty/error states, HTTP/DB/log access. Used by pro-agent-test, pro-design-brief, pro-figma."
---

# pro-launch — 띄우고, 조작하고, 찍는다

## When to use

- '에뮬레이터 띄워서 찍어줘', '시뮬레이터 스크린샷', '브라우저로 이 화면 캡처해줘', '모바일 폭으로 찍어줘'
- '빈 목록 화면 찍어줘', '500 났을 때 화면 보여줘', '이 API 한 번 불러줘'
- 무엇을 왜 찍을지는 정하지 않는다 — 그건 부르는 작업 스킬(pro-agent-test · pro-design-brief · pro-figma)의 일이다.
- 버그를 찾으며 끝까지 밟는 QA 는 pro-agent-test 다. Google·Apple 로그인 화면은 자동화 표식을 가려 차단을 줄인다.

**능력 스킬이다.** 무엇을 부르면 무엇이 나오는지만 적는다. 무엇을 왜 찍을지는 부르는 작업 스킬
(pro-agent-test · pro-design-brief · pro-figma · pro-report)이 정하고, 이 스크립트를 **Skill 호출이 아니라 스크립트로** 부른다(같은 층의 능력 스킬: pro-github · pro-ssh).
판단은 agent, 스크립트는 실행과 기록만 한다 — 라우트·화면 목록을 스캔해 프로젝트 구조를 알아맞히지 않는다.

`../references/common-rules.md` 의 **절대 규칙** 적용 (Git 커밋 금지, 민감 정보 보호). 인자: $ARGUMENTS

## 무엇을 하려는가 → 명령 → 자세한 문서

모든 명령은 `{PYTHON} {SCRIPTS}/launch_cli.py <명령>` 이다. **레포 밖(셸 작업 폴더가 바뀐 뒤)에서 부르면 `--root <프로젝트>`를 붙인다** —
없으면 `$PROJECT_ROOT` > 작업 폴더(git) > 최근에 쓴 루트 순으로 찾고, 실패 응답에 `root_candidates`·`retry` 가 온다 (#885).

| 하려는 것 | 명령 | 자세히 |
|---|---|---|
| 도구(adb · simctl · Chromium · Pillow · cwebp · ffmpeg) · 무엇을 띄울 수 있나(app · web · server, 패키지명 · 번들 ID) · 붙은 기기 · 부팅된 시뮬레이터 · AVD | `doctor` · `detect --path .` · `devices` | — |
| 호스트 메모리 압박(ok·high·critical) · 큰 프로세스 · 켜진 기기를 묶은 레포 — **가상 기기를 더 띄우기 전에** | `doctor --resources` | 아래 공통 규칙 |
| 참가자가 둘 이상 — 역할을 기기에 묶기 · 남이 쓰는 기기 표시 | `device list\|bind\|unbind\|show\|claim\|release` | `references/app.md` |
| 에뮬레이터·시뮬레이터 띄우기(기본 창 없음, 창이 필요하면 작게) · 재부팅 · 언어 · 다크 모드 — **raw simctl/emulator 대신** | `device boot\|reboot [--cold]\|locale\|appearance\|text-size` · `app install --path` | `references/app.md` |
| 앱 띄우기 · 찍기 | `app launch` · `app shot [--clean-status]` | `references/app.md` |
| 앱 화면 구조 · 누르기 · 밀기 | `app tree` · `app tap` · `app swipe` | `references/app.md` |
| 앱 여러 단계 한 번에 (iOS 는 Maestro 1회) | `app run --steps steps.json` | `references/app.md` |
| 복잡한 제스처(밀고 곧바로 탭 · 요소에서 밀기) — 프로젝트 Maestro flow 실행 + 캡처 | `app flow --file x.yaml` | `references/app.md` 제스처 플레이북 |
| iOS 를 여러 번 보고 누를 때 — 상주 세션 (호출당 20초 > 1초) | `app session start\|stop\|status` | `references/app.md` |
| 앱에 글자 넣기(저장된 로그인, iOS 는 Maestro) | `app type --cred 이름` | `references/app.md` |
| 화면이 바뀔 때까지(사라질 때까지) 기다리기 · 화면 녹화 · 동작 직후 연속 캡처 | `app wait [--gone]` · `app record start\|stop` · `--burst` | `references/app.md` |
| 앱 끄기 · 다시 띄우기 · 위치 · 권한 · 푸시(iOS) · 딥링크 — **raw simctl/adb 대신** | `app terminate\|relaunch\|location\|permission\|push\|openurl` | `references/app.md` |
| 브라우저 열기 · **화면 읽기 · 누를 것 고르기** · 확인하며 클릭 · 입력 · 캡처 | `web setup\|open\|goto\|text\|find\|click\|type\|shot\|assert\|console\|close` | `references/web.md` |
| 폭 바꾸기 · 응답 바꿔치기(빈 목록 · 500 · 지연) | `web viewport` · `web route` | `references/web.md` |
| **폼 읽기**(입력·버튼·체크·선택 + 값·비활성·ref) · 줄만 골라 읽기 · 고르기 · 체크 · 키 · 올리기 · 대화상자 · 내려받기 — **raw CDP 스크립트 대신** | `web inspect` · `web text --grep` · `web select\|check\|press\|hover\|dialog\|download` | `references/web.md` |
| 조건 기다리기(승인·토스트·주소) · 안쪽 상자 스크롤·조각 캡처 · 파일 올리기 · iframe 안 조작 · **고정 동작에 없는 일** | `web wait\|scroll\|upload` · `web shot --container` · `--frame` · `web script` | `references/web.md` |
| 저장이 갔는지 요청으로 확인 · 입력칸·복사 버튼의 비밀값을 출력 없이 저장 · 키를 하나씩 입력 · 남은 브라우저 정리 | `--capture-requests` · `web value\|clipboard --save-env` · `web type --keys` · `web close --stale` | `references/web.md` |
| 코드로 상태를 그려 찍기 | `render snapshot` → `render run` | `references/render.md` |
| 단건 HTTP · 붙는 법 기록 · SQL · 로그 | `http` · `access show\|set\|unset` · `db` · `logs` | `references/server.md` |
| 자격증명 저장 · 원격 명령 · 이 맥 sudo | `cred list\|show\|set\|unset\|import-ssh` · `ssh` · `local sudo` | `references/credentials.md` |
| 로그인 중간 화면(기기 신뢰 · 로그인 유지 · 권유) 정책 | `cred policy get\|set\|unset` | `references/web.md` "로그인 중간 화면" |
| 이슈 첨부용 축소 | `shrink` | `references/memory.md` |
| 이 컴퓨터에서 먹힌 방식 꺼내기 · 남기기 · 지우기 · 정리 | `recall [--match 낱말]` · `learn [--detail]` · `forget` · `tidy` (흩어진 기억) · `tidy --buckets` (용량·가짜 버킷, `--apply` 때만 삭제) | `references/memory.md` |
| 작업을 마칠 때 — 막혔다 풀렸는데 learn 안 한 영역 | `session-check` | `references/memory.md` |
| 공식 트러블슈팅 찾기 · 보기 · 목록 · 내 기억에서 공식 항목 초안 | `kb search\|show\|list\|propose` | `references/troubleshooting.md` · `references/memory.md` |
| 했던 작업을 자유롭게 적어 두고 다음에 다시 읽기 (작업 일지) | `journal [--add "..."] [--title] [--site]` | `references/memory.md` |
| 이번 실행 자리 + `env.sh` | `get-output-path` | 아래 |
| 새 플랫폼 · 새 동작 추가(기여자) | — | `references/extending.md` |

## 스크립트 찾기

**Bash 도구는 호출마다 상태가 초기화된다.** 한 번 찾은 뒤 **실제 경로를 이후 블록에 값으로 직접 써넣는다.**
다른 스킬에서 부를 때도 `SKILL=pro-launch` 그대로 쓴다.

**고정 진입점이 있으면 그것을 쓴다** (#897) — 버전 폴더(`.../projectops/4.xx.x/...`)를 박아 쓰면 세션 중 문서와
스크립트 버전이 어긋난다. `~/.projectops/bin/launch_cli.py` 는 한 번이라도 실행하면 생기고, 부를 때마다 가장
새 설치본(체크아웃 > 플러그인 캐시 최고 버전 > Cursor)을 찾아 인자를 그대로 넘긴다. 특정 폴더를 강제하려면 `PROJECTOPS_LAUNCH_SCRIPTS`.

```bash
E="${PROJECTOPS_HOME:-$HOME/.projectops}/bin/launch_cli.py"; [ -f "$E" ] && echo "SCRIPTS 대신: {PYTHON} $E <명령>"
```

- **zsh 에서 `L="python3 …/launch_cli.py"; $L web …` 처럼 명령을 변수에 담지 않는다** — 한 단어로 취급돼 `no such file` 이 난다. 고정 진입점은 실행 권한이 있어 `"$E" <명령>` 으로 바로 부르거나,
  `launch() { python3 "$HOME/.projectops/bin/launch_cli.py" "$@"; }` 함수로 감싼다. 버전이 박힌 캐시 경로를 붙여 넣지 않는다.
- 응답에 **`newer_installed`** 가 있으면 더 새 버전이 깔려 있다(JSON 안에 있고 성공 응답에도 온다) — 안내된 `use` 명령으로 바꿔 부른다.
  `doctor` 의 `docs_dir` 이 지금 읽는 SKILL.md 폴더와 다르면 문서가 옛 버전이다.

없으면(첫 실행) 아래로 찾는다.

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
- **실패 응답에 `known_fix` 가 오면 그 해결부터 시도한다** — 검증된 공식 지식의 요약(최대 2건)이다. 전체 증상·원인은
  `kb show <id>`, 응답에 없을 때 직접 찾기는 `kb search "<오류 문구>" --code <code>`.
- **결과를 `head`·`cut`·python 으로 자르지 않는다** — `next`·`memory`·`known_fix` 가 같이 잘려 나간다.
  짧게 받으려면 어느 명령에든 `--brief`(ok·code·summary·next·error·known_fix·memory·learn_hint 만),
  특정 키만 원하면 `--fields path,url` 을 붙인다. 둘 다 그 안내 키들은 항상 남긴다. 키 순서는 언제나
  `ok`·`code`·`summary`·`next` → `known_fix`·`memory` → 나머지다.
- **`bad_args` 면 `unknown`·`did_you_mean`·`valid_options`·`example` 을 읽고 고친다** — 짐작으로 다시 부르지 않는다.
  `empty_values` 가 오면 그 옵션 값이 비었다(`$VAR` 미설정).
- **`pressure: critical`(doctor --resources · devices 의 `resources`)이면 가상 기기를 새로 띄우기 전에 사용자에게 묻는다.**
  다른 세션의 에뮬레이터·시뮬레이터·프로세스는 끄지 않는다 — `bound_by` 로 누가 쓰는지 보고만 한다.
- 캡처는 기본 긴 변 1200px WebP. 픽셀 대조처럼 원본이 필요할 때만 `--keep-format`. **찍은 것은 Read 로 열어 본다.**
  텍스트로 확인되면(`web assert` · `app tree` · 로그) 이미지를 읽지 않는다 — 가장 비싼 것이 이미지다.
- **호스트 마우스로 좌표를 누르지 않는다**(`cliclick` · AppleScript · CGEvent) — 사용자 커서를 빼앗는다. 앱은 `app tap`, 웹은 `web find` → `web click --ref`.
- **자격증명을 평문으로 다루지 않는다.** 명령줄 `--text` 대신 `--cred`(저장된 것) · `--text-env`(일회용),
  명령 문자열에는 `$CRED_*` 환경변수. 결과·보고·이슈·커밋에 값을 옮기지 않는다. `access` 에는 비밀을 적지 않는다.
- 바꾸는 조작(제출 · 삭제 · 결제 · 발송)은 **로컬만 그냥** 한다. 그 밖은 멈추고 묻는다 (`references/web.md` 안전 계약).
- 캡처를 위해 AI 생성 API 를 부르지 않는다. 상태 관리 방식·프로젝트 구조를 추측하지 않는다.
- **막히면 직접 만들기 전에 이 순서로 간다** (#934): 해당 동작의 `--help` > `kb search` > `web script`(웹) · `app flow`(앱).
  raw Playwright·CDP 스크립트, `adb`·`simctl`·`maestro` 직접 호출, 대기 루프를 새로 짜지 않는다 — 같은 연결·시간 상한·비밀값 가림을 거치지 않는다.
  **사용자 계정에 쓰는 우회**(Apps Script 같은 스크립트 프로젝트 만들기, API 직접 호출)는 먼저 묻는다.
- **자격증명을 config 파일에서 직접 읽지 않는다** — 저장된 값은 `--cred` 로만 쓴다. 다른 에이전트에게 일을 맡길 때 raw Maestro·simctl·adb 를 쓰라고 지시하지 않고, 이 스킬을 쓰게 한다.
- 인증 코드(OTP)를 기다리는 동안 **로그인 폼을 다시 제출하지 않는다** — 새 코드가 나가 앞 코드가 무효가 된다.
- `--timeout` 은 **초** 단위다(최대 300). 3000 을 넣으면 `timeout_too_large` 로 거절한다.
- 막혔다 우회로 풀었으면 끝내기 전에 `learn` 으로 남긴다 — 다음 세션이 같은 우회를 다시 만들지 않게.

## 앱 — 이럴 땐 이것

```bash
source "{env_file 값}"
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app launch --device "$DEV" --pkg "$PKG"
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app shot   --device "$DEV" --out 01_로그인 --clean-status
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app tree   --device "$DEV"
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app tap    --device "$DEV" --text "로그인" --shot after_login
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app swipe  --device "$DEV" --dir up --shot list_scrolled
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app relaunch   --device "$DEV" --pkg "$PKG"     # terminate 도 같은 모양
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app location   --device "$DEV" --lat 37.5665 --lon 126.978
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app permission --device "$DEV" --pkg "$PKG" --service location --grant
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app push       --device "$DEV" --pkg "$PKG" --payload push.json
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app openurl    --device "$DEV" --url "myapp://home"
```

- 누를 대상은 **요소로** 찾는다: `--text`(화면 언어 그대로) · `--id`(resource-id · accessibilityIdentifier) · `--desc`(접근성 설명),
  여러 개면 `--index N`(0부터). 문구를 모르면 `app tree` 의 `elements` · `locale` 을 먼저 본다.
- 캔버스·지도처럼 요소가 없을 때만 `--at 0.5,0.8` **비율(0~1)** 좌표. 픽셀은 거절한다(`bad_ratio`).
- 밀기는 `--dir up|down|left|right`, 정확한 궤적이면 `--from 0.5,0.8 --to 0.5,0.2 --ms 300`.
- **두 단계 이상은 `app run --steps steps.json`** 으로 묶는다 — iOS 는 Maestro 를 한 번만 띄운다(단계 모양은 `references/app.md`).
- `--shot 이름` 을 붙이면 화면이 멈춘 뒤 찍어 준다. `screen_changed: false` 면 반응이 없었다 — 다른 요소를 고른다.
- iOS 는 `app tap`·`app swipe` 뿐 아니라 **`app tree` 도 Maestro 를 쓴다**(호출당 10~40초). 긴 시나리오는 프로젝트의 E2E flow 로 한 번에 돌린다.
- **iOS 에서 보고 → 판단 → 누르기를 여러 번 하면 `app session start --device $DEV` 를 먼저** 한다(시작 8초, 이후 tree 0.6초 · tap 1초 실측).
  결과의 `transport: session` 이면 탔고, `session_fallback` 이면 호출마다 띄우는 길로 내려간 사유다. 끝나면 `app session stop`(안 해도 20분 유휴면 스스로 끝난다).
  `app type` 은 비밀 값이라 세션을 타지 않는다(`session_fallback: secret_input_per_call`).
- 화면 전환·로딩 직후 `not_found` 면 `app shot` 으로 지금 화면을 확인한 뒤 `--shot` 을 붙여 **1회만** 다시 누른다. 또 실패하면 `candidates` 에서 고른다.
- iOS 번들 ID(시스템 앱 포함)는 `references/app.md` 의 iOS 절.
- 앱 끄기·위치·권한·푸시·딥링크에 `xcrun simctl`·`adb shell am|pm` 를 직접 치지 않는다 — 위 `app` 동작이 기기 고르기·실패 code 를 맞춰 준다.

| code | 다음 행동 |
|---|---|
| `no_device` | `devices` 로 보고 `--device` 를 준다 |
| `not_found` | `candidates` 에서 고른다 |
| `ui_dump_failed` | 화면 구조를 못 읽었다(전환 중·보안 화면). 응답의 `foreground_package` 가 내 앱이 아니면 다른 앱이 덮은 것이다. 잠시 뒤 다시, 계속이면 `--at` 비율 좌표 |
| `not_foreground` · `app_exited` | launch·relaunch 는 보냈지만 앱이 앞에 없다 / 곧바로 죽었다. `blocking_activity`·`crash_report`·`exception_line` 을 읽는다. 남의 기기면 먼저 묻는다 |
| `device_unresponsive` | 기기가 응답하지 않는다(호스트 메모리 포함 `resources`). `device reboot --cold` 를 사용자에게 묻고 한다 |
| `typed_text_mismatch` | 입력칸 글자가 넣은 값과 다르다(조합형 키보드). `app type --ime ascii` |
| `device_owned_by_other`(필드) | 다른 세션이 쓰는 기기다. 조작 전에 확인한다 |
| `no_focused_window` | 초점 창이 없다(화면 꺼짐·잠금·전환 중). 깨우고 세 번까지 다시 읽은 뒤다. `app shot` 으로 화면을 본다 |
| `android_system_not_ready` · `ui_automation_unavailable` · `ui_dump_timeout` | 기기 쪽 문제다(시스템 재시작 중 · UiAutomation 연결 실패 · 시간 초과). `app shot` 으로 보고, 계속이면 사용자에게 에뮬레이터 cold boot 를 묻는다 |
| `session_start_failed` · `session_tools_missing` | 세션 없이 그대로 쓴다(호출마다 Maestro). `reason` 을 본다 |
| `tree_unsupported` | 이 기기는 화면 구조를 못 읽는다. `app shot` 으로 보고 `--text` 또는 `--at` 비율 좌표 |
| `ios_tool_missing` · `android_tool_missing` · `adb_missing` | 결과의 설치 안내를 사용자에게 제안한다 |
| `non_ascii_unsupported` · `ios_text_unsupported` | `app type` 이 못 넣는다. 영문 대체 또는 사용자에게 맡긴다 |
| `unsupported_on_platform` | 이 플랫폼·기기에서 안 되는 동작(Android push · 실기기 Android location 등). `next` 의 대안을 쓴다 |
| `build_mismatch` | 기기마다 설치된 빌드가 다르다. 멈추고 양쪽을 맞춘다 |

## 웹 — 이럴 땐 이것

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web open --url {주소}              # 떠 있으면 다시 붙는다(reused)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web text                           # 화면 글자를 읽는다 — 스크린샷보다 싸다
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web find --text "로그인"            # 후보를 ref · 링크 주소와 함께
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web click --ref 1 --expect-url /home   # 고른 것만, 결과까지 확인
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web viewport --preset mobile
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web route --match "**/api/items*" --status 200 --body "[]"
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web goto --url {그 화면}            # 규칙은 이동할 때 걸린다
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web shot --out 02_빈목록
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web route --clear
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web wait --url-contains /home --timeout 180   # 2단계 승인·저장 토스트 — 이동하지 말고 기다린다
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web scroll --to "결제 내역"           # 또는 --ref N · --by 600 [--container "#list"]
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web upload --files a.png,b.png       # 숨은 input[type=file] · 드롭존은 --click-ref N
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web type --frame login --selector "#account_name_text_field" --cred apple --cred-field account   # iframe 안
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web script --file snippet.py          # 고정 동작에 없는 일 — page · context 로 Playwright 조각
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web tab new --name edit --url {주소}  # 긴 작업은 자기 탭에서 — 이후 LAUNCH_TAB=edit 를 앞에 붙인다
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web login --cred {이름} --user-selector "#email" --password-selector "#pw" --submit-selector "#go" --until-url /home --handoff-seconds 120   # 2단계 인증은 사용자에게 넘기고 기다린다
```

- **`type`·`click` 전에 `find`/`inspect` 를 먼저 부른다** — 선택자가 직전 `find`·`inspect` 결과에서 온 것이 아니면. 빗나간 추측은 4초 뒤 `candidates`(ref 포함)와 함께 실패한다.
- **읽고 → 번호로 고르고 → 확인하며 누른다.** 선택자를 짐작하지 않는다. `click` 은 무엇을 눌렀고(`clicked`) 주소·제목이
  바뀌었는지(`changed`) 돌려준다. `changed: false` 면 엉뚱한 것을 누른 것이다 — `find` 로 다시 고른다. 정보는 `web text` 로 읽고 `shot` 은 모양을 볼 때만.
- **관리 콘솔(Play Console · App Store Connect · 결제·관리자)은 `web open --readonly`.** 삭제·출시·제출 같은 **버튼**은
  `mutating_blocked` 로 막힌다(링크·탭·표 행은 이동이라 열린다). 승인받은 경우에만 `--confirm-mutating`.
- 빈 목록 · 실패 · 로딩은 **서버를 건드리지 않고** `route` 로 연출한다(`--status 500` · `--delay 5000`). 끝나면 `--clear`.
- Google·Apple 로그인이 막히면 먼저 `web open --headed`. 사이트가 이상하면 `--no-stealth` 로 비교한다.
- `playwright_missing` 이면 사용자에게 묻고 `web setup`. `browser_not_open` · `browser_gone` 이면 `web open` 을 다시.
- 폼은 `web inspect --role input --near "이메일"` 로 읽고 받은 `ref` 로 `type` · `check` · `select` 한다. 비활성이면 기다리지 않고 `element_disabled`.
- **자주 쓰고 위험한 일은 고정 동작, 그 밖의 긴 꼬리는 `web script`.** 직접 CDP 에 붙는 스크립트를 새로 짜지 않는다 — `script` 는 같은 연결·재설치·시간 상한·비밀값 가림을 거친다.
- 로그인 폼이 iframe 안이면(`find` 가 `nothing_found` + `frames`) `--frame <이름|iframe 선택자|주소 일부>` 를 `find` · `type` · `click` · `assert` · `text` · `inspect` 에 붙인다.
- **브라우저는 같은 레포의 세션들이 함께 쓴다.** 저장 안 한 긴 입력은 `web tab new --name <이름>` 으로 만든 자기 탭에서 하고(`LAUNCH_TAB=<이름>`), 단계마다 저장한다.
  다른 세션이 내 탭을 옮겼으면 결과에 `tab_warning`(`page_changed_by_other_session`)이 붙는다.
- `web open` 은 멈춘 브라우저·남은 프로필 잠금을 스스로 치우고 `recovered` 로 알린다. 손으로 잠금을 지우지 않는다.
- 옵션은 동작마다 다르다 — `web <동작> --help`. 그 동작이 안 받는 옵션은 `bad_args` 로 거절된다(쓸 수 있는 옵션이 error 에 실린다).

| code | 다음 행동 |
|---|---|
| `nothing_found` · `selector_not_found` | 결과의 `candidates` 에서 골라 `next` 대로 `--ref` 로 다시. 후보가 없으면 `web text` 로 화면 글자를 읽고 `find` |
| `element_not_actionable` | 요소는 있지만 숨김·가려짐이라 4초 안에 못 눌렀다. `covered_by` 가 있으면 고정 머리글·오버레이가 덮은 것 — `next` 대로 `--dom-click`. 아니면 `candidates` 에서 다시 고른다 |
| `frame_not_found` | `frames` 의 name · url 일부를 `--frame` 에 넣는다 |
| `wait_timeout` | 조건이 안 맞았다. `url` · `title` 로 판단한다. 승인 대기면 이동하지 말고 다시 `wait` |
| `script_failed` · `script_timeout` | 조각의 첫 오류 줄을 보고 고친다 · `--timeout` 을 늘리거나 기다림을 줄인다 |
| `ref_stale` | 화면이 바뀌었다. `find` 를 다시 |
| `expect_not_met` | 기대한 결과가 안 왔다. `web text` 로 지금 화면을 보고 다른 후보를 고른다 |
| `mutating_blocked` | 읽기 전용 세션이 위험 버튼을 막았다. 무엇이 바뀌는지 사용자에게 말하고 승인받는다 |
| `needs_user` | 로그인 남은 단계(2단계 인증·기기 승인)를 사용자에게 넘긴다. `ask_user` 로 묻고, 마쳤다고 하면 `next` 의 `web login --resume ...` |
| `tab_gone` | `LAUNCH_TAB` 탭이 닫혔다. `web tab new --name <같은 이름>` |
| `browser_start_failed` | 자가 복구 뒤에도 실패. `stderr_tail` · `causes` 를 보고 판단한다 |
- **처음 웹을 몰기 전에 `references/web.md` 의 안전 계약을 읽는다.**

## render · 서버 · 자격증명 · 기억 — 이럴 땐 이것

- 실기기로 만들기 어려운 상태(빈 목록 · 긴 글자 · 권한 거부)는 `render snapshot` → 임시 렌더 코드 → `render run`.
  `render_failed` 는 `first_error` 부터 보고(없으면 `output_tail`) 고치고, `residue` 는 **네가 만든 것만** 지운다(`references/render.md`).
- 서버에 붙는 법은 코드를 읽어 정하고 `access set` 에 적는다. `http --url /경로` · `db --profile db --sql …` · `logs --tail 100`.
- 서버·DB·로그인 화면을 만지기 전, "사용자가 직접 로그인해야 한다"고 말하기 전에 **`cred list` 를 먼저 본다.**
  `use_when` 이 맞는 것만 쓰고, 새 정보는 저장해도 되는지 묻고 `cred set`. 원격은 `ssh --cred 이름 --command '…'`(저장 없이는 `ssh --host … --user … --password-env|--key-path …`),
  이 맥 관리자 권한은 `local sudo --cred 이름 -- <명령>`(첫 등록은 사용자가 `cred set --prompt` 로 직접). 상세는 `references/credentials.md`.
- **응답에 `memory` 가 오면 먼저 읽고 그 방식부터 쓴다**(자동으로 실린다 — recall 을 따로 부를 필요 없다). 썼으면 `learn --key <그 key> --result ok|fail`,
  `learn_hint` 가 오면 막혔다 풀린 방식을 `learn` 으로 남긴다. 레포와 무관한 방법은 `--scope machine`.
  비밀값과 호스트 마우스 방식은 저장되지 않는다. 캡처는 이슈에 붙이기 전에 `shrink`. 상세는 `references/memory.md`.

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-launch`.
Keys for this skill: the common `language`, `tone`, `rules` only.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.
