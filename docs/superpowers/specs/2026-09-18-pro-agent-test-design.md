# pro-agent-test — 앱·웹·서버를 모두 밟는 범용 실행 테스트 스킬

`pro-flutter-e2e`를 Flutter 전용에서 벗어나게 한다. 앱·웹·서버 어느 프로젝트에서도
**agent가 직접 조작해 밟고 결과를 데이터로 증명하는** 하나의 스킬로 만든다.

## 왜 필요한가

프로젝트마다 타입이 다르다. elum은 Flutter 앱, pickerpicker는 웹, 백엔드만 있는 레포도 있다.
지금 스킬은 이름부터 `flutter`라 **웹·서버 레포에서는 후보로 떠오르지도 않는다.**

그런데 내용을 열어 보면 절반 가까이가 이미 플랫폼과 무관하다.

| 이미 범용 | 플랫폼 종속 |
|---|---|
| `scenario` (시나리오 파일·전제 상속·순환 참조 검증) | `detect` (pubspec·패키지명·번들ID) |
| `note` (learned.json 자가발전) | `devices` (adb·emulator) |
| `.gitignore` 보호·비밀값 탐지·마스킹 | `bootstrap` (`lib/features`·`*_screen.dart`) |
| `shrink` (이미지 축소) | `edges` (dart `catch` 스캔) |
| `backend` (DB·로그 대조 — 서버가 이미 일부 있다) | `doctor` (SDK 도구 점검) |

Phase 구조(경로 확정 → 관측 가능성 → 밟기 루프 → 사람 개입 → 보고)와 3축(상태 조합·실패 주입·
환경 조건)도 전부 플랫폼 무관한 사고틀이다. **바꿔야 하는 것은 "무엇으로 조작하고 무엇으로
판독하는가" 한 층뿐이다.**

## 결정 사항

### 이름: `pro-agent-test`

| 후보 | 탈락 이유 |
|---|---|
| `pro-e2e` | 부하 테스트를 담지 못한다. agent가 직접 밟는다는 성격도 안 드러난다 |
| `pro-agent-e2e` | 위와 같은 이유 — `e2e`가 종류 축의 족쇄가 된다 |
| `pro-e2e-testcase` | **기존 `pro-testcase`와 충돌.** 그쪽은 문서를 쓰고 이쪽은 실행한다 — 정반대인데 이름이 닮는다 |

`agent`는 이 스킬만의 성격(사람이 스크립트를 쓰는 게 아니라 agent가 화면을 보고 판단하며 조작)을,
`test`는 e2e·부하·그 밖의 종류를 함께 담는다.

### 두 개의 독립 축

혼동을 막기 위해 명시한다. **타겟과 모드는 다른 축이다.**

| 축 | 뜻 | 값 | 시나리오 키 |
|---|---|---|---|
| **target** | 무엇으로 조작하나 | `app` · `web` · `server` | `target` |
| **mode** | 무슨 종류의 테스트인가 | `e2e` (이번) · `load` (예약) | `mode` |

부하(`load`)는 **이번에 구현하지 않는다.** 스키마와 문서에 축만 예약해 둔다 — 예약 비용은
필드 하나와 문서 한 줄이지만, 나중에 없는 축을 끼워 넣으려면 스키마와 CLI를 다시 뜯어야 한다.

부하는 **`target: server`에서만 의미가 있다.** UI로는 부하를 걸 수 없고, 판정 기준도 다르다
(됐다/안 됐다가 아니라 p95·에러율·RPS라는 숫자).

### 웹 조작: Playwright 직접 (gstack 의존 금지)

gstack `/browse`는 Playwright의 대체제가 아니라 **Playwright 위에 얹은 래퍼**다
(`package.json`에 `playwright ^1.58.2`, 요구사항은 Bun v1.0+, Windows면 Node.js 추가).

projectops 스킬은 **남의 레포에 설치되는 물건**이라 별도 설치가 필요한 도구에 의존하면
그 사람 환경에서 아예 동작하지 않는다. 그래서 Playwright를 직접 쓴다. 웹 프로젝트라면
Node/npm이 이미 있으므로 진입장벽이 낮고, 없으면 설치를 시도한 뒤 안내한다
(`skills/references/`의 PyNaCl 선례와 같은 처리).

#### 브라우저 세션 유지 — 이 작업에서 가장 까다로운 지점

이 스킬은 **agent가 스크린샷을 보고 다음 수를 정하므로** 조작이 여러 번의 CLI 호출로 쪼개진다.
Playwright를 호출마다 새로 띄우면 **매번 브라우저가 새로 뜨고 로그인이 풀린다**(기동 ~3초).
gstack이 상주 데몬을 만든 이유가 이것이다.

데몬을 직접 구현하지 않고 **CDP 재연결**로 푼다.

```
① web open   → Chromium을 --remote-debugging-port로 띄우고 포트를 상태파일에 기록
② web click  → connect_over_cdp로 그 브라우저에 붙었다 떨어진다 (~100ms)
③ web shot   → 같은 방식. 세션·쿠키·로그인 상태가 유지된다
```

#### ⚠️ 실측 정정 — Playwright의 `launch()`로 띄우면 안 된다

처음에는 `pw.chromium.launch(args=["--remote-debugging-port=..."])`로 띄우고 `pw.stop()`은
"연결만 끊는다"고 적었다. **틀렸다.** `launch()`로 띄운 브라우저는 Playwright 드라이버
프로세스에 묶여 있어 **드라이버가 끝나면 브라우저도 함께 죽는다.** 실제로 두 번째 명령이
`connect ECONNREFUSED`로 실패했다.

그래서 **브라우저를 Playwright 밖에서 독립 프로세스로 띄운다.**

```python
with sync_playwright() as pw:
    exe = pw.chromium.executable_path      # 설치된 크로미움 경로만 얻는다
subprocess.Popen([exe, f"--remote-debugging-port={port}",
                  f"--user-data-dir={profile}", "--headless=new"],
                 start_new_session=True)   # 우리가 끝나도 살아 있다
```

`--user-data-dir`을 주면 쿠키·로그인이 다음 실행에도 남는다. 포트가 열릴 때까지 기다린 뒤
상태파일을 쓴다 — 안 기다리면 바로 다음 명령이 붙지 못한다. 닫을 때는 `browser.close()`만으로는
독립 프로세스가 안 죽으므로 기록해 둔 pid를 함께 정리한다.

#### 설치도 스킬이 한다

macOS의 Homebrew 파이썬은 **PEP 668로 `pip install`을 막는다**(externally-managed).
"`pip install playwright` 하세요"라고 안내만 하면 사용자는 거기서 멈춘다.

그래서 `web setup`이 **전용 가상환경(`~/.projectops/agent-test/.venv`)을 만들고 Playwright와
Chromium까지 받는다.** 시스템 파이썬은 건드리지 않는다. 약 100MB를 받으므로 **agent가 먼저
사용자에게 물어본다** — 물어보고 설치해 주는 것까지가 스킬의 역할이다.

### 서버: 단독 E2E까지

지금 `backend`는 "앱을 밟으면서 서버에 뭐가 남았나 대조하는 보조 수단"이다.
여기에 **서버 자체를 밟는 경로**를 더한다 — 화면 없는 백엔드 레포도 이 스킬로 검증된다.

서버 밟기의 핵심은 **이전 응답에서 값을 뽑아 다음 요청에 물리는 것**이다.

```json
{ "target": "server", "mode": "e2e",
  "steps": [
    { "do": "POST /api/auth/login {...}", "expect_status": 200,
      "save": { "token": "$.accessToken" } },
    { "do": "POST /api/routines {...}", "auth": "{token}", "expect_status": 201,
      "expect_server": "select count(*) from routine where ..." } ] }
```

DB는 **PostgreSQL을 유지한다**(현행 `_psql`). MySQL 등 확장은 이번 범위 밖 — 필요해지면 그때 넣는다.

## 구조

```
skills/pro-agent-test/
├── SKILL.md                 # 공통 방법론만: Phase 0~5, 3축, 시나리오, 자가발전
├── references/
│   ├── target-app.md        # adb·simctl·좌표 계산·한글 입력 함정 (현 device-control.md)
│   ├── target-web.md        # Playwright·CDP 재연결·셀렉터·콘솔 에러·뷰포트   (신규)
│   ├── target-server.md     # API 시퀀스·토큰 체이닝·DB 대조                  (신규)
│   ├── reporting.md         # 변경 없음
│   └── learning.md          # 변경 없음
├── scripts/e2e_cli.py
└── tests/test_e2e_cli.py    # 신규 — 아래 "테스트 전략"
```

**agent는 타겟이 확정된 뒤 해당 문서 하나만 읽는다.** 웹 프로젝트에서 adb 함정 표를 읽을 이유가 없다.
SKILL.md가 1000줄로 부푸는 것도 이 분리로 막는다.

### 타입 감지

순서대로 본다. 앞에서 정해지면 뒤는 보지 않는다.

1. **사용자가 명시** — `/pro-agent-test web`
2. **`version.yml`의 `project_types`** — projectops가 통합된 레포면 이미 있다
3. **마커 파일** — `pubspec.yaml`→app / `package.json`(react·next)→web / `build.gradle`·`pyproject.toml`→server

멀티타입이면(elum = flutter + spring) **묻는다.** 임의로 고르면 엉뚱한 것을 밟는다.

### CLI 서브커맨드

조작 수단이 셸에 이미 있는지에 따라 CLI 필요 여부가 갈린다.

| 타겟 | 조작 | CLI |
|---|---|---|
| app | `adb shell input tap` | ❌ agent가 셸로 직접 (현행 유지) |
| web | Playwright | ✅ `web` 신설 (open/goto/click/type/shot/assert/close) |
| server | HTTP 요청 | ✅ `api` 신설 (call — 토큰 체이닝·JSON 판정 때문) |

기존 서브커맨드 변화:

| 서브커맨드 | 변화 |
|---|---|
| `detect` | 타입 판정 추가 (위 3단계). 기존 출력 필드는 유지 |
| `bootstrap` | 타겟별 스캐너 분기 — app: `lib/features`·라우트 / web: 페이지·라우트 / server: 컨트롤러·엔드포인트 |
| `edges` | 타겟별 — dart `catch` / ts `catch` / java `@ExceptionHandler`·`throw` |
| `scenario` | `target`·`mode` 필드 검증 추가. 없으면 각각 `app`·`e2e` |
| `devices` · `doctor` | app 타겟 전용으로 남는다 |
| `note` · `shrink` · `backend` | 변경 없음 (`backend`는 서버 단독 E2E의 DB 확인에도 재사용) |

## 시나리오 스키마

**"무엇을 조작하는가"와 "무엇을 확인하는가"를 분리한다.** 이게 이 설계의 핵심 판단이다.

elum은 지금도 *앱을 밟으면서 서버 DB를 확인*한다(`steps[].expect_server`). 타겟을 시나리오
단위로만 묶으면 이 조합이 깨진다.

```json
{
  "name": "일과 만들기",
  "target": "app",              // 없으면 app — 기존 파일이 그대로 동작한다
  "mode": "e2e",                // 없으면 e2e
  "precondition": "_shared/login-kakao",
  "steps": [{
    "do": "...",                // 타겟 어댑터가 해석한다
    "expect_screen": "...",     // app · web
    "expect_device": "...",     // app
    "expect_status": 200,       // server
    "expect_server": "..."      // 모든 타겟 — 조작 대상과 무관하게 대조한다
  }]
}
```

`target`이 정하는 것은 **`do`를 누가 실행하느냐**뿐이다. `expect_*`는 타겟과 무관하게 여러 개
붙는다. 그래서 웹에서 밟고 서버 DB를 확인하는 것도, 서버 API를 밟고 로그를 확인하는 것도
같은 문법이 된다.

## 쌓인 지식은 워크트리를 건너 살아남아야 한다

**현재 설계의 결함이다.** 설계를 쓰면서 "경로를 바꾸면 learned.json이 끊긴다"고 적었는데,
실제로는 **이미 끊기고 있다.**

`learned.json`은 `{프로젝트루트}/docs/testing/e2e/`에 저장되고 `.gitignore`로 추적에서 빠진다.
**추적되지 않는 파일은 새 워크트리에 복사되지 않는다.** 그런데 이 조직은 `/pro-init-worktree`로
이슈마다 워크트리를 만드는 것이 기본이라, **이슈 하나가 끝날 때마다 쌓인 지식이 통째로 사라진다.**

실측: elum 본체에는 `learned.json` 13KB·`app-map.json` 5.4KB·`flows/`가 쌓여 있는데,
워크트리에는 하나도 없다. 자가발전이라고 부르지만 실제로는 매번 처음부터 시작하고 있었다.

### 홈으로 옮긴다

```
~/.projectops/agent-test/<owner>__<repo>/
├── learned.json      # 쌓은 지식 (함정·좌표·제약)
├── app-map.json      # 구조 스캔 결과
├── _shared/          # 전제 시나리오 (로그인 등)
└── flows/            # 기능별 시나리오
```

**프로젝트 식별은 `git remote`의 `owner/repo`로 한다.** 경로를 키로 쓰면 워크트리마다
갈라져 지금과 같은 문제가 그대로 남는다. remote가 없으면 폴더명으로 떨어진다.

`~/.projectops/`는 이미 config가 사는 곳이라 새 규칙을 만들지 않는다.

### 읽는 순서 (기존 지식을 잃지 않는다)

1. **홈에 있으면** 그것을 쓴다
2. 홈에 없고 **프로젝트에 있으면** 홈으로 1회 이전한 뒤 쓴다 — elum의 13KB가 그대로 살아난다
3. 둘 다 없으면 홈에 새로 만든다

이전은 **복사가 아니라 이동**이다. 두 곳에 남으면 어느 쪽이 최신인지 알 수 없어진다.
이전했다는 사실은 화면에 알린다 — 사용자가 프로젝트 폴더에서 파일을 찾다가 없어서 당황하지 않게.

### 함께 따라오는 이점

- 워크트리 여러 개에서 동시에 작업해도 **같은 지식을 본다**
- 산출물이 레포에 아예 생기지 않으므로 `.gitignore` 방어가 필요 없다 (서버 주소·토큰이
  공개 레포로 새던 경로가 구조적으로 사라진다 — #578에서 실제로 겪은 사고다)
- 프로젝트를 지워도 지식은 남는다

### 주의

여러 세션이 같은 프로젝트를 동시에 밟으면 `learned.json`에 동시 쓰기가 일어난다.
지금도 같은 위험이 있지만 홈으로 모으면 워크트리 간에도 겹친다. **읽기 → 병합 → 쓰기**로
처리하고, 통째로 덮어쓰지 않는다.

## 테스트 전략

**`e2e_cli.py` 1442줄에 현재 테스트가 하나도 없다.** (`skills/pro-github/tests/test_github_cli.py`는
있는데 e2e만 없다.) 이 상태로 타겟 어댑터를 넣겠다고 뜯으면 기존 앱 E2E가 조용히 깨져도 모른다.

**순서를 지킨다: 지금 동작을 고정하는 테스트를 먼저 쓰고, 그다음 확장한다.** 반대로 하면
"고치면서 깨진 것"과 "원래 그랬던 것"을 구분할 수 없다.

1. **회귀 고정** (리팩터 전에 작성)
   - 시나리오 전제 상속 · 순환 참조 거부 · 기대결과 없는 단계 거부
   - `target`·`mode` 없는 기존 파일이 `app`·`e2e`로 도는 것
   - 비밀값 탐지·마스킹 · `.gitignore` 보호
2. **타겟 어댑터** — 실제 기기·브라우저·서버 없이 **어댑터 선택과 명령 생성까지만** 검증한다.
   실행은 대역으로 막는다. 안 그러면 CI에서 돌릴 수 없다.
3. **타입 감지** — version.yml 있음/없음, 마커 파일별, 멀티타입일 때 묻는지

`skills/pro-github/tests/` 배치와 호출 방식을 그대로 따른다.

## 기존 것을 깨지 않기

| 대상 | 처리 |
|---|---|
| elum의 기존 시나리오 | `target`·`mode` 키가 없으므로 `app`·`e2e`로 간주 — **한 글자도 안 고친다** |
| 쌓인 지식(`learned.json` 등) | **홈으로 옮긴다.** 지금 위치는 워크트리마다 끊긴다 — 아래 별도 절 참조 |
| 폴더명 | `pro-flutter-e2e` → `pro-agent-test`. 플러그인 설치본이라 대상 레포에 남는 파일은 없다 |
| `pro-testcase` | 건드리지 않는다. 문서를 쓰는 스킬과 실행하는 스킬은 계속 별개다 |

CLAUDE.md의 Skill routing 표와 Skills 목록에서 `pro-flutter-e2e` 항목을 갱신한다.

## 이번 범위 밖

YAGNI로 잘라낸 것들. 필요해지면 그때 넣는다.

- **부하 테스트 구현** — 축만 예약한다
- **PostgreSQL 외 DB** — MySQL 등
- **Playwright 스크립트(.spec.ts) 내보내기** — CI 연동용. 지금은 agent가 밟는 것에 집중한다
- **iOS 좌표 탭** — 공식 명령이 없다는 현행 제약을 그대로 둔다
