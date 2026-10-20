# 앱에 붙는 법 — Android 에뮬레이터 · iOS 시뮬레이터 · 실기기

> 언제 읽나: 기기를 부팅·설치·녹화하거나, `app tap`·`app swipe` 가 뜻대로 안 될 때, iOS 를 조작해야 할 때.

누르기·밀기는 `launch_cli.py app tap` · `app swipe` 를 쓴다. 그것으로 안 되는 조작(설치·로그·녹화)만 도구를 직접 쓴다.
**모든 adb 명령에 `-s "$DEV"` 를 붙인다.** 기기가 여러 대면 빠뜨린 명령이 엉뚱한 쪽으로 간다.

## PATH

Android SDK 도구는 PATH 에 없을 수 있다. `doctor`·`devices` 결과의 `adb_path` 를 그대로 쓰거나:

```bash
export PATH="$PATH:$HOME/Library/Android/sdk/platform-tools:$HOME/Library/Android/sdk/emulator"
```

---

## 찍기 · 띄우기 · 누르기 · 밀기 — 공통

```bash
source "{env_file 값}"
{PYTHON} {SCRIPTS}/launch_cli.py app launch --device "$DEV" --pkg "$PKG"
{PYTHON} {SCRIPTS}/launch_cli.py app shot   --device "$DEV" --out 01_로그인 --clean-status
{PYTHON} {SCRIPTS}/launch_cli.py app tree   --device "$DEV"                       # 누를 수 있는 문구·id + 화면 언어
{PYTHON} {SCRIPTS}/launch_cli.py app tap    --device "$DEV" --text "로그인" --shot after_login
{PYTHON} {SCRIPTS}/launch_cli.py app tap    --device "$DEV" --id login_button      # resource-id · accessibilityIdentifier
{PYTHON} {SCRIPTS}/launch_cli.py app tap    --device "$DEV" --desc "닫기" --index 1 # 접근성 설명 · 여러 개면 몇 번째(0부터)
{PYTHON} {SCRIPTS}/launch_cli.py app tap    --device "$DEV" --at 0.5,0.8           # 요소로 못 찾을 때만 — 비율 좌표
{PYTHON} {SCRIPTS}/launch_cli.py app swipe  --device "$DEV" --dir up --shot list_scrolled
{PYTHON} {SCRIPTS}/launch_cli.py app swipe  --device "$DEV" --from 0.5,0.8 --to 0.5,0.2 --ms 500
```

- `--device` 는 Android 시리얼이나 iOS UDID. 없으면 `$DEV` → 붙은 기기가 한 대뿐이면 그것.
  **여러 대인데 안 고르면 `no_device` 로 멈춘다** — 엉뚱한 기기를 찍지 않게 하려는 것이다.
- `--clean-status` 는 상태바를 9:41 · 배터리 100% 로 고정해 찍고 **찍은 뒤 되돌린다**
  (iOS `simctl status_bar`, Android 데모 모드 + 허용 설정 원복). 캡처끼리 시각이 달라 보이지 않게 한다.
- 기본은 긴 변 1200px WebP 다. **픽셀 대조처럼 원본이 필요하면** `--keep-format`
  (또는 `--out` 에 경로를 직접 주면 그대로 저장한다). `--max-side` · `--quality` 로 조정한다.
- **좌표를 눈대중하지 않고 화면 요소로 찾는다.** 문구는 **화면 언어 그대로** 쓴다. 모르면 `app tree` 의
  `locale` 과 `elements` 를 먼저 본다. 못 찾으면 `not_found` 와 함께 화면에 실제로 있는 `candidates` 가 오니
  **추측을 반복하지 말고** 거기서 고른다.
- `--shot` 을 붙이면 **화면이 바뀌고 멈춘 뒤** 찍어 경로를 준다(확인용 `app shot` 호출이 필요 없다).
  `screen_changed: false` 면 눌렀는데 아무 일도 없었다는 뜻이다 — 다른 요소를 고른다.
- 요소로 못 찾는 것(캔버스·지도)만 `--at 0.5,0.8` **비율** 좌표(0~1)를 쓴다. 픽셀은 거절한다(`bad_ratio`) —
  캡처는 축소돼 있어 그 좌표로 누르면 빗나간다.
- `swipe --dir up|down|left|right` 는 화면 가장자리 제스처를 피하려고 15% 안쪽에서 움직인다.
  정확한 궤적이 필요하면 `--from`·`--to` 비율 좌표와 `--ms`(기본 300).
- Android 는 기기 내장 `uiautomator` 라 설치가 필요 없다. **iOS 는 Maestro 가 필요하다**(simctl 에 탭 명령이
  없다). 호출마다 Maestro 가 새로 떠서 10~40초 걸린다 — 결과의 `elapsed_seconds` 에 보인다.
  **두 단계 이상이면 `app run` 으로 묶는다**(아래). 더 긴 시나리오는 프로젝트의 Maestro flow 로 돌린다.

### 여러 단계를 한 번에 — `app run` (#894)

```bash
cat > steps.json <<'JSON'
[{"tap": {"text": "이메일"}}, {"type": {"env": "LOGIN_EMAIL"}},
 {"tap": {"id": "password_field"}}, {"type": {"cred": "staging", "submit": true}},
 {"wait": {"text": "홈", "timeout": 10}}]
JSON
{PYTHON} {SCRIPTS}/launch_cli.py app run --device "$DEV" --steps steps.json --shot after_login
```

| 단계 | 키 |
|---|---|
| `tap` | `text` · `id` · `desc` 중 하나 (+`index`), 또는 `point: "0.5,0.8"` 비율 |
| `swipe` | `direction: up\|down\|left\|right`, 또는 `from`·`to` 비율 (+`ms`) |
| `type` | `env`(환경변수 이름) 또는 `cred`(+`field`), `submit` — **값을 파일에 적지 않는다** |
| `wait` | `text` · `id` · `desc` 중 하나 + `timeout`(초, 기본 10 · 최대 60) |
| `back` | `true` — Android 만 (iOS 는 `step_unsupported_on_platform`) |

- iOS 는 **Maestro 를 한 번만** 띄운다(실측: 4단계 20초, 따로 부르면 단계당 15~45초). Android 는 같은 파일을 차례로 실행한다.
- 결과: `steps[]`(단계별 `status`: completed · failed · not_run · unknown) · `failed_step` · `elapsed_seconds`.
  `--shot` 은 전부 성공했을 때만 찍는다. iOS 의 `text`·`wait` 은 **요소 문구 전체**와 맞아야 한다.

| code | 다음 행동 |
|---|---|
| `bad_steps` | `step_index` 번 단계를 고친다 (`null` 이면 파일 자체 — 경로·JSON·빈 배열) |
| `step_failed` | `failed_step` 부터 `app tree` 로 보고 고쳐 다시 run. `null` 이면 단계 전에 멈췄다(`error`) |
| `step_unsupported_on_platform` | `next` 의 대안(뒤로 버튼 tap · 가장자리 swipe) |
| `env_not_set` · `cred_field_missing` · `non_ascii_unsupported` | `step_index` 의 type 단계 값 출처를 고친다 |

결과에 `cause`(예: `android_system_not_ready`)가 있으면 단계가 아니라 **기기 상태**가 원인이다 — 단계를 고치지 말고 기기부터 본다.

### 기다리기 · 녹화 · 연속 캡처 · 상태바 시각 (#928)

```bash
{PYTHON} {SCRIPTS}/launch_cli.py app wait --device "$DEV" --text "로드 중" --gone --timeout 30   # 사라질 때까지 (없으면 나타날 때까지)
{PYTHON} {SCRIPTS}/launch_cli.py app record start --device "$DEV" --out login_flow                # iOS simctl recordVideo · Android screenrecord(180초 제한)
{PYTHON} {SCRIPTS}/launch_cli.py app record stop  --device "$DEV" --gif                           # ffmpeg 가 있으면 poster · gif 도
{PYTHON} {SCRIPTS}/launch_cli.py app tap --device "$DEV" --text "계속" --burst 6:0.4              # 동작 전후 6초, 0.4초 간격 — 변한 프레임만 돌려준다
{PYTHON} {SCRIPTS}/launch_cli.py app shot --device "$DEV" --out store_01 --time 7:42              # 상태바 시각을 알림 시각에 맞춘다 (--clean-status 포함)
```

- `app wait` 는 읽지 못한 화면을 "사라졌다"로 세지 않는다. `app run` 단계에서는 `{"gone": {...}}` 또는 `{"wait": {...}, "gone": true}`.
- `--burst` 는 바이트 해시로 중복을 걷는다(시계·애니메이션 변화도 변경으로 센다). 최대 150장 · 30초.
- `app shot --shot 이름` 은 `--out` 의 별칭이다.

### 제스처 플레이북 — 밀다가 찍기 · 요소 기준 밀기 · 밀고 곧바로 탭 (#862)

전용 옵션을 늘리지 않는다. **`tap`·`swipe`·`run` 으로 되는 것은 그것으로, 안 되는 것은 Maestro flow 를 `app flow` 로** 돌린다.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py app flow --device "$DEV" --file .maestro/swipe_undo.yaml --shot undo [--timeout 300]
```

- 결과: `commands[]`(Maestro 명령별 `completed`·`failed`·`skipped`) · `failed_command` · `screenshots[]`(flow 의
  `takeScreenshot` 결과를 `SHOT_DIR` 로 옮겨 `<--shot>_<이름>.webp`) · `driver_retried` · `elapsed_seconds`.
  Maestro 기록(`maestro.log`)은 임시 폴더에 두었다가 지운다. 프로젝트 `.maestro/` flow 를 그대로 쓴다.
- Android · iOS 둘 다 된다(Maestro 필요). `maestro test` 를 새로 띄우므로 iOS 상주 세션 연결이 끊긴다(다음 호출에서 다시 붙는다).

| 하고 싶은 것 | 방법 |
|---|---|
| 밀고 **곧바로** 탭 (밀어서 삭제 > 4초 안 "되돌리기") | iOS: `app run` 의 `swipe` > `wait` > `tap` (Maestro 한 번). Android 는 단계마다 화면 구조를 다시 읽어 늦을 수 있다 — `app flow` 로 묶는다 (아래 예시) |
| 시작점을 요소 기준으로 | 밀기 **직전에** `app tree` 를 다시 본다(배너가 뜨면 줄의 y 가 바뀐다 — 87% > 80% 실측). 줄 안의 **스위치·버튼(오른쪽 끝)을 피해** 문구 쪽에서 시작한다. flow 에서는 `swipe: {from: {text: "..."}, direction: LEFT}` 처럼 요소에서 시작한다 |
| Maestro 시작 직후 첫 탭이 안 먹음 | `tapOn` 에 `retryTapIfNoChange: true`, 앞에 `extendedWaitUntil: {visible: ...}` |
| **밀고 있는 도중** 화면 | 아래 "중간 장면" |

```yaml
appId: com.example.app
---
- extendedWaitUntil: {visible: "알림 1", timeout: 5000}
- swipe: {from: {text: "알림 1"}, direction: LEFT, duration: 400}   # 문구에서 시작 — 오른쪽 스위치를 피한다
- takeScreenshot: after_swipe
- tapOn: {text: "되돌리기", retryTapIfNoChange: true}
- takeScreenshot: after_undo
```

**중간 장면(누른 채 멈춘 화면)은 기기 조작으로 찍지 않는다.**

- iOS 시뮬레이터: Maestro `swipe` 는 `duration` 을 늘려도 "길게 누른 뒤 빠르게 이동"이라 중간 장면이 없다(20·40초로 프레임 34장 모두 변화 없음 — 이슈 보고).
- Android: `adb shell input motionevent DOWN/MOVE/UP` 은 명령마다 프로세스가 떠서 **부하 걸린 에뮬레이터에서 호출당 3.5초**였고,
  첫 MOVE 전에 길게 누르기로 인식돼 홈 화면 메뉴가 떴다(실측 2026-10-17, API 36). 느린 `input swipe` 를 백그라운드로 걸고
  `screencap` 을 찍는 방법도 검은 화면이 나와 확인하지 못했다 — 기기·부하에 따라 다르니 믿지 않는다.
- **대신**: Flutter 는 해당 위젯을 테스트에서 드래그 중간 상태로 만들고 `RepaintBoundary` 의 `toImage()` 로 PNG 를 뽑는다
  (`flutter test` 로 수 초, 기기 불필요). 실기기 느낌이 필요하면 `simctl io recordVideo` / `screenrecord` 로 녹화하고
  사람이 직접 밀게 한 뒤 프레임을 뽑는다(아래 "움직임을 수치로 확인하기").

| code (`app flow`) | 다음 행동 |
|---|---|
| `flow_file_required` · `bad_timeout` | 인자를 고친다 |
| `flow_failed` | `failed_command` 를 `app tree` 로 보고 flow 를 고친다. `screenshots` 에 실패 직전까지의 캡처가 있다 |
| `flow_timeout` | `--timeout` 을 늘리거나 flow 를 나눈다 |
| `maestro_driver_timeout` | driver 가 시간 안에 안 떴다(`did not start up in time`). CLI 가 driver 앱(Android `dev.mobile.maestro*`)을 강제 종료하고 한 번 더 돌린 뒤에 낸다. **기계 과부하**다 — 빌드를 멈추거나 cold boot 를 사용자에게 묻는다 |
| `maestro_tool_missing` | `next` 의 설치 명령을 사용자에게 제안한다 |

### iOS 상주 세션 — `app session` (#894 2단계, 선택)

호출마다 Maestro(JVM)를 띄우는 대신 `maestro mcp` 를 한 번 띄워 두고 쓴다. 보고 → 판단 → 누르기를 여러 번 할 때 켠다.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py app session start  --device "$DEV"      # UDID 로 (booted 는 session_needs_udid)
{PYTHON} {SCRIPTS}/launch_cli.py app tree           --device "$DEV"      # transport: session
{PYTHON} {SCRIPTS}/launch_cli.py app session status --device "$DEV"
{PYTHON} {SCRIPTS}/launch_cli.py app session stop   --device "$DEV"
```

- **`tap_failed` 가 90초로 반복되고 `session start` 도 실패하면** 응답의 `stale_maestro_drivers`(남은 Maestro 드라이버)·`host_load`(부하)를 본다.
  남은 것은 `app session stop --device "$DEV" --kill-stale` 로 끈다(살아 있는 부모가 있는 것은 건드리지 않고 `other_maestro_processes` 로 알리기만 한다). 부하가 높으면 `MAESTRO_DRIVER_STARTUP_TIMEOUT=180000` 이 자동으로 걸린다.
  Maestro 시작은 컴퓨터 단위 잠금으로 직렬화된다(`maestro_lock.waited_seconds`).
- **라벨로 누를 때** `--text` 는 text · desc · label 을 모두 본다. 순서는 정확 일치 > 정규화(Flutter 가 겹쳐 넣는 `"X\nX"`, 보이지 않는 표식, 공백) > 부분 일치.
  응답의 `matched_by` 로 어느 칸이 맞았는지 알 수 있고, 못 찾으면 `did_you_mean`(예: `--desc '홈 탭'`)과 text · desc 후보가 온다.

| 실측 (iOS 18.3 시뮬레이터, Maestro 2.10.0) | 세션 없음 | 세션 |
|---|---|---|
| `session start` (기동 + 기기 연결 예열) | — | 7.8초 |
| `app tree` | 11.5 · 11.7초 | 0.6초 |
| `app tap --at` · `--text` | 16.8~17.5초 | 0.9~1.1초 |
| `app swipe` | 14~22초 | 1.3초 |
| `app run` 4단계 | 20초 | 단계당 0.1~1초 |

- 켜져 있으면 `tap`·`swipe`·`tree`·`run` 이 **알아서** 세션을 탄다. 결과의 `transport: session`. 못 쓰면 지금의 길로 조용히
  내려가고 `session_fallback`(`session_gone` · `session_timeout` · `session_not_ready` · `device_unreachable` 등)에 사유를 남긴다.
- 세션의 `app run` 은 단계마다 run 을 따로 불러(단계당 1초 안팎) 어느 단계가 실패했는지 정확히 짚는다.
- **`app type`(그리고 type 단계가 든 `app run`)은 세션을 타지 않는다** — `maestro mcp` 가 run 응답에 env 값을 평문으로
  되돌려 주고, 상주 프로세스의 기록 자리는 호출마다 임시 폴더로 돌릴 수 없다. 대신 호출마다 띄우는 길에서 Maestro 기록을
  임시 폴더로 돌려 함께 지운다(기본 자리 `~/.maestro/tests/*/maestro.log` 에 입력값이 평문으로 남는 것을 실측).
- **같은 기기에 다른 `maestro test` 가 붙으면 세션의 기기 연결이 끊긴다**(type 포함). 다음 호출에서 중계가 다시 붙는다
  (한 번 9초 안팎, `session_reconnected: true`).
- 20분 동안 안 쓰면 스스로 끝난다(`--idle-minutes`로 1~240분). 중계가 강제로 죽었으면 다음 호출·`status` 가 남은 파일을 걷는다.
- 웹 뷰어(기본 포트 9999)는 `--no-viewer` 로 끈다. 그 옵션이 없는 옛 Maestro 는 빈 포트로 띄우고 `viewer.url` 에 적는다
  (9999 가 차 있으면 다음 빈 포트 — 실패하지 않는다).
- 상태: `{PROJECTOPS_HOME 또는 ~/.projectops}/launch/maestro-sessions/<UDID>.json`(권한 600 — 접속 토큰) · 중계 기록 `<UDID>.log`.

| code | 다음 행동 |
|---|---|
| `session_start_failed` | `reason`(`device_unreachable` · `maestro_mcp_start_failed` · `session_start_timeout`)을 본다. 세션 없이 그대로 써도 된다 |
| `session_tools_missing` | 이 Maestro 버전의 MCP 도구 이름이 다르다(`tools_available`). 세션 없이 쓴다 |
| `session_starting` | 다른 호출이 띄우는 중이다. 잠시 뒤 `status` |
| `session_needs_udid` · `session_verb_required` · `bad_idle_minutes` | 인자를 고친다 |
| `session_stop_failed` | `next` 의 kill 명령 |

| code | 다음 행동 |
|---|---|
| `no_device` | `devices` 로 목록을 보고 `--device` 를 준다 |
| `not_found` · `index_out_of_range` | `candidates` 에서 고른다. 화면 언어는 `locale` |
| `ui_dump_failed` | 화면이 전환 중이거나 보안 화면이다. 잠시 뒤 `app tree` 를 다시 본다. 계속 실패하면 `--at` 비율 좌표 |
| `no_focused_window` | Android 에 초점을 가진 창이 없다(화면 꺼짐·잠금·재부팅 직후). CLI 가 화면을 깨우고(`WAKEUP`·잠금 해제) 세 번까지 다시 읽은 뒤에 낸다. 비밀번호 잠금이면 사용자에게 풀어 달라고 한다 |
| `android_system_not_ready` | 부팅 애니메이션이 떠 있다(system_server 재시작 반복 실측). 기다려도 그대로면 사용자에게 cold boot 를 묻는다 |
| `ui_automation_unavailable` | uiautomator 가 UiAutomation 에 못 붙었다. 다른 자동화(Maestro·Appium)가 기기를 쥐고 있는지 본다 |
| `ui_dump_timeout` | 20초 안에 안 끝났다(한 번 더 시도한 뒤). 애니메이션이 계속되는 화면이면 `--at` 비율 좌표 |
| `tree_unsupported` | 이 기기 백엔드는 화면 구조를 못 읽는다. `app shot` 으로 보고 `--text` 로 누르거나 `--at` 비율 좌표 |
| `ios_tool_missing` · `android_tool_missing` | `next` 의 설치 명령(iOS 는 Maestro)을 사용자에게 제안한다 |
| `adb_missing` | 아래 PATH 를 잡거나 `doctor` 의 `adb_path` 를 쓴다 |
| `capture_failed` | 잠긴 화면이거나 `FLAG_SECURE` 다(아래 "관측") |

## 끄기 · 다시 띄우기 · 위치 · 권한 · 푸시 · 딥링크 (#893)

raw `xcrun simctl` · `adb shell am|pm` 대신 쓴다. 패키지는 `--pkg` → `$PKG` → `device bind` 의 package 순.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py app terminate  --device "$DEV" --pkg "$PKG"      # 꺼져 있었으면 was_running=false (Android 는 null)
{PYTHON} {SCRIPTS}/launch_cli.py app relaunch   --device "$DEV" --pkg "$PKG"      # 끄기 실패면 띄우지 않는다
{PYTHON} {SCRIPTS}/launch_cli.py app location   --device "$DEV" --lat 37.5665 --lon 126.978
{PYTHON} {SCRIPTS}/launch_cli.py app permission --device "$DEV" --pkg "$PKG" --service photos --grant   # 또는 --revoke
{PYTHON} {SCRIPTS}/launch_cli.py app push       --device "$DEV" --pkg "$PKG" --payload push.json       # iOS 시뮬레이터만
{PYTHON} {SCRIPTS}/launch_cli.py app openurl    --device "$DEV" --url "myapp://home?id=1"              # Android 는 --pkg 를 주면 그 앱으로 고정
```

| 동작 | iOS 시뮬레이터 | Android |
|---|---|---|
| terminate · relaunch | `simctl terminate` · `launch` | `am force-stop` · `monkey` |
| location | `simctl location set` | 에뮬레이터만 `emu geo fix` (실기기 → `unsupported_on_platform`) |
| permission | `simctl privacy` — 서비스: `all` `calendar` `contacts` `location` `location-always` `photos` `photos-add` `media-library` `microphone` `motion` `reminders` `siri` (권한이 바뀌면 앱이 꺼진다) | `pm grant/revoke` — `camera` `microphone` `location` `location-always` `contacts` `calendar` `photos` `notifications` 또는 `android.permission.X` 원문 |
| push | `simctl push` (payload 에 `Simulator Target Bundle` 이 있으면 `--pkg` 불필요) | `unsupported_on_platform` — FCM 테스트 메시지로 |
| openurl | `simctl openurl` | `am start -a VIEW -d` |

| code | 다음 행동 |
|---|---|
| `package_required` | `--pkg` 를 준다 |
| `unsupported_on_platform` | `next` 의 대안. 다른 플랫폼에만 있는 권한 서비스(iOS `camera` 등)도 이 code |
| `bad_coordinates` · `permission_mode_required` · `payload_invalid` · `url_required` | 인자를 고친다 (`error` 에 이유) |
| `unknown_permission_service` | `candidates` 에서 고른다 |
| `terminate_failed` · `launch_failed` · `location_failed` · `permission_failed` · `push_failed` · `openurl_failed` | `error` 의 도구 출력을 본다. openurl 은 앱이 scheme 을 등록했는지 |

새 플랫폼(백엔드)을 붙이는 법은 `extending.md`.

---

## 기기 빌리기 · 띄우기 · 소유 · 언어·외관 (#923 · #924 · #925 · #929 · #953)

```bash
{PYTHON} {SCRIPTS}/launch_cli.py device boot    --device "{UDID|이름|AVD}" [--window headless|small|normal] [--scale 0.4] [--cold]
{PYTHON} {SCRIPTS}/launch_cli.py device reboot  --device "$DEV" [--cold] [--yes]   # 소프트 · cold(emu kill > 강제 종료 > -no-snapshot-load)
{PYTHON} {SCRIPTS}/launch_cli.py device acquire --platform ios --purpose "#953 로그인" [--form tablet] [--os ">=17"] [--wait 90]
{PYTHON} {SCRIPTS}/launch_cli.py device release --device "$DEV" [--keep-booted]    # 바꾼 언어·외관 되돌림 > 이 빌림이 켰으면 끈다
{PYTHON} {SCRIPTS}/launch_cli.py device release --all                              # 이 세션의 모든 lease (세션 종료 훅도 이것)
{PYTHON} {SCRIPTS}/launch_cli.py device shutdown --device "$DEV" [--yes]            # 끈다 (남이 빌린 기기는 --yes 없이 거부)
{PYTHON} {SCRIPTS}/launch_cli.py device claim   --device "$DEV"                    # 특정 기기를 이 세션이 쥔다
{PYTHON} {SCRIPTS}/launch_cli.py device acquire --platform ios --need login:kakao   # 그 상태가 기록된 기기 (#954)
{PYTHON} {SCRIPTS}/launch_cli.py device acquire --platform ios --fresh | --count 2  # 아무도 안 쓴 새 폰 · 서로 다른 두 대 (없으면 만든다)
{PYTHON} {SCRIPTS}/launch_cli.py device mark    --device "$DEV" --kind login --name kakao --note "guardian 계정"   # --verify 로 확인 시각 갱신
{PYTHON} {SCRIPTS}/launch_cli.py device unmark  --device "$DEV" --kind login --name kakao
{PYTHON} {SCRIPTS}/launch_cli.py device adopt   --device "{UDID|AVD 이름|기기 이름}"   # 원장에 없던 기기를 올린다
{PYTHON} {SCRIPTS}/launch_cli.py device records [--platform ios]                    # 출처 · mark · 임시 기한 · 빌린 세션 · 한도
{PYTHON} {SCRIPTS}/launch_cli.py device create  --platform ios --reason "#954 두 대 동시" [--form tablet] [--os ">=17"] [--ttl-days 3] [--name ...]
{PYTHON} {SCRIPTS}/launch_cli.py device erase|delete --device "{키}" [--yes]          # mark · 남의 빌림 · 사람이 켠 기기는 --yes 없이 거부
{PYTHON} {SCRIPTS}/launch_cli.py device clone   --device "{꺼진 iOS 기기}" --reason "#955 로그인된 두 대"   # 상태 기록은 확인 전으로 복사
{PYTHON} {SCRIPTS}/launch_cli.py device gc [--sizes]                                 # 보고만 · --apply 로 실행
{PYTHON} {SCRIPTS}/launch_cli.py device locale  --device "$DEV" --lang en --region US [--app "$PKG"]   # --restore 로 원복
{PYTHON} {SCRIPTS}/launch_cli.py device appearance dark --device "$DEV"            # light|dark, --restore 로 원복
{PYTHON} {SCRIPTS}/launch_cli.py device text-size largest --device "$DEV"           # default|large|largest (또는 1.3), --restore 로 원복 (큰 글씨 QA)
```

- **창 크기와 캡처 크기는 무관하다.** 캡처는 기기 화면을 그대로 읽고 `--max-side` 로 줄인다. 창은 사람이 디버깅할 때만 필요하므로 에이전트가 띄울 때는 **headless 가 기본**이다.
  iOS 에서 `--window small|normal` 은 Simulator.app 이 **꺼져 있을 때** 그 기기의 창 배율(`DevicePreferences.<UDID>.SimulatorWindowGeometry.<화면>.WindowScale`)을 쓰고 그 기기 창만 연다.
  Simulator.app 이 이미 떠 있으면(다른 세션 것일 수 있다) 끄지 않고 `window_scale_pending: true` + `window_hint` 만 낸다. 이미 켜져 있는 기기는 바꾸지 않는다(`already_booted`).
- **앞에 나왔나 (#923).** `app launch|relaunch` 는 띄운 뒤 확인한다. Android 는 초점 창·재개된 액티비티가 대상 패키지인지 최대 ~5초 본다 — 아니면 `not_foreground`(`foreground_package` · `blocking_activity`).
  iOS 는 ~2.5초 뒤 `launchctl list` 에 `UIKitApplication:<번들>` 이 있는지 본다 — 없으면 `app_exited` + 가장 새 크래시 리포트(`crash_report.path` · `exception_line`). 확인을 못 하면(`dumpsys` 시간 초과) 성공을 뒤집지 않는다.
- **빌리기 · 반납 (#953).** `acquire` 는 조건(플랫폼 · 폼팩터 · OS)에 맞는 빈 기기를 고른다: 켜져 있는 것 > 최근 쓴 것, 꺼져 있으면 켠다.
  켜져 있지만 원장 기록이 없는 기기는 사람이 쓰는 것일 수 있어 고르지 않는다. 같은 세션이 다시 부르면 **다른** 기기를 준다(병렬 하위 agent).
  남이 다 쓰는 중이면 `wait`, 합친 대기가 10분(`launch.devices.wait_limit_minutes`)을 넘거나 메모리 `critical` 에서 새로 켜야 하면 `ask`.
  `--wait` 한 번은 최대 90초 — 도구 명령 시간 상한 안이다. Claude Code 는 세션이 끝나면 훅이 `release --all` 을 부른다.
- **공들인 상태 · 만들기 (#954).** 기기에서 읽을 수 없는 상태(로그인 · 테스트 데이터 · 권한 · 설정)는 `device mark` 로 남긴다. kind·name 은 자유 문자열(권장 kind: login · data · permission · config · other).
  mark 는 14일(`launch.devices.mark_stale_days`)이 지나면 `is_stale` — 로그인이 살아 있는지 보고 `mark --verify`. `--need` 는 stale 이어도 그 기기를 고른다.
  `acquire` 는 빈 기기가 없고 `--need`·`--device` 가 아닐 때만 임시 기기를 만든다(`verdict: create`). 한도 3개에 걸리면 만들지 않는다:
  메모리 `critical` · 디스크 여유 20GB(`min_free_disk_gb`) 미만 · 켜진 가상 기기 수 `max_booted`(RAM 에서 계산, 16GB 2대 · 32GB 6대).
  만든 기기는 이유·기한(`temp_ttl_days`, 기본 3일)과 함께 원장에 남는다. 초기화(`erase`)는 mark·설정 기록도 지우고 새 폰으로 표시한다.
  iOS 는 가장 새 런타임의 첫 기기 종류(폼팩터별)로, Android 는 같은 폼팩터 AVD 를 본으로(시스템 이미지·하드웨어 프로필) 만든다 — 본 AVD 가 없으면 `create_failed`.
- **복제 · 정리 (#955 · #959).** 복제는 꺼진 원본만 된다. iOS(simctl) 실측: 데이터·키체인 파일이 그대로 넘어가고, APFS 복제라 디스크는 10MB 정도, 8초.
  Android 는 AVD 폴더를 통째로 복제한다(macOS `cp -c`) — 디스크 백업 경로가 상대 경로라 원본과 묶이지 않고, 로그인은 userdata 에 있어 스냅샷이 안 맞아 처음부터 부팅해도 남는다.
  복제본의 mark 는 "확인 전"(stale)이다 — 로그인 토큰이 기기에 묶이는 서비스도 있어 복제본에서 살아 있는지 보고 `mark --verify`.
  `acquire --count 2 --need login:X` 는 그 상태가 있는 꺼진 기기가 모자라면 먼저 복제한다. Android 읽기전용 동시 실행(`-read-only`)은 쓰지 않는다 — 복제로 같은 일을 한다.
  `gc` 가 지우는 것은 기한 지난 임시 기기(빌린 세션 없음 · mark 없음)뿐이고, 원장이 켜 둔 채 20분 넘게 버려진 기기는 끈다.
  기록 없는 기기 · mark 있는 기기는 보고만 한다. 크기는 정리 대상만 센다 — 전부는 `--sizes`(수십 GB 를 훑어 수십 초).
- **에뮬레이터가 offline 에 멈추면** 로그에 `hvf is not enabled` · `mprotect failed` 가 있는지 본다 — 호스트 스왑이 거의 차면 하드웨어 가속을 못 얻어
  소프트웨어 모드로 떨어지고 끝나지 않는다(실측: 스왑 28.9/29.7GB). `boot`·`acquire` 는 이 징후를 보면 기다리지 않고 끈 뒤 `emulator_no_acceleration` 으로 알린다.
- **소유 (#925 · #953).** 소유 주인은 lease = (세션, agent 호스트 pid). 호스트가 죽으면 즉시, 살아 있어도 30분(`launch.devices.lease_idle_minutes`) 안 쓰면 풀린다.
  다른 살아 있는 세션의 기기에서 **바꾸는 조작**(install · launch · tap · type · swipe · run · flow · permission · push · locale · appearance 등)은 `device_owned_by_other` 로 거부된다 — 사용자에게 묻고 `--yes`.
  읽기(shot · tree · wait)는 경고 필드만 붙는다. `device reboot`·`release`·`shutdown`·`claim` 도 `--yes` 없이 멈춘다.
  세션은 `LAUNCH_SESSION` > `CLAUDE_CODE_SESSION_ID`, 둘 다 없으면 호스트 pid 로 가른다(`owner_identity: weak` 면 `LAUNCH_SESSION` 을 정한다). `device list`·`devices` 의 `owners` 에서 소유자를 본다.
- **언어 한계.** iOS 시스템 언어는 `defaults write -g AppleLanguages/AppleLocale` 후 재부팅(그 시뮬레이터의 앱 상태가 사라진다). `--app` 은 앱 도메인만 바꾸고 재시작이면 된다.
  Android 는 API 33+ 만: 앱별은 `cmd locale set-app-locales`(Google Maps 같은 라벨이 앱 언어를 따를 때), 시스템은 `cmd locale set-device-locale` 이 있는 이미지에서만 된다.

---

## Android

### 기기 준비

```bash
adb devices                       # 연결 확인
emulator -list-avds               # 쓸 수 있는 AVD 목록

# 부팅 — 창 없이 띄우고 쓸 수 있을 때까지 기다린다 (raw emulator / nohup 루프 대신)
{PYTHON} {SCRIPTS}/launch_cli.py device boot --device {AVD명}                  # 기본 headless(-no-window)
{PYTHON} {SCRIPTS}/launch_cli.py device boot --device {AVD명} --window small   # 창이 필요할 때 (-scale 0.4)
{PYTHON} {SCRIPTS}/launch_cli.py device boot --device {AVD명} --cold           # -no-snapshot-load
```

준비 완료 = 셸 응답 + `sys.boot_completed` + 패키지 서비스 + 초점 창이 "Not Responding" 아님(연속 3회). `init.svc.bootanim` 은 보지 않는다.

기기를 나중에 띄웠으면 `device list` 를 한 번 더 돌린다 — `env.sh` 의 `$DEV` 를 채운다.

> **Google Play 이미지는 `adb root`가 안 된다.** 앱 내부 파일(`/data/data/...`)을 직접 열
> 수 없으므로 상태 확인은 **앱 로그**로 한다. Google APIs 이미지를 쓰면 root 가 되지만
> 실제 사용자 환경과 멀어진다.

### 설치

```bash
{PYTHON} {SCRIPTS}/launch_cli.py app install --device "$DEV" --path {apk}   # 준비 확인 > push > pm install -r -t (단계별 시간 한도)
adb -s "$DEV" uninstall {패키지} && adb -s "$DEV" install {apk}   # 서명이 다르면 이 순서
adb -s "$DEV" shell pm clear {패키지}        # 데이터만 초기화 (앱은 유지)
```

`app install` 은 부팅 직후 `Broken pipe` / `Can't find service: package` 를 만나면 서비스가 돌아오길 기다려 **한 번** 다시 한다.
기기가 안 답하면 `device_unresponsive` + 호스트 메모리 수치(`resources`)와 `next: device reboot --device <id> --cold` 를 낸다.

`INSTALL_FAILED_UPDATE_INCOMPATIBLE` 은 서명 불일치다. CI 빌드와 로컬 빌드는 키가 다르다.

### 조작

```bash
{PYTHON} {SCRIPTS}/launch_cli.py app launch --device "$DEV" --pkg "$PKG"
{PYTHON} {SCRIPTS}/launch_cli.py app terminate --device "$DEV" --pkg "$PKG"

{PYTHON} {SCRIPTS}/launch_cli.py app tap   --device "$DEV" --text "{화면 문구}" --shot {이름}
{PYTHON} {SCRIPTS}/launch_cli.py app swipe --device "$DEV" --dir up
adb -s "$DEV" shell input text "{문자열}"          # 공백은 %s, 한글은 입력되지 않는 기기가 있다
adb -s "$DEV" shell input keyevent KEYCODE_BACK    # 키보드 내리기 / 뒤로
adb -s "$DEV" shell input keyevent KEYCODE_ENTER   # 완료 키
```

한글이 입력되지 않으면 영문으로 대체하고 그 사실을 기록한다.

### 글자 입력 — 로그인 정보는 저장된 것으로 (Android · iOS)

```bash
{PYTHON} {SCRIPTS}/launch_cli.py app type --device "$DEV" --cred naver-test --cred-field account
{PYTHON} {SCRIPTS}/launch_cli.py app type --device "$DEV" --cred naver-test --submit      # 비밀번호 + Enter
```

- 값은 **명령줄이 아니라 표준입력**으로만 기기에 간다(호스트 `ps` 에 남지 않는다). `--text` 로 값을 직접 주는 방식은 없다.
- 포커스된 입력창에 들어간다 — 입력창은 먼저 `app tap --text|--id`(요소 기준)로 눌러 포커스를 준다. 입력 뒤에는 `app shot` 으로 확인한다.
- **`adb input text` 는 ASCII 만 된다**(한글 불가 → `non_ascii_unsupported`). 한글이 필요하면 IME 를 설치한다.
- **ASCII 라도 한국어·일본어·중국어 키보드에서는 자모로 조합된다.** `--ime auto`(기본)가 조합형 키보드를 알아보면 입력하는 동안만 글자를 그대로 넣는 입력기(Maestro IME · ADBKeyboard)로 바꿨다가 되돌린다.
  입력 뒤 입력칸을 다시 읽어 다르면 `typed_text_mismatch`(비밀이면 길이만, 값은 싣지 않음 · 비밀번호 칸은 `verification: skipped_password_field`). `--ime keep` 은 바꾸지 않는다, `--ime ascii` 는 강제로 바꾼다. 입력기는 기기 전역 설정이라 남의 기기면 먼저 묻는다.
- **iOS 는 Maestro `inputText` 로 넣는다(#895).** 값은 `MAESTRO_` 환경변수로만 넘겨 flow 파일·명령줄에 남지 않는다.
  Maestro 가 없으면 `ios_tool_missing`(`next` 에 설치 명령), 실패하면 `app_type_failed`(출력의 값은 `***`). 호출당 10~40초.
  상주 세션이 있어도 type 은 타지 않는다(`session_fallback: secret_input_per_call`, 위 "iOS 상주 세션").
- 저장된 로그인 정보가 없으면 사용자에게 묻고, **허락받은 것만 `cred set`** 한다(`references/web.md` 의 "로그인 정보를 저장할 때").
- 결과의 `login_policy` 로 앱 안 로그인 중간 화면(기기 신뢰 · 로그인 유지 · 권유)을 처리한다 — 규칙은 웹과 같다
  (`references/web.md` 의 "로그인 중간 화면", "2단계 인증"). 화면은 `app shot` · 트리로 읽고, 캡처를 대화로 보내며,
  코드는 대화로 받아 `app type --text-env` 로 넣는다. 승인 대기는 화면을 다시 읽어 넘어갔는지 확인한다.

### 관측

```bash
{PYTHON} {SCRIPTS}/launch_cli.py app shot --device "$DEV" --out {이름}
adb -s "$DEV" shell dumpsys window | grep mCurrentFocus    # 현재 화면
adb -s "$DEV" logcat -c                                     # 버퍼 비우기
adb -s "$DEV" logcat -d | grep -i flutter                   # 앱 로그
adb -s "$DEV" logcat -d -b crash | tail -40                 # 크래시

# 녹화 (애니메이션 확인용)
adb -s "$DEV" shell screenrecord --time-limit {초} --bit-rate 12000000 /sdcard/rec.mp4
adb -s "$DEV" pull /sdcard/rec.mp4 "$RUN_DIR/{이름}.mp4" && adb -s "$DEV" shell rm /sdcard/rec.mp4
```

`app shot` 이 `capture_failed` 로 멈추면 화면이 잠겼거나 보안 화면(`FLAG_SECURE`)이다.
보안 화면은 캡처가 검게 나오거나 막힌다 — 앱이 일부러 막은 것이라 결함이 아니다.

### 움직임을 수치로 확인하기

```bash
ffmpeg -i rec.mp4 -vf "fps=60,crop={w}:{h}:{x}:{y}" frames/f%03d.png
```

`crop` 은 **측정할 요소 크기로 좁힌다.** 넓게 자르면 제목·키보드가 함께 잡혀 무게중심이
엉뚱하게 움직인다 (이 실수로 화면 전환을 흔들림으로 오인한 적이 있다).

---

## iOS 시뮬레이터

```bash
xcrun simctl list devices                      # 목록
{PYTHON} {SCRIPTS}/launch_cli.py device boot --device "{기기명 또는 UDID}"            # 창 없이 부팅 (기본 headless)
{PYTHON} {SCRIPTS}/launch_cli.py device boot --device "{기기명}" --window small      # 창 배율 0.4 로 연다
{PYTHON} {SCRIPTS}/launch_cli.py device boot --device "{기기명}" --scale 0.5         # 배율을 직접 (0.3~1.0, 주면 창을 연다)

{PYTHON} {SCRIPTS}/launch_cli.py app install --device {UDID} --path {Runner.app}   # .app 폴더 (.ipa 는 실기기용)
{PYTHON} {SCRIPTS}/launch_cli.py app launch --device {UDID} --pkg {번들ID}
{PYTHON} {SCRIPTS}/launch_cli.py app terminate --device {UDID} --pkg {번들ID}
xcrun simctl uninstall {UDID} {번들ID}

{PYTHON} {SCRIPTS}/launch_cli.py app shot --device {UDID} --out {이름} --clean-status
xcrun simctl io {UDID} recordVideo {경로}.mp4   # Ctrl+C로 종료
```

`--pkg` 에는 번들 ID 를 준다. 자기 앱은 `detect --path .` 가 돌려주는 번들 ID 를 쓴다.
시스템 앱 예: 설정 `com.apple.Preferences` · 사파리 `com.apple.mobilesafari` · 사진 `com.apple.mobileslideshow`.

### iOS 시뮬레이터는 좌표로 누르지 않는다 ⚠️

**금지: `cliclick` · AppleScript/`osascript`(System Events) 로 Simulator 창 클릭 · CGEvent 등,
호스트 마우스를 움직여 화면 좌표를 누르는 모든 방법.**

- 사용자의 **실제 커서를 움직인다.** 사용자가 다른 앱에서 일하는 중이면 방해하고, 엉뚱한 앱을 누른다
  (실사고: 시뮬레이터가 아닌 다른 앱이 눌렸다).
- 창 위치·크기, 앞에 뜬 창에 의존해 빗나가고 **무엇이 눌렸는지 알 수 없다.**

조작이 필요하면 이 순서로 한다:

0. **한두 번 누르는 것은 `app tap --text` · `app swipe`, 여러 단계는 `app run --steps` 로 한다.** 안에서 Maestro 를 불러 접근성 정보로
   요소를 찾으므로 호스트 커서를 건드리지 않는다. Maestro 가 없으면 `ios_tool_missing` 과 `next` 에 설치 명령이 온다.
1. **긴 시나리오는 프로젝트에 이미 있는 E2E 방식을 먼저 찾는다.** `e2e/` · `.maestro/` · `tool/*e2e*` ·
   `integration_test/` 를 본다. 있으면 그것을 쓴다 — 위젯 **텍스트로 찾으므로** 좌표가 필요 없다.
   원래 쓰던 방식을 확인하지 않고 임의로 고르지 않는다.
2. 없으면 **사용자에게 어느 방법을 쓸지 묻는다**: Maestro 플로우 작성 / `flutter drive`·`integration_test`
   작성 / 몇 단계 안 되면 사용자가 직접 조작.
3. **좌표 없이** 되는 것은 `app` 동작을 쓴다: 실행·종료(`app launch|terminate|relaunch`) · 딥링크(`app openurl`) ·
   권한(`app permission`) · 위치(`app location`) · 푸시(`app push`) · 캡처(`app shot`). 녹화만 `simctl` 을 직접 쓴다.

**앱 밖 화면은 자동으로 못 누른다.** 네이버·구글 같은 웹 인증 창은 앱 바깥이라 E2E 로 조작할 수 없다.
앱이 인증 요청을 보내는 데까지만 자동으로 확인하고, 그 안은 사용자에게 부탁한다.

생체 인증은 시뮬레이터 메뉴로 대체할 수 있다: `Features → Face ID → Matching Face`.

---

## 기기가 여러 대일 때

```bash
{PYTHON} {SCRIPTS}/launch_cli.py device list
{PYTHON} {SCRIPTS}/launch_cli.py device bind --role A --serial {시리얼} --note "{이 역할이 무엇인지}"
```

`env.sh` 에 `ROLE1='A'; DEV1='{시리얼}'` 처럼 **번호로** 들어간다.

> ⚠️ **역할 이름을 셸 변수명에 쓰지 않는다.** 한글·공백·하이픈이 든 이름은
> `export DEV_{이름}=...` 이 거부되고, `$DEV_{이름}` 은 **터지지 않고 엉뚱한 값으로 전개된다.**

`device list` 는 역할마다 설치된 빌드를 **APK 해시로** 대조해 다르면 `build_mismatch` 로 알린다.
**버전으로 재면 안 된다** — 컴파일타임 플래그만 바꾼 재빌드는 버전이 똑같다(#603).
불일치가 보고되면 거기서 멈추고 양쪽을 맞춘다.

## 빌드 플래그 ⚠️

| 함정 | 대응 |
|---|---|
| **빌드 인자로 넘겼는데 안 먹는다** | 앱이 그 플래그를 **어디서 읽는지** 본다. 컴파일타임(`String.fromEnvironment` 등)과 런타임 설정 파일(dotenv 등)은 **다른 층**이다 |
| **설정 파일 끝에 덧붙였는데 무시된다** | 같은 키가 두 번이면 대개 **앞의 것이 이긴다.** 그 줄을 직접 바꾼다 |
| **테스트용 플래그가 그대로 남는다** | 쓰고 나면 **바로** 되돌린다. 기기가 여러 대면 켠 기기를 전부 |

> **한 층만 맞아도 빌드는 통과한다.** 로그가 "적용 완료"라고 해도 실제로는 꺼져 있을 수
> 있다 — 설치해서 그 기능이 화면에 실제로 있는지 본다.
