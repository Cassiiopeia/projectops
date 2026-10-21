# pro-launch 코드 지도

> 언제 읽나: 이 스킬의 코드를 처음 고치려는 사람이 **어디를 열어야 하는지** 찾을 때.
> 새로 붙이는 법의 절차와 코드 예시는 `../../references/extending.md`, 쓰는 법은 `../../SKILL.md`.

`scripts/launch_cli.py` 는 진입점일 뿐이다. 구현은 이 패키지에 있고, **서브커맨드 하나 = 모듈 하나**다.

## 한 번의 호출이 가는 길

```mermaid
flowchart TD
    A(["launch_cli.py web click --ref 3"]) --> B["cli.main<br/>인자를 해석한다"]
    B --> C["registry<br/>commands/ 의 선언을 모은다"]
    C --> D["commands/web/__init__.py<br/>동작을 고르고 필요한 준비만 한다"]
    D --> E["commands/web/actions/click.py<br/>동작 하나가 일한다"]
    E --> F["runtime/output.py out()<br/>공통 후처리를 붙여 JSON 하나로 낸다"]
```

## 폴더

```
scripts/
  launch_cli.py             진입점 (얇다)
  credentials.py            자격증명 저장 · 마스킹
  knowledge.py              이 컴퓨터에서 먹힌 방식의 기억
  app_input.py              앱 조작 플랫폼 백엔드 (Android · iOS)
  maestro_session.py        iOS 상주 Maestro 세션 — 상태 파일 · 중계를 부르는 클라이언트 (#894)
  maestro_session_relay.py  그 중계 프로세스 (`maestro mcp` 표준입출력 소유 · 127.0.0.1 TCP · 유휴 종료)
  maestro_runs.py           pro-launch 가 Maestro 를 띄운 구간 기록 · 그 밖의 실행 세기 (session-check) · 컴퓨터 단위 시작 잠금 (#922)
  maestro_drivers.py        남은 Maestro iOS 드라이버 찾기 · 분류(session·orphan·active) · 정리 (#922)
  node_match.py            화면 요소 고르기 공통 — 정확 > 정규화(겹친 라벨) > 부분, text·desc·label (#927)
  knowledge_stale.py       낡은 기억 표 (대체 표시 · 테스트 오염 삭제) (#932)
  browser_pick.py           어떤 브라우저로 띄울지
  stealth.py                자동화 표식 가리기
  pro_launch/
    registry.py             Command · Action 선언과 자동 발견
    cli.py                  파서 조립 · main()
    runtime/                아래층 — 명령들이 함께 쓰는 것
      context.py            프로젝트 루트 해석 · 한 실행의 표시들
      output.py             out() — 결과를 내는 단 하나의 길
      shots.py              캡처 자리 · 이름 · 줄이기
      envfile.py            env.sh 쓰기 (여기 하나뿐)
      devices.py            붙은 기기 · 역할 묶기 · 고르기
      creds.py              저장된 자격증명을 명령에서 꺼내는 얇은 층
      browser.py            브라우저 상태 파일 · Playwright 준비 · 어떤 브라우저
      procs.py              프로세스 확인 · 종료 · 목록 · 클립보드 — OS 분기는 여기만
      foreground.py · crash_reports.py   맨 앞 앱 확인 · 크래시 리포트 읽기 (#923)
      device_claims.py · session_identity.py   기기 점유 기록 · 전역 설정 복구 · 세션 식별 (#925)
      device_boot.py · android_device.py       기기 띄우기·재부팅·준비 대기 · 호스트 압박 필드 (#924)
      app_identity.py       프로젝트 파일에서 패키지·번들 ID 읽기 (#932)
      arg_diagnosis.py      bad_args 진단 — 모르는 이름 · 비슷한 이름 · 그 명령의 옵션 · 예시 (#886)
      recent_roots.py       최근에 쓴 프로젝트 루트 · 후보 (레포 밖에서 불릴 때, #885)
      device_claims.py      기기 소유 · 바꾼 전역 설정 기록 (이 컴퓨터 공용 자리, #925) · session_identity.py 세션 가르기
      device_boot.py        시뮬레이터·에뮬레이터 띄우기 · 창 모드(headless·small·normal)
      android_device.py     Android 준비 상태 · 기다리기 · APK 설치 · foreground.py 맨 앞 앱 · crash_reports.py iOS 크래시 리포트
      host_resources.py     호스트 메모리 압박 · 큰 프로세스 · 켜진 기기와 묶은 레포 (#883)
      plugin_version.py     실행 중인 projectops 버전 (실패 응답 · doctor, 프로세스당 1회)
    commands/               위층 — 서브커맨드
      doctor.py detect.py output_path.py
      device/               __init__ 디스패치 · bindings.py(list·bind) · claims.py(claim·release) · boot.py(boot·reboot) · settings.py(locale·appearance)
                            action_options.py 동작별 받는 옵션 표 (안 읽는 옵션은 bad_args, #972) — 동작이 새 옵션을 읽으면 표에도 넣는다
      http.py access.py db.py logs.py ssh.py cred.py local.py render.py shrink.py memory.py kb.py session_check.py
      app/                  __init__ 디스패치 · gestures.py(조작) · app_control.py(기기·패키지·도구 실행) · steps.py(app run 단계 파일) · android_ime.py(Android 입력기 전환·입력 대조) · burst.py(연속 캡처) · launch_check.py(띄운 뒤 앞 화면 확인) · actions/ (동작 하나 = 모듈 하나)
      web/                  __init__ 디스패치 · options.py 공통 옵션 표 · session.py · targets.py · element.py 대상 고르기 · watchdog.py 시간 상한 · request_capture.py 요청 기록 · saved_values.py 비밀값 저장 · candidates.py 실패 때 후보 · actions/
```

## 규칙 (테스트가 지킨다)

`tests/test_launch_architecture.py` 가 아래를 매번 검사한다. 어기면 CI 가 실패한다.

| 규칙 | 이유 |
|---|---|
| `runtime/` 은 `commands/` 를 import 하지 않는다 | 아래층이 위층을 알면 순환이 생기고, 공용 코드를 바꿀 때 어느 명령이 깨질지 알 수 없다 |
| 명령(모듈·폴더)끼리 import 하지 않는다 | 둘 이상이 쓰는 것은 `runtime/` 으로 내린다. 그래야 명령 하나를 지워도 다른 것이 안 깨진다 |
| `sys.platform` 분기는 `runtime/procs.py` 에만 둔다 | OS 차이가 흩어지면 기여자가 쓰는 OS 에서만 시험된다. 한 곳이면 OS 를 흉내 내 어디서나 시험한다 |
| 모듈은 450줄을 넘기지 않는다 | 원래 한 파일이 3,500줄이었다. 넘으면 나눌 때다 |
| 동작의 인자 수는 `needs` 가 정한다 | 디스패처가 그대로 부르므로 어긋나면 실행 중에야 터진다 |
| 진입점은 80줄 미만 | 구현이 다시 진입점에 쌓이지 않게 |

## 무엇을 하려면 어디를 고치나

| 하려는 것 | 고칠 곳 |
|---|---|
| 서브커맨드를 새로 | `commands/` 에 모듈 하나 (`COMMANDS = [Command(...)]`) |
| `web` 동작을 새로 | `commands/web/actions/` 에 모듈 하나 (`ACTION = Action(...)`) |
| `app` 동작을 새로 | `commands/app/actions/` 에 모듈 하나 |
| 새 앱 플랫폼 | `scripts/app_input.py` 에 백엔드 하나 + 등록 |
| 브라우저를 고르는 규칙 | `scripts/browser_pick.py` (환경변수 → 번들 → 설치된 것) |
| OS 마다 다른 프로세스 처리 (백그라운드 띄우기 · 묶음 종료 포함) | `runtime/procs.py` |
| iOS 상주 세션으로 보낼 동작 · 내려가는 조건 | `scripts/app_input.py` 의 `IOSMaestroBackend._session_call` |
| 모든 결과에 붙는 공통 후처리 | `runtime/output.py` 의 `out()` |
| 키 순서 · `--brief` · `--fields` 로 줄이기 | `runtime/output.py` 의 `shape_payload()` (옵션 꺼내기는 `cli.py` `_pop_output_options`) |
| 붙어 있는 동안만 사는 브라우저 설정 | `commands/web/session.py` 의 `web_connect` |
| 읽기 전용 세션이 막을 버튼 | `commands/web/targets.py` |
| `web` 동작이 받는 공통 옵션 · 동작별 `--help` | 동작의 `Action(options=..., help=..., example=...)` · 공통 옵션 표는 `commands/web/options.py` |
| 조작 대상 찾기 · 비활성 · 읽기 전용 막기 | `commands/web/element.py` 의 `locate_target` |
| 조작 동작의 기본 대기(대상 4초 · 결과 10초) · 시간 초과를 후보 실패로 | `commands/web/element.py` 의 `*_wait_seconds` · `perform_on_target` |
| 못 찾음 · 시간 초과 때 싣는 후보와 순위 | `commands/web/candidates.py` |
| 캡처 이름 · 크기 규칙 | `runtime/shots.py` |
| 도움말에서 보이는 서브커맨드 순서 | `cli.py` 의 `HELP_ORDER` |

## 알아 둘 것

- **출력은 언제나 JSON 하나**다. 새 실패는 새 `code` 로 낸다. 기존 `code` 의 뜻을 바꾸지 않는다 —
  `pro-agent-test` · `pro-design-brief` 가 이 스킬을 서브프로세스로 부르며 그 값에 기대고 있다.
- **상태는 모듈 전역을 쓴다.** `runtime/context.py` 의 `ROOT_CTX` · `ACCESS_CTX` · `MEMORY_CTX` · `MIGRATION` 이 그것이고,
  `cli.main()` 이 호출마다 비운다. 명령 사이에 값을 몰래 넘기는 데 쓰지 않는다.
- **테스트는 쓰는 곳의 이름을 고친다.** `from x import f` 로 가져온 `f` 를 바꾸려면 `x` 가 아니라 가져온 모듈의 `f` 를 monkeypatch 한다.
- **사용자에게 보이는 문구는 지금 한국어로 코드에 있다.** 문구 카탈로그로 분리하는 것은 이 구조 위에서 별도로 할 일이다
  (명령 모듈별로 문구가 모여 있어 옮기기 쉬운 모양이 됐다).
