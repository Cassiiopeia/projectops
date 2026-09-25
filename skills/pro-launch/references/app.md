# 앱에 붙는 법 — Android 에뮬레이터 · iOS 시뮬레이터 · 실기기

`launch_cli.py app shot` · `app launch` 로 안 되는 조작(탭·설치·로그·녹화)은 도구를 직접 쓴다.
**모든 adb 명령에 `-s "$DEV"` 를 붙인다.** 기기가 여러 대면 빠뜨린 명령이 엉뚱한 쪽으로 간다.

## PATH

Android SDK 도구는 PATH 에 없을 수 있다. `doctor`·`devices` 결과의 `adb_path` 를 그대로 쓰거나:

```bash
export PATH="$PATH:$HOME/Library/Android/sdk/platform-tools:$HOME/Library/Android/sdk/emulator"
```

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

adb -s "$DEV" shell input tap {x} {y}
adb -s "$DEV" shell input swipe {x1} {y1} {x2} {y2} {ms}
adb -s "$DEV" shell input text "{문자열}"          # 공백은 %s, 한글은 입력되지 않는 기기가 있다
adb -s "$DEV" shell input keyevent KEYCODE_BACK    # 키보드 내리기 / 뒤로
adb -s "$DEV" shell input keyevent KEYCODE_ENTER   # 완료 키
```

한글이 입력되지 않으면 영문으로 대체하고 그 사실을 기록한다.

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

### 좌표 조작의 제약 ⚠️

**시뮬레이터에는 `adb shell input tap` 에 해당하는 공식 명령이 없다.**

| 방법 | 쓸 수 있는 때 |
| --- | --- |
| `flutter drive` / `integration_test` | 앱에 테스트 하네스를 넣을 수 있을 때 |
| AppleScript 로 Simulator 창 클릭 | 화면 좌표 → 창 좌표 환산 필요, 창 위치에 의존 |
| 사용자에게 조작을 부탁 | 몇 단계 안 되는 확인일 때 |

iOS 에서 좌표 조작이 필요하면 **먼저 사용자에게 어느 방법을 쓸지 확인한다.**

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
