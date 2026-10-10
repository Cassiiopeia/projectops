# 이 컴퓨터에서 먹힌 방식 · 토큰 · 저장 위치

> 언제 읽나: `recall`·`learn`·`forget` 을 처음 쓸 때, 상태 파일이 어디 있는지 알아야 할 때, 캡처가 토큰을 많이 먹을 때.

## 먹힌 방식을 기억한다 (쓸수록 정확해진다)

> 공통 원칙: [`../../references/memory-principles.md`](../../references/memory-principles.md)

사람마다 컴퓨터마다 잘 되는 방식이 다르다(iOS 는 Maestro 가 깔린 곳에서만, Google 로그인은 `--headed` 여야 하는 곳 등).
같은 실패를 반복하지 않고 토큰을 아끼려고 **먹힌 방식을 홈에 적어 둔다.**

**읽기는 자동이다 (#833).** `app` · `web` · `http` · `db` · `logs` 의 응답에 그 영역 기억이 `memory` 로 실려 온다
(레포·영역마다 하루 한 번, 최대 3건, 실패가 크게 앞서는 것은 빠진다). `recall` 을 따로 부르지 않아도 된다 —
agent 가 "모른다는 것을 모르는" 상태에서 꺼내 볼 생각을 하지 못해, 기억이 한 번도 다시 읽히지 않았다(실측).

| 응답에 오는 것 | 할 일 |
|---|---|
| `memory` | **먼저 읽고** 그 방식부터 쓴다. 썼으면 결과를 `learn --key <그 key> --result ok\|fail` |
| `learn_hint` | 방금 실패를 다른 방식으로 넘겼다는 뜻. 다음에도 쓸 방식이면 `learn` 으로 남긴다 |
| `learn` 결과의 `related` | 비슷한 기억이 이미 있다. 같은 지식이면 새 항목을 `forget` 하고 그 key 로 다시 `learn --scope machine` |
| `promoted_from` | 다른 레포에 같은 지식이 있어 이 컴퓨터 범위로 합쳤다 |

- **검증된 성공은 CLI 가 직접 기록한다.** `app tap/swipe/tree` 가 성공하면 "이 컴퓨터는 이 방식으로 조작된다"가
  이 컴퓨터 범위에 하루 한 번 올라간다. **실패·미설치는 자동 기록하지 않는다** — 환경 따라 바뀌어 쓰레기가 된다.
- `verify:true` 는 실패가 앞서거나 90일이 지난 것이니 **한 번 확인하고** 쓴다. 잘못 배운 것은 `forget`.
- 흩어진 기억(여러 레포에 같은 것, 잘못된 버킷)은 `tidy` 로 정리한다 — 확실한 것만 자동으로 합친다.

**남기지 않는 것** (Hermes Agent 의 저장 금지 목록을 따랐다): 미설치·미인증 같은 환경 의존 실패,
"X 는 안 된다" 같은 부정 단정, 해결 안 된 시행착오, 일회성 이야기, 비밀값, 호스트 마우스 방식.

**범위**: 레포와 상관없는 방법(로그인 방식, 도구 사용법)은 `--scope machine`. 그 레포의 앱·프로필에
묶인 것만 기본(repo) 범위에 둔다. 다른 레포에 같은 지식이 있으면 `learn` 이 알아서 이 컴퓨터 범위로 올린다.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py recall --area ios                 # --area ios|android|web|server · --scope both|repo|machine · --limit
{PYTHON} {SCRIPTS}/launch_cli.py learn --area ios --key ios.tap \
    --how "client/tool/e2e_shot.sh (Maestro) 로 위젯 텍스트를 누른다" --result ok
# 이 컴퓨터 전체에 해당하면 --scope machine (기본은 이 레포)
{PYTHON} {SCRIPTS}/launch_cli.py forget --key ios.tap --area ios
{PYTHON} {SCRIPTS}/launch_cli.py tidy                              # 흩어진 기억 정리
```

- **안전 규칙이 기억보다 위다.** 호스트 마우스로 좌표를 누르는 방법(`cliclick` 등)은 저장도, 꺼내기도 막힌다.
- 비밀번호·토큰·이메일 같은 비밀값은 저장을 거절한다.
- **앱 화면·좌표·함정은 여기가 아니다** — `pro-agent-test` 의 `note` 가 맡는다. 여기는 **도구·방식**만.
- 설명이 필요한 긴 사례(왜 막혔고 어떻게 풀었나)는 `pro-note` 로 남긴다. 여기에는 결론만.
- 계정은 `cred`(`credentials.md`), 방식은 `learn` 으로 나눈다.

## 토큰을 아낀다

- 화면 이미지를 읽는 것이 가장 비싸다. **텍스트로 확인되면(`assert` · 로그 · `app tree` · E2E 의 assertVisible) 스크린샷을 읽지 않는다.**
- 한 번 만든 E2E 플로우는 경로를 `learn` 으로 남겨 다시 짜지 않는다.
- 캡처는 기본 축소본(긴 변 1200px WebP)을 쓰고, 원본은 픽셀 대조처럼 꼭 필요할 때만.
- `shrink` 로 줄인다 — 파일 크기는 WebP 가, 세션 토큰은 해상도가 줄인다. 둘을 함께 해야 한다.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py shrink "$SHOT_DIR"/*.png           # 긴 변 1200 + WebP (--max-side · --quality · --keep-format)
```

## 저장 위치

| 자리 | 담는 것 |
|---|---|
| `~/.projectops/launch/<owner__repo>/` | devices.json · browser.json · access.json(**비밀 없음**) · access_status.json(접속 방법 성적) · knowledge.json · `.browser-profile/` · `shots/` |
| `~/.projectops/config/config.json` → `launch.credentials` | **자격증명**(값 포함, 파일 600). `pro-ssh`·`pro-github` 와 같은 파일 |
| `~/.projectops/launch/_machine/` | knowledge.json — 이 컴퓨터 전체에 해당하는 방식. 레포를 알 수 없을 때의 상태도 여기 둔다(아래) |
| `~/.projectops/launch/.venv` | Playwright · Pillow (옛 `agent-test/.venv` 가 있으면 그것을 쓴다) |

`PROJECTOPS_HOME` 환경변수가 있으면 `~/.projectops` 대신 그 자리를 쓴다(테스트 격리용). venv 는 설치물이라
그 자리에 없으면 실제 홈의 것을 찾아 쓴다.

**레포를 알 수 없을 때** — 스킬·플러그인 캐시 폴더(경로에 `/skills/pro-` · `/plugins/cache/`)에서 불렸고 git 원격이
없으면 폴더 이름(`scripts` 등)을 레포로 삼지 않는다. `$PROJECT_ROOT` 가 있으면 그것을 쓰고, 없으면 상태를
`_machine/` 에 쓰며 응답에 `root_unknown: true` 와 `--root <프로젝트>` 로 다시 부르라는 `next` 를 붙인다.
레포 범위 기억은 이때 쓰지 않는다.

예전에는 `~/.projectops/agent-test/` 에 섞여 있었다. 처음 부를 때 launch 몫을 옮기고
결과에 `migrated` 로 알린다. 두 번째부터는 아무 일도 없다. 브라우저가 떠 있으면 브라우저
관련은 닫은 뒤로 미룬다.
