# 무엇을 밟을지 정한다 — 타겟 확인 · 구조 읽기 · 경로 · 세 축

> 언제 읽나: `detect` 결과에 `confirm` 이 붙었을 때, 처음 들어온 프로젝트일 때, 밟을 경로와 실패·환경 조건을 고를 때.

`SKILL.md` 의 Phase 0 · 0.5 · 1 을 펼친 것이다.

## Phase 0 — 타겟 판정

`detect` 의 판정 순서는 **① 사용자 지정 → ② 네가 확인해 적어 둔 것 → ③ version.yml 의 project_types → ④ 마커 파일**이다.

| 결과 | 무엇을 한다 |
|---|---|
| 하나 | 그것으로 간다 |
| 여럿 (예: `app`·`server`) | **묻는다.** 임의로 고르면 엉뚱한 것을 밟는다 |
| 없음 | 사용자에게 `--target app\|web\|server\|other` 로 알려 달라고 한다 |

> **밟을 것이 앱·웹·서버가 아니면 `other` 다.** CI 워크플로·CLI 툴·라이브러리·템플릿·
> 배치가 전부 여기다. 자동으로 감지되지 않으므로 네가 정해서 `--target other` 로
> 지정하거나 `note target` 으로 적어 둔다.

### `confirm` 이 붙어 있으면 네가 확인한다 ⚠️

`target_source` 가 `version.yml` 이면 그 결과는 **확인된 것이 아니라 선언**이다. "이 레포는
스프링이다"는 말이지 "화면이 없다"는 말이 아니다.

**서버가 화면을 직접 뿌리는 구조는 전혀 이상하지 않다** — Thymeleaf·JSP·Django 템플릿·
Rails·Next의 서버 렌더링이 전부 그렇다. 그런데 선언만 보면 `server` 하나로 끝나고, 그러면
브라우저를 열 생각을 못 해 **화면에서만 보이는 결함을 통째로 놓친다.**

py는 여기서 맞히려 들지 않는다. 프레임워크마다 템플릿 자리가 달라 정규식으로 될 일이
아니다. **코드를 보고 판단하는 것은 네 일이다.**

| 무엇을 보나 | 어디를 |
|---|---|
| 템플릿 폴더가 있나 | `templates/` · `views/` · `src/main/resources/templates` · `app/views` |
| 라우트가 HTML을 돌려주나 | 컨트롤러가 뷰 이름을 반환하는지, JSON만 내보내는지 |
| 정적 파일을 서빙하나 | `static/` · `public/` · `assets/` |
| 클라이언트가 한 레포에 같이 있나 | `client/` · `web/` · `app/` 형제 폴더 |

판단했으면 **적어 둔다.** 다음 실행부터는 묻지 않는다.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note target --root {ROOT} --targets server,web --why "{판단 근거}"
```

`--why` 는 필수다 — 다음에 이 기록이 맞는지 다시 볼 수 있어야 한다. 선언이 이미 맞으면
아무것도 하지 않아도 된다.

> **준비물이 없으면 물어보고 깐다.** 웹은 브라우저(약 100MB)가 필요하다 — 안내만 하고
> 멈추지 않는다. 자세한 절차는 `target-web.md`, 공통 원칙은 `../../references/common-rules.md` 의
> "필요한 것이 없을 때".

### 기기를 확정한다 — `app` 타겟

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py device list --root {PROJECT_ROOT}
```

한 대뿐이면 `$DEV` 가 그 한 대로 채워지고 더 할 일이 없다. **여러 대면 역할을 묶는다** — `devices.md`.

> **`build_mismatch` 가 나오면 거기서 멈춘다.** 역할마다 다른 빌드가 깔려 있다는 뜻이고,
> 그대로 밟으면 "한쪽에서만 재현된다"는 가짜 결함을 만들게 된다. 버전이 같아도 다를 수
> 있어서 APK 해시로 잰다 — 컴파일타임 플래그만 바꾼 재빌드는 버전이 똑같다.

기기를 나중에 띄웠으면 `device list` 를 한 번 더 돌려 환경을 새로 고친다.

> `adb`·`emulator`는 SDK를 설치해도 PATH에 없는 경우가 많다. `detect` 결과의 `adb_path` 를 그대로
> 쓰면 "기기가 없다"는 오진을 피한다. (AVD = Android Virtual Device, 에뮬레이터 기기 정의)

> **서버 주소·DB는 detect가 맞히지 않는다.** 스프링·노드·장고·레일즈는 설정이 있는 자리가
> 제각각이라 정규식으로 맞힐 수 없다. 네가 코드를 읽어 알아낸 뒤 `access` 에 적는다
> (`target-server.md`). 한 번 적으면 다음 실행부터 `detect` 가 알려준다.

## 되는 것 · 안 되는 것 (Android 에뮬레이터 실측) — `app` 타겟

**추측하지 말고 이 표를 본다.** 안 되는 것을 모르고 계획을 세우면 중간에 멈춘다.

| 조작 | 되나 | 명령 |
| --- | --- | --- |
| 누르기·밀기 | ✅ | `launch_cli.py app tap --text …` · `app swipe --dir up` (요소 기준) |
| 영문/숫자 입력 | ✅ | `adb -s "$DEV" shell input text` · 저장된 로그인은 `app type --cred` |
| **한글 입력** | ❌ | `input text`가 ASCII만 받는다. 클립보드·keyevent 모두 불가 |
| 다크모드 전환 | ✅ | `cmd uimode night yes` |
| 네트워크 끊기 | ✅ | `svc wifi disable && svc data disable` |
| 권한 거부·부여 | ✅ | `pm revoke` / `pm grant` |
| 폰트 크기 (접근성) | ✅ | `settings put system font_scale 1.3` |
| 동작 줄이기 | ✅ | `settings put global transition_animation_scale 0` |
| 화면 회전 | ✅ | `settings put system user_rotation 1` |
| 딥링크 직접 진입 | ✅ | `am start -a android.intent.action.VIEW -d "{scheme}://..."` |
| 지문 인증 | ✅ | `adb -s "$DEV" emu finger touch 1` |
| 카메라·마이크 실제 입력 | ❌ | 가상 입력만 가능 |
| 실제 푸시 발송 | ❌ | 서버에서 별도로 쏴야 한다 |
| 인앱결제 실제 승인 | ❌ | 테스트 계정·스토어 설정이 필요하다 |
| **iOS 호스트 마우스 좌표 탭** | ❌ **하지 않는다** | `cliclick`·AppleScript 는 실제 커서를 움직여 금지 — `app tap`(Maestro) 이나 프로젝트 E2E 를 쓴다. `../../pro-launch/references/app.md` 참조 |

### 한글을 꼭 넣어야 하면

1. **영문으로 대체하고 보고에 적는다** — 값 자체가 검증 대상이 아니면 이것으로 충분하다
2. 한글 처리(자소 분리·길이 제한)가 검증 대상이면 **ADBKeyboard 같은 IME를 설치**한다
3. 그것도 어려우면 **사용자에게 직접 입력을 부탁한다** (Phase 4 형식으로 — `social-login.md`)

`FLAG_SECURE`가 걸린 화면(일부 금융·인증 앱)은 스크린샷이 검은색으로 찍힌다. 그때는
`dumpsys window`의 `mCurrentFocus`로 어느 화면인지만 확인하고 사용자에게 넘긴다.

## Phase 0.5 — 이 프로젝트가 어떻게 생겼는지 먼저 읽는다

처음 들어온 프로젝트라면 **구조를 한 번 읽어 둔다.** 매번 화면·엔드포인트를 찾아 헤매지
않기 위해서다.

**읽는 것은 네가 한다.** Grep·Read로 직접 본다 — 예전에는 스크립트가 흔한 규칙
(`lib/features/` · `*_screen.dart`)으로 맞혀 줬는데, 프로젝트마다 구조가 달라 틀리면
**"없다"고 답해 오해를 만들었다.** 네가 읽는 편이 언제나 더 정확하다.

| 타겟 | 볼 것 |
| --- | --- |
| app | 화면 파일이 어디에 어떤 이름으로 있나 · 라우트가 어떻게 정의되나 · 로그인 방식 |
| web | 페이지·라우트 정의 · 상태 관리 · API를 부르는 자리 |
| server | 엔드포인트 목록 · 인증 방식 · **자원에 주인이 있나**(권한 확인의 전제) |

알아낸 것은 **기록에 남긴다.** 다음 실행은 여기서 시작한다.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note screen --root {ROOT} --name "{화면}" --anchor "{알아보는 단서}"
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py access set --root {ROOT} --key {db|logs|base_url} --json '{...}'
```

무엇을 어떤 순서로 쌓는지, 자격증명을 어떻게 걸러내는지는 `learning.md`.

## Phase 1 — 밟을 경로 확정

이미 만들어 둔 시나리오가 있으면 그것을 따른다 (`scenario list`). 없고 사용자가 경로를
지정했으면 그대로 간다. 둘 다 없으면 **한 번만** 묻는다.

```
어디까지 밟을까요?
1) 첫 실행부터 홈 도달까지 (로그인·약관·온보딩 전 구간)
2) 특정 화면만 — 어느 화면인지 알려주세요
3) 사용자가 제보한 버그 재현 — 증상을 알려주세요
```

경로가 정해지면 **단계 목록**을 먼저 적는다. 각 단계에 "무엇을 누르고 → 무엇이 보여야 하고
→ 기기/서버에 무엇이 남아야 하는가"를 쓴다. 이 목록이 판정 기준이 된다 (이유: 기준 없이
밟으면 "화면이 떴으니 됐다"로 끝나고, 실제로는 서버에 아무것도 안 들어가 있을 수 있다).

### 시나리오로 굳힌다

같은 경로를 다시 밟을 것 같으면 파일로 남긴다. `server` 타겟은 `api`가 시나리오를
요구하므로 **반드시** 만든다.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py scenario init --root {ROOT} --name {이름} --target {app|web|server}   # 틀을 만든다
#   틀의 {중괄호} 자리를 채운다 — 파일 위치는 출력의 file 필드
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py scenario show --root {ROOT} --name {이름}                              # 밟기 전에 검증
```

**`show`를 건너뛰지 않는다.** 기대 결과가 없는 단계, 안 채운 중괄호, 모르는 타겟을
여기서 막는다. 이걸 통과시키면 엉뚱한 곳을 누르거나 "화면이 떴으니 통과"로 끝난다.

> 시나리오와 기록은 프로젝트가 아니라 **홈**(`detect`의 `knowledge_dir`)에 쌓인다.
> 워크트리를 새로 만들어도 살아남는다.

## 해피 패스만 밟지 않는다 — 세 축 ⚠️

정상 경로는 개발자가 이미 수십 번 밟아봤다. **버그는 대개 그 바깥에 있다.**
아래 세 축에서 밟을 것을 고른다 — 전부 할 필요는 없고, 이 앱에서 말이 되는 것만.

**축 1 — 상태 조합.** 앱은 저장된 상태에 따라 다르게 시작한다.

| 세션 | 온보딩 | 기대 | 확인법 |
| --- | --- | --- | --- |
| 없음 | — | 로그인부터 | `pm clear` 후 실행 |
| 있음 | 미완료 | 이어서 진행 | 온보딩 중간에 앱 강제 종료 후 재실행 |
| 있음 | 완료 | 홈 직행 | 그냥 재실행 |
| 만료 | 완료 | 갱신 또는 재로그인 | 서버에서 토큰 폐기 후 실행 |

무엇을 밟을지 고를 때 **코드에서 후보를 먼저 뽑는다.** `catch` 블록과 폴백은 대개
한 번도 실행되지 않은 채 배포된다.

```bash
# 예: 예외 처리·폴백이 어디 있는지 (Grep 으로 직접 찾는다)
catch · rescue · except · \.catch\( · onError · fallback · ?? · orElse
```

예외 경로·네트워크 실패·빈 목록·권한 거부·폴백·에러 코드·토큰 만료·재시도가 후보다.
**전부 밟을 필요는 없다** — 많이 걸린 곳과 사용자가 자주 닿는 곳부터 고른다.
찾는 것도 고르는 것도 **네 판단이다.** 스크립트가 대신 골라 주면 그 목록 밖은 영영 안 밟는다.

**축 2 — 실패 주입.** 위 표의 조작으로 실패를 **만들어서** 밟는다.

| 상황 | 만드는 법 | 봐야 할 것 |
| --- | --- | --- |
| 네트워크 끊김 | `svc wifi disable && svc data disable` | 무한 로딩·빈 화면이 아니라 재시도 경로가 있는가 |
| 권한 거부 | `pm revoke {패키지} {권한}` | 앱이 죽지 않고 우회 경로를 주는가 |
| 서버 오류 | 서버를 잠시 내리거나 잘못된 토큰 주입. **웹이면 `web route --status 500`** — 서버를 건드리지 않는다 | **에러 코드가 화면에 보이는가** (제보받았을 때 추적하려면 필요하다) |
| 목록 0건 | 데이터를 비운 계정으로. **웹이면 `web route --status 200 --body "[]"`** | 로딩과 구분되는 빈 상태 화면이 있는가 |
| 느린 응답 | **웹이면 `web route --delay 5000`** | 로딩 표시가 있는가 · 두 번 눌러지지 않는가 |

**축 3 — 환경 조건.** 접근성과 표시 설정을 바꿔 레이아웃이 버티는지 본다.

| 조건 | 명령 | 봐야 할 것 |
| --- | --- | --- |
| 큰 글씨 | `settings put system font_scale 1.3` | 글자가 잘리거나 버튼을 밀어내지 않는가 |
| 다크모드 | `cmd uimode night yes` | 대비가 무너지거나 보이지 않는 글자가 없는가 |
| 동작 줄이기 | `settings put global transition_animation_scale 0` | 애니메이션에 기대던 화면이 멈추지 않는가 |
| 가로 회전 | `settings put system user_rotation 1` | 오버플로가 나지 않는가 |

> **되돌리는 것을 잊지 않는다.** 바꾼 설정은 다음 테스트에 그대로 영향을 준다.
> 각 조건을 끝낸 직후 원래대로 돌린다 (`font_scale 1.0`, `night no`, `user_rotation 0`,
> `transition_animation_scale 1`, `svc wifi enable`).

> **이 세 축은 "무엇을 밟을지" 고르는 것이다.** "밟으면서 무엇을 볼지"는 별개이고
> `looks-wrong.md` 의 축 4·5·6·7 이 그것이다 — 기능이 도는 것만 보면
> 폰트가 제각각이거나 뒤로가기가 막힌 것은 전부 통과로 끝난다.
