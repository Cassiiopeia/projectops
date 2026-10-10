# 앱을 밟는다 (target: app)

> 언제 읽나: Phase 0 에서 타겟이 `app` 으로 정해졌을 때.

**기기를 띄우고·설치하고·조작하고·찍는 법은 pro-launch 로 옮겼다** →
`../../pro-launch/references/app.md` (Android 에뮬레이터 · iOS 시뮬레이터 · 실기기 · 녹화 · iOS 좌표 조작의 제약).

여기에는 **QA 로 밟을 때만 필요한 것**만 남긴다.

```bash
source "{env_file 값}"
{PYTHON} {LAUNCH}/launch_cli.py app launch --device "$DEV" --pkg "$PKG"
{PYTHON} {LAUNCH}/launch_cli.py app shot --device "$DEV" --out step_N
{PYTHON} {LAUNCH}/launch_cli.py app tap --device "$DEV" --text "{화면 문구}" --shot step_N_after   # 요소로 누른다 (좌표 아님)
{PYTHON} {LAUNCH}/launch_cli.py app swipe --device "$DEV" --dir up
```

> **Google Play 이미지는 `adb root`가 안 된다.** 앱 내부 파일(`/data/data/...`)을 직접 열
> 수 없으므로 상태 확인은 **앱 로그**로 한다 (`stepping.md` Phase 2).

## 앱에서만 나는 함정

### 화면

| 함정 | 대응 |
|---|---|
| **큰 글씨로 바꿨는데 글자가 안 커진다** | 앱 전체가 무시한다고 단정하기 전에 **그 화면이 스케일 단위를 쓰는지** 본다 (Flutter 라면 `flutter_screenutil` 의 `.sp` 같은 것). 일부 화면만 고정 크기를 쓰는 경우가 흔하다 — 일반 화면에서 다시 재 본다 |
| **뒤로가기가 안 되는 화면이 있다** | 라우터가 화면을 **교체**하며 열었는지 **쌓으며** 열었는지 본다 (`go_router` 의 `go` vs `push`). 교체였으면 돌아갈 자리가 없다. 화살표만 고치면 **기기 뒤로가기는 여전히 막힌다** — 둘을 따로 밟는다 |

### 빌드 플래그 ⚠️

개발 스위치가 안 먹을 때 가장 많이 헤매는 자리다. 표는 `../../pro-launch/references/app.md` 의
"빌드 플래그" 절에 있다. QA 로 밟을 때 덧붙일 것은 하나다.

> **테스트용 플래그를 켠 빌드로 밟았으면 보고에 적는다.** 그 결과는 배포 빌드의 결과가 아니다.
> 되돌리는 것까지가 한 단위다 — 기기가 여러 대면 켠 기기를 전부 되돌린다 (`devices.md`).

## 서버 데이터 대조

접속 정보를 **하드코딩하지 않는다.** 코드를 읽어 붙는 법을 알아낸 뒤 pro-launch `access` 에 적고,
그 기록으로 조회한다 (`../../pro-launch/references/server.md`).

```bash
{PYTHON} {LAUNCH}/launch_cli.py access set --root {ROOT} --key db --json '{"how":"direct","engine":"postgres","host":"...","db":"...","user":"...","password_env":"DB_PASSWORD"}'
DB_PASSWORD=... {PYTHON} {LAUNCH}/launch_cli.py db --profile db --root {ROOT} --sql "select ..."
```

> 설정 파일은 대개 gitignore 대상이다. **값을 출력하거나 커밋하지 않는다.**
> 보고에는 호스트·DB명 정도만 적는다.
