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
  없다). 호출마다 Maestro 가 새로 떠서 10~40초 걸리니, 긴 시나리오는 프로젝트의 Maestro flow 로 한 번에 돌린다.

| code | 다음 행동 |
|---|---|
| `no_device` | `devices` 로 목록을 보고 `--device` 를 준다 |
| `not_found` · `index_out_of_range` | `candidates` 에서 고른다. 화면 언어는 `locale` |
| `ui_dump_failed` | 화면이 전환 중이거나 보안 화면이다. 잠시 뒤 `app tree` 를 다시 본다 |
| `ios_tool_missing` · `android_tool_missing` | `next` 의 설치 명령(iOS 는 Maestro)을 사용자에게 제안한다 |
| `adb_missing` | 아래 PATH 를 잡거나 `doctor` 의 `adb_path` 를 쓴다 |
| `capture_failed` | 잠긴 화면이거나 `FLAG_SECURE` 다(아래 "관측") |

새 플랫폼(백엔드)을 붙이는 법은 `extending.md`.

---

## Android

### 기기 준비

```bash
adb devices                       # 연결 확인
emulator -list-avds               # 쓸 수 있는 AVD 목록

# 부팅 (백그라운드) — 완료까지 기다린다
nohup emulator -avd {AVD명} -no-snapshot-load >/dev/null 2>&1 &
for i in $(seq 1 40); do
  [ "$(adb -s "$DEV" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ] && break
  sleep 10
done
```

기기를 나중에 띄웠으면 `device list` 를 한 번 더 돌린다 — `env.sh` 의 `$DEV` 를 채운다.

> **Google Play 이미지는 `adb root`가 안 된다.** 앱 내부 파일(`/data/data/...`)을 직접 열
> 수 없으므로 상태 확인은 **앱 로그**로 한다. Google APIs 이미지를 쓰면 root 가 되지만
> 실제 사용자 환경과 멀어진다.

### 설치

```bash
adb -s "$DEV" install -r {apk}              # 덮어쓰기 (데이터 유지)
adb -s "$DEV" uninstall {패키지} && adb -s "$DEV" install {apk}   # 서명이 다르면 이 순서
adb -s "$DEV" shell pm clear {패키지}        # 데이터만 초기화 (앱은 유지)
```

`INSTALL_FAILED_UPDATE_INCOMPATIBLE` 은 서명 불일치다. CI 빌드와 로컬 빌드는 키가 다르다.

### 조작

```bash
{PYTHON} {SCRIPTS}/launch_cli.py app launch --device "$DEV" --pkg "$PKG"
adb -s "$DEV" shell am force-stop {패키지}

{PYTHON} {SCRIPTS}/launch_cli.py app tap   --device "$DEV" --text "{화면 문구}" --shot {이름}
{PYTHON} {SCRIPTS}/launch_cli.py app swipe --device "$DEV" --dir up
adb -s "$DEV" shell input text "{문자열}"          # 공백은 %s, 한글은 입력되지 않는 기기가 있다
adb -s "$DEV" shell input keyevent KEYCODE_BACK    # 키보드 내리기 / 뒤로
adb -s "$DEV" shell input keyevent KEYCODE_ENTER   # 완료 키
```

한글이 입력되지 않으면 영문으로 대체하고 그 사실을 기록한다.

### 글자 입력 — 로그인 정보는 저장된 것으로 (Android)

```bash
{PYTHON} {SCRIPTS}/launch_cli.py app type --device "$DEV" --cred naver-test --cred-field account
{PYTHON} {SCRIPTS}/launch_cli.py app type --device "$DEV" --cred naver-test --submit      # 비밀번호 + Enter
```

- 값은 **명령줄이 아니라 표준입력**으로만 기기에 간다(호스트 `ps` 에 남지 않는다). `--text` 로 값을 직접 주는 방식은 없다.
- 포커스된 입력창에 들어간다 — 누르는 것은 지금처럼 좌표로 한다. 입력 뒤에는 `app shot` 으로 확인한다.
- **`adb input text` 는 ASCII 만 된다**(한글 불가 → `non_ascii_unsupported`). 한글이 필요하면 IME 를 설치한다.
- iOS 시뮬레이터에는 텍스트를 넣는 공식 명령이 없다(`ios_text_unsupported`) — Maestro 같은 도구나 사용자에게 맡긴다.
- 저장된 로그인 정보가 없으면 사용자에게 묻고, **허락받은 것만 `cred set`** 한다(`references/web.md` 의 "로그인 정보를 저장할 때").

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
xcrun simctl boot "{기기명}"                    # 부팅
open -a Simulator                              # 창 띄우기

xcrun simctl install {UDID} {앱.app}
{PYTHON} {SCRIPTS}/launch_cli.py app launch --device {UDID} --pkg {번들ID}
xcrun simctl terminate {UDID} {번들ID}
xcrun simctl uninstall {UDID} {번들ID}

{PYTHON} {SCRIPTS}/launch_cli.py app shot --device {UDID} --out {이름} --clean-status
xcrun simctl io {UDID} recordVideo {경로}.mp4   # Ctrl+C로 종료
```

### iOS 시뮬레이터는 좌표로 누르지 않는다 ⚠️

**금지: `cliclick` · AppleScript/`osascript`(System Events) 로 Simulator 창 클릭 · CGEvent 등,
호스트 마우스를 움직여 화면 좌표를 누르는 모든 방법.**

- 사용자의 **실제 커서를 움직인다.** 사용자가 다른 앱에서 일하는 중이면 방해하고, 엉뚱한 앱을 누른다
  (실사고: 시뮬레이터가 아닌 다른 앱이 눌렸다).
- 창 위치·크기, 앞에 뜬 창에 의존해 빗나가고 **무엇이 눌렸는지 알 수 없다.**

조작이 필요하면 이 순서로 한다:

0. **한두 번 누르는 것은 `app tap --text` · `app swipe` 로 한다.** 안에서 Maestro 를 불러 접근성 정보로
   요소를 찾으므로 호스트 커서를 건드리지 않는다. Maestro 가 없으면 `ios_tool_missing` 과 `next` 에 설치 명령이 온다.
1. **긴 시나리오는 프로젝트에 이미 있는 E2E 방식을 먼저 찾는다.** `e2e/` · `.maestro/` · `tool/*e2e*` ·
   `integration_test/` 를 본다. 있으면 그것을 쓴다 — 위젯 **텍스트로 찾으므로** 좌표가 필요 없다.
   원래 쓰던 방식을 확인하지 않고 임의로 고르지 않는다.
2. 없으면 **사용자에게 어느 방법을 쓸지 묻는다**: Maestro 플로우 작성 / `flutter drive`·`integration_test`
   작성 / 몇 단계 안 되면 사용자가 직접 조작.
3. `simctl` 로 **좌표 없이** 되는 것은 그대로 쓴다: 실행 · 종료 · 딥링크(`xcrun simctl openurl {UDID} {URL}`) ·
   권한(`xcrun simctl privacy`) · 캡처 · 녹화.

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
