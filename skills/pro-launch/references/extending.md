# 확장하기 — 새 제어 대상 · 플랫폼을 붙이는 법

> 언제 읽나: pro-launch 에 새 플랫폼(앱 백엔드)이나 새 web 동작, 새 서브커맨드를 추가하려는 기여자가 코드를 고치기 전에.

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

앱 조작(`app tap` · `swipe` · `tree`, #826)은 `scripts/app_input.py` 의 **플랫폼 백엔드**가 맡는다. `launch_cli.py` 는 이 모듈만 부르고,
플랫폼 차이는 전부 여기 있다. 지금은 `AndroidBackend`(adb + uiautomator, 기기 내장이라 설치 없음)와
`IOSMaestroBackend`(Maestro — simctl 에 탭·화면 구조 명령이 없다) 둘이다.

```python
BACKENDS = {
    "android": lambda app_id=None: AndroidBackend(),
    "ios": lambda app_id=None: IOSMaestroBackend(app_id=app_id),
}
# get_backend(platform, app_id) 가 이 표에서 만든다. 키는 _pick_device 가 돌려주는 플랫폼 이름과 같아야 한다
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
2. `BACKENDS` 에 등록한다. `launch_cli.py` 의 `app` 서브커맨드는 백엔드를 골라 부를 뿐이라 **고칠 필요가 없어야 한다.**
   고쳐야 한다면 인터페이스가 새는 것이니 그 부분을 백엔드 쪽으로 옮긴다.
3. 테스트를 추가한다(아래). 등록만 해도 `tests/test_launch_cli.py` 의 `test_every_registered_backend_implements_the_contract` 가
   새 백엔드가 계약 멤버를 다 갖췄는지 검사한다 — 이것과 별도로 그 백엔드의 파싱·실패 경로 단위 테스트를 넣는다.
4. 붙는 법 · 함정을 `references/app.md` 에 적는다. 이 맥에서 먹힌 방식은 문서가 아니라 `learn` 이 맡는다.

**금지**: 호스트 마우스로 좌표를 누르는 구현(`cliclick` · AppleScript System Events · CGEvent). 사용자 커서를 빼앗고
무엇이 눌렸는지 알 수 없다. 접근성 트리 · 기기 내장 입력 · E2E 도구처럼 **기기 안에서** 누르는 방법만 쓴다.

## 새 web 동작

1. `launch_cli.py` 의 `web` 서브커맨드 `action` choices 에 이름을 넣는다. 필요한 옵션은 같은 파서에 붙인다.
2. `cmd_web` 의 분기에 동작을 구현한다. 한 호출 = 한 동작이다 — agent 가 화면을 보고 다음 수를 정한다.
3. **붙어 있는 동안만 사는 것은 상태 파일에 적고 붙을 때마다 다시 건다.** `web` 은 매 호출 CDP(`connect_over_cdp`)로
   붙었다 떨어지므로, 콘솔 훅 · stealth · 뷰포트 · 응답 바꿔치기 같은 설정은 연결이 끊기면 사라진다(#625 실측).
   새 설정도 `_web_connect` 에서 재설치되게 한다. 브라우저를 Playwright `launch()` 로 띄우지 않는다 — 드라이버와 함께 죽는다.
4. 바꾸는 조작을 추가하면 `references/web.md` 의 안전 계약(로컬만 · 그 밖은 묻는다)이 적용되는지 확인한다.
   읽기 전용 세션(`state["readonly"]`)에서는 `_is_mutating_target()` 으로 걸러 `mutating_blocked` 를 돌려준다.
5. **결과를 agent 가 판단할 수 있게 돌려준다 (#825).** 화면을 바꾸는 동작은 전후 `url` · `title` 과 무엇을 대상으로 했는지,
   실패는 문구가 아닌 `code` 와 다음에 부를 명령(`next`)을 준다. "성공했다"만 돌려주면 agent 는 엉뚱한 것을 누르고도 다음으로 간다
   (Play Console 실측). 대상은 선택자 추측 대신 `web find` 의 `ref`(`data-pops-ref`)로 받을 수 있게 한다.

## 새 서브커맨드

- `build_parser()` 에 `add_parser` 로 추가하면 **SKILL.md 에 그 이름이 호출 예로 있어야 한다**
  (`scripts/tests/test_cli_signatures_doc_sync.py` 가 막는다). 라우터 표에 한 줄, 상세는 references 에 둔다.
- 산출물 경로는 `get-output-path` 가 돌려준 값만 쓴다. 경로를 조립하지 않는다(#623).

## 테스트 규칙

| 무엇 | 어디 · 어떻게 |
|---|---|
| 단위 테스트 — **필수** | `skills/pro-launch/tests/`(앱 백엔드는 `test_launch_cli.py`). 기기·브라우저 없이 돈다. 외부 명령은 가짜 실행 파일(PATH 앞에 둔 스크립트)이나 monkeypatch 로 바꾸고, `nodes` 파싱 · 비율 계산 · 실패 code · JSON 필드를 검사한다 |
| 실제 기기 · 브라우저가 필요한 것 | `@pytest.mark.local_only` 를 붙인다. 로컬에 도구가 있으면 돌고, CI(`CI=true`)에서는 건너뛴다 |
| 순수 값 검사 | `local_only` 를 붙이지 않는다. 도구가 없는 상태를 테스트가 직접 만들어 어디서나 돌게 한다(#591) |

```bash
python3 -m pytest skills/pro-launch/tests -q
python3 -m pytest scripts/tests -q        # 문서 · 서브커맨드 정합성
```

테스트 코드는 사용자에게 복사되지 않는다(`src/core/ide/adapters/cursor.js` 의 `SKIP_IN_COPY`). 스킬에 보조 파일을
새로 넣을 때는 "이게 스킬을 쓰는 사람에게 필요한가"를 먼저 묻는다.
