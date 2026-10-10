# 밟기 — 관측 확보 · 핵심 루프 · 되돌리기 · 한계 · 함정

> 언제 읽나: 앱을 실제로 밟기 직전(Phase 2·3), 누른 게 안 먹거나 판정이 애매할 때, 처음부터 다시 밟으려 할 때(Phase 6).

`SKILL.md` 의 Phase 2 · 3 · 6 을 펼친 것이다. 명령 자체(옵션·code)는 `../../pro-launch/references/app.md` 가 정본이다.

## Phase 2 — 관측 가능성 확보 ⚠️

밟기 전에 **상태를 볼 수 있는지** 먼저 확인한다.

```bash
adb -s "$DEV" logcat -c
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app launch --device "$DEV" --pkg "$PKG"
sleep 5 && adb -s "$DEV" logcat -d | grep -i "flutter"
```

로그가 없으면 **그 자체가 결함이다.** "추적 불가"로 적어 두고 밟는다 — 로깅을 대신 넣어
주지 않는다. 이 skill은 **버그를 찾는 쪽이지 고치는 쪽이 아니다.**
없는 채로 진행하면 "화면은 넘어갔는데 저장이 됐는지" 알 수 없어 통과 판정이 추측이 된다.

있어야 할 로그의 최소 조건 (보고할 때 이 기준으로 "무엇이 빠졌나"를 적는다):

| 대상 | 남길 것 | 남기면 안 되는 것 |
| --- | --- | --- |
| 로컬 저장 | 키 이름, 읽기/쓰기 구분, 값의 **유무** | 토큰·PIN 원문 (`***`로 마스킹) |
| API 호출 | 경로, 메서드, 결과 요약 | 요청 본문의 개인정보 |
| 화면 전환 | 어디서 어디로 | — |

로그가 없는 채로 밟았다면, 그 구간의 판정에 **"근거 부족"을 함께 적는다.** 화면은 넘어갔지만
저장이 됐는지 확인할 수 없었다는 뜻이고, 그것을 "통과"로 적으면 추측이 사실처럼 남는다.

## Phase 3 — 밟기 (핵심 루프)

한 단계마다 아래를 **순서대로** 반복한다.

```
① 화면 읽기 → ② 요소로 조작 → ③ 결과 확인 → ④ 양쪽 대조 → ⑤ 서버 쪽
```

### ① 화면 읽기

```bash
source "{env_file 값}"   # SHOT_DIR · DEV · PKG — SKILL.md '산출물 자리' 에서 받은 것
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app tree --device "$DEV"            # 누를 수 있는 문구·id + 화면 언어(locale)
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app shot --device "$DEV" --out step_N # 눈으로 봐야 할 때만
```

- **텍스트로 확인되면 이미지를 읽지 않는다.** `app tree` 의 `elements` 로 무엇이 있는지 알 수 있으면 충분하다.
  가장 비싼 것이 이미지다.
- **매 조작 전에 새로 읽는다.** 이전 화면 기억으로 누르지 않는다 — 키보드가 올라왔거나
  안내 문구가 추가돼 요소가 밀려 있을 수 있다 (실제로 자주 발생한다).

> **캡처를 줄여야 하는 것이 둘인데 방법이 다르다 (실측).**
>
> | 무엇이 | 무엇으로 | 효과 |
> | --- | --- | --- |
> | 세션 토큰 | **해상도 축소** | 1080x2400 원본 1,473 토큰 → 긴 변 1200 으로 864 토큰 |
> | 파일·전송량 | **WebP 변환** | 495KB → 34KB |
>
> **포맷은 토큰에 아무 영향이 없다** — 토큰은 가로x세로에서만 나온다. 그래서
> `app shot` · `web shot` 이 둘을 함께 하고 저장한다. 원본이 필요하면 `--keep-format`.
> 다른 도구로 찍은 이미지는 `{LAUNCH}/launch_cli.py shrink` 로 같은 처리를 한다.
> 한 세션에 스크린샷 20장이면 **29,460 → 5,880 토큰**이다. 밟는 길이가 길어질수록 벌어진다.

### ② 요소로 조작

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app tap   --device "$DEV" --text "다음" --shot step_N_after
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app tap   --device "$DEV" --id submit_button
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app tap   --device "$DEV" --desc "닫기" --index 1
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app tap   --device "$DEV" --at 0.5,0.8      # 요소가 없을 때만 — 0~1 비율
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app swipe --device "$DEV" --dir up --shot list_scrolled
adb -s "$DEV" shell input text "{문자열}"        # 공백은 %s, ASCII 만
adb -s "$DEV" shell input keyevent KEYCODE_BACK  # 키보드 내리기 · 기기 뒤로가기
```

- 문구는 **화면 언어 그대로** 쓴다(`app tree` 의 `locale`). 못 찾으면 `not_found` 와 `candidates`
  (화면에 실제로 있는 값)가 온다 — **추측을 반복하지 말고 거기서 고른다.**
- **픽셀 좌표를 계산해 누르지 않는다.** 캡처는 축소돼 있어 그 위에서 잰 좌표는 빗나간다.
  요소가 없는 캔버스·지도만 `--at` 비율 좌표(픽셀은 `bad_ratio` 로 거절된다).
- 목록을 스크롤할 때는 **끝까지 내린다.** 한 번만 밀고 "잘렸다"고 판단하면 오진한다
  (이유: 실제로 이 오진이 발생해 없는 버그로 이슈를 올린 적이 있다).
- iOS 는 `app tap`·`app swipe` 가 Maestro 로 돈다(호출당 10~40초). 긴 시나리오는 프로젝트 E2E flow 로.

### ③ 결과 확인

`--shot` 결과의 `screen_changed: false` 면 **눌렀는데 아무 일도 없었다** — 다른 요소를 고르거나,
그 자체가 결함("반응 없는 요소", `looks-wrong.md` 축 5)인지 본다. 화면만 보지 않는다. 크래시·에러를 함께 본다.

`note screen` 에 기록해 둔 대상을 눌렀다면 **결과를 남긴다** — 다음 실행이 그 기록을 믿어도 되는지 알게 된다.

```bash
# screen_changed: true → ok / not_found · screen_changed: false → fail
{PYTHON} {SCRIPTS}/e2e_cli.py note screen --root {PROJECT_ROOT} --name "{화면}" --target "{라벨}" --result ok
```

```bash
adb -s "$DEV" shell dumpsys window | grep mCurrentFocus   # 지금 어느 화면인가
adb -s "$DEV" logcat -d -b crash | tail -40               # 죽지 않았나
```

`Application Error` 나 `FATAL EXCEPTION` 이 보이면 **거기서 멈추고 원인부터 찾는다.**

### ④ 양쪽 대조

Phase 1에서 정한 "무엇이 남아야 하는가"를 확인한다.

```bash
adb -s "$DEV" logcat -d | grep -E "action:|key:"          # 기기에 무엇이 저장됐나
{프로젝트의 DB 클라이언트} -c "select ..."        # 서버에 무엇이 들어갔나
```

화면이 넘어갔는데 서버가 비어 있으면 **통과가 아니다.** 반대도 마찬가지다.

> 저장 시점이 단계마다가 아니라 **마지막에 몰아서**인 설계도 흔하다. 비어 있다고 바로
> 버그로 판단하지 말고 코드에서 저장 시점을 먼저 확인한다.

### ⑤ 서버 쪽을 함께 본다 ⚠️

**화면만 보고 통과시키지 않는다.** 화면은 멀쩡한데 서버에 이상한 값이 들어가 있을 수 있다.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py db   --profile db --root {ROOT} --sql "select ... where ..."   # 진짜 들어갔나
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py logs --root {ROOT} --tail 100 --grep "{키워드}"                 # 무엇을 보냈나·에러가 났나
```

**붙는 법과 로그 보는 법은 프로젝트마다 다르다.** 코드를 읽어 알아낸 뒤 `access`에 적어 두면
다음부터는 `--profile`로 바로 쓴다. 붙는 법은 `../../pro-launch/references/server.md`, 서버를 밟는 QA 는 `target-server.md`.

## Phase 6 — 되돌리기

같은 경로를 처음부터 다시 밟으려면 **계정과 앱 상태를 모두** 지워야 한다. 소셜 로그인은
한 번 가입하면 provider 식별자로 계정이 붙어 "첫 로그인" 경로를 다시 탈 수 없다.

```bash
adb -s "$DEV" shell pm clear {패키지}     # 앱 로컬 데이터
# 서버 계정 삭제는 프로젝트가 제공하는 도구를 쓴다
```

서버 계정을 지울 때는 **지울 대상을 먼저 조회해서 보여주고**, 테스트 계정만 지워지는지
확인한 뒤 실행한다. 운영 데이터가 섞여 있으면 사용자에게 확인받는다.

## 이 방식의 한계 — 언제 integration_test로 가야 하나 ⚠️

이 skill은 **화면을 읽고 그 자리에서 눌러** 밟는다. 무엇을 누를지 판단하는 부분은 사람(모델)이 해야
하므로, 아래가 구조적으로 불가능하다.

| 못 하는 것 | 왜 |
| --- | --- |
| CI에서 무인 실행 | 화면 판독에 사람이 필요하다 |
| 회귀 감지 | 이전 실행과 자동으로 비교하지 못한다 |
| 빠른 반복 | 한 단계마다 화면을 읽는다 |
| 위젯 내부 상태 확인 | 화면에 그려진 것만 볼 수 있다 |

**Flutter 는 요소 트리가 비어 있을 수 있다.** `uiautomator dump`는 캔버스만 보고,
`SemanticsBinding.ensureSemantics()`를 앱에 넣어도 접근성 서비스가 실제로 붙어야
노출되어 에뮬레이터에서는 여전히 빈 트리였다 (2026-09-17 실측). `app tree` 가 비면
`app tap --at` 비율 좌표로 가고, 누른 뒤 `--shot` 으로 반드시 확인한다.

### 그래서 이렇게 나눠 쓴다

| | `integration_test` · `patrol` | 이 skill |
| --- | --- | --- |
| 요소 찾기 | Finder — 위젯 키로, 안 깨진다 | 접근성 트리(문구·id). 트리가 없으면 비율 좌표 — 레이아웃 바뀌면 빗나간다 |
| CI 반복 | 된다 | 안 된다 |
| 앱 수정 | **필요** (pubspec·integration_test·빌드 설정) | 불필요 |
| 외부 앱(소셜 로그인 웹) | 제한적 (patrol은 네이티브까지) | **넘나든다** |
| 서버 DB 대조 | 직접 안 됨 | **한다** |
| 탐색적 발견 | 정해둔 것만 본다 | **예상 못 한 것을 찾는다** |

**반복 검증할 경로가 정해졌으면 `integration_test`로 옮긴다.** 이 skill은 그 앞 단계 —
아직 무엇을 검증해야 할지 모를 때, 외부 앱을 거칠 때, 서버까지 함께 봐야 할 때 쓴다.

> 프로젝트에 `integration_test/`나 `patrol`이 이미 있으면 **그쪽을 먼저 확인한다.**
> 같은 것을 두 번 검증할 이유가 없다.

## 자주 묻는 함정 (실전에서 겪은 것들)

| 함정 | 증상 | 대응 |
| --- | --- | --- |
| **누른 게 안 먹는다** | `screen_changed: false` | `app tree` 를 다시 읽는다. 키보드·안내 문구가 레이아웃을 민다. 같은 문구가 여럿이면 `--index` |
| **문구로 못 찾는다** | `not_found` | `candidates`·`locale` 에서 고른다. 화면 언어가 기기 설정과 다를 수 있다 |
| **스크롤을 덜 했다** | 요소가 잘려 보여 "가려졌다"고 오판 | 여러 번 밀어 끝까지 간다. 구조상 겹칠 수 없는데 잘려 보이면 스크롤을 의심한다 |
| **release에서만 죽는다** | debug는 멀쩡, 배포본만 크래시 | debug로 재현하려 하지 않는다. R8·서명·manifest는 release에서만 작동한다 |
| **서명 불일치로 설치 실패** | `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | 기존 앱을 지우고 설치한다. CI 빌드와 로컬 빌드는 서명이 다르다 |
| **로컬 데이터로 화면이 뜬다** | 서버에서 계정을 지웠는데 홈이 보임 | 앱 데이터도 지워야 초기 상태다 |
| **세션이 남아 2FA가 안 뜬다** | 어떤 때는 뜨고 어떤 때는 안 뜸 | 브라우저 쿠키가 남아서다. 매번 뜬다고 가정하고 안내 문구를 준비한다 |
| **한글이 입력되지 않는다** | `input text`에서 `NullPointerException` · `app type` 은 `non_ascii_unsupported` | ASCII만 받는다. 영문으로 대체하고 보고에 적거나, 한글 자체가 검증 대상이면 IME를 설치한다 |
| **요소 트리가 비어 있다** | `app tree` 에 위젯 텍스트가 안 나온다 | Flutter는 캔버스라 그렇다. `ensureSemantics()`를 넣어도 접근성 서비스가 붙어야 해서 에뮬레이터에서는 안 된다 — `--at` 비율 좌표로 간다 |
| **화면 전환을 움직임으로 오인** | 무게중심(밝기로 잰 요소의 평균 위치) 측정값이 계속 튐 | 측정 영역을 요소 크기로 좁힌다. 제목·키보드가 섞이면 값이 무의미하다 |
| **되돌릴 수 없는 동작을 성공 경로만 밟았다** | 통과로 보고했는데 실패 시 동작이 정해져 있지 않음 | 서버가 실패한 경우를 **일부러 만들어** 같은 버튼을 누른다. 성공·실패 두 경로를 다 밟아야 판정이 선다 |
| **첫 화면에 보이는 게 전부라고 봤다** | 화면 밖 항목에 영향을 주는 버튼(전체 선택 등)의 효과를 놓침 | 세로로 긴 목록은 **끝까지 스크롤해 항목 수를 센다.** 전체 선택이 있으면 무엇까지 켜는지 확인한다 |
| **화면만 보고 통과시켰다** | 화면은 멀쩡한데 서버에 이상한 값이 들어감 | 앱이 **무엇을 보냈는지** 서버 로그의 요청 본문으로 대조한다 (`logs --grep`) |
| **네트워크를 껐다 켰더니 DNS가 안 돌아온다** | 특정 도메인만 `Failed host lookup` | `svc wifi disable` 대신 `cmd connectivity airplane-mode enable/disable`을 쓴다 |
| **구글 계정 선택창이 비어 보인다** | 기기에 계정을 막 추가했는데 앱에서 안 보임 | 등록은 됐다. 앱을 재시작하면 나타난다 |
| **목록이 바뀐 화면에 옛 비율 좌표를 썼다** | 엉뚱한 항목이 눌려 전혀 다른 화면이 열림 | 항목이 하나만 늘어도 아래가 전부 밀린다. 가능하면 `--text` 로 누르고, `--at` 이면 **목록이 바뀐 화면은 다시 잰다.** 기기마다 빌드가 다르면 기기별로 따로 (`devices.md`) |

더 많은 명령과 iOS 대응은 `target-app.md` · `../../pro-launch/references/app.md`.
