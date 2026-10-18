# 공식 트러블슈팅

> 생성물이다 — 손으로 고치지 않는다. 원본은 `troubleshooting/<area>/<id>.json`,
> 다시 만들기: `python3 scripts/build_troubleshooting.py skills/<skill>` (레포 루트에서).
> 작성 규칙: `skills/references/memory-principles.md` §6. 실패 응답의 `known_fix` 가 이 항목들의 요약이다.

## 웹 (`web`)

| id | 제목 | 코드 |
|---|---|---|
| `browser-start-stale-process-or-lock` | web open 이 browser_start_failed — 자가 복구 뒤에도 남은 문제 | `browser_start_failed` · `browser_hung` |
| `web-browser-gone` | web 명령이 browser_gone — 띄워 둔 브라우저에 붙지 못했다 | `browser_gone` |
| `web-browser-not-open-other-root` | 방금 연 브라우저인데 browser_not_open — 다른 프로젝트 자리로 불렸다 | `browser_not_open` |
| `web-click-wait-with-expect` | sleep 으로 기다리지 말고 click 의 --expect-url · --expect-text 로 | `expect_not_met` |
| `web-find-nothing-found` | web find 가 nothing_found — 기본은 누를 수 있는 요소만 찾는다 | `nothing_found` |
| `web-goto-failed` | web open·goto 이동 실패 — 주소·서버·인증서를 본다 | `goto_failed` |
| `web-iframe-login-fields` | iframe 안의 로그인 칸(App Store Connect 등)을 못 찾는다 | — |
| `web-orphan-headless-chrome` | HTML 을 더블클릭해도 Chrome 이 안 열린다 — 고아 headless Chrome | `browser_hung` |
| `web-page-changed-by-other-session` | 다른 세션이 같은 탭을 옮겨 입력이 사라진다 | `page_changed_by_other_session` · `tab_gone` |
| `web-playwright-or-browser-missing` | playwright_missing · browser_missing — web setup 이 필요하다 | `playwright_missing` · `browser_missing` |
| `web-readonly-mutating-blocked` | 읽기 전용 세션에서 저장·제출 버튼이 mutating_blocked | `mutating_blocked` |
| `web-save-by-network` | 저장이 됐는지 화면 문구 대신 요청 응답으로 판정한다 | — |
| `web-scroll-container-capture` | 내부 스크롤 화면(Google Forms 편집기 등)은 full-page 로 안 찍힌다 | — |
| `web-secret-in-input` | 비밀값이 입력칸·복사 버튼 안에만 있다 | — |
| `web-selector-guess-timeout` | 추측한 --selector 가 빗나감 — 결과의 candidates 에서 골라 --ref 로 누른다 | `selector_not_found` · `element_not_actionable` · `element_disabled` |
| `web-viewport-width-height` | web viewport --width --height 가 bad_viewport — 크기는 --preset 으로 | `bad_viewport` |

### `browser-start-stale-process-or-lock` — web open 이 browser_start_failed — 자가 복구 뒤에도 남은 문제

- 코드: `browser_start_failed` · `browser_hung`
- 핵심어: SingletonLock, SingletonSocket, profile_locked, stderr_tail, recovered
- 증상: web open 이 browser_start_failed 로 끝나고 브라우저가 뜨지 않는다. 응답에 causes·recovered·stderr_tail 이 온다
- 원인: web open 은 기록된 브라우저를 먼저 판정한다 — 죽었으면 남은 잠금을 치우고, 살아 있는데 CDP 가 3초 안에 답하지 않으면 끄고 새로 띄운다(recovered 에 dead_pid·stale_lock·hung_browser). 그래도 실패하면 기록에 없는 다른 프로세스가 같은 프로필을 쓰고 있거나(잠금은 그때 지우지 않는다) 브라우저 자체가 바로 죽은 것이다
- 해결:
  1. 응답의 stderr_tail 을 읽는다 — 브라우저가 바로 죽은 이유가 거기 있다
  2. profile_locked 가 true 면 응답 profile 폴더를 쓰는 브라우저 프로세스를 찾아(ps · 작업 관리자) 사용자에게 확인한 뒤 끝낸다
  3. launch_cli.py web open --url <주소>
  4. 응답이 browser_still_alive 면 next 의 종료 명령(kill -9 <pid> 또는 taskkill)으로 그 pid 를 끝낸다
- 근거: #711, #712, #887 · 확인 2026-10-17

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

### `web-orphan-headless-chrome` — HTML 을 더블클릭해도 Chrome 이 안 열린다 — 고아 headless Chrome

- 코드: `browser_hung`
- 핵심어: headless, chrome
- 증상: 더블클릭한 html 이 아무 화면도 안 띄우거나 web open 이 멈춘다
- 원인: 프로필이 사라진 headless Chrome(PPID 1)이 남아 기본 Chrome 요청을 받는다
- 해결:
  1. launch_cli.py web close --stale 로 고아를 정리한다 (남의 살아 있는 브라우저는 보고만 한다)
  2. 직접: ps -axo pid,ppid,command | grep -- --headless 에서 PPID 1 인 것을 확인한다
  3. 재접속이 멈추면 새 절대 경로 --root 로 열되 로그인이 사라진다는 점을 감안한다
- 근거: #921 · 확인 2026-10-18
- 함께 볼 것: `browser-start-stale-process-or-lock`

### `web-page-changed-by-other-session` — 다른 세션이 같은 탭을 옮겨 입력이 사라진다

- 코드: `page_changed_by_other_session` · `tab_gone`
- 핵심어: tab_warning, LAUNCH_TAB
- 증상: web 결과에 tab_warning(page_changed_by_other_session)이 붙거나, 하던 페이지가 엉뚱한 사이트로 바뀌어 있다
- 원인: 같은 레포의 브라우저를 여러 세션이 함께 쓰고, 이름 없는 세션은 모두 같은 기본 탭을 몬다
- 해결:
  1. launch_cli.py web tab new --name <이름> --url <주소>
  2. 이 세션의 모든 web 명령 앞에 LAUNCH_TAB=<이름> 을 붙인다
  3. tab_gone 이면 web tab new --name <같은 이름> 으로 다시 만든다
  4. 긴 입력은 단계마다 저장한다
- 근거: #878 · 확인 2026-10-17

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

### `web-save-by-network` — 저장이 됐는지 화면 문구 대신 요청 응답으로 판정한다

- 핵심어: POST, 저장
- 증상: 저장 버튼이 눌렸는데 성공 여부가 화면에 안 보인다
- 원인: 콘솔 화면은 성공 문구가 없거나 사라진다
- 해결:
  1. launch_cli.py web click --capture-requests 로 POST/PUT 응답 상태를 본다
  2. status 200 대 4xx 로 판정한다 (URL 쿼리는 가려진다)
- 근거: #930 · 확인 2026-10-18

### `web-scroll-container-capture` — 내부 스크롤 화면(Google Forms 편집기 등)은 full-page 로 안 찍힌다

- 핵심어: full-page, container
- 증상: web shot --full-page 가 첫 화면에서 잘린다
- 원인: 문서가 아닌 안쪽 컨테이너가 스크롤된다
- 해결:
  1. launch_cli.py web shot --container <선택자> --tiles 5
  2. 직접: web scroll --container <선택자> 후 web shot 을 반복한다
- 근거: #930 · 확인 2026-10-18

### `web-secret-in-input` — 비밀값이 입력칸·복사 버튼 안에만 있다

- 핵심어: Client Secret, SHA-1
- 증상: web text 에 값이 나오지 않는다
- 원인: 값이 input.value 이거나 복사 버튼 뒤에만 있다
- 해결:
  1. launch_cli.py web value --selector <선택자> --save-env NAME (값을 출력하지 않고 저장)
  2. 복사 버튼은 클릭 후 web clipboard --save-env NAME
  3. 화면에 찍힌 값을 OCR 하지 않는다 (I/l 혼동)
- 근거: #930 · 확인 2026-10-18

### `web-selector-guess-timeout` — 추측한 --selector 가 빗나감 — 결과의 candidates 에서 골라 --ref 로 누른다

- 코드: `selector_not_found` · `element_not_actionable` · `element_disabled`
- 핵심어: waiting for locator, Timeout
- 증상: web click·type 이 selector_not_found · element_not_actionable 이나 web_action_failed('Timeout … exceeded … waiting for locator')로 끝난다. 선택자를 바꿔 가며 같은 실패를 되풀이한다
- 원인: 화면을 읽지 않고 선택자를 추측했다. 맞는 요소가 없거나, 있어도 숨김·가려짐이라 대상 대기 시간(--timeout, 조작 동작 기본 4초 — 이전 10초)을 다 쓴다. disabled 면 기다리지 않고 element_disabled 로 바로 끝난다
- 해결:
  1. 실패 결과의 candidates 에서 맞는 것을 골라 next 대로 --ref 로 다시 부른다 (앞일수록 추측한 선택자에 가깝다)
  2. launch_cli.py web click --ref <번호> --expect-url <바뀔 주소 일부>
  3. candidates 가 없으면 web find --text <버튼 글자> 로 고른다
  4. launch_cli.py web find --text <버튼 글자>
  5. launch_cli.py web inspect --role input
  6. 입력칸은 web inspect --role input 으로 ref 를 받고 web type --ref <번호> --text <값> 으로 넣는다
  7. find·inspect·candidates 의 disabled 가 true 거나 element_disabled 가 오면, 그 버튼을 켜는 조건(필수 칸 입력·체크)부터 채운다
  8. 느리게 그려지는 화면이 확실하면 --timeout 10 처럼 늘린다
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
| `android-app-not-foreground` | app launch 가 ok 인데 다른 화면이 맨 위에 있다 | `not_foreground` |
| `android-emulator-unresponsive-host-swap` | 에뮬레이터가 응답하지 않는다 — 호스트 메모리가 꽉 찼다 | `device_unresponsive` · `ui_dump_failed` |
| `android-flutter-doubled-desc` | Android Flutter 버튼 desc 가 두 번 들어간다 | `not_found` |
| `android-korean-ime-jamo` | Android app type 이 ok 인데 한국어 키보드가 자모로 바꿔 넣는다 | `typed_text_mismatch` |
| `android-maestro-driver-start-timeout` | maestro_driver_timeout — Maestro Android driver 가 시간 안에 안 뜸 | `maestro_driver_timeout` |
| `android-maps-locale` | Google Maps 라벨이 앱 언어를 따르지 않는다 | — |
| `android-no-focused-window` | no_focused_window — 초점 창이 없어 화면 구조를 못 읽음 (null root node) | `no_focused_window` |
| `android-non-ascii-text` | Android app type 이 non_ascii_unsupported — adb 는 한글을 못 넣는다 | `non_ascii_unsupported` |
| `android-system-restart-loop` | android_system_not_ready · ui_automation_unavailable — 에뮬레이터 시스템 재시작 반복 | `android_system_not_ready` · `ui_automation_unavailable` · `ui_dump_timeout` |

### `android-adb-missing` — adb_missing · android_tool_missing — adb 를 찾지 못했다

- 코드: `adb_missing` · `android_tool_missing`
- 증상: Android 기기 조작이 adb_missing 이나 android_tool_missing 으로 끝난다
- 원인: adb 가 PATH 에도, 표준 SDK 자리(~/Library/Android/sdk, ~/Android/Sdk, $ANDROID_HOME, $ANDROID_SDK_ROOT 의 platform-tools)에도 없다
- 해결:
  1. SDK 가 다른 곳에 있으면 ANDROID_HOME=<SDK 경로> 를 앞에 붙여 다시 부른다
  2. launch_cli.py doctor
  3. SDK platform-tools 설치는 사용자에게 먼저 묻는다
- 근거: #889 · 확인 2026-10-17

### `android-app-not-foreground` — app launch 가 ok 인데 다른 화면이 맨 위에 있다

- 코드: `not_foreground`
- 핵심어: mCurrentFocus, MinuteMaidActivity
- 증상: launch·relaunch·back 이 성공인데 화면은 그대로다 (다른 세션의 Google 로그인 등)
- 원인: 공용 에뮬레이터 맨 위를 다른 앱(예: com.google.android.gms 로그인)이 잡고 있다. back 이 통하지 않을 수 있다
- 해결:
  1. 응답의 blocking_activity 를 확인한다
  2. adb shell dumpsys window | grep mCurrentFocus 로 직접 본다
  3. 남이 쓰는 기기인지 device list 의 owner 로 확인하고, 맞으면 먼저 묻는다
  4. 풀리지 않으면 launch_cli.py device reboot --cold (35초 안팎)
- 근거: #923, #925 · 확인 2026-10-18
- 함께 볼 것: `android-no-focused-window`

### `android-emulator-unresponsive-host-swap` — 에뮬레이터가 응답하지 않는다 — 호스트 메모리가 꽉 찼다

- 코드: `device_unresponsive` · `ui_dump_failed`
- 핵심어: swap, offline, system_server
- 증상: adb install·shell 이 시간 초과하고 ui_dump_failed(count 0) 나 offline 이 이어진다
- 원인: 호스트 swap 이 거의 찼거나 AVD 가 1코어/2GB 라 system_server 가 watchdog 으로 반복 재시작한다
- 해결:
  1. launch_cli.py doctor --resources 로 메모리 압박을 본다
  2. launch_cli.py device reboot --device <id> --cold 로 정리하고 다시 띄운다
  3. AVD 가 작으면 emulator -avd <이름> -no-snapshot -cores 4 -memory 4096
  4. 부팅 직후 'Broken pipe'/'Can't find service: package' 는 service check package 가 found 될 때까지 기다린 뒤 재시도
  5. -no-snapshot-save 로 켜면 끈 사이 앱 데이터가 사라진다
- 근거: #924 · 확인 2026-10-18
- 함께 볼 것: `android-system-restart-loop`

### `android-flutter-doubled-desc` — Android Flutter 버튼 desc 가 두 번 들어간다

- 코드: `not_found`
- 핵심어: desc, Semantics
- 증상: app tap --text 가 not_found 인데 tree 의 desc 는 '라벨\n라벨' 이다
- 원인: Flutter 가 Semantics 를 content-desc 에 합쳐 같은 줄이 반복된다
- 해결:
  1. launch_cli.py app tap --desc <라벨> (최신 버전은 줄 단위로 맞춘다)
  2. 이전 버전은 개행 포함 전체 문자열을 --desc 로 준다
- 근거: #927 · 확인 2026-10-18

### `android-korean-ime-jamo` — Android app type 이 ok 인데 한국어 키보드가 자모로 바꿔 넣는다

- 코드: `typed_text_mismatch`
- 핵심어: 자모, Gboard, IME
- 증상: app type 으로 영문 아이디를 넣었는데 입력칸에 자모가 들어 있다
- 원인: adb input text 는 키 이벤트라 Gboard 한국어 자판이 조합한다. 값이 ASCII 여도 결과가 달라진다
- 해결:
  1. launch_cli.py app type --ime ascii --text <값> (입력 동안 Maestro IME 로 바꿨다 원복)
  2. 수동: adb shell ime set dev.mobile.maestro/.input.MaestroInputMethodService 후 입력하고 원래 IME 로 되돌린다
  3. IME 는 기기 전역 설정이다 — 다른 세션이 쓰는 기기면 먼저 묻는다
- 근거: #926 · 확인 2026-10-18
- 함께 볼 것: `android-non-ascii-text`

### `android-maestro-driver-start-timeout` — maestro_driver_timeout — Maestro Android driver 가 시간 안에 안 뜸

- 코드: `maestro_driver_timeout`
- 핵심어: did not start up in time
- 증상: app flow(또는 직접 부른 maestro test)가 'Maestro Android driver did not start up in time' 으로 멈춘다. 같은 flow 가 다른 때에는 돈다
- 원인: 에뮬레이터·호스트 과부하로 기기 안 driver 앱(dev.mobile.maestro, dev.mobile.maestro.test)이 기동 시간 안에 응답하지 못했다(이슈 보고: 3회, 빌드와 겹쳤을 때)
- 해결:
  1. app flow 는 이미 driver 앱을 force-stop 하고 한 번 더 돌린 뒤에 이 code 를 낸다 — 같은 명령을 바로 반복하지 않는다
  2. 빌드(gradle·xcodebuild) 같은 무거운 작업이 도는지 보고 끝난 뒤 다시 돌린다
  3. 그래도 계속이면 에뮬레이터 cold boot 를 사용자에게 묻는다(emulator -avd <이름> -no-snapshot-load)
- 근거: #862 · 확인 2026-10-17

### `android-maps-locale` — Google Maps 라벨이 앱 언어를 따르지 않는다

- 핵심어: locale, Maps
- 증상: Flutter 앱 언어를 바꿨는데 지도 라벨은 그대로다
- 원인: 지도 라벨은 Activity locale 을 따른다. 시스템 언어를 바꾼 직후에는 GMS 가 locale 을 캐시한다
- 해결:
  1. launch_cli.py device locale --device <id> --lang ja --region JP --app <패키지>
  2. 직접: adb shell cmd locale set-app-locales <pkg> --locales ja-JP (확인은 get-app-locales)
  3. 타일이 비면 앱과 Play services 를 재시작한다
  4. 끝나면 --restore 로 되돌린다
- 근거: #929 · 확인 2026-10-18

### `android-no-focused-window` — no_focused_window — 초점 창이 없어 화면 구조를 못 읽음 (null root node)

- 코드: `no_focused_window`
- 핵심어: null root node returned by UiTestAutomationBridge
- 증상: app tree · app tap --text · app run 의 wait 가 실패하고, uiautomator dump 가 'ERROR: null root node returned by UiTestAutomationBridge.' 를 낸다. 화면에는 홈 화면이 떠 있어 보인다
- 원인: Android 에 초점을 가진 창이 없다(dumpsys window 의 mCurrentFocus=null). 재부팅 직후 · 화면 꺼짐 · 잠금 · 화면 전환 중에 생긴다(실측: 에뮬레이터 소프트 재부팅 직후 5회 연속)
- 해결:
  1. CLI 가 이미 화면을 깨우고(WAKEUP · 잠금 해제) 세 번까지 다시 읽은 뒤에 이 code 를 낸다 — 몇 초 뒤 app tree 를 한 번 더 부른다
  2. app shot 으로 지금 화면을 본다. 비밀번호 잠금 화면이면 사용자에게 풀어 달라고 한다
  3. 계속이면 adb -s <시리얼> shell dumpsys window | grep mCurrentFocus 로 초점 창이 생겼는지 본다
- 근거: #894 · 확인 2026-10-17

### `android-non-ascii-text` — Android app type 이 non_ascii_unsupported — adb 는 한글을 못 넣는다

- 코드: `non_ascii_unsupported`
- 증상: Android 에서 app type 으로 한글을 넣으려 하면 non_ascii_unsupported 로 끝난다
- 원인: Android 입력은 adb input text 를 쓰는데 ASCII 만 받는다
- 해결:
  1. 영문·숫자 값으로 바꿔 넣을 수 있으면 그렇게 한다
  2. 한글이 꼭 필요하면 ADBKeyboard 같은 IME 설치를 사용자에게 먼저 묻는다
  3. 안 되면 사용자에게 직접 입력을 부탁한다
- 근거: #889 · 확인 2026-10-17

### `android-system-restart-loop` — android_system_not_ready · ui_automation_unavailable — 에뮬레이터 시스템 재시작 반복

- 코드: `android_system_not_ready` · `ui_automation_unavailable` · `ui_dump_timeout`
- 핵심어: Timeout while connecting UiAutomation, Can't find service, Transport endpoint is not connected
- 증상: uiautomator dump 가 'Killed' 로 끝나거나 멈추고, 화면은 Google 부팅 로고에 머문다. adb shell dumpsys activity 가 'Can't find service: activity', /sdcard 가 'Transport endpoint is not connected'
- 원인: system_server 가 몇 분마다 다시 뜬다(pidof system_server 가 바뀐다, getprop init.svc.bootanim = running). 오래 켜 둔 에뮬레이터(실측: 가동 1일 10시간 · 메모리 2GB 중 여유 100MB)에서 생겼다. sys.boot_completed 는 1 로 남아 부팅이 끝난 것처럼 보인다
- 해결:
  1. adb -s <시리얼> shell getprop init.svc.bootanim  — running 이면 시스템이 아직 안 떴다
  2. 사용자 확인 뒤 adb -s <시리얼> reboot (소프트 재부팅, 데이터 유지) — 실측: 52초 만에 부팅이 끝나고 app run 이 정상으로 돌았다
  3. 몇 분 기다려도 그대로면 사용자에게 에뮬레이터 cold boot 를 묻는다: emulator -avd <AVD> -no-snapshot-load (다른 세션이 쓰는 중일 수 있어 임의로 끄지 않는다)
  4. ui_automation_unavailable 만 계속이면 다른 자동화(Maestro·Appium)가 UiAutomation 을 쥐고 있는지 본다
- 근거: #894 · 확인 2026-10-17

## iOS (`ios`)

| id | 제목 | 코드 |
|---|---|---|
| `ios-app-vanishes-after-launch` | iOS 앱이 실행 직후 사라지는데 app shot 은 홈 화면을 찍는다 | `app_exited` |
| `ios-label-in-desc-doubled` | iOS Flutter 버튼 라벨이 desc 에 겹쳐 나와 --text 로 못 누른다 | `not_found` |
| `ios-maestro-log-keeps-input-text` | Maestro 기록(maestro.log)에 inputText 의 실제 값이 평문으로 남는다 | — |
| `ios-maestro-not-installed` | iOS app tap·swipe·tree 가 ios_tool_missing — Maestro 미설치 | `ios_tool_missing` |
| `ios-maestro-point-integer-percent` | Maestro flow 의 point 퍼센트는 정수만 받는다 (NumberFormatException) | — |
| `ios-maestro-session-reconnect` | 상주 세션이 끊겼다 — 같은 기기에 다른 maestro test 가 붙었다 | `session_start_failed` |
| `ios-maestro-slow-cold-start` | iOS app tap·swipe·tree 가 수십 초 걸린다 — 호출마다 Maestro(JVM)가 뜬다 | — |
| `ios-maestro-stale-driver-or-overload` | iOS tap 이 90초 실패하고 app session start 도 실패한다 — 남은 Maestro 드라이버·부하 | `session_start_failed` |
| `ios-status-bar-custom-time` | iOS 캡처 상태바 시각을 알림 시각에 맞춰야 한다 | — |

### `ios-app-vanishes-after-launch` — iOS 앱이 실행 직후 사라지는데 app shot 은 홈 화면을 찍는다

- 코드: `app_exited`
- 핵심어: SIGABRT, crash
- 증상: app launch 가 ok 인데 앱이 안 보이고 shot 이 홈 화면이다
- 원인: 실행 직후 앱이 죽는다 (예: 워크트리에 Secrets.xcconfig 가 없어 GADInvalidInitializationException)
- 해결:
  1. launch_cli.py app launch 응답의 crash_report 와 exception 줄을 본다
  2. 없으면 ~/Library/Logs/DiagnosticReports 의 최신 Runner-*.ips 를 연다
  3. xcrun simctl launch --console-pty <UDID> <bundle> 로 콘솔 오류를 본다
  4. 워크트리에 로컬 설정 파일(Secrets.xcconfig 등)이 복사됐는지 확인한다
- 근거: #923 · 확인 2026-10-18

### `ios-label-in-desc-doubled` — iOS Flutter 버튼 라벨이 desc 에 겹쳐 나와 --text 로 못 누른다

- 코드: `not_found`
- 핵심어: desc, Semantics
- 증상: app tap --text 가 not_found 인데 tree 에는 그 글자가 있다 ('GitHub로 계속하기\nGitHub로 계속하기')
- 원인: Flutter Semantics 라벨은 desc 로 나오고 같은 줄이 두 번 들어간다. 예전 버전은 text 칸만 봤다
- 해결:
  1. app tree 에서 해당 요소의 desc 를 확인한다
  2. launch_cli.py app tap --desc <글자> 로 누른다 (최신 버전은 desc·겹친 라벨을 자동으로 맞춘다)
  3. 웹뷰 안 버튼은 이름으로 안 잡히면 --at 비율 좌표를 쓴다
- 근거: #927 · 확인 2026-10-18

### `ios-maestro-log-keeps-input-text` — Maestro 기록(maestro.log)에 inputText 의 실제 값이 평문으로 남는다

- 핵심어: maestro.log, evaluatedCommand, InputTextCommand
- 증상: ~/.maestro/tests/<시각>/maestro.log 에 InputTextCommand(text=<실제 값>) 이 남아 있다 — 환경변수(${...})로 넘겼는데도
- 원인: maestro test 는 실행한 명령을 환경변수를 풀어 쓴 모양(evaluatedCommand)으로 기록한다. 기록 자리의 기본값이 ~/.maestro/tests 라 실행이 끝나도 남는다 (Maestro 2.10.0 실측)
- 해결:
  1. pro-launch 의 app type · type 단계는 --debug-output <임시 폴더> --flatten-debug-output 으로 기록을 임시 폴더로 돌려 함께 지운다 — 직접 maestro test 를 부를 때도 같은 옵션을 쓴다
  2. 이미 남은 기록이 있으면 사용자에게 알리고 지울지 묻는다 (임의로 지우지 않는다)
- 근거: #894, #895 · 확인 2026-10-17

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

### `ios-maestro-point-integer-percent` — Maestro flow 의 point 퍼센트는 정수만 받는다 (NumberFormatException)

- 핵심어: NumberFormatException, point
- 증상: raw flow 의 tapOn point: "38%,72.7%" 가 재시도해도 계속 실패하고 드라이버 문제처럼 보인다
- 원인: Maestro point 좌표의 퍼센트는 정수만 받아 72.7 에서 NumberFormatException 이 난다. 래퍼가 재시도만 하면 진짜 오류가 숨는다
- 해결:
  1. maestro.log 의 마지막 오류 줄을 먼저 읽는다 (~/.maestro/tests/<시각>/maestro.log)
  2. 퍼센트를 정수로 반올림한다 (72.7% → 73%)
  3. 가능하면 raw flow 대신 app tap --at 비율 좌표를 쓴다 (pro-launch 가 반올림한다)
- 근거: #922 · 확인 2026-10-18

### `ios-maestro-session-reconnect` — 상주 세션이 끊겼다 — 같은 기기에 다른 maestro test 가 붙었다

- 코드: `session_start_failed`
- 핵심어: Device became unreachable, session_fallback, device_unreachable
- 증상: app session start 뒤 빠르던 tree·tap 이 한 번 9초쯤 걸리거나(session_reconnected: true), session_fallback: device_unreachable 로 호출마다 띄우는 길로 내려간다
- 원인: maestro mcp 세션이 기기에 붙어 있는 동안 같은 시뮬레이터에 maestro test(app type 포함, 다른 세션의 테스트 포함)가 붙으면 세션의 드라이버 연결이 끊긴다 — 'Failed to run flow: Device became unreachable during deviceInfo' (Maestro 2.10.0 실측). 중계가 다음 호출에서 maestro mcp 를 다시 띄워 붙는다
- 해결:
  1. 한 번 느린 것은 정상이다 — 그대로 이어서 쓴다
  2. 계속 device_unreachable 이면 다른 세션이 같은 기기로 maestro 를 돌리는 중인지 본다 (ps -ax | grep maestro)
  3. launch_cli.py app session stop --device <UDID> 뒤 다시 start
- 근거: #894 · 확인 2026-10-17
- 함께 볼 것: `ios-maestro-slow-cold-start`

### `ios-maestro-slow-cold-start` — iOS app tap·swipe·tree 가 수십 초 걸린다 — 호출마다 Maestro(JVM)가 뜬다

- 핵심어: maestro, 90초
- 증상: iOS 시뮬레이터에서 app tap·swipe·tree 가 한 번에 20~50초 걸리거나 'maestro 응답 없음 (90초)'로 실패한다. Android 는 몇 초다
- 원인: simctl 에는 탭·화면구조 명령이 없어 iOS 조작은 Maestro 에 맡기고, 호출마다 Maestro(JVM)가 새로 뜬다. 한 동작 제한은 90초다. 고장이 아니라 예상된 느림이다
- 해결:
  1. 보고 → 판단 → 누르기를 여러 번 하면 상주 세션을 먼저 켠다: launch_cli.py app session start --device <UDID> (이후 tree 0.6초 · tap 1초)
  2. 느리다고 같은 명령을 겹쳐 부르지 않는다 — 앞 호출이 끝나길 기다린다
  3. 화면 확인은 따로 shot 을 부르지 말고 동작에 --shot 을 붙인다: launch_cli.py app tap --device <UDID> --text <글자> --shot <이름>
  4. 긴 시나리오는 프로젝트의 Maestro flow 로 한 번에 돌린다
- 근거: #826, #889, #894 · 확인 2026-10-17
- 함께 볼 것: `ios-maestro-not-installed`, `ios-maestro-session-reconnect`

### `ios-maestro-stale-driver-or-overload` — iOS tap 이 90초 실패하고 app session start 도 실패한다 — 남은 Maestro 드라이버·부하

- 코드: `session_start_failed`
- 핵심어: tools/call timed out, maestro 응답 없음, xcodebuild
- 증상: tap_failed 가 'maestro 응답 없음 (90초)' 로 반복되고, 권장대로 app session start 를 해도 'tools/call timed out after 120s' 로 실패한다
- 원인: 이전 실행이 남긴 xcodebuild(maestro-driver-ios-config.xctestrun)·maestro JVM 이 살아 있거나 호스트 load 가 높아 드라이버가 뜨지 못한다. 세션을 켜는 것으로는 풀리지 않는다
- 해결:
  1. uptime 으로 load 를 본다 (코어 수의 2배 이상이면 과부하)
  2. ps 에서 maestro-driver-ios-config · maestro/lib 가 pro-launch 세션 소유가 아닌지 확인한다
  3. 남은 것만 끈다: pkill -f maestro-driver-ios-config; pkill -f maestro/lib 후 launch_cli.py app tree 로 확인
  4. 부하가 높으면 MAESTRO_DRIVER_STARTUP_TIMEOUT=180000 으로 다시 시도한다 (iOS driver not ready in time)
- 근거: #922 · 확인 2026-10-18
- 함께 볼 것: `ios-maestro-slow-cold-start`, `ios-maestro-session-reconnect`

### `ios-status-bar-custom-time` — iOS 캡처 상태바 시각을 알림 시각에 맞춰야 한다

- 핵심어: status_bar, 상태바
- 증상: 스토어 캡처에서 상태바 시각을 9:41 이 아닌 다른 시각으로 맞춰야 한다
- 원인: app shot --clean-status 는 기본 9:41 로 고정한다. 임의 시각은 simctl status_bar 로 직접 지정한다
- 해결:
  1. launch_cli.py app shot --clean-status --time 7:42
  2. 직접 할 때: xcrun simctl status_bar <UDID> override --time 7:42 후 찍고 status_bar clear 로 되돌린다
- 근거: #928 · 확인 2026-10-18

## SSH (`ssh`)

| id | 제목 | 코드 |
|---|---|---|
| `ssh-sshpass-missing` | 암호 ssh 가 sshpass_missing — 키 접속이나 호환 경로로 | `sshpass_missing` |
| `ssh-windows-cmd-encoding` | Windows cmd(CP949) 호스트의 출력이 깨진다 | — |

### `ssh-sshpass-missing` — 암호 ssh 가 sshpass_missing — 키 접속이나 호환 경로로

- 코드: `sshpass_missing`
- 증상: launch_cli.py ssh 가 sshpass_missing(암호 접속에는 sshpass 가 필요하다)으로 끝난다
- 원인: 저장된 서버가 암호 접속인데 sshpass 가 설치돼 있지 않다. 키(key_path)로 접속하면 sshpass 가 필요 없다
- 해결:
  1. 키가 있으면: launch_cli.py ssh --cred <서버> --key-path <키 파일> --command '<명령>'
  2. sshpass 설치는 사용자에게 먼저 묻는다: brew install hudochenkov/sshpass/sshpass
  3. 설치가 안 되는 환경(Windows 등)은 pro-ssh 의 scripts/ssh_connect.py(paramiko)를 쓴다 — skills/pro-ssh/SKILL.md
- 근거: #841, #889 · 확인 2026-10-17

### `ssh-windows-cmd-encoding` — Windows cmd(CP949) 호스트의 출력이 깨진다

- 핵심어: UnicodeDecodeError, chcp
- 증상: ssh 응답에 깨진 글자가 있거나 예전 버전은 UnicodeDecodeError 로 끝난다
- 원인: Windows cmd 는 CP949 로 출력한다
- 해결:
  1. 최신 버전은 UTF-8 > CP949 순으로 해석한다 (stdout_encoding 확인)
  2. 옛 버전은 명령 앞에 'chcp 65001 >nul &' 를 붙인다
- 근거: #933 · 확인 2026-10-18

## 공통 (`general`)

| id | 제목 | 코드 |
|---|---|---|
| `general-app-no-device` | app 명령이 no_device — 기기가 여러 대거나 시뮬레이터가 안 켜졌다 | `no_device` |
| `general-bad-args-option-names` | bad_args — 옵션 이름을 착각했다 (--full-page · --field · 위치 인자) | `bad_args` |
| `general-cred-field-missing` | --cred 가 cred_field_missing — 필드를 안 고르면 password 를 넣는다 | `cred_field_missing` |
| `general-cred-never-read-config` | 자격증명을 config 파일에서 직접 읽지 않는다 | — |
| `general-env-not-set` | --text-env 가 env_not_set — 값이 아니라 환경변수 이름을 넘긴다 | `env_not_set` |
| `general-login-interstitial-policy` | 로그인 도중 기기 신뢰·로그인 유지·권유 화면에서 매번 멈춘다 | — |
| `general-otp-no-resubmit` | 인증 코드를 기다리는 동안 로그인 폼을 다시 제출하지 않는다 | — |
| `general-plugin-cache-version-drift` | 세션마다 다른 버전의 플러그인 캐시 경로로 스크립트를 부른다 | — |
| `general-render-failed-first-error` | render run 이 render_failed — first_error 부터, 흔한 원인은 services.dart | `render_failed` |
| `general-root-unknown-skill-folder` | 캡처·상태가 ~/.projectops/launch/scripts 등 엉뚱한 곳에 쌓인다 | — |
| `general-timeout-unit-seconds` | --timeout 을 밀리초로 넣었다 — 단위는 초 | `timeout_too_large` |
| `general-zsh-variable-command` | zsh 에서 변수에 담은 명령이 한 단어로 취급되어 'no such file' 이 난다 | — |

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

### `general-cred-never-read-config` — 자격증명을 config 파일에서 직접 읽지 않는다

- 핵심어: config.json, password
- 증상: raw 도구(maestro 등)에 비밀번호를 넘기려고 config.json 을 읽어 임시 파일을 만든다
- 원인: 저장된 값은 --cred 로 쓰면 마스킹되고 기록에 남지 않는다. 직접 읽으면 평문이 파일·명령줄·대화에 남는다
- 해결:
  1. app type --cred <이름> --cred-field <필드> / web type --cred 를 쓴다
  2. app run 단계에서도 cred 참조를 쓴다
  3. 평문이 이미 남았으면 파일을 지우고 사용자에게 변경을 권한다
- 근거: #934 · 확인 2026-10-18

### `general-env-not-set` — --text-env 가 env_not_set — 값이 아니라 환경변수 이름을 넘긴다

- 코드: `env_not_set`
- 증상: web type·app type 이 env_not_set(환경변수 … 가 비어 있다)으로 끝난다
- 원인: --text-env 는 환경변수 이름을 받는다. 그 이름의 변수가 launch_cli 프로세스 환경에 없다 — 값 자체를 넘겼거나, 다른 Bash 호출에서 설정해 사라졌다(Bash 는 호출마다 초기화된다)
- 해결:
  1. 같은 명령줄 앞에 붙인다: CODE=<값> launch_cli.py web type --selector <칸> --text-env CODE
  2. 명령줄은 세션 기록에 남는다 — 일회용 인증 코드처럼 남아도 되는 값만 이렇게 넘긴다
  3. 저장된 로그인이면 값을 다루지 말고 --cred <이름> 을 쓴다 (값이 명령줄·기록에 남지 않는다)
- 근거: #604, #889 · 확인 2026-10-17

### `general-login-interstitial-policy` — 로그인 도중 기기 신뢰·로그인 유지·권유 화면에서 매번 멈춘다

- 핵심어: trust this device, 기기 신뢰, 다시 묻지, 로그인 상태 유지, stay signed in, passkey, 패스키
- 해당: web · android · ios
- 증상: 로그인할 때마다 이 기기 신뢰(다시 묻지 않기) · 로그인 상태 유지 · 패스키·연락처 추가 권유 화면에서 사용자에게 같은 질문을 되풀이한다. 원격(remote-control)에서는 사용자가 화면을 못 봐 흐름이 끊긴다
- 원인: 로그인 중간 화면 정책이 저장되지 않았다(모든 키가 ask). 제공자마다 화면 모양이 달라 자동 클릭 코드는 없고, agent 가 화면 종류를 판단해 저장된 정책대로 누른다
- 해결:
  1. launch_cli.py cred policy get --name <이름>
  2. launch_cli.py cred policy set --name <이름> --key trust_device --value always
  3. launch_cli.py cred policy set --key skip_nags --value always
  4. web type --cred · app type --cred 결과의 login_policy 가 always·never 면 묻지 않고 그대로 누른다. ask 면 캡처와 함께 묻고 '이 계정만 / 모든 사이트 / 이번만' 답을 cred policy set 으로 저장한다
  5. 어느 종류인지 모르겠는 화면은 누르지 않는다 — 캡처를 대화로 보내고 묻는다. 2단계 인증 해제·계정 보안 설정 변경은 하지 않는다
- 근거: #905 · 확인 2026-10-18

### `general-otp-no-resubmit` — 인증 코드를 기다리는 동안 로그인 폼을 다시 제출하지 않는다

- 핵심어: Invalid OTP, 인증 코드
- 증상: 사용자가 코드를 보냈는데 입력하니 Invalid OTP 가 뜬다
- 원인: 로그인을 다시 제출하면 새 코드가 나가 앞 코드가 무효가 된다
- 해결:
  1. 코드를 기다리는 동안 폼을 다시 제출하지 않는다
  2. 먼저 web text 로 지금 OTP 화면인지 확인한다
  3. 이미 다시 제출했으면 사용자에게 새 코드를 요청한다
- 근거: #881, #934 · 확인 2026-10-18

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
- 근거: #901, #889 · 확인 2026-10-17

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

### `general-timeout-unit-seconds` — --timeout 을 밀리초로 넣었다 — 단위는 초

- 코드: `timeout_too_large`
- 핵심어: --timeout
- 증상: web type --timeout 3000 이 50분 동안 멈춘다
- 원인: --timeout 은 초 단위다. 3000 은 50분이다
- 해결:
  1. --timeout 은 초로 준다 (기본 10, 최대 300)
  2. 이미 멈췄으면 web close 후 web open 으로 복구한다
- 근거: #931 · 확인 2026-10-18

### `general-zsh-variable-command` — zsh 에서 변수에 담은 명령이 한 단어로 취급되어 'no such file' 이 난다

- 핵심어: no such file or directory: python3, zsh
- 증상: L="python3 …/launch_cli.py"; $L web … 가 'no such file or directory: python3 /…/launch_cli.py' 로 실패한다
- 원인: zsh 는 변수를 단어로 쪼개지 않는다 (bash 와 다름)
- 해결:
  1. 고정 진입점을 직접 부른다: python3 ~/.projectops/bin/launch_cli.py doctor
  2. 반복하면 함수로 감싼다: launch() { python3 "$HOME/.projectops/bin/launch_cli.py" "$@"; }
  3. 'web $a' 처럼 변수에 인자 여러 개를 담지 않는다 (필요하면 bash -c)
- 근거: #920 · 확인 2026-10-18
- 함께 볼 것: `general-plugin-cache-version-drift`
