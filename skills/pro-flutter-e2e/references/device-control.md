# 기기 제어 명령 모음

`pro-flutter-e2e` Phase 0·3·4에서 쓰는 명령. 플랫폼별로 나눠 둔다.

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
  [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ] && break
  sleep 10
done
```

> **Google Play 이미지는 `adb root`가 안 된다.** 앱 내부 파일(`/data/data/...`)을 직접 열
> 수 없으므로 상태 확인은 **앱 로그**로 한다 (SKILL.md Phase 2). Google APIs 이미지를 쓰면
> root가 되지만, 실제 사용자 환경과 멀어진다 — 로그 방식을 권한다.

### 설치

```bash
adb install -r {apk}              # 덮어쓰기 (데이터 유지)
adb uninstall {패키지} && adb install {apk}   # 서명이 다르면 이 순서
adb shell pm clear {패키지}        # 데이터만 초기화 (앱은 유지)
```

`INSTALL_FAILED_UPDATE_INCOMPATIBLE`은 서명 불일치다. CI 빌드와 로컬 빌드는 키가 다르다.

### 조작

```bash
adb shell am start -n {패키지}/.MainActivity
adb shell am force-stop {패키지}

adb shell input tap {x} {y}
adb shell input swipe {x1} {y1} {x2} {y2} {ms}
adb shell input text "{문자열}"          # 공백은 %s, 한글은 입력되지 않는 기기가 있다
adb shell input keyevent KEYCODE_BACK    # 키보드 내리기 / 뒤로
adb shell input keyevent KEYCODE_ENTER   # 완료 키
```

한글이 입력되지 않으면 영문으로 대체하고 그 사실을 보고에 적는다 (테스트 목적상 값 자체가
중요한 경우가 아니면 문제되지 않는다).

### 관측

```bash
adb exec-out screencap -p > {경로}.png
adb shell dumpsys window | grep mCurrentFocus    # 현재 화면
adb logcat -c                                     # 버퍼 비우기
adb logcat -d | grep -i flutter                   # 앱 로그
adb logcat -d -b crash | tail -40                 # 크래시

# 녹화 (애니메이션 확인용)
adb shell screenrecord --time-limit {초} --bit-rate 12000000 /sdcard/rec.mp4
adb pull /sdcard/rec.mp4 {경로} && adb shell rm /sdcard/rec.mp4
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
