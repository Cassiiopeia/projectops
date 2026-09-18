# 기기 제어 명령 모음

`pro-agent-test` Phase 0·3·4에서 쓰는 명령. 플랫폼별로 나눠 둔다.

## 공통 — PATH

Android SDK 도구는 PATH에 없을 수 있다. 매 호출에 붙인다.

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

> **Google Play 이미지는 `adb root`가 안 된다.** 앱 내부 파일(`/data/data/...`)을 직접 열
> 수 없으므로 상태 확인은 **앱 로그**로 한다 (SKILL.md Phase 2). Google APIs 이미지를 쓰면
> root가 되지만, 실제 사용자 환경과 멀어진다 — 로그 방식을 권한다.

### 설치

```bash
adb -s "$DEV" install -r {apk}              # 덮어쓰기 (데이터 유지)
adb -s "$DEV" uninstall {패키지} && adb -s "$DEV" install {apk}   # 서명이 다르면 이 순서
adb -s "$DEV" shell pm clear {패키지}        # 데이터만 초기화 (앱은 유지)
```

`INSTALL_FAILED_UPDATE_INCOMPATIBLE`은 서명 불일치다. CI 빌드와 로컬 빌드는 키가 다르다.

### 조작

```bash
adb -s "$DEV" shell am start -n {패키지}/.MainActivity
adb -s "$DEV" shell am force-stop {패키지}

adb -s "$DEV" shell input tap {x} {y}
adb -s "$DEV" shell input swipe {x1} {y1} {x2} {y2} {ms}
adb -s "$DEV" shell input text "{문자열}"          # 공백은 %s, 한글은 입력되지 않는 기기가 있다
adb -s "$DEV" shell input keyevent KEYCODE_BACK    # 키보드 내리기 / 뒤로
adb -s "$DEV" shell input keyevent KEYCODE_ENTER   # 완료 키
```

한글이 입력되지 않으면 영문으로 대체하고 그 사실을 보고에 적는다 (테스트 목적상 값 자체가
중요한 경우가 아니면 문제되지 않는다).

### 관측

```bash
adb -s "$DEV" exec-out screencap -p > "$SHOT_DIR/{이름}.png"
adb -s "$DEV" shell dumpsys window | grep mCurrentFocus    # 현재 화면
adb -s "$DEV" logcat -c                                     # 버퍼 비우기
adb -s "$DEV" logcat -d | grep -i flutter                   # 앱 로그
adb -s "$DEV" logcat -d -b crash | tail -40                 # 크래시

# 녹화 (애니메이션 확인용)
adb -s "$DEV" shell screenrecord --time-limit {초} --bit-rate 12000000 /sdcard/rec.mp4
adb -s "$DEV" pull /sdcard/rec.mp4 "$RUN_DIR/{이름}.mp4" && adb -s "$DEV" shell rm /sdcard/rec.mp4
```

### 움직임을 수치로 확인하기

애니메이션 품질을 눈대중이 아니라 값으로 보려면 프레임을 뽑아 위치를 측정한다.

```bash
ffmpeg -i rec.mp4 -vf "fps=60,crop={w}:{h}:{x}:{y}" frames/f%03d.png
```

`crop`은 **측정할 요소 크기로 좁힌다.** 넓게 자르면 제목·키보드가 함께 잡혀 무게중심이
엉뚱하게 움직인다 (실제로 이 실수로 화면 전환을 흔들림으로 오인한 적이 있다).

---

## iOS 시뮬레이터

```bash
xcrun simctl list devices                      # 목록
xcrun simctl boot "{기기명}"                    # 부팅
open -a Simulator                              # 창 띄우기

xcrun simctl install booted {앱.app}
xcrun simctl launch booted {번들ID}
xcrun simctl terminate booted {번들ID}
xcrun simctl uninstall booted {번들ID}

xcrun simctl io booted screenshot {경로}.png
xcrun simctl io booted recordVideo {경로}.mp4   # Ctrl+C로 종료
```

### 좌표 조작의 제약 ⚠️

**시뮬레이터에는 `adb shell input tap`에 해당하는 공식 명령이 없다.** 선택지는:

| 방법 | 쓸 수 있는 때 |
| --- | --- |
| `flutter drive` / `integration_test` | 앱에 테스트 하네스를 넣을 수 있을 때 |
| AppleScript로 Simulator 창 클릭 | 화면 좌표 → 창 좌표 환산 필요, 창 위치에 의존 |
| 사용자에게 조작을 부탁 | 몇 단계 안 되는 확인일 때 |

iOS에서 좌표 조작이 필요하면 **먼저 사용자에게 어느 방법을 쓸지 확인한다.** 임의로
AppleScript를 쓰면 창 위치가 달라 엉뚱한 곳을 누른다.

생체 인증은 시뮬레이터 메뉴로 대체할 수 있다: `Features → Face ID → Matching Face`.
명령으로는 `xcrun simctl ui booted ...` 계열이 버전마다 달라 신뢰하기 어렵다.

---

## 앱에서만 나는 함정

### 화면

| 함정 | 대응 |
|---|---|
| **큰 글씨로 바꿨는데 글자가 안 커진다** | 앱 전체가 무시한다고 단정하기 전에 **그 화면이 스케일 단위를 쓰는지** 본다 (Flutter 라면 `flutter_screenutil` 의 `.sp` 같은 것). 일부 화면만 고정 크기를 쓰는 경우가 흔하다 — 일반 화면에서 다시 재 본다 |
| **뒤로가기가 안 되는 화면이 있다** | 라우터가 화면을 **교체**하며 열었는지 **쌓으며** 열었는지 본다 (`go_router` 의 `go` vs `push`). 교체였으면 돌아갈 자리가 없다. 화살표만 고치면 **기기 뒤로가기는 여전히 막힌다** — 둘을 따로 밟는다 |

### 빌드 플래그 ⚠️

개발 스위치가 안 먹을 때 가장 많이 헤매는 자리다.

| 함정 | 대응 |
|---|---|
| **빌드 인자로 넘겼는데 안 먹는다** | 그 플래그를 앱이 **어디서 읽는지** 확인한다. 컴파일타임(`String.fromEnvironment` 등)과 런타임 설정 파일(dotenv 등)은 **다른 층**이고, 한 앱이 둘을 섞어 쓴다 |
| **설정 파일 끝에 덧붙였는데 무시된다** | 같은 키가 두 번 있으면 대개 **앞의 것이 이긴다.** 덧붙이지 말고 그 줄을 직접 바꾼다 |
| **테스트용 플래그가 그대로 남는다** | 빌드 직후 **바로** 되돌린다. 미루면 그 상태로 커밋되거나 다음 빌드가 어긋난다. 기기가 여러 대면 **켠 기기를 전부** 되돌린다 |

> **한 층만 맞아도 빌드는 통과한다.** 로그가 "적용 완료"라고 해도 실제로는 꺼져 있을 수
> 있다 — 설치해서 그 기능이 화면에 실제로 있는지 눌러 본다. 파일만 봐서는 알 수 없다.

## 서버 데이터 대조

프로젝트 설정에서 접속 정보를 읽는다. **하드코딩하지 않는다.**

```bash
# Spring 예시 — 설정 파일에서 추출
YML={프로젝트}/src/main/resources/application-{프로파일}.yml
URL=$(grep -m1 "jdbc:postgresql" "$YML" | sed 's|.*jdbc:postgresql://||; s/[[:space:]]*$//')
export PGHOST="${URL%%:*}"
REST="${URL#*:}"; export PGPORT="${REST%%/*}"; export PGDATABASE="${REST#*/}"
export PGUSER=$(grep -A4 datasource "$YML" | grep -m1 username: | sed 's/.*username: *//' | tr -d "\"' ")
export PGPASSWORD=$(grep -A4 datasource "$YML" | grep -m1 password: | sed 's/.*password: *//' | tr -d "\"' ")
psql -c "select ..."
```

> 설정 파일은 대개 gitignore 대상이다. **값을 출력하거나 커밋하지 않는다.**
> 셸 변수로만 넘기고, 보고에는 호스트·DB명 정도만 적는다.
