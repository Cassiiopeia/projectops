---
name: pro-agent-test
description: "앱·웹·서버를 실제로 실행해 밟으며 **버그를 찾는 QA**다. 코드를 고치지 않고 결함을 찾아 재현 절차·근거·심각도와 함께 보고한다. 유닛/위젯 테스트가 아니라 사람이 하듯 화면을 누르고(앱·웹) 요청을 보내며(서버), 단계마다 기기 저장소·브라우저 상태·서버 DB를 대조한다. **요청받은 자리만 보지 않는다** — 같은 성격의 다른 화면·대칭이 되는 동작(가입↔탈퇴, 생성↔삭제)도 함께 확인해 일관성 결함을 찾는다. 로그가 없으면 그것을 추적 불가 결함으로 보고한다. '실제로 테스트해줘', '에뮬레이터로 돌려봐', '브라우저로 확인해줘', 'API 순서대로 밟아줘', 'QA해줘', '버그 찾아줘', '엣지 케이스 봐줘', '회원가입 테스트해줘', 'E2E 해줘', '로그인부터 끝까지 밟아줘', '실기기 검증' 같은 요청에 사용한다. QA 문서를 만드는 일(pro-testcase)과는 다르다 — 이 skill은 실제로 실행한다."

version: "2.1"
---

# agent QA — 앱·웹·서버를 실제로 밟아 버그를 찾는다

**너는 QA다. 코드를 고치는 쪽이 아니라 버그를 찾는 쪽이다.** 깨뜨려 보고, 재현 절차와 근거를 남기고,
심각도를 매겨 보고한다. 고치는 것은 다른 skill(`superpowers:*`)의 일이다 —
여기서 고치기 시작하면 무엇이 원래 결함이었는지 알 수 없게 된다.

> **목적은 통과가 아니라 발견이다.** 정상 경로는 개발자가 이미 수십 번 밟았다. 밟을 목록은
> "되는지 확인"이 아니라 **"어디가 깨질까"** 로 정하고, **요청받은 자리만 보지 않는다**(Phase 4.5).

쓰지 않는 경우: QA 문서 작성(`/pro-testcase`), 위젯 단위 검증(`flutter test` 가 빠르고 정확하다).
쓰는 경우: 배포 전 주요 흐름 확인 · 사용자 제보 재현 · release 빌드에서만 나는 문제(R8·서명·manifest 병합은
debug 에서 동작하지 않는다) · 기기와 서버에 무엇이 남는지 단계별 확인 · 한 곳을 고쳤을 때 같은 성격의 다른 곳.

`../references/common-rules.md` 의 **절대 규칙** 적용 (Git 커밋 금지, 민감 정보 보호). 사용자가 준 계정·비밀번호는
**파일·커밋·보고 문장에 남기지 않는다** — 기기 입력에만 쓴다. 인자: $ARGUMENTS

## 무엇을 하려는가 → 명령 → 자세한 문서

QA 판단은 이 스킬(`{SCRIPTS}/e2e_cli.py`), **실행·캡처는 pro-launch**(`{LAUNCH}/launch_cli.py`)다.

| 하려는 것 | 명령 | 자세히 |
|---|---|---|
| 무엇을 밟을 수 있나 · 타겟별 정보(패키지명 · 기기 · `adb_path` · 웹 주소 · 적어 둔 접속 정보) | `e2e_cli.py detect --path .` | `references/planning.md` |
| 판단한 타겟 적기 · 화면·규칙·함정·실행 결과 쌓기 · 범위 정리 | `e2e_cli.py note show\|target\|screen\|constraint\|pitfall\|run\|tidy\|forget` | `references/learning.md` |
| 시나리오 틀 · 목록 · **밟기 전 검증** | `e2e_cli.py scenario init\|list\|show` | `references/planning.md` |
| 서버 시나리오를 끝까지 밟기 | `e2e_cli.py api --name` | `references/target-server.md` |
| 앱·웹·서버가 아닌 것(CI·CLI·라이브러리) 돌리고 산출물 보기 | `e2e_cli.py other run` | `references/target-other.md` |
| 산출물 자리 + `env.sh` | `launch_cli.py get-output-path --skill agent-test` | 아래 |
| 기기 고르기 · 역할 묶기(참가자 둘 이상) | `launch_cli.py devices` · `device list\|bind` | `references/devices.md` |
| 앱 띄우기 · 화면 구조 · 누르기 · 밀기 · 찍기 | `launch_cli.py app launch\|tree\|tap\|swipe\|shot` | `references/stepping.md` · `references/target-app.md` |
| 브라우저 · 빈 목록/500/지연 연출 | `launch_cli.py web …` · `web route` | `references/target-web.md` |
| 서버 DB · 로그 대조 | `launch_cli.py access` · `db` · `logs` | `references/target-server.md` |
| 로그인 관문 · 사람이 해야 하는 화면 | `web open --headed` · `web type --text-env` | `references/social-login.md` |
| 되는데 이상한 것(축 4·5·6·7) | — | `references/looks-wrong.md` |
| 횡단 · 대칭 · 남의 환경 · 파급 · 제안 | `note constraint` · `other run --env` | `references/wide-view.md` |
| 결함 리포트 · 이슈 등록 · 정정 | `launch_cli.py shrink` · `github_cli.py upload-image` | `references/reporting.md` |

## 스크립트 찾기 — 한 번만

**Bash 도구는 호출마다 상태가 초기화된다.** 한 번 찾은 뒤 **실제 경로를 이후 블록에 값으로 직접 써넣는다.**

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
for SKILL in pro-agent-test pro-launch; do
  ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  [ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
    H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
    [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
  done
  [ -d "$ROOT/skills/$SKILL/scripts" ] || { echo "$SKILL 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
  echo "$SKILL=$ROOT/skills/$SKILL/scripts"
done
echo "PYTHON=$PYTHON PROJECT_ROOT=$PROJECT_ROOT"
```

`pro-agent-test=` 값이 `{SCRIPTS}`, `pro-launch=` 값이 `{LAUNCH}` 다. 명령별 옵션과 함정은 `../pro-launch/SKILL.md`.

## 산출물 자리 — 먼저 받는다. 경로를 지어내지 않는다 ⚠️

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py get-output-path --skill agent-test --title "{무엇을 밟는지}"
```

돌려준 `env_file` 을 **이후 모든 블록 첫 줄에서 source 한다** — `$SHOT_DIR` · `$RUN_DIR` · `$DEV` · `$PKG`.
`/tmp` 나 `docs/testing` 같은 임의 경로에 쌓지 않는다 — 실제로 대상 레포에 **8MB가 `.gitignore` 밖에 쌓인** 적이
있다(#611). 이 자리는 `docs/projectops/` 우산 아래이고 폴더가 `.gitignore` 를 스스로 들고 있다.

> `e2e_cli.py` 로 옛 이름(`web` · `device` · `access` …)을 불러도 한 마이너 버전 동안은 pro-launch 로
> 넘겨준다(`moved_to` · `next`). 새로 쓰는 명령은 `{LAUNCH}` 로 쓴다.

## 공통 규칙

- **JSON 하나를 돌려준다.** `ok` 로 성패, `code` 로 갈래(문구가 아니라 code 로 판단), `next` 를 다음 명령 후보로 읽는다.
- **앱은 요소로 누른다.** `app tree` 로 문구·id·`locale` 을 보고 `app tap --text|--id|--desc [--index N]`.
  요소가 없을 때만 `--at 0.5,0.8` **비율** 좌표. 픽셀 좌표 계산 · raw `adb shell input tap` · 호스트 마우스(`cliclick` · AppleScript)는 쓰지 않는다.
- **`--shot 이름` 을 붙여 누른다.** 화면이 바뀌고 멈춘 뒤 찍어 준다. `screen_changed: false` 면 반응이 없었다.
- **텍스트로 확인되면 이미지를 읽지 않는다**(`app tree` · `web assert` · 로그). 캡처는 긴 변 1200px WebP 가 기본이다.
- **`adb` 는 항상 `-s "$DEV"`.** 기기가 여러 대면 빠뜨린 명령이 엉뚱한 쪽으로 간다.
- **화면만 보고 통과시키지 않는다.** 기기 저장소·서버 DB·서버 로그를 함께 대조한다.
- 바꾼 설정(글씨 크기 · 다크모드 · 네트워크 · 회전 · 테스트용 빌드 플래그)은 **끝나면 바로 되돌린다.**
- 비밀번호는 `--text` 가 아니라 `--text-env` · `--cred`. 자동 재시도는 한 번까지.

## 순서 — 단계별 결정 규칙

**Phase 0 — 타겟부터 정한다 ⚠️** `detect` 의 `targets` 가 하나면 그것, 여럿이면 **묻는다**, 없으면 `--target app|web|server|other`
를 받는다. 앱·웹·서버가 아니면 `other`. `target_source` 가 `version.yml` 이고 **`confirm`** 이 붙으면 선언일 뿐이다 —
서버가 화면을 직접 뿌리는지(템플릿 폴더 · 뷰 반환 컨트롤러) 코드를 보고 판단해 `note target --targets server,web --why "…"` 로 적는다.
타겟이 정해지면 **그 문서 하나만** 읽는다: `references/target-app.md` · `references/target-web.md` · `references/target-server.md` · `references/target-other.md`.
앱이면 `device list` 로 기기를 확정한다 — `build_mismatch` 면 거기서 멈춘다(`references/devices.md`).

**Phase 0.5 — 구조를 읽는다.** 화면·라우트·엔드포인트·인증·자원 소유는 **네가 Grep·Read 로** 읽고 `note screen` · `access set` 에 남긴다.

**Phase 1 — 경로를 정한다.** `scenario list` → 없으면 사용자 지정 → 둘 다 없으면 한 번만 묻는다. 단계마다
"무엇을 누르고 → 무엇이 보이고 → 기기/서버에 무엇이 남아야 하나"를 적는다. 다시 밟을 경로와 `server` 타겟은
`scenario init` → 채우기 → **`scenario show` 로 검증**. 해피 패스만 밟지 않는다 — 상태 조합 · 실패 주입 · 환경 조건
세 축에서 고른다(`references/planning.md`).

**Phase 2 — 관측을 확보한다.** 밟기 전에 로그로 상태를 볼 수 있는지 본다. **로그가 없으면 그 자체가 결함**(관측성)이다 —
로깅을 넣어 주지 않고, 그 구간 판정에 "근거 부족"을 적는다.

**Phase 3 — 밟는다.** `① app tree/shot → ② app tap/swipe --shot → ③ screen_changed · mCurrentFocus · crash 로그 →
④ 기기 저장 대조 → ⑤ db · logs 로 서버 대조`. 목록은 끝까지 민다. 크래시가 보이면 멈추고 원인부터. 상세·함정 표는 `references/stepping.md`.

```bash
source "{env_file 값}"
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app tree  --device "$DEV"
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app tap   --device "$DEV" --text "{화면 문구}" --shot step_01
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py db --profile db --root {ROOT} --sql "select ..."
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py api --name {시나리오} --root {ROOT}       # server
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py other run --command "{명령}" --watch {예상 경로}   # other
```

**Phase 4 — 사람이 해야 하는 지점에서 멈춘다.** 2단계 인증 · 생체 · 결제 · 외부 앱 · 캡차. 무엇을 어디서 누르는지
한 줄로 알린다. **로그인 화면 자체는 네가 통과시킨다** — 이메일·비밀번호까지 넣고 2단계 인증에서만 멈춘다.
누르기 전에 **주소의 `flowName` 을 읽는다**: `WebLiteSignIn` 이면 자동화로 인식돼 이메일 단계에서 거부된다(시도하지 않는다),
`GlifWebSignIn` 이면 정상. 그래서 로그인이 필요하면 **처음부터 `web open --headed`** 로 연다(2026-09-18 실측: headless 는
`WebLiteSignIn`, `--headed` 는 `GlifWebSignIn`). 비밀번호는 `--text-env`. 상세는 `references/social-login.md`.
Android 네이티브 Google 로그인(Play Services 계정 선택 창)은 앱 밖 화면이다 — 기기에 테스트 계정이 있으면 `app tap --text <계정>` 으로 고르고, 없거나 2단계 인증이면 멈추고 사용자에게 넘긴다.

**Phase 4.4 — 되는데 이상한 것.** `$SHOT_DIR` 의 화면을 나란히 놓고 축 4(같은 것이 같게) · 5(눌러서 말이 되나) ·
6(움직임) · 7(시안 대조 기록)을 **값으로** 본다 — "느낌"이 아니라 "제목 크기 4개 화면에서 3종류". 시안이 있는 화면인데
대조 기록이 없으면 그 자체를 결함으로 보고한다(`pro-figma`). `references/looks-wrong.md`.

**Phase 4.5 ~ 4.8 — 넓게 본다(밟은 뒤 반드시).** 규칙을 한 문장으로 뽑아 같은 성격의 자리를 **전부** 확인(횡단),
가입↔탈퇴 · 생성↔삭제 짝 확인(대칭), 남의 환경(기본값 · 설치물 · 첫 상태 · 안 밟은 분기 · 결과물), 고치면 함께 움직이는 곳(파급),
결함은 아니지만 더 나은 방식(제안). 규칙은 `note constraint` 로 쌓는다. `references/wide-view.md`.

**Phase 5 — 결함 리포트.** 기능 결함 · 일관성 결함 · 관측성 · 개선 제안 · 통과 · 보류를 **나눠** 적는다. 결함마다 재현 절차 ·
기대 vs 실제 · 근거 · 심각도(치명/높음/보통/낮음/관측성) · 영향 범위. 추측으로 심각도를 올리지 않는다. 이미지는
`shrink` → `upload-image` → 본문 순서. 잘못 본 것은 즉시 정정한다. `references/reporting.md`.

**Phase 6 — 되돌린다.** `pm clear` + 서버 테스트 계정 정리(지울 대상을 먼저 조회해 보여준다). `references/stepping.md`.

## 기록 쌓기

앱·웹 작업을 시작할 때 `pro-launch` 의 `recall --area ios|android|web|server` 를 한 번 보고, 끝나면 먹힌 방식을 `learn --result ok|fail` 로 남긴다.
알아낸 화면·규칙·함정·실행 결과는 `note` 로 남긴다. **`detect` · `scenario show` 응답의 `memory` 에 맥락에 맞는 규칙·함정이 몇 건 실려 온다**
(하루·영역 한 번) — 먼저 읽는다. 전부는 `note show --all`, 기본 `note show` 는 요약이다. 기록은 홈
(`detect` 의 `knowledge_dir`)에 쌓여 워크트리를 새로 만들어도 산다. 이메일·전화·JWT·비밀번호가 섞이면 거부된다.

- 화면 기록은 **요소**(`--target "라벨=text:문구"`) 또는 **비율**(`"라벨=at:0.5,0.8"`)로 남긴다. 픽셀은 거절된다.
- 기록한 대상으로 `app tap --shot` 을 했으면 **결과를 남긴다** — `screen_changed: true` 면 `note screen --name 화면 --target 라벨 --result ok`,
  `not_found` 거나 `screen_changed: false` 면 `--result fail`. 실패가 앞선 대상은 `verify` 가 붙어 다음에 다시 확인하게 된다.
- 함정·규칙을 쓰면 비슷한 것을 먼저 찾는다. 확실히 같으면 합쳐지고(`merged_into`), 애매하면 `related` 가 온다 — 같은 지식이면 `next` 대로 합친다.
- `flutter` · `platform` 범위 함정은 이 컴퓨터 범위(`_machine`)에 쌓인다. 예전 기록은 `note tidy`(계획) → `note tidy --apply` 로 옮긴다.

`references/learning.md`.

## 실패 code → 다음 행동

| code | 다음 행동 |
|---|---|
| `no_device` | `devices` 로 보고 `--device` 를 준다. 기기가 없으면 `next` 의 부팅 안내 |
| `not_found` · `index_out_of_range` | `candidates` 에서 고른다. 화면 언어는 `locale`. 추측을 반복하지 않는다 |
| `bad_ratio` | `--at` 은 0~1 비율만 받는다. 픽셀이면 화면 크기로 나눈다 |
| `pixels_rejected` (note screen) | 픽셀은 저장하지 않는다. `hint` 의 `라벨=at:…` 비율로, 요소가 보이면 `text:`·`id:`·`desc:` 로 |
| `tree_unsupported` · 빈 `elements` | Flutter 캔버스 등 — `--at` 비율 좌표로 누르고 `--shot` 으로 확인한다 |
| `build_mismatch` | 기기마다 빌드가 다르다. 멈추고 양쪽을 맞춘다 |
| `ios_tool_missing` · `android_tool_missing` · `adb_missing` | 결과의 설치 안내를 사용자에게 제안한다 |
| `non_ascii_unsupported` | 한글 불가. 영문 대체 후 보고에 적거나, 검증 대상이면 IME · 사용자 입력 |
| `playwright_missing` | 사용자에게 묻고 `web setup` |
| `env_not_set` | `--text-env` 로 지정한 환경변수가 비었다. 값을 넣어 다시 |
| `scenario show` 의 검증 실패 | 기대 결과 · 중괄호 · 타겟을 채우고 다시 `show` |
