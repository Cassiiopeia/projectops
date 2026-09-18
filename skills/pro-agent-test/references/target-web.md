# 웹을 밟는다 (target: web)

`pro-agent-test`가 **브라우저를 직접 몰 때** 쓰는 문서. 앱(`target-app.md`)·서버
(`target-server.md`)를 밟을 때는 읽을 필요가 없다.

## 준비 — 없으면 설치를 제안한다

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py detect --path {PROJECT_ROOT}
```

`web.playwright.ready`가 `false`면 **사용자에게 물어본 뒤 설치한다.** 안내만 하고 세워 두지
않는다 — 그러면 사용자는 거기서 멈춘다.

```
웹을 밟으려면 브라우저(약 100MB)를 받아야 합니다. 설치할까요?
```

승인받으면:

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py web setup
```

전용 가상환경(`~/.projectops/agent-test/.venv`)에 Playwright와 Chromium을 받는다.
**시스템 파이썬은 건드리지 않는다** — macOS의 Homebrew 파이썬은 PEP 668로 `pip install`을
막아 두어 거기에 깔려고 하면 애초에 실패한다. 멱등이라 여러 번 불러도 괜찮다.

## 조작 — 한 번에 하나씩

```bash
... web open  --root {ROOT} --url {주소}        # 브라우저를 연다
... web goto  --root {ROOT} --url {주소}
... web click --root {ROOT} --selector "{셀렉터}"
... web type  --root {ROOT} --selector "{셀렉터}" --text "{값}"
... web shot  --root {ROOT}                     # 화면을 찍는다
... web assert --root {ROOT} --url /home --text "환영"
... web console --root {ROOT}                   # 콘솔 오류를 듣는다
... web close --root {ROOT}
```

**매 조작 전에 `shot`으로 화면을 본다.** 이전 화면 기억으로 누르지 않는다 — 모달이 떴거나
안내 문구가 늘어 요소가 밀려 있을 수 있다. 앱을 밟을 때와 같은 규칙이다.

### 왜 호출이 쪼개져 있나

이 스킬은 **agent가 화면을 보고 다음 수를 정한다.** 그래서 한 번에 다 밟는 스크립트가 아니라
명령 하나가 동작 하나를 한다. 대신 브라우저는 계속 살아 있어야 한다.

```
web open  → Chromium을 독립 프로세스로 띄우고 CDP 포트를 상태파일에 적는다
web click → 그 브라우저에 붙었다 떨어진다 (세션·쿠키 유지)
```

> **⚠️ `launch()`로 띄우면 안 된다 (실측).** Playwright의 `launch()`로 만든 브라우저는
> 드라이버 프로세스에 묶여 있어 **드라이버가 끝나면 함께 죽는다.** 두 번째 명령이
> `connect ECONNREFUSED`로 실패한다. 그래서 `executable_path`만 얻어 `subprocess`로 직접
> 띄운다. 이 구조를 바꾸면 세션 유지가 통째로 깨진다.

## 셀렉터 — 무엇을 가리킬 것인가

| 방식 | 예 | 언제 |
|---|---|---|
| 텍스트 | `text=로그인` | **기본값.** 사람이 보는 것과 같아 화면이 바뀌어도 잘 버틴다 |
| 역할+이름 | `button:has-text('저장')` | 같은 글자가 여러 곳에 있을 때 |
| id | `#email` | 개발자가 붙인 안정된 이름이 있을 때 |
| CSS 경로 | `div > ul > li:nth-child(3)` | **마지막 수단.** 레이아웃이 조금만 바뀌어도 깨진다 |

좌표로 누르지 않는다. 앱과 달리 웹은 요소를 이름으로 가리킬 수 있으므로 좌표를 쓸 이유가 없다.

## 되는 것 · 안 되는 것

| 조작 | 되나 | 비고 |
|---|---|---|
| 클릭·입력·스크롤 | ✅ | |
| **한글 입력** | ✅ | 앱(adb)과 달리 제약이 없다 |
| 파일 업로드 | ✅ | `set_input_files` — 필요해지면 서브커맨드를 추가한다 |
| 다크모드·뷰포트 변경 | ✅ | `conditions`로 시나리오에 적는다 |
| 콘솔 오류 수집 | ⚠️ | **부른 뒤부터** 듣는다. 이미 지나간 오류는 못 본다 — 조작 직후에 부른다 |
| 새 탭·팝업 | ⚠️ | 현재는 첫 탭만 본다. 필요해지면 확장한다 |
| 파일 다운로드 | ❌ | 아직 없다 |

## 시나리오에 쓰는 것

```json
{
  "target": "web",
  "steps": [{
    "screen": "로그인",
    "do": "type #email 'a@b.c' → click text=로그인",
    "expect_url": "/home",
    "expect_text": "환영합니다",
    "expect_server": "select count(*) from login_log where ..."
  }]
}
```

`expect_url`은 **부분 일치**다(`/home`이 현재 주소에 들어 있으면 통과). 쿼리스트링까지
맞추려 들면 시나리오가 쉽게 깨진다.

`expect_server`는 타겟과 무관하게 붙는다 — 웹에서 밟고 서버 DB를 확인하는 조합이 그래서 된다.

## 밟기 전에 확인할 것

**화면이 떴다고 통과가 아니다.** 웹은 특히 이 착각이 쉽다 — 자바스크립트 오류로 버튼이
죽어 있어도 화면은 멀쩡해 보인다.

1. `web console`로 오류가 없는지 본다
2. `expect_server`로 서버에 실제로 남았는지 대조한다
3. 빈 목록·로딩 실패 같은 **바깥 경로**를 밟는다 (SKILL.md의 3축)
