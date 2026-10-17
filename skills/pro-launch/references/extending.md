# 확장하기 — 새 제어 대상 · 플랫폼을 붙이는 법

> 언제 읽나: pro-launch 에 새 플랫폼(앱 백엔드)이나 새 web 동작, 새 서브커맨드를 추가하려는 기여자가 코드를 고치기 전에.

**코드 지도는 `scripts/pro_launch/ARCHITECTURE.md` 다 — 어디에 무엇이 있는지, 무엇을 하려면 어느 파일을 고치는지가 거기 있다.**
이 문서는 그 위에서 "새로 붙이는 법"만 다룬다.

먼저 레포 `CLAUDE.md` 의 **"Python 행동 스크립트 표준"** 절과 `skills/references/mcp-subcommand-rules.md` 를 읽는다.
요점만 옮기면 이렇다.

- **표준 라이브러리 우선.** 외부 패키지가 꼭 필요하면 설치 안내를 결과에 담는다(Playwright 는 전용 venv 에 받는다).
- **출력은 언제나 JSON 하나.** plain text 모드를 두지 않는다.
- **해석은 agent, 실행은 스크립트.** 스크립트는 프로젝트 구조를 알아맞히지 않는다.
- 인자는 argparse 명명 플래그 · 환경변수로 받는다. 선택 위치 인자를 줄줄이 두지 않는다(#622).

## 출력 JSON 계약

| 필드 | 언제 | 뜻 |
|---|---|---|
| `ok` | 항상 | 성공 여부 |
| `code` | 항상 | `ok` 또는 snake_case 실패 이름. agent 는 이 값으로 갈래를 탄다 — **문구가 아니라 code 로** |
| `summary` | 성공 시 권장 | 한 줄 요약 |
| `error` · `hint` | 실패 시 | 무엇이 틀렸나 · 어떻게 고치나 |
| `next` | 가능하면 항상 | agent 가 이어서 부를 명령 한 줄 (끝이면 `null`) |
| `candidates` · `locale` | 요소를 못 찾았을 때(`not_found`) | 화면에 실제로 있는 값 · 화면 언어 — agent 가 추측을 반복하지 않게 한다 |
| `shot` · `screen_changed` | `--shot` 을 받았을 때 | 찍은 경로 · 조작 전후 화면이 달라졌나(`false` 면 반응 없음) |

- 새 실패는 **새 code** 로 낸다. 기존 code 의 뜻을 바꾸지 않는다 — 부르는 스킬(`pro-agent-test` 등)이 그 값에 기대고 있다.
- 비밀 값(비밀번호·토큰)은 결과·로그에 넣지 않는다. 섞일 수 있으면 `***` 로 가린다.

## 새 앱 플랫폼 — 백엔드 클래스 하나 + 레지스트리 등록 + 테스트

앱 조작(`app tap` · `swipe` · `tree`, #826)은 `scripts/app_input.py` 의 **플랫폼 백엔드**가 맡는다. `pro_launch/commands/app/` 은 이 모듈만 부르고,
플랫폼 차이는 전부 여기 있다. 지금은 `AndroidBackend`(adb + uiautomator, 기기 내장이라 설치 없음)와
`IOSMaestroBackend`(Maestro — simctl 에 탭·화면 구조 명령이 없다) 둘이다.

```python
BACKENDS = {
    "android": lambda app_id=None: AndroidBackend(),
    "ios": lambda app_id=None: IOSMaestroBackend(app_id=app_id),
}
# get_backend(platform, app_id) 가 이 표에서 만든다. 키는 runtime/devices.py 의 pick_device 가 돌려주는 플랫폼 이름과 같아야 한다
```

`Backend` 를 상속해 채운다. 동작 메서드는 모두 `(성공 여부, 사람이 읽을 사유)` 를 돌려준다.

| 멤버 | 돌려줄 것 | 비고 |
|---|---|---|
| `name` | 플랫폼 이름 | 레지스트리 키와 같게 |
| `available()` | `bool` | 도구가 있나. 없으면 `{name}_tool_missing` code 와 함께 `install_hint`(설치 명령 문자열)가 `next` 에 실린다 — 예: `ios_tool_missing` |
| `selects_itself` | `bool` | `True` 면 백엔드가 요소를 직접 찾아 누른다(`tap_selector`, Maestro 방식). `False` 면 `nodes()` 로 찾아 `tap_xy` 로 누른다 |
| `locale(dev)` | 화면 언어 또는 `None` | `not_found` · `tree` 응답에 실린다 |
| `nodes(dev)` | `list[dict]` 또는 `None` | 각 dict 는 `text`·`id`·`desc`·`clickable`·`bounds`·`center` (`make_node` 로 만든다). 화면 구조를 못 읽으면 `None` |
| `tap_xy(dev, x, y)` | `(bool, str)` | 픽셀 좌표 탭 — `nodes` 의 `center` 를 누를 때 쓰는 내부용 |
| `tap_ratio(dev, rx, ry)` | `(bool, str)` | 0~1 비율 좌표 탭 (`--at`) |
| `tap_selector(dev, field, value)` | `(bool, str)` | `selects_itself` 백엔드만. `field` 는 `text` · `id` · `desc` |
| `swipe_ratio(dev, start, end, ms)` | `(bool, str)` | 비율 좌표 두 점과 시간(ms). `--dir` 은 `SWIPE_DIRS` 가 두 점으로 바꿔 준다 |
| `grab(dev)` | PNG `bytes` 또는 `None` | `--shot` 이 "바뀐 뒤 멈춘 화면"을 고르고 `screen_changed` 를 정할 때 쓴다 |

순서:

1. `scripts/app_input.py` 에 `Backend` 를 상속한 클래스를 만든다. 외부 도구는 `subprocess` 로 부른다.
   화면 덤프 파싱처럼 **기기 없이 검사할 수 있는 것은 모듈 수준 순수 함수로** 뺀다(`ui_nodes` · `maestro_nodes` · `match_nodes` · `parse_ratio` 가 그 예).
2. `BACKENDS` 에 등록한다. `pro_launch/commands/app/` 은 백엔드를 골라 부를 뿐이라 **고칠 필요가 없어야 한다.**
   고쳐야 한다면 인터페이스가 새는 것이니 그 부분을 백엔드 쪽으로 옮긴다.
3. 테스트를 추가한다(아래). 등록만 해도 `tests/test_launch_cli.py` 의 `test_every_registered_backend_implements_the_contract` 가
   새 백엔드가 계약 멤버를 다 갖췄는지 검사한다 — 이것과 별도로 그 백엔드의 파싱·실패 경로 단위 테스트를 넣는다.
4. 붙는 법 · 함정을 `references/app.md` 에 적는다. 이 맥에서 먹힌 방식은 문서가 아니라 `learn` 이 맡는다.

**금지**: 호스트 마우스로 좌표를 누르는 구현(`cliclick` · AppleScript System Events · CGEvent). 사용자 커서를 빼앗고
무엇이 눌렸는지 알 수 없다. 접근성 트리 · 기기 내장 입력 · E2E 도구처럼 **기기 안에서** 누르는 방법만 쓴다.

## 새 web 동작

동작 하나는 `scripts/pro_launch/commands/web/actions/` 의 **모듈 하나**다. 다른 파일은 고치지 않는다 —
`web` 이 그 폴더를 훑어 선택지·옵션·디스패치를 만든다.

```python
# commands/web/actions/scroll.py
from pro_launch.commands.web.element import locate_target
from pro_launch.registry import Action

def configure(p) -> None:                       # 이 동작만 쓰는 옵션 (선택)
    p.add_argument("--pixels", type=int, default=600, help="내릴 거리(px)")

def execute(page, args, state) -> dict:          # needs="page" 면 (page, args, state) → 결과 dict
    element, info, failure = locate_target(page, args, state, "scroll", should_guard_mutating=False)
    if failure:
        return failure
    element.evaluate("(e, n) => e.scrollBy(0, n)", args.pixels)
    return {"action": "scroll", "target": info, "summary": "내렸다", "next": "web text"}

# options: 쓰는 공통 옵션(commands/web/options.py 의 이름). 여기 없는 공통 옵션은 bad_args 로 거절된다
ACTION = Action(name="scroll", run=execute, configure=configure, options=("selector", "ref"),
                help="요소 안을 내린다", example="web scroll --ref 3 --pixels 800")
```

`needs` 가 디스패처가 해 줄 준비를 정한다.

| needs | `run` 의 모양 | 언제 |
|---|---|---|
| `page` (기본) | `(page, args, state) -> dict` | 붙어서 화면을 조작한다. 연결 · 마지막 사용 시각 · 예외 변환(비밀값 가림) · 연결 끊기는 디스패처가 한다 |
| `nothing` | `(args) -> int` | 상태도 브라우저도 안 읽는다 (`setup`) |
| `launch` | `(args, root, state_file) -> int` | 브라우저를 새로 띄운다 (`open`) |
| `state_offline` | `(args, state, state_file) -> int` | 상태 파일만 만진다. 브라우저가 없어도 된다 (`viewport` · `route`) |
| `state_online` | `(args, state, state_file) -> int` | 떠 있는 브라우저 정보가 있어야 하나 연결은 맺지 않는다 (`close`) |

순서:

1. 위 모양대로 모듈을 만든다. 동작마다 하위 파서가 따로라 자기 옵션 이름은 다른 동작과 겹쳐도 된다. 여러 동작이 쓰는 옵션
   (`--url` · `--selector` · `--ref` · `--text` · `--timeout` …)은 `commands/web/options.py` 에 있고, 쓰는 것만 `options=` 에 적는다
   (#896 — `web <동작> --help` 는 그것과 `help` · `example` 만 보여 준다). `app` 동작은 `options` 를 적지 않는다(전부 받는다).
2. **붙어 있는 동안만 사는 것은 상태 파일에 적고 붙을 때마다 다시 건다.** `web` 은 매 호출 CDP(`connect_over_cdp`)로
   붙었다 떨어지므로, 콘솔 훅 · stealth · 뷰포트 · 응답 바꿔치기 같은 설정은 연결이 끊기면 사라진다(#625 실측).
   새 설정도 `commands/web/session.py` 의 `web_connect` 에서 재설치되게 한다. 브라우저를 Playwright `launch()` 로 띄우지 않는다 — 드라이버와 함께 죽는다.
3. 바꾸는 조작을 추가하면 `references/web.md` 의 안전 계약(로컬만 · 그 밖은 묻는다)이 적용되는지 확인한다.
   읽기 전용 세션(`state["readonly"]`)에서는 `commands/web/targets.py` 의 `is_mutating_target()` 으로 걸러 `mutating_blocked` 를 돌려준다.
4. **결과를 agent 가 판단할 수 있게 돌려준다 (#825).** 화면을 바꾸는 동작은 전후 `url` · `title` 과 무엇을 대상으로 했는지,
   실패는 문구가 아닌 `code` 와 다음에 부를 명령(`next`)을 준다. "성공했다"만 돌려주면 agent 는 엉뚱한 것을 누르고도 다음으로 간다
   (Play Console 실측). 대상은 선택자 추측 대신 `web find` 의 `ref`(`data-pops-ref`)로 받을 수 있게 한다.
5. 단위 테스트를 `tests/` 에 넣는다. `tests/test_launch_architecture.py` 가 동작의 모양(`needs` 와 인자 수)을 자동으로 검사한다.

## 새 app 동작

`scripts/pro_launch/commands/app/actions/` 에 모듈 하나. `ACTION = Action(name=..., run=execute, configure=...)` 이고
`execute(args) -> int` 가 결과를 `out(...)` 으로 직접 낸다. 플랫폼을 알 필요가 없다 — `commands/app/gestures.py` 의
`backend_for(args)` 가 백엔드를 골라 준다.

## 새 서브커맨드

`scripts/pro_launch/commands/` 에 **모듈 하나**를 둔다. 파서 · 도움말 · 디스패치는 선언에서 만들어지므로 다른 파일은 고치지 않는다.

```python
# commands/ping.py
from pro_launch.registry import Command
from pro_launch.runtime.output import out

def configure(p) -> None:
    p.add_argument("--host", required=True)

def cmd_ping(args) -> int:
    return out({"ok": True, "code": "ok", "summary": f"{args.host} 확인", "next": None})

COMMANDS = [Command(name="ping", help="호스트가 응답하는지 본다", run=cmd_ping, configure=configure)]
```

- 결과는 언제나 `runtime.output.out()` 으로 낸다 — 마이그레이션 알림 · 루트 경고 · 접속 방법 성적 · 기억 싣기가 거기서 공통으로 붙는다.
- 다른 명령 모듈을 import 하지 않는다. 둘 이상이 쓸 것이면 `runtime/` 으로 내린다 (`test_launch_architecture.py` 가 막는다).
- `sys.platform` 으로 갈리는 동작은 `runtime/procs.py` 에만 둔다.
- 새 이름은 **SKILL.md 에 호출 예로 있어야 한다** (`scripts/tests/test_cli_signatures_doc_sync.py` 가 `Command(name=...)` 선언을 읽어 막는다).
  라우터 표에 한 줄, 상세는 references 에 둔다.
- 산출물 경로는 `get-output-path` 가 돌려준 값만 쓴다. 경로를 조립하지 않는다(#623).
- `--help` 에서 보이는 순서는 `pro_launch/cli.py` 의 `HELP_ORDER` 다. 없어도 등록은 되고 이름순으로 뒤에 붙는다.

## 테스트 규칙

| 무엇 | 어디 · 어떻게 |
|---|---|
| 단위 테스트 — **필수** | `skills/pro-launch/tests/`(앱 백엔드는 `test_launch_cli.py`, 구조 규칙은 `test_launch_architecture.py`). 기기·브라우저 없이 돈다. 외부 명령은 가짜 실행 파일(PATH 앞에 둔 스크립트)이나 monkeypatch 로 바꾸고, `nodes` 파싱 · 비율 계산 · 실패 code · JSON 필드를 검사한다 |
| 실제 기기 · 브라우저가 필요한 것 | `@pytest.mark.local_only` 를 붙인다. 로컬에 도구가 있으면 돌고, CI(`CI=true`)에서는 건너뛴다 |
| 순수 값 검사 | `local_only` 를 붙이지 않는다. 도구가 없는 상태를 테스트가 직접 만들어 어디서나 돌게 한다(#591) |

```bash
python3 -m pytest skills/pro-launch/tests -q
python3 -m pytest scripts/tests -q        # 문서 · 서브커맨드 정합성
```

테스트 코드는 사용자에게 복사되지 않는다(`src/core/ide/adapters/cursor.js` 의 `SKIP_IN_COPY`). 스킬에 보조 파일을
새로 넣을 때는 "이게 스킬을 쓰는 사람에게 필요한가"를 먼저 묻는다.
