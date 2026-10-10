# 알아낸 것을 쌓고, 산출물을 안전하게 두기

> 언제 읽나: 알아낸 화면·규칙·함정을 `note` 로 쌓을 때, 쌓인 기록을 읽을 때, 산출물을 어디에 둘지 헷갈릴 때.

> **산출물 폴더는 기본이 "올리지 않는다"** 이다. 무엇이 생길지 미리 알 수 없는 폴더에서
> 예외를 기본값으로 두면, 언젠가 계정이나 주소가 적힌 파일이 함께 올라간다 — 실제로
> 그럴 뻔했다.
>
> 이제 `get-output-path` 가 만든 실행 폴더가 **추적 제외를 스스로 들고 다닌다** — 따로
> 할 일이 없다. `learned.json` 은 애초에 프로젝트 밖(홈)에 쌓여 저장소에 닿지 않는다.
> 나눌 파일이 생기면 그것만 골라 이슈에 올린다.

이 문서는 `SKILL.md`의 **"기록 쌓기"** 를 펼친 것이다.
노트를 남기는 명령과 그 이유, 그리고 테스트 산출물을 레포에 올릴 때의 규칙을 담는다.

### 알아낸 것은 프로젝트에 남긴다 (자가발전)

밟다 보면 이 앱에서만 통하는 것들을 알게 된다 — 어느 화면의 버튼이 어디 있는지,
어디서 발을 헛디뎠는지. **그것을 남기지 않으면 다음에 처음부터 다시 알아내야 한다.**

#### 먼저 이 앱이 무엇을 지켜야 하는지 적는다

좌표와 함정만 알면 "화면이 떴다"까지밖에 못 본다. **이 앱의 규칙을 알아야 위반을 알아본다.**

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note constraint \
  --text "실패·오류에 경고색을 쓰지 않는다" \
  --check "빨간 글자·Icons.error가 화면에 있으면 위반" --root {PROJECT_ROOT}
```

`--check`가 핵심이다. 규칙만 적으면 밟으면서 떠올리지 못한다. **무엇을 보면 위반인지**를
함께 적어야 화면을 보는 순간 판정할 수 있다.

어디서 가져오나 — 프로젝트의 `CLAUDE.md`·`docs/`의 서비스 원칙·디자인 시스템 문서.
Phase 1에서 밟을 것을 정할 때 이 목록을 **확인 항목으로 함께 쓴다.**

> 실제 사례: 어떤 프로젝트에 "실패했는데 식별자가 없으면 위반"을 등록해 두었더니, 세션이 끊긴 채
> 홈이 정상처럼 보이는 상황을 곧바로 문제로 판정할 수 있었다.

**무엇을 어디에 남길지 구분한다.** 이 앱에서만 통하는 것은 프로젝트에, 어느 앱에나 통하는 것은
**이 컴퓨터 범위 한 곳**에 둔다 (이유: 범용 지식을 프로젝트마다 묻어두면 다음 프로젝트에서 똑같이 한 번 더 겪는다).
도구 사용법(브라우저 로그인 방식·녹화 명령 등)은 여기가 아니라 `pro-launch` 의 `learn` 몫이다.

| scope | 무엇 | 어디에 남나 |
| --- | --- | --- |
| `project` | 이 앱의 화면·규칙·구성 | `~/.projectops/agent-test/{owner}__{repo}/learned.json` |
| `flutter` | 모든 Flutter 앱에 해당 | `~/.projectops/agent-test/_machine/learned.json` (모든 레포가 함께 본다) |
| `platform` | 기기·OS 차원 | 위와 같다 |

```bash
# 요약 (제약·함정 각 5건, 항목당 120자). 전부는 --all
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note show --root {PROJECT_ROOT}

# 화면을 알아보는 단서와 누를 대상 — 요소가 먼저, 요소 트리가 비는 화면(Flutter 캔버스·지도)만 비율
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note screen --name 로그인 --anchor "로그인하고 시작하기" \
      --target "구글=text:Google로 계속하기" "닫기=desc:닫기" "지도핀=at:0.5,0.3725" \
      --screen-size 1080x2400 --root {PROJECT_ROOT}

# 그 대상을 app tap --shot 으로 눌러 본 결과 — screen_changed true 면 ok, not_found·false 면 fail
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note screen --name 로그인 --target 구글 --result ok --root {PROJECT_ROOT}

# 헛디딘 것
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note pitfall --text "동의 목록은 3~4회 밀어야 끝까지 간다" --scope project --root {PROJECT_ROOT}

# 이미 있는 함정·규칙을 다시 겪었거나(ok) 틀렸다면(fail) — 번호는 note show 의 index
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note pitfall --index 3 --result fail --root {PROJECT_ROOT}

# 이번 실행 결과
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note run --name social-signup --text "통과 — 버그 2건 발견" --root {PROJECT_ROOT}
```

`--target` 형식: `라벨=text:문구` · `라벨=id:리소스id` · `라벨=desc:설명` (같은 문구가 여럿이면 끝에 `|index=1`) ·
`라벨=at:0.5,0.8`(0~1 비율). **픽셀은 거절한다**(`pixels_rejected`) — `app tap` 이 픽셀을 받지 않아 저장해도 못 쓴다.
`--screen-size` 를 함께 주면 비율로 바꾼 값을 `hint` 로 알려 준다.

#### 기록은 도구가 꺼내 준다 — 기억 원칙 (`skills/references/memory-principles.md`)

- **읽기**: `detect` · `scenario show` 응답의 `memory` 에 맥락에 맞는 규칙 2 · 함정 2 · 이 컴퓨터 함정 1 까지 실린다.
  같은 영역(detect 는 타겟, scenario 는 시나리오 이름)은 하루 한 번만 싣는다. 실패가 크게 앞선 기억은 싣지 않는다.
- **중복**: 함정·규칙을 쓰기 전에 이 레포와 이 컴퓨터 범위에서 비슷한 것을 찾는다. 확실히 같으면(고유어 60% 이상)
  새로 쓰지 않고 합친다(`merged_into`). 애매하면(25~60%) 새로 쓰되 `related` 를 보여 준다 — 같은 지식이라고
  판단하면 `next` 대로 `note forget --kind pitfall --index <새 번호>` 후 `--merge-into <그 번호> --text "…"`.
- **성적과 낡음**: 항목은 `ok` · `fail` · `last_seen` 을 가진다. 같은 날 같은 결과는 한 번만 센다.
  90일이 지났거나 실패가 앞서면 `verify` 가 붙어 뒤로 밀린다 — 지우지 않는다. 지우는 것은 `note forget` 으로만.
  예전 항목(성적 없음)은 0·0·추가한 날로 읽는다.
- **화면 기록 이전**: 예전 픽셀 기록(`taps`)은 읽을 때 `measured_on` 으로 비율(`at`)로 바뀌고 `verify` 가 붙는다.
  원본은 `legacy_taps` 에 남는다. 해상도를 모르는 기록은 `unconverted` 로 표시된다 — 다시 재서 `--target` 으로 적는다.
  파일은 다음 쓰기 때 새 판(`schema: 3`)으로 저장된다.

#### 섞인 범위 정리 — `note tidy`

예전에는 `flutter` · `platform` 함정도 레포에 쌓였다. `note tidy` 는 **계획만** 보여 주고, `--apply` 를 줄 때만 옮긴다.
옮기기만 하고 지우지 않는다.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note tidy --root {PROJECT_ROOT}           # 계획
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note tidy --apply --root {PROJECT_ROOT}   # 실제로 옮긴다
```

| 결과 칸 | 뜻 |
| --- | --- |
| `to_machine` | `flutter` · `platform` 함정 → 이 컴퓨터 범위. 같은 것이 이미 있으면 성적을 합친다 |
| `to_launch` | 도구 사용법으로 보이는 함정 → `launch_cli learn`(project 는 레포, 나머지는 이 컴퓨터 범위) |
| `skipped` | 옮기지 않는다 — 영역을 못 정했거나(`--launch 번호=web` 으로 지정) 200자를 넘는다(줄여서 직접 `learn`) |
| `review` | 부정 단정("안 된다"·"수 없다") — 지금도 맞는지 확인하고 아니면 `note forget` |

#### 쌓인 것은 skill을 갱신해도 사라지지 않는다

| 무엇 | 어디 | skill 업데이트 영향 |
| --- | --- | --- |
| 절차·스크립트 | 하네스 설치 경로 (`~/.claude/plugins/cache/...` 등) | 통째로 교체된다 |
| **쌓인 기록** | **홈** `~/.projectops/agent-test/{owner}__{repo}/learned.json` — 워크트리를 만들어도 살아남는다 | **없다** |

기록은 프로젝트에 있고 skill은 그것을 읽을 뿐이다. 그래서 skill이 몇 번을 갱신돼도,
어느 하네스(Claude Code·Codex·Gemini·Pi)에서 불려도 같은 파일이 이어진다.

읽고 쓸 때 아래를 지킨다 — **쌓은 것을 잃지 않는 쪽이 항상 우선이다.**

- **모르는 필드는 건드리지 않는다.** 다음 버전이나 다른 하네스가 넣은 값일 수 있다
- **읽지 못해도 지우지 않는다.** 파일이 깨졌으면 `learned.broken-{시각}.json`으로 옮기고
  경고를 띄운 뒤 새로 시작한다 (조용히 덮으면 그동안 쌓은 것이 사라진다)
- **원자적으로 쓴다.** 임시 파일에 쓰고 바꿔치기하므로, 쓰는 도중 멈춰도 기존 파일은 온전하다
- `schema` 필드로 판을 표시한다. 필드를 **없애는** 변경을 할 때만 올린다

> 누를 대상은 **먼저 요소로**(`launch_cli.py app tap --text|--id|--desc`) 찾는다. `at:` 비율 기록은
> 요소 트리가 비는 화면(Flutter 캔버스·지도)을 위한 것이고 그대로 `app tap --at` 에 넘긴다.
> `note screen` 의 응답 `targets` 에 각 대상을 누르는 `app tap` 인자가 적혀 온다.
>
> 기록은 **힌트지 보증이 아니다.** 화면이 바뀌면 빗나간다. 기록된 대상을 쓰더라도 누른 뒤 결과를
> 확인하는 단계(`stepping.md` Phase 3 ③)는 건너뛰지 않고, 그 결과를 `--result` 로 남긴다.

### 쌓인 것에 자격증명을 넣지 않는다 ⚠️

기록은 **레포가 아니라 홈**(`~/.projectops/agent-test/{owner}__{repo}/`)에 쌓인다.
커밋되지 않으니 히스토리에 남을 걱정은 없지만, **평문으로 디스크에 남고 실행할 때마다
다시 읽힌다.** 한 번 들어가면 계속 노출되므로 쓰기 전에 막는다.

`note`에 이메일·전화번호·JWT·비밀번호가 섞이면 **기록을 거부하고 이유를 알린다.**
구체적인 값 대신 "테스트 계정으로"처럼 바꿔 적는다. `access`도 마찬가지로 비밀번호
값을 받지 않는다 — 어느 환경변수에서 읽을지만 적는다.

```
{"ok": false, "code": "secret_detected",
 "error": "이메일이 들어 있습니다",
 "hint": "이 파일은 평문으로 디스크에 남고 다음 실행마다 다시 읽힙니다"}
```

어디에 쌓이는지는 `detect`의 `knowledge_dir`, 또는 `doctor --root`가 알려준다.

### 증거로 올리는 것은 따로 판단한다

이슈에 붙이는 스크린샷은 `pro-github`의 `upload-image`로 올린다 (레포에 커밋하지 않는다 —
`references/reporting.md`). **여기서는 자동으로 걸러줄 수 없다.** 이미지 안의 글자까지
판단해야 하기 때문이다. 소셜 로그인 화면에는 **이메일 주소가 그대로 찍힌다.** 문제를
보여주는 데 꼭 필요하면 해당 부분을 잘라내거나 가린 뒤 올린다.
