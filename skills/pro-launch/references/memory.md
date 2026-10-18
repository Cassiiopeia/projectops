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
| `learn_hint` | 방금 실패(N번)를 다른 방식으로 넘겼다는 뜻. 다음에도 쓸 방식이면 `learn` 으로 남긴다 |
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
{PYTHON} {SCRIPTS}/launch_cli.py recall --match swipe               # 키·방법·노트에 낱말이 든 것만
# 경위가 길면 how 는 한 줄 결론, 긴 글은 --detail (또는 --detail-file) → notes/<key>.md, recall 이 detail_path 로 준다
{PYTHON} {SCRIPTS}/launch_cli.py learn --area android --key android.swipe --result ok \
    --how "app swipe 로 민다. 먼저 app shot 으로 줄 y 를 정한다" --detail "광고 배너로 y 가 87% → 80% 로 바뀌어 엉뚱한 카드를 밀었다 ..."
{PYTHON} {SCRIPTS}/launch_cli.py session-check                      # 작업을 마칠 때: 막혔다 풀렸는데 learn 안 한 영역 · pro-launch 밖 Maestro 실행 수
```

- **안전 규칙이 기억보다 위다.** 호스트 마우스로 좌표를 누르는 방법(`cliclick` 등)은 저장도, 꺼내기도 막힌다.
- 비밀번호·토큰·이메일 같은 비밀**값**은 저장을 거절한다(`secret_detected` + 가린 `matched_span`). 낱말만으로는 막지 않는다 —
  `#password_text_field` 같은 셀렉터는 저장된다 (#882).
- `how` 는 200자 상한이다. 넘으면 **자르지 않고** `too_long`(길이·상한)으로 거절한다 — `--detail` 로 나눈다 (#863).
- **앱 화면·좌표·함정은 여기가 아니다** — `pro-agent-test` 의 `note` 가 맡는다. 여기는 **도구·방식**만.
- `how` 에는 결론만 남기고, 왜 막혔고 어떻게 풀었는지는 `--detail` 노트에 둔다. 팀이 함께 봐야 하는 사례는 레포 문서(`CLAUDE.md` 등)에 적는다.
- `adb`·Maestro·`simctl` 을 직접 쓰면 응답에 `memory` 가 실리지 않는다 — 작업 시작 때 `doctor`(영역별 기억 건수)나 `recall --area <영역>` 을 본다.
- `session-check` 의 `outside_launch.maestro_runs`: 최근 24시간 `~/.maestro/tests/<시각>/` 폴더 중 pro-launch 가 띄운 구간(`launch/maestro_runs.json`)과 시각이 안 맞는 수. 폴더 이름·시각만 보고 내용은 읽지 않는다(비밀 입력 로그). `adb`·`simctl` 은 흔적을 남기지 않아 세지 않는다.
- 계정은 `cred`(`credentials.md`), 방식은 `learn` 으로 나눈다.

## 공식 지식 vs 내 기억 (#889)

| | 공식 트러블슈팅 | 내 기억 (`learn`) |
|---|---|---|
| 내용 | 검증된 증상 · 원인 · 해결 | 이 컴퓨터 · 이 레포에서 먹힌 방식 |
| 위치 | 스킬 안 `troubleshooting/<area>/<id>.json` (목록: `troubleshooting.md`) | `~/.projectops/launch/` |
| 쓰는 사람 | 관리자가 PR 로 | 에이전트가 자동으로 |
| 응답에 실림 | 실패 응답의 `known_fix` (최대 2건, 매번) | 영역 명령 응답의 `memory` (하루 한 번) |

- 실패하면 `known_fix` 부터 시도하고, 전체는 `kb show <id>`. 응답에 없으면 `kb search "<오류 문구>" --code <code>` · `kb list --area web`.
- 여러 번 먹힌 내 기억(ok 3 이상, fail < ok)은 `kb propose` 가 공식 항목 초안으로 뽑는다(비밀값은 거르고, 파일에 쓰지 않는다).
  todo 칸을 채워 **사용자 확인 뒤** 이슈나 PR 로 올린다. 공식에 자동으로 섞이지 않는다.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py kb search "브라우저가 뜨지 않았습니다" --code browser_start_failed
{PYTHON} {SCRIPTS}/launch_cli.py kb show browser-start-stale-process-or-lock
{PYTHON} {SCRIPTS}/launch_cli.py kb list --area ios
{PYTHON} {SCRIPTS}/launch_cli.py kb propose --key web.google-login     # → {"drafts":[{"path":..., "draft":{...}, "todo":[...]}]}
```

## 했던 작업을 적어 둔다 (작업 일지)

`learn` 은 "이 방식이 먹혔다"라는 한 줄 결론용이다. 한 건의 **작업 맥락**(무엇을 왜 했고, 어떤 순서였고,
무엇을 기준으로 판단했고, 결과가 어땠고, 다음에 헷갈릴 점)은 `journal` 에 자유롭게 적는다. 형식은 없다.

**언제 적나**
- 작업을 마치고 창을 닫으면 응답에 `journal_hint` 가 온다. 다음에도 반복될 만한 작업이면 **사용자에게 먼저
  "이 작업을 기록해 둘까요?" 라고 묻고**, 동의하면 적는다.
- 사용자가 먼저 "이거 기록해 줘" 라고 하면 묻지 않고 바로 적는다.

**언제 읽히나**: 같은 영역(web·app·server)을 다시 열면 응답에 `journal`(최근 2건, 하루 한 번)이 실려 온다.
**참고만 한다** — 순서와 판단 기준을 이어 쓰되, 변경하는 동작(제외·삭제·제출 등)은 사용자 확인을 거친다.
적힌 것이 낡았거나 화면이 달라졌으면 그대로 따르지 말고 달라진 점을 `--add` 로 덧붙인다.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py journal --add-file "$NOTE" --title "sparrow 오탐 제외 요청" --area web --site 10.206.10.195
{PYTHON} {SCRIPTS}/launch_cli.py journal --site sparrow       # 찾기 (최근 것부터)
{PYTHON} {SCRIPTS}/launch_cli.py journal --forget "sparrow 오탐 제외 요청"
```

- 긴 글·줄바꿈은 `--add-file`(UTF-8 파일)로 넘긴다. 한 건 1500자, 레포당 40건까지.
- **비밀번호·토큰은 저장을 거절한다.** 계정은 `cred` 로 둔다.
- 저장 위치: `~/.projectops/launch/<owner__repo>/journal.jsonl`.

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

**루트 찾는 순서 (#885)** — `--root` > `$PROJECT_ROOT` > 작업 폴더(git 이면) > 최근에 쓴 루트(`_machine/recent_roots.json`) > 작업 폴더.
최근 루트를 썼으면 응답에 `root_source: "last_used"` 와 `root_note` 가 온다. 레포 밖이라 실패하면(`browser_not_open` 등)
`root_candidates`(브라우저가 살아 있는 것이 앞)와 그대로 복사해 쓸 `retry` 명령이 온다.

**레포를 알 수 없을 때** — 스킬·플러그인 캐시 폴더(경로에 `/skills/pro-` · `/plugins/cache/`)에서 불렸고 git 원격이
없으면 폴더 이름(`scripts` 등)을 레포로 삼지 않는다. `$PROJECT_ROOT` 가 있으면 그것을 쓰고, 없으면 상태를
`_machine/` 에 쓰며 응답에 `root_unknown: true` 와 `--root <프로젝트>` 로 다시 부르라는 `next` 를 붙인다.
레포 범위 기억은 이때 쓰지 않는다.

예전에는 `~/.projectops/agent-test/` 에 섞여 있었다. 처음 부를 때 launch 몫을 옮기고
결과에 `migrated` 로 알린다. 두 번째부터는 아무 일도 없다. 브라우저가 떠 있으면 브라우저
관련은 닫은 뒤로 미룬다.
