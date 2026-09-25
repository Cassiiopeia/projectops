# pro-launch — 앱·웹·서버를 띄우고 조작하고 찍는 능력 스킬

> 상태: 설계 확정 · 작성 2026-09-25 · 이슈 #629 (본체) · #631 (이관) · #632 (render) · #633 (figma-verify 정리)
> 관련: `2026-09-25-pro-design-brief-design.md` (이 스킬의 첫 번째 새 사용처)
> 선례: `2026-09-18-pro-agent-test-redesign.md` ("판단은 agent, py는 실행·기록")

## 1. 왜 만드나

`pro-agent-test` 안에는 성격이 다른 두 가지가 섞여 있다.

| 들어 있는 것 | 예 | 성격 |
|---|---|---|
| **실행 능력** | 기기 찾기, 앱 띄우기, 스크린샷, 브라우저 조작, HTTP 요청, 로그·DB 보기 | 다른 작업도 쓰는 **도구** |
| **QA 방법론** | 시나리오, 해피 패스 밖 보기, 대칭 짝, 결함 리포트, 심각도 | QA만의 **절차** |

그래서 "에뮬레이터 띄워서 이 화면 하나 찍어줘"를 하려 해도 867줄짜리 QA 절차를 불러야 한다.
실제로 불편하다는 요구가 나왔고(2026-09-25), 새 스킬 `pro-design-brief`도 캡처가 필요하다.

**projectops 스킬을 두 층으로 본다.**

```
작업 스킬 (무엇을·어떤 절차로)   pro-agent-test   pro-design-brief   pro-figma-verify   pro-report
                                     │                 │                 │
능력 스킬 (어떻게·도구)          pro-launch        pro-github        pro-ssh
                                 띄우기·조작·캡처   이슈·이미지        서버 접속
```

이미 `pro-github` 이 이 모양이다 — `pro-agent-test` 는 스킬을 부르지 않고 `github_cli.py upload-image` 를
**스크립트로 바로** 부른다. 실행·캡처도 같은 자리로 올린다.

## 2. 지금 코드의 사실 (2026-09-25 조사)

`skills/pro-agent-test/scripts/e2e_cli.py` (3,056줄) 명령별 성격.

| 명령 | 성격 | 비고 |
|---|---|---|
| `doctor` `devices` `device` `web` `shrink` `get-output-path` | 실행·캡처 | 옮긴다 |
| `detect` | 혼합 | 실행 탐지(기기·브라우저·패키지)는 옮기고, `note target` 기록 참조는 agent-test 에 남긴다 |
| `access` `logs` `db` | 경계 | "서버에 붙는 법"이라 옮긴다 |
| `api` | 혼합 | 단건 HTTP 는 `launch http` 로, 시나리오 실행·판정은 agent-test 에 남긴다 |
| `other` | 혼합 | 명령 실행 + 산출물 스냅샷 판정 → agent-test 에 남긴다 |
| `scenario` `note` | QA | 남긴다 |

**감싸지 않은 것 / 없는 것**

- 앱 스크린샷은 CLI 가 감싸지 않는다. 문서가 `adb exec-out screencap -p`, `xcrun simctl io booted screenshot` 을
  직접 안내하고, 같은 안내가 `pro-figma-verify/references/rendering.md` 에도 중복돼 있다.
- **코드 렌더(위젯 렌더·Playwright locator 캡처)는 어디에도 기능이 없다.** rendering.md 에 설명만 있다.

**분리를 막는 결합** (각각 해결책이 §4 에 있다)

1. 저장 폴더 하나 — `~/.projectops/agent-test/<owner__repo>/` 에 devices.json · browser.json · access.json ·
   learned.json · 시나리오 · `.browser-profile` · `shots/` 가 섞여 있다 (`_home_dir()` E:1169).
2. venv 경로에 이름이 박혀 있다 — `~/.projectops/agent-test/.venv` (E:1828).
3. `env.sh` 변수가 `AGENT_TEST_RUN` · `RUN_DIR` · `SHOT_DIR` · `PKG` · `DEVn` · `ROLEn` 이고 문서 30~40곳이 기댄다.
4. 저수준 헬퍼(`_run` `_sdk_tool` `_to_webp` `_has_pillow` `_load_access`)를 두 그룹이 같이 쓴다.

**스킬 간 공유 수단은 `scripts/common/` 하나뿐이다.** 각 CLI 가 `_HERE.parents[3]/"scripts"` 를
`sys.path` 에 넣고 `from common.xxx import` 한다. 스킬끼리 파이썬 import 는 하지 않는다.

## 3. 원칙

1. **판단은 agent, 스크립트는 실행과 기록.** 스크립트가 프로젝트 모양(폴더 구조·파일명·설정 형식)을
   알아맞히지 않는다. 선례 문서의 교훈을 그대로 따른다.
2. **능력 스킬은 절차를 강요하지 않는다.** SKILL.md 는 "무엇을 부르면 무엇이 나오는가"와 함정만 담는다.
   무엇을 찍을지·왜 찍을지는 부르는 쪽이 정한다.
3. **다른 스킬은 스크립트로 부른다.** 스킬 호출(Skill tool)이 아니라 `launch_cli.py` 서브프로세스.
   발견 스니펫은 `skills/references/common-rules.md` 의 것을 `SKILL=pro-launch` 로 쓴다.
4. **모든 명령은 JSON 을 돌려준다** — `ok` `code` `summary` `next`. 기존 규약(`mcp-subcommand-rules.md`).
5. **흔적을 남기지 않는다.** 캡처는 `get-output-path` 가 준 자리에만 둔다. 대상 레포에 임시 파일을
   만들었으면 끝날 때 지웠는지 `git status` 로 확인한다 (`render` 가 강제한다).
6. **돈 드는 호출을 하지 않는다.** 캡처를 위해 AI 생성 API 를 부르지 않는다. 가짜 데이터로 채운다.

## 4. 구조

```
scripts/common/                ← 두 CLI 가 같이 쓰는 저수준 (신규 모듈)
  proc.py     run(), sdk_tool()             — adb/emulator 가 PATH 에 없을 때 실제 경로 찾기 포함
  image.py    to_webp(), shrink(), has_pillow()
  access.py   load_access(), save_access()  — 저장 위치는 state.py 가 정한다
  state.py    state_dir(kind, repo)          — kind: "launch" | "agent-test"
              venv_dir()                      — ~/.projectops/launch/.venv (옛 경로 폴백)

skills/pro-launch/
  SKILL.md
  scripts/launch_cli.py
  references/
    app.md          Android 에뮬레이터 · iOS 시뮬레이터 · 실기기 (agent-test target-app.md·devices.md 에서 이동)
    web.md          브라우저 준비·조작·응답 바꿔치기 (target-web.md 에서 이동 + route/viewport 추가)
    server.md       접속 정보·로그·DB (target-server.md 의 "붙는 법" 부분 이동)
    render.md       스택별 상태 연출 렌더 레시피 (신규 — #632)
  tests/

skills/pro-agent-test/scripts/e2e_cli.py
  scenario · note · api(시나리오 → common + launch http) · other
  옮긴 명령: 호환 기간 동안 launch_cli 로 넘겨주고 결과에 "pro-launch 로 옮겼다" next 를 싣는다
```

### 4.1 저장 폴더를 나눈다

| 폴더 | 담는 것 |
|---|---|
| `~/.projectops/launch/<owner__repo>/` | devices.json · browser.json · access.json · `.browser-profile/` · `shots/` |
| `~/.projectops/launch/.venv` | Playwright · Pillow |
| `~/.projectops/agent-test/<owner__repo>/` | learned.json · 시나리오 · flows/ |

**이전(migration)** — `state.py` 가 첫 호출 때 옛 폴더에 launch 몫 파일이 있고 새 폴더에 없으면 **옮기고**
결과 JSON 에 `migrated: [...]` 를 싣는다. 옛 venv 는 옮기지 않고 새 경로가 없으면 옛 경로를 쓴다
(재설치 비용 회피). 두 번째 실행부터는 아무 일도 하지 않는다 (멱등). 옮기기 실패 시 옛 경로를 그대로
읽고 경고만 낸다 — 기능이 멈추지 않는다.

### 4.2 `env.sh` 변수 이름은 그대로 둔다

`$SHOT_DIR` `$RUN_DIR` `$DEV` `$DEVn` `$ROLEn` `$PKG` 는 유지한다. 문서 예시 30~40곳이 기대고 있어
바꾸는 비용이 이득보다 크다. `AGENT_TEST_RUN` 은 agent-test 가 만든 env 에서만 쓰고, launch 가 만든 env 는
`LAUNCH_RUN` 을 쓴다. 공통 변수는 두 쪽 모두 같은 이름이다.

### 4.3 산출물 자리

`common/paths.py` 의 `EVIDENCE_SKILLS` 에 `"launch"` 를 넣는다 (폴더별 `.gitignore` 자동). 호출하는
작업 스킬이 자기 id 로 자리를 받고 싶으면 `get-output-path --skill <id>` 로 넘긴다 — design-brief 는
`--skill design-brief` 로 자기 폴더에 캡처를 받는다.

## 5. 명령 (launch_cli.py)

| 명령 | 하는 일 | 출처 |
|---|---|---|
| `doctor` | 도구(adb · simctl · Chromium · Pillow · cwebp · ffmpeg) 설치 여부 · 저장 위치 | 이동 |
| `detect --path` | 무엇을 띄울 수 있는지(app/web/server) · 패키지명·번들 ID · 기기 · 브라우저 준비 상태. **프로젝트 구조를 알아맞히지 않는다** — 마커 파일(pubspec.yaml · package.json · build.gradle 등) 유무만 본다 | 이동(실행 탐지만) |
| `devices` | 붙은 기기·부팅된 시뮬레이터·AVD | 이동 |
| `device list\|bind\|unbind\|show` | 역할을 기기에 묶는다 | 이동 |
| `app shot --device <id> --out <name>` | **신규.** Android 는 `adb exec-out screencap -p`, iOS 시뮬레이터는 `simctl io <udid> screenshot`. 저장 자리는 `$SHOT_DIR`. 상태바 시각을 고정하고 싶으면 `--clean-status` (iOS `simctl status_bar override`, Android demo mode) | 문서 → 명령 |
| `app launch --device <id> [--pkg]` | **신규.** 설치된 앱 실행 (`am start` / `simctl launch`) | 문서 → 명령 |
| `web setup\|open\|goto\|click\|type\|shot\|assert\|console\|close` | 브라우저 조작 (CDP 연결 방식 그대로) | 이동 |
| `web viewport --preset mobile\|tablet\|desktop\|<w>x<h>` | **신규.** 폭 바꿔 찍기 | 신규 |
| `web route --match <glob> --status <code> [--body <file>]` | **신규.** 응답 바꿔치기 — 빈 목록·500·지연을 연출한다. 규칙은 `browser.json` 에 저장하고 `add_init_script` 가 아니라 CDP `Fetch.enable` 로 건다 (연결이 끊겨도 규칙이 남도록 다음 연결 때 다시 건다). `web route --clear` 로 해제 | 신규 |
| `render run --cmd "<명령>" --collect <glob> [--cleanup <path>...]` | **신규.** 렌더 명령(agent 가 짠 테스트)을 돌리고, 나온 PNG 를 `$SHOT_DIR` 로 옮기고, `--cleanup` 경로를 지운 뒤 **대상 레포 `git status` 가 실행 전과 같은지** 확인한다. 다르면 `ok:false, code:"residue"` 와 남은 경로를 돌려준다 | 신규 (#632) |
| `http --method --url [--header] [--data]` | 단건 요청. 상태·헤더·본문 저장 | `api` 에서 분리 |
| `access show\|set\|unset` · `logs` · `db` | 서버에 붙는 법 | 이동 |
| `shrink` | 이슈 첨부용 축소·WebP | 이동 |
| `get-output-path [--skill <id>] --title` | 이번 실행 자리 + `env.sh` | 이동 |

### 5.1 `render` 는 왜 이 모양인가

스택마다 렌더 방법이 다르고, 같은 Flutter 라도 상태 관리(Riverpod · Bloc · Provider)에 따라 가짜 값을
넣는 법이 다르다. 스크립트가 이걸 알아맞히면 선례 문서가 지적한 병이 재발한다. 그래서

- **렌더 코드는 agent 가 `references/render.md` 레시피를 보고 대상 레포에 임시로 짠다.**
- **`render run` 은 실행 · 수집 · 청소 · 흔적 검사만 한다.**

2026-09-25 elum #419 에서 실제로 이 순서로 했다: 임시 테스트 파일로 실제 화면 9장을 뽑고,
파일을 치운 뒤 `git status` 로 확인했다. 그때 사람이 챙긴 "흔적 검사"를 명령이 강제한다.

## 6. render.md — 스택별 레시피 (#632)

| 스택 | 기본 캡처 | 엣지 상태 연출 | 보조 |
|---|---|---|---|
| Flutter | 위젯 테스트 렌더 (`matchesGoldenFile` 을 임시 경로로 + `--update-goldens`). 폰트를 싣는 `flutter_test_config.dart` 가 있는지 먼저 본다 — 없으면 한글이 □ 로 나온다 | 상태 관리 override (Riverpod `overrideWith`, Bloc `MockBloc` 등). 안전영역은 `MediaQuery` padding 으로 재현 | 시뮬레이터 `app shot` |
| React / Next | Playwright `page.screenshot` / locator 캡처. Storybook 이 있으면 스토리 URL 을 우선 | `web route` 로 API 응답 교체. 폭은 `web viewport` | dev 서버 실화면 |
| React Native | 시뮬레이터·에뮬레이터 `app shot` | 목 서버 · 개발 메뉴 플래그 · 테스트 빌드 환경변수 | Expo 웹 빌드 + Playwright |
| Spring 서버 렌더(Thymeleaf 등) | 서버를 test 프로필로 띄우고 Playwright | 시드 데이터 · test 프로필 | MockMvc 로 HTML 만 뽑아 정적 렌더 |
| 순수 API 서버 | **화면이 없다** → 에러 코드별 사용자 문구 카탈로그 + 상태 목록 + ASCII | 에러 응답을 하나씩 `http` 로 확인 | — |
| 렌더 불가 | ASCII 와이어 (등폭 · 박스 문자) | — | — |

레시피마다 **알려진 함정**을 적는다 (elum 실측):

- Flutter 오버레이를 `Material` 밖에 그리면 글자에 노란 이중 밑줄이 붙는다.
- 무한 애니메이션 화면은 `pumpAndSettle` 이 끝나지 않는다 → "동작 줄이기"를 켠다.
- 골든 기준 파일과 섞지 않도록 임시 폴더명을 쓰고 끝나면 지운다.

## 7. 호환 · 이전 (#631)

- `e2e_cli.py` 의 옮긴 명령은 **한 마이너 버전 동안** launch_cli 로 넘겨준다. 출력은 그대로에
  `next: "pro-launch 의 launch_cli.py <명령> 을 쓴다"` 를 싣는다. 다음 마이너에서 제거한다.
- 문서 교체 범위: agent-test SKILL.md 약 25곳, references 약 30곳(target-web 13 · target-server 6 ·
  devices 6 · target-other 4 · learning · social-login · reporting), `skills/references/doc-output-path.md:19`.
- 테스트 이동: `tests/test_e2e_cli.py` 중 web · device · shrink · webp · output · env 계열 약 30개를
  `skills/pro-launch/tests/` 로 옮기고 import 를 바꾼다. `local_only`(실제 Chromium) 3건 포함.
- `scripts/tests/test_cli_signatures_doc_sync.py` 의 `CLI_TO_SKILL` 에 `launch_cli.py → pro-launch` 추가.
  (e2e_cli 는 현재 목록에 없다 — 이번에 함께 넣는다.)
- **함께 고칠 기존 결함** — `references/social-login.md:119` 가 없는 명령 `note trap` 을 안내한다.
  `SKILL.md:59` 가 "아래 5줄로 SCRIPTS 를 찾는다"고 하지만 그 5줄이 없다.

## 8. pro-figma-verify 정리 (#633)

`references/rendering.md` 의 simctl/adb·Playwright 안내를 `pro-launch` 로 가리키게 바꾼다. figma-verify
에만 해당하는 내용(RepaintBoundary 3배 캡처, 골든은 대조 대상이 아니다)은 남긴다. `get-output-path` 의
중복 구현(figma_verify_cli.py:860)은 `common/paths.py` 를 쓰는지 확인만 한다.

## 9. 실패 경로

| 상황 | 동작 |
|---|---|
| 기기 없음 | `ok:false, code:"no_device"`, `next` 에 부팅 명령 |
| Chromium 미설치 | `code:"browser_missing"`, `next: "web setup"` |
| Pillow 없음 | shrink 는 sips → ffmpeg 순 폴백, 셋 다 없으면 원본을 그대로 두고 경고 |
| render 명령 실패 | 수집하지 않고 청소만 한 뒤 `code:"render_failed"` + 명령 출력 끝 40줄 |
| render 뒤 흔적 | `code:"residue"` + 남은 경로 (지우지 않는다 — 남의 변경일 수 있다) |
| 옛 저장 폴더 이전 실패 | 옛 경로를 읽고 경고, 기능은 계속 |

## 10. 검증 기준

- `pytest skills/pro-launch/tests skills/pro-agent-test/tests scripts/tests` 전부 통과
- `test_cli_signatures_doc_sync` 통과 (launch_cli 모든 서브커맨드가 SKILL.md 에 호출 예로 있다)
- 실측: Android 에뮬레이터 · iOS 시뮬레이터 `app shot`, 웹 `web route` 로 빈 목록·500 연출 캡처,
  Flutter 레포(elum)에서 `render run` 으로 상태 캡처 + residue 검사가 잡히는지
- pro-agent-test 로 기존 시나리오 하나를 끝까지 밟아 회귀 없음 확인

## 11. 하지 않는 것

- 프로젝트 구조 추측 (라우트·화면 목록 스캔 등) — agent 가 코드를 읽는다
- 앱 조작을 위한 새 추상화 (탭·스와이프는 지금처럼 `adb shell input` 직접) — 요구가 생기면 따로
- Figma 에 그리기 — MCP 가 읽기 전용이다
