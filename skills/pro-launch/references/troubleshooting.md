# 공식 트러블슈팅

> 생성물이다 — 손으로 고치지 않는다. 원본은 `troubleshooting/<area>/<id>.json`,
> 다시 만들기: `python3 scripts/build_troubleshooting.py skills/<skill>` (레포 루트에서).
> 작성 규칙: `skills/references/memory-principles.md` §6. 실패 응답의 `known_fix` 가 이 항목들의 요약이다.

## 웹 (`web`)

| id | 제목 | 코드 |
|---|---|---|
| `browser-start-stale-process-or-lock` | web open 이 browser_start_failed — 남은 브라우저 프로세스나 프로필 잠금 | `browser_start_failed` |
| `web-browser-gone` | web 명령이 browser_gone — 띄워 둔 브라우저에 붙지 못했다 | `browser_gone` |
| `web-browser-not-open-other-root` | 방금 연 브라우저인데 browser_not_open — 다른 프로젝트 자리로 불렸다 | `browser_not_open` |
| `web-click-wait-with-expect` | sleep 으로 기다리지 말고 click 의 --expect-url · --expect-text 로 | `expect_not_met` |
| `web-find-nothing-found` | web find 가 nothing_found — 기본은 누를 수 있는 요소만 찾는다 | `nothing_found` |
| `web-goto-failed` | web open·goto 이동 실패 — 주소·서버·인증서를 본다 | `goto_failed` |
| `web-iframe-login-fields` | iframe 안의 로그인 칸(App Store Connect 등)을 못 찾는다 | — |
| `web-playwright-or-browser-missing` | playwright_missing · browser_missing — web setup 이 필요하다 | `playwright_missing` · `browser_missing` |
| `web-readonly-mutating-blocked` | 읽기 전용 세션에서 저장·제출 버튼이 mutating_blocked | `mutating_blocked` |
| `web-selector-guess-timeout` | 추측한 --selector 가 시간 초과 — web find 로 고르고 --ref 로 누른다 | `selector_not_found` · `element_disabled` |
| `web-viewport-width-height` | web viewport --width --height 가 bad_viewport — 크기는 --preset 으로 | `bad_viewport` |

### `browser-start-stale-process-or-lock` — web open 이 browser_start_failed — 남은 브라우저 프로세스나 프로필 잠금

- 코드: `browser_start_failed`
- 핵심어: SingletonLock, SingletonSocket, profile_locked, stale_pid
- 증상: web open 이 browser_start_failed 로 끝나고 브라우저가 뜨지 않는다. 응답에 causes·stale_pid·profile_locked 가 온다
- 원인: 이전에 띄운 브라우저가 아직 같은 프로필을 쓰고 있거나 프로필 잠금(SingletonLock·SingletonSocket)이 남아 새 브라우저가 그 프로필로 뜨지 못한다. web open 은 아무 프로세스도 프로필을 쓰지 않을 때만 잠금을 스스로 치운다
- 해결:
  1. launch_cli.py web close
  2. close 가 browser_still_alive 면 응답 next 의 종료 명령(kill -9 <pid> 또는 taskkill)으로 그 pid 를 끝낸다
  3. launch_cli.py web open --url <주소>
  4. 그래도 같으면 응답의 profile 폴더를 쓰는 브라우저가 없는지 확인한 뒤 SingletonLock·SingletonSocket 을 지운다
- 근거: #711, #712 · 확인 2026-10-17

### `web-browser-gone` — web 명령이 browser_gone — 띄워 둔 브라우저에 붙지 못했다

- 코드: `browser_gone`
- 증상: web text·shot·click 이 browser_gone(열린 브라우저에 붙지 못했다)으로 끝난다
- 원인: 상태 파일에 적힌 브라우저(CDP 포트)에 연결하지 못했다 — 그 브라우저가 닫혔거나 응답하지 않는다. CLI 는 상태 파일에서 죽은 브라우저 정보(cdp·pid)만 지우고 뷰포트·바꿔치기 규칙은 남긴다
- 해결:
  1. launch_cli.py web open --url <주소>
  2. open 이 browser_start_failed 면 kb show browser-start-stale-process-or-lock
  3. 로그인이 필요한 사이트면 다시 연 뒤 로그인 상태부터 web text 로 확인한다
- 근거: #825, #889 · 확인 2026-10-17
- 함께 볼 것: `browser-start-stale-process-or-lock`

### `web-browser-not-open-other-root` — 방금 연 브라우저인데 browser_not_open — 다른 프로젝트 자리로 불렸다

- 코드: `browser_not_open`
- 증상: web open 은 성공했는데 다음 web text·shot 이 browser_not_open(열린 브라우저가 없다)을 낸다. next 의 --root 경로가 스크립트·플러그인 캐시·임시 폴더다
- 원인: 브라우저 상태 파일은 프로젝트(git 원격 owner/repo)마다 따로 있다. open 과 다음 명령의 작업 폴더(--root, 기본 '.')가 다르면 서로 다른 상태 파일을 본다. 스크립트 폴더로 cd 하거나 임시 폴더에서 부르면 이렇게 갈린다
- 해결:
  1. launch_cli.py web text --root <프로젝트 경로>
  2. open 부터 같은 --root 로 부른다. cd 로 스크립트 폴더에 들어가지 말고 절대경로로 스크립트를 부른다
  3. 정말 안 떠 있으면: launch_cli.py web open --root <프로젝트 경로> --url <주소>
- 근거: #833, #836, #889 · 확인 2026-10-17
- 함께 볼 것: `general-root-unknown-skill-folder`

### `web-click-wait-with-expect` — sleep 으로 기다리지 말고 click 의 --expect-url · --expect-text 로

- 코드: `expect_not_met`
- 증상: 클릭 뒤 sleep 5 같은 고정 대기를 넣고 web text 로 결과를 확인한다. 느린 화면에서는 아직 안 바뀐 화면을 읽고, 빠른 화면에서는 시간을 버린다. expect_not_met 이 나기도 한다
- 원인: web click 은 --expect-url·--expect-text 를 주면 그것이 나올 때까지(--timeout 초) 기다리고, 안 나오면 expect_not_met 으로 알려 준다. 주지 않으면 짧게만(몇 초) 기다린다. web type 은 칸이 나타날 때까지 --timeout 만큼 스스로 기다린다
- 해결:
  1. launch_cli.py web click --ref <번호> --expect-text <다음 화면 글자> --timeout 30
  2. launch_cli.py web click --ref <번호> --expect-url <바뀔 주소 일부>
  3. expect_not_met 이면 web text 로 지금 화면을 읽는다 — 엉뚱한 것을 눌렀으면 web find 로 다시 고른다
  4. web text·assert 의 --selector 는 기다리지 않는다 — 바로 읽을 것이면 click 의 expect 로 먼저 기다린다
- 근거: #825, #889 · 확인 2026-10-17

### `web-find-nothing-found` — web find 가 nothing_found — 기본은 누를 수 있는 요소만 찾는다

- 코드: `nothing_found`
- 증상: 화면에 글자가 보이는데 web find 가 nothing_found(조건에 맞는 보이는 요소가 없다)를 낸다
- 원인: --selector·--role 이 없으면 링크·버튼·role 이 달린 것 같은 클릭 대상만 본다. 일반 입력칸(input·textarea)은 여기에 없다. --role 은 role 속성이 실제로 붙은 요소만 찾는다(--role textbox 는 <input> 을 못 찾는다). iframe 안도 보지 않는다
- 해결:
  1. launch_cli.py web text --max-chars 3000
  2. launch_cli.py web find --text <text 에서 본 글자 그대로>
  3. 입력칸은 CSS 로 찾는다: launch_cli.py web find --selector input
  4. 그래도 없으면 iframe 안일 수 있다 — kb show web-iframe-login-fields
- 근거: #825, #889 · 확인 2026-10-17
- 함께 볼 것: `web-iframe-login-fields`

### `web-goto-failed` — web open·goto 이동 실패 — 주소·서버·인증서를 본다

- 코드: `goto_failed`
- 핵심어: ERR_CERT_AUTHORITY_INVALID
- 증상: web open --url 이 goto_failed 로, 또는 web goto 가 web_action_failed 로 끝난다. 오류에 Timeout, ERR_CONNECTION_REFUSED, ERR_CERT_* 같은 문구가 있다
- 원인: 이동 자체가 실패했다 — 서버가 안 떴거나 주소가 틀렸거나(Timeout·CONNECTION_REFUSED), 사설·자체서명 인증서라 막혔다(ERR_CERT·ERR_SSL). web goto 는 404·500 페이지도 이동 성공으로 보고 status 로 알려 준다
- 해결:
  1. 로컬 서버면 먼저 떠 있는지 본다: launch_cli.py http --url <주소>
  2. 인증서 오류(테스트 서버 전용): launch_cli.py web close
  3. launch_cli.py web open --ignore-cert-errors --url <주소>  # 새로 띄울 때만 적용된다
- 근거: #711, #889 · 확인 2026-10-17

### `web-iframe-login-fields` — iframe 안의 로그인 칸(App Store Connect 등)을 못 찾는다

- 핵심어: iframe, enter-frame
- 해당: web (Playwright 선택자)
- 증상: 로그인 칸이 화면에 보이는데 web find 가 못 찾고, web type·click --selector 가 시간 초과나 assert_failed 로 끝난다. 'iframe >> input' 처럼 써도 안 맞는다
- 원인: 로그인 폼이 iframe 안에 있다(App Store Connect 로그인 등). web find 는 최상위 문서만 훑는다. type·click·text·assert 의 --selector 는 Playwright 선택자라 iframe 안으로 들어가는 구간(internal:control=enter-frame)이 있어야 닿는다
- 해결:
  1. launch_cli.py web type --selector "iframe >> internal:control=enter-frame >> input#account_name_text_field" --cred <이름> --cred-field account
  2. launch_cli.py web click --selector "iframe >> internal:control=enter-frame >> #sign-in" --expect-text <로그인 뒤 보일 글자>
  3. iframe 이 여럿이면 앞 구간을 iframe#<id> 로 좁힌다. web find 는 iframe 안을 보지 않으니 칸 이름은 web shot 으로 보고 정한다
  4. 읽기 전용(--readonly) 세션이면 로그인 버튼도 막힐 수 있다 — 사용자에게 알리고 --confirm-mutating 을 붙인다
- 근거: #889 · 확인 2026-10-17

### `web-playwright-or-browser-missing` — playwright_missing · browser_missing — web setup 이 필요하다

- 코드: `playwright_missing` · `browser_missing`
- 증상: web open 이 playwright_missing(Playwright 없음) 또는 browser_missing(Chromium 이 설치돼 있지 않다)으로 끝난다
- 원인: 웹 조작은 전용 가상환경(~/.projectops 아래)의 Playwright 와 브라우저를 쓴다. 아직 준비하지 않았거나, 패키지는 있는데 브라우저 파일이 없다
- 해결:
  1. 설치(약 100MB)는 사용자에게 먼저 묻는다: launch_cli.py web setup
  2. 내부망이면 설치된 Chrome·Edge 를 쓴다: LAUNCH_CHROMIUM_PATH=<브라우저 실행 파일 경로> 를 앞에 붙여 web open
  3. web setup 이 pip_failed 면 사내 PyPI 미러로 playwright pillow 를 먼저 깔아 둔다 (사용자에게 먼저 묻는다)
- 근거: #857, #889 · 확인 2026-10-17

### `web-readonly-mutating-blocked` — 읽기 전용 세션에서 저장·제출 버튼이 mutating_blocked

- 코드: `mutating_blocked`
- 증상: web click 이 mutating_blocked(읽기 전용 세션이라 누르지 않았다)로 끝난다
- 원인: web open --readonly 로 연 세션에서는 문구가 삭제·제출·저장·게시 같은 버튼을 --confirm-mutating 없이 누르지 않는다. 링크·탭·행은 이동이라 막지 않는다
- 해결:
  1. 무엇이 바뀌는지 사용자에게 말하고 승인을 받는다 (되돌리기 어려운 조작)
  2. 승인 뒤: launch_cli.py web click --ref <번호> --confirm-mutating
  3. 단순히 화면만 볼 거면 링크·탭으로 이동한다 — 버튼을 누를 필요가 없는지 먼저 본다
- 근거: #825, #889 · 확인 2026-10-17

### `web-selector-guess-timeout` — 추측한 --selector 가 시간 초과 — web find 로 고르고 --ref 로 누른다

- 코드: `selector_not_found` · `element_disabled`
- 핵심어: waiting for locator, Timeout
- 증상: web click·type 이 web_action_failed('Timeout 10000ms exceeded … waiting for locator')나 selector_not_found 로 끝난다. 선택자를 바꿔 가며 같은 실패를 되풀이한다
- 원인: 화면을 읽지 않고 선택자를 추측했다. 맞는 요소가 없거나, 있어도 disabled 라 눌릴 수 없어 대기 시간(--timeout, 기본 10초)을 다 쓴다(오류의 'locator resolved to <button disabled' 가 그 표시)
- 해결:
  1. launch_cli.py web find --text <버튼 글자>
  2. launch_cli.py web click --ref <번호> --expect-url <바뀔 주소 일부>
  3. find·inspect 결과의 disabled 가 true 거나 element_disabled 가 오면, 그 버튼을 켜는 조건(필수 칸 입력·체크)부터 채운다
  4. launch_cli.py web inspect --role input
  5. 입력칸은 web inspect --role input 으로 ref 를 받고 web type --ref <번호> --text <값> 으로 넣는다
- 근거: #825, #889, #888 · 확인 2026-10-17

### `web-viewport-width-height` — web viewport --width --height 가 bad_viewport — 크기는 --preset 으로

- 코드: `bad_viewport`
- 증상: web viewport --width 1280 --height 900 이 bad_viewport(뷰포트 '' 을 모릅니다)로 끝난다
- 원인: viewport 는 --preset 만 읽는다. --width·--height 는 web open 이 새 창을 띄울 때의 창 크기 옵션이라 viewport 에서는 쓰이지 않는다
- 해결:
  1. launch_cli.py web viewport --preset 1280x900
  2. launch_cli.py web viewport --preset mobile
  3. 프리셋은 mobile(390x844) · tablet(820x1180) · desktop(1280x800). 풀 때는 web viewport --clear
- 근거: #889 · 확인 2026-10-17

## Android (`android`)

| id | 제목 | 코드 |
|---|---|---|
| `android-adb-missing` | adb_missing · android_tool_missing — adb 를 찾지 못했다 | `adb_missing` · `android_tool_missing` |
| `android-non-ascii-text` | Android app type 이 non_ascii_unsupported — adb 는 한글을 못 넣는다 | `non_ascii_unsupported` |

### `android-adb-missing` — adb_missing · android_tool_missing — adb 를 찾지 못했다

- 코드: `adb_missing` · `android_tool_missing`
- 증상: Android 기기 조작이 adb_missing 이나 android_tool_missing 으로 끝난다
- 원인: adb 가 PATH 에도, 표준 SDK 자리(~/Library/Android/sdk, ~/Android/Sdk, $ANDROID_HOME, $ANDROID_SDK_ROOT 의 platform-tools)에도 없다
- 해결:
  1. SDK 가 다른 곳에 있으면 ANDROID_HOME=<SDK 경로> 를 앞에 붙여 다시 부른다
  2. launch_cli.py doctor
  3. SDK platform-tools 설치는 사용자에게 먼저 묻는다
- 근거: #889 · 확인 2026-10-17

### `android-non-ascii-text` — Android app type 이 non_ascii_unsupported — adb 는 한글을 못 넣는다

- 코드: `non_ascii_unsupported`
- 증상: Android 에서 app type 으로 한글을 넣으려 하면 non_ascii_unsupported 로 끝난다
- 원인: Android 입력은 adb input text 를 쓰는데 ASCII 만 받는다
- 해결:
  1. 영문·숫자 값으로 바꿔 넣을 수 있으면 그렇게 한다
  2. 한글이 꼭 필요하면 ADBKeyboard 같은 IME 설치를 사용자에게 먼저 묻는다
  3. 안 되면 사용자에게 직접 입력을 부탁한다
- 근거: #889 · 확인 2026-10-17

## iOS (`ios`)

| id | 제목 | 코드 |
|---|---|---|
| `ios-maestro-not-installed` | iOS app tap·swipe·tree 가 ios_tool_missing — Maestro 미설치 | `ios_tool_missing` |
| `ios-maestro-slow-cold-start` | iOS app tap·swipe·tree 가 수십 초 걸린다 — 호출마다 Maestro(JVM)가 뜬다 | — |

### `ios-maestro-not-installed` — iOS app tap·swipe·tree 가 ios_tool_missing — Maestro 미설치

- 코드: `ios_tool_missing`
- 해당: macOS + iOS 시뮬레이터
- 증상: iOS 시뮬레이터에서 app tap·app swipe·app tree 가 ios_tool_missing(ios 조작 도구가 없다)으로 멈춘다
- 원인: simctl 에는 탭·화면구조 명령이 없어 iOS 조작은 Maestro 에 맡긴다. maestro 가 PATH 에도 ~/.maestro/bin/maestro 에도 없다
- 해결:
  1. 설치는 사용자에게 먼저 묻는다: curl -fsSL "https://get.maestro.mobile.dev" | bash
  2. launch_cli.py app tree --device <시뮬레이터 id>
  3. 호출마다 Maestro(JVM)가 새로 떠 10~40초 걸린다 — 긴 시나리오는 프로젝트의 Maestro flow 로 한 번에 돌린다
- 근거: #826 · 확인 2026-10-17

### `ios-maestro-slow-cold-start` — iOS app tap·swipe·tree 가 수십 초 걸린다 — 호출마다 Maestro(JVM)가 뜬다

- 핵심어: maestro, 90초
- 증상: iOS 시뮬레이터에서 app tap·swipe·tree 가 한 번에 20~50초 걸리거나 'maestro 응답 없음 (90초)'로 실패한다. Android 는 몇 초다
- 원인: simctl 에는 탭·화면구조 명령이 없어 iOS 조작은 Maestro 에 맡기고, 호출마다 Maestro(JVM)가 새로 뜬다. 한 동작 제한은 90초다. 고장이 아니라 예상된 느림이다
- 해결:
  1. 느리다고 같은 명령을 겹쳐 부르지 않는다 — 앞 호출이 끝나길 기다린다
  2. 화면 확인은 따로 shot 을 부르지 말고 동작에 --shot 을 붙인다: launch_cli.py app tap --device <UDID> --text <글자> --shot <이름>
  3. 긴 시나리오는 프로젝트의 Maestro flow 로 한 번에 돌린다
- 근거: #826, #889 · 확인 2026-10-17
- 함께 볼 것: `ios-maestro-not-installed`

## SSH (`ssh`)

| id | 제목 | 코드 |
|---|---|---|
| `ssh-sshpass-missing` | 암호 ssh 가 sshpass_missing — 키 접속이나 호환 경로로 | `sshpass_missing` |

### `ssh-sshpass-missing` — 암호 ssh 가 sshpass_missing — 키 접속이나 호환 경로로

- 코드: `sshpass_missing`
- 증상: launch_cli.py ssh 가 sshpass_missing(암호 접속에는 sshpass 가 필요하다)으로 끝난다
- 원인: 저장된 서버가 암호 접속인데 sshpass 가 설치돼 있지 않다. 키(key_path)로 접속하면 sshpass 가 필요 없다
- 해결:
  1. 키가 있으면: launch_cli.py ssh --cred <서버> --key-path <키 파일> --command '<명령>'
  2. sshpass 설치는 사용자에게 먼저 묻는다: brew install hudochenkov/sshpass/sshpass
  3. 설치가 안 되는 환경(Windows 등)은 pro-ssh 의 scripts/ssh_connect.py(paramiko)를 쓴다 — skills/pro-ssh/SKILL.md
- 근거: #841, #889 · 확인 2026-10-17

## 공통 (`general`)

| id | 제목 | 코드 |
|---|---|---|
| `general-app-no-device` | app 명령이 no_device — 기기가 여러 대거나 시뮬레이터가 안 켜졌다 | `no_device` |
| `general-bad-args-option-names` | bad_args — 옵션 이름을 착각했다 (--full-page · --field · 위치 인자) | `bad_args` |
| `general-cred-field-missing` | --cred 가 cred_field_missing — 필드를 안 고르면 password 를 넣는다 | `cred_field_missing` |
| `general-env-not-set` | --text-env 가 env_not_set — 값이 아니라 환경변수 이름을 넘긴다 | `env_not_set` |
| `general-plugin-cache-version-drift` | 세션마다 다른 버전의 플러그인 캐시 경로로 스크립트를 부른다 | — |
| `general-render-failed-first-error` | render run 이 render_failed — first_error 부터, 흔한 원인은 services.dart | `render_failed` |
| `general-root-unknown-skill-folder` | 캡처·상태가 ~/.projectops/launch/scripts 등 엉뚱한 곳에 쌓인다 | — |

### `general-app-no-device` — app 명령이 no_device — 기기가 여러 대거나 시뮬레이터가 안 켜졌다

- 코드: `no_device`
- 증상: app shot·tap·type 이 no_device 로 끝난다. 응답에 android·ios_booted 목록이 온다
- 원인: --device 가 없고 $DEV 도 없는데 붙은 기기가 한 대가 아니다(여러 대면 엉뚱한 기기를 찍지 않으려고 멈춘다). 또는 --device 로 준 UDID 가 부팅된 시뮬레이터가 아니다(목록은 Booted 만 본다)
- 해결:
  1. 응답의 android·ios_booted 에서 하나를 골라 --device <시리얼 또는 UDID> 로 다시 부른다
  2. 역할을 묶어 두면 env.sh 의 $DEV 로 고정된다: launch_cli.py device bind --role <역할> --serial <시리얼>
  3. 목록이 비었으면 부팅부터: emulator -avd <AVD명> 또는 xcrun simctl boot <UDID>
- 근거: #583, #889 · 확인 2026-10-17

### `general-bad-args-option-names` — bad_args — 옵션 이름을 착각했다 (--full-page · --field · 위치 인자)

- 코드: `bad_args`
- 증상: 명령이 bad_args(인자가 올바르지 않습니다: unrecognized arguments …)로 끝난다
- 원인: 없는 옵션이나 위치 인자를 넘겼다. 자주 틀리는 것: web shot 은 --full(--full-page 아님), 자격증명 필드는 --cred-field(--field 아님), cred show 는 --name <이름>(위치 인자 아님), cred 동작은 list·show·set·unset·import-ssh 뿐(add 없음)
- 해결:
  1. error 의 unrecognized arguments·invalid choice 부분을 먼저 읽는다
  2. launch_cli.py web --help
  3. launch_cli.py cred show --name <이름>
  4. 응답에 load_errors 가 있으면 모듈이 깨져 서브커맨드가 안 보이는 것이다 — 플러그인 버전을 확인한다
- 근거: #889 · 확인 2026-10-17

### `general-cred-field-missing` — --cred 가 cred_field_missing — 필드를 안 고르면 password 를 넣는다

- 코드: `cred_field_missing`
- 증상: web type·app type --cred 가 cred_field_missing('<이름>' 에 'password' 값 없음)으로 끝난다
- 원인: --cred 는 --cred-field 가 없으면 password 필드 값을 넣는다. 아이디 칸에 넣으려 했거나 그 자격증명에 그 필드가 없다. 응답 fields 가 있는 필드 목록이다
- 해결:
  1. 아이디 칸이면: launch_cli.py web type --selector <칸> --cred <이름> --cred-field account
  2. 필드가 정말 없으면 사용자에게 값을 받아 cred set 으로 채운다 (값을 직접 적지 않는다)
- 근거: #604, #889 · 확인 2026-10-17

### `general-env-not-set` — --text-env 가 env_not_set — 값이 아니라 환경변수 이름을 넘긴다

- 코드: `env_not_set`
- 증상: web type·app type 이 env_not_set(환경변수 … 가 비어 있다)으로 끝난다
- 원인: --text-env 는 환경변수 이름을 받는다. 그 이름의 변수가 launch_cli 프로세스 환경에 없다 — 값 자체를 넘겼거나, 다른 Bash 호출에서 설정해 사라졌다(Bash 는 호출마다 초기화된다)
- 해결:
  1. 같은 명령줄 앞에 붙인다: CODE=<값> launch_cli.py web type --selector <칸> --text-env CODE
  2. 명령줄은 세션 기록에 남는다 — 일회용 인증 코드처럼 남아도 되는 값만 이렇게 넘긴다
  3. 저장된 로그인이면 값을 다루지 말고 --cred <이름> 을 쓴다 (값이 명령줄·기록에 남지 않는다)
- 근거: #604, #889 · 확인 2026-10-17

### `general-plugin-cache-version-drift` — 세션마다 다른 버전의 플러그인 캐시 경로로 스크립트를 부른다

- 핵심어: plugins/cache, projectops-marketplace
- 증상: ~/.claude/plugins/cache/…/projectops/<버전>/skills/pro-launch/scripts 를 직접 적어 부른다. 읽은 문서와 실행한 스크립트의 버전이 달라 옵션이 없다(bad_args)거나 문서와 다르게 동작한다
- 원인: 플러그인 캐시에는 여러 버전 폴더가 함께 남는다. 지난 세션·기억에서 복사한 버전 경로는 지금 버전이 아닐 수 있다. SKILL.md 의 '스크립트 찾기'는 sort -V | tail -1 로 가장 높은 버전을 고른다
- 해결:
  1. 세션을 시작할 때 SKILL.md '스크립트 찾기' 블록을 다시 돌려 SCRIPTS 를 받는다 — 옛 버전 경로를 붙여 넣지 않는다
  2. 문서도 같은 버전 폴더의 것(SCRIPTS 의 상위 references/)을 읽는다
  3. 같은 세션 안에서는 받은 경로를 값으로 써넣는다 (Bash 는 호출마다 변수가 사라진다)
- 근거: #889 · 확인 2026-10-17

### `general-render-failed-first-error` — render run 이 render_failed — first_error 부터, 흔한 원인은 services.dart

- 코드: `render_failed`
- 핵심어: MethodChannel, services.dart
- 증상: render run 이 render_failed(렌더 명령 실패)로 끝나고 아무것도 모으지 않는다. 같은 실패가 여러 번 이어진다
- 원인: 렌더 명령(flutter test 등)이 컴파일·실행에 실패했다. 가장 흔한 원인은 렌더 뼈대에 package:flutter/services.dart import 가 빠져 MethodChannel·SystemChrome 을 못 찾는 것이다
- 해결:
  1. 응답의 first_error 를 먼저 읽는다 (없으면 output_tail)
  2. Undefined name·Couldn't find constructor 'MethodChannel' 이면 import 'package:flutter/services.dart'; 를 넣는다
  3. 화면 위젯·가짜 모델을 쓰면 그 파일의 package:<앱>/... import 도 함께 넣는다
  4. references/render.md 의 함정 표를 본다
- 근거: #898, #889 · 확인 2026-10-17

### `general-root-unknown-skill-folder` — 캡처·상태가 ~/.projectops/launch/scripts 등 엉뚱한 곳에 쌓인다

- 핵심어: root_unknown, root_warning
- 증상: 캡처가 프로젝트가 아니라 ~/.projectops/launch/scripts/shots 나 공용 자리에 생긴다. 응답에 root_unknown·root_warning 이 붙는다. 앞에서 연 브라우저·기억이 안 보인다
- 원인: 스크립트 폴더로 cd 한 뒤 --root . 로(또는 --root 없이) 불렀다. 상태·캡처 자리는 --root 의 git 원격으로 정한다. 플러그인 캐시는 프로젝트가 아니라 이 컴퓨터 공용 자리로 돌린다(예전 버전은 폴더 이름 scripts 로 갈렸다)
- 해결:
  1. 프로젝트 폴더에서 스크립트를 절대경로로 부르고 --root <프로젝트 경로> 를 붙인다
  2. 또는 PROJECT_ROOT=<프로젝트 경로> 를 앞에 붙인다 (스크립트·캐시 폴더에서 불렸을 때 이 값을 쓴다)
  3. 캡처 자리를 먼저 받는다: launch_cli.py get-output-path --root <프로젝트 경로> --title <제목> 뒤 env.sh 를 source
- 근거: #833, #836, #889 · 확인 2026-10-17
- 함께 볼 것: `web-browser-not-open-other-root`
