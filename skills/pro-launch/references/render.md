# 상태를 연출해 찍는다 — 스택별 렌더 레시피 (#632)

실기기 캡처로는 **엣지 상태**(빈 목록 · 실패 · 긴 글자 · 권한 거부)를 만들기 어렵다. 서버
데이터를 건드려야 해서 느리고 위험하다. 그래서 **코드로 그 상태를 그려서 찍는다.**

원칙은 둘이다.

1. **렌더 코드는 네가 레시피를 보고 대상 레포에 임시로 짠다.** 상태 관리 방식(Riverpod ·
   Bloc · Provider · Redux …)을 스크립트가 알아맞히지 않는다.
2. **`render run` 은 실행 · 수집 · 청소 · 흔적 검사만 한다.** 끝난 뒤 레포가 처음과 같은지
   `git status` 로 확인하는 것을 명령이 강제한다.

## 순서 — 이 순서가 곧 계약이다

```bash
# ① 임시 파일을 만들기 **전에** 기준을 뜬다
{PYTHON} {SCRIPTS}/launch_cli.py render snapshot --root {대상 레포}

# ② 임시 렌더 코드를 만든다 (아래 스택별 레시피) — 전용 폴더 하나에 모은다

# ③ 돌리고 · 모으고 · 청소하고 · 흔적을 검사한다
source "{env_file 값}"      # 모은 그림은 $SHOT_DIR 로 간다
{PYTHON} {SCRIPTS}/launch_cli.py render run --root {대상 레포} --cwd client \
  --cmd "flutter test test/_launch_render --update-goldens" \
  --collect "client/test/_launch_render/shots/*.png" \
  --cleanup client/test/_launch_render
```

| 결과 `code` | 뜻 | 할 일 |
|---|---|---|
| `ok` | 모았고 흔적 없음 | Read 로 열어 본다 |
| `render_failed` | 명령이 실패했다 — **수집하지 않고 청소만 했다** | `output_tail` 을 보고 렌더 코드를 고친다. 아래 함정 표를 먼저 본다 |
| `residue` | 끝난 뒤 레포에 **처음에 없던 것**이 남았다 | 네가 만든 것이면 지우거나 `--cleanup` 에 넣어 다시 돈다. **모르는 변경이면 건드리지 않는다** — 다른 세션의 작업일 수 있다. 스크립트도 지우지 않는다 |
| `nothing_collected` | 성공했는데 그림이 없다 | `--collect` 글롭이 레포 루트 기준으로 맞는지 본다 |

> **①을 건너뛰지 않는다.** 기준 없이 `run` 만 부르면 그 순간을 기준으로 삼는다 — 이미 만든
> 임시 파일이 기준에 들어가, `--cleanup` 에서 빠뜨린 파일이 남아도 **흔적으로 안 잡힌다.**
> (구현하며 실제로 짜 보다가 발견했다.)

- `--cleanup` 은 **레포 안 경로만** 지운다. 밖을 주면 거절하고 경고한다.
- 모은 그림은 원본 PNG 그대로다. 이슈에 붙이려면 `shrink` 로 줄인다.
- **캡처를 위해 AI 생성 API 를 부르지 않는다** — 돈이 든다. 가짜 데이터를 코드로 넣는다.
- **골든 기준 파일과 섞지 않는다.** 임시 폴더(`_launch_render`)에 따로 두고 끝나면 지운다.
  레포의 `goldens/` 에 쓰면 회귀 테스트 기준이 바뀐다.

---

## Flutter

**기본 캡처**: 위젯 테스트 렌더 — `matchesGoldenFile` 을 임시 경로로 + `--update-goldens`.

```dart
// client/test/_launch_render/states_test.dart — render run 이 끝나면 지운다
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Widget wrap(Widget child) => MaterialApp(
        theme: /* 레포의 테마 */ ThemeData(),
        home: Scaffold(body: Center(child: child)),
      );

  for (final (name, items) in [('empty', <String>[]), ('many', List.generate(30, (i) => '항목 $i'))]) {
    testWidgets('list $name', (tester) async {
      await tester.pumpWidget(wrap(/* 실제 화면 위젯에 가짜 데이터 */ Text('$items')));
      await tester.pumpAndSettle();
      await expectLater(find.byType(MaterialApp), matchesGoldenFile('shots/list_$name.png'));
    });
  }
}
```

**먼저 확인할 것**: 폰트를 싣는 `test/flutter_test_config.dart` 가 있는가. **없으면 한글이 전부 □ 로
나온다.** 있으면 그대로 쓰고, 없으면 임시 폴더 안에 `flutter_test_config.dart` 를 같이 만들어
`FontLoader` 로 앱 폰트를 싣는다 (그 폴더에만 적용된다).

**엣지 상태 연출**

| 상태 관리 | 가짜 값을 넣는 법 |
|---|---|
| Riverpod | `ProviderScope(overrides: [xProvider.overrideWith(...)])` |
| Bloc | `BlocProvider.value(value: MockBloc(...))` 또는 원하는 상태로 `emit` 한 큐빗 |
| Provider | `ChangeNotifierProvider.value(value: 가짜모델)` |
| 생성자 주입 | 위젯에 가짜 데이터를 직접 넘긴다 — 가장 단순하다 |

- 안전영역·기기 크기는 `MediaQuery` padding 과 `tester.view.physicalSize` 로 재현한다.
  레포에 뷰포트 도우미(예: `useFigmaViewport()`)가 있으면 그것을 쓴다.
- 다크 모드·글자 크기는 `MaterialApp(themeMode:)`·`MediaQuery(textScaler:)` 로.

**보조**: 시뮬레이터 `app shot` — 실제 화면 전환·애니메이션이 필요할 때.

**함정 (한 Flutter 앱의 요청서 작업에서 실측)**

| 증상 | 원인 | 대응 |
|---|---|---|
| 글자에 **노란 이중 밑줄** | 오버레이를 `Material` 밖에 그렸다 | `Material` 로 감싼다 (`Scaffold` 안에 두면 된다) |
| `pumpAndSettle` 이 끝나지 않는다 | 무한 애니메이션 (로딩 스피너 · 반복 효과) | `pump(Duration)` 로 한 프레임만, 또는 "동작 줄이기"(`MediaQuery(disableAnimations: true)`)를 켠다 |
| 건드리지 않은 줄까지 diff | `dart format` 이 파일 전체를 다시 썼다 | 임시 파일에만 돌린다. 레포 파일에 포맷터를 돌리지 않는다 |
| 한글이 □ | 폰트를 안 실었다 | 위 "먼저 확인할 것" |
| `render_failed` + 오버플로 | 레포의 테스트 설정이 오버플로를 실패로 만든다 | **그 자체가 발견이다.** 그 상태에서 화면이 깨진다는 뜻 — 보고에 적는다 |

## React / Next

**기본 캡처**: Playwright 스크린샷. **Storybook 이 있으면 스토리 URL 을 우선한다** — 상태별
스토리가 이미 있으면 렌더 코드를 짤 필요가 없다.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py web open --url http://localhost:6006/iframe.html?id=list--empty
{PYTHON} {SCRIPTS}/launch_cli.py web shot --selector "#storybook-root" --out list_empty
```

**엣지 상태 연출**: 서버를 건드리지 않고 `web route` 로 API 응답을 바꿔친다. 폭은 `web viewport`.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py web route --match "**/api/items*" --status 200 --body "[]"
{PYTHON} {SCRIPTS}/launch_cli.py web route --match "**/api/items*" --status 500 --body '{"message":"x"}'
{PYTHON} {SCRIPTS}/launch_cli.py web route --match "**/api/items*" --delay 5000     # 로딩
{PYTHON} {SCRIPTS}/launch_cli.py web viewport --preset mobile
{PYTHON} {SCRIPTS}/launch_cli.py web goto --url http://localhost:3000/items
{PYTHON} {SCRIPTS}/launch_cli.py web shot --out items_empty_mobile
{PYTHON} {SCRIPTS}/launch_cli.py web route --clear
```

이 경로는 레포에 파일을 만들지 않으므로 `render run` 이 필요 없다.

| 함정 | 대응 |
|---|---|
| 빈 목록을 걸었는데 목록이 채워진다 | 서버 렌더(SSR)에서 이미 데이터를 넣었다. route 는 **브라우저 요청**만 바꾼다 — SSR 데이터는 스토리나 테스트 목으로 |
| 규칙을 걸었는데 그대로다 | 이미 열린 화면이다. `web goto` 로 다시 부른다 |

**보조**: dev 서버 실화면.

## React Native

**기본 캡처**: 시뮬레이터·에뮬레이터 `app shot`.

**엣지 상태 연출**: 목 서버(MSW 네이티브 · json-server) · 개발 메뉴 플래그 · 테스트 빌드 환경변수로
응답을 바꾼다. 앱 코드에 연출용 분기를 **영구로 넣지 않는다** — 넣었으면 끝나고 되돌린다
(`render snapshot` → 수정 → 찍기 → 되돌리기 → `render run --cmd true` 로 흔적만 검사할 수도 있다).

**보조**: Expo 웹 빌드가 되면 Playwright 로 React 와 같은 경로를 쓴다.

## Spring 서버 렌더 (Thymeleaf 등)

**기본 캡처**: 서버를 test 프로필로 띄우고 Playwright.

**엣지 상태 연출**: 시드 데이터 · test 프로필. 운영 DB 를 쓰지 않는다.

**보조**: MockMvc 로 HTML 만 뽑아 정적 파일로 열어 찍는다 (서버를 못 띄울 때).

```bash
# 테스트가 HTML 을 build/_launch_render/*.html 로 떨군다고 할 때
{PYTHON} {SCRIPTS}/launch_cli.py render snapshot --root {레포}
{PYTHON} {SCRIPTS}/launch_cli.py render run --root {레포} \
  --cmd "./gradlew test --tests '*LaunchRender*'" --collect "build/_launch_render/*.png" \
  --cleanup src/test/java/{패키지}/LaunchRenderTest.java
```

## 순수 API 서버 — 화면이 없다

찍을 화면이 없다. 대신 **사용자가 보게 될 말**을 모은다.

1. 에러 코드별 사용자 문구 카탈로그 — 코드를 읽어 `code → 문구` 표를 만든다
2. 상태 목록 — 어떤 요청이 어떤 상태를 낳는지
3. 필요하면 ASCII 와이어

에러 응답은 `http` 로 하나씩 실제로 확인한다.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py http --url /api/items/999 --expect-status 404
```

## 렌더할 수 없을 때 — ASCII 와이어

도구가 없거나 렌더에 실패한 상태는 ASCII 로 그리고 **"렌더 실패"** 라고 적는다.

규칙: **등폭** · 박스 문자(`┌ ─ ┐ │ └ ┘ ├ ┤`) · **한글은 두 칸**으로 센다(폭이 맞지 않으면 선이 어긋난다).

```
┌──────────────────────────────┐
│  목록                    ⚙   │
├──────────────────────────────┤
│                              │
│        (빈 상태 그림)        │
│    아직 만든 카드가 없어요   │
│      [ 카드 만들기 ]         │
│                              │
└──────────────────────────────┘
  상태: 목록 0건 · 렌더 실패(폰트 없음) → ASCII
```

> 실제 화면을 대신하지 못한다. **무엇이 어디에 있는지**만 전한다 — 글꼴·간격·색은 담지 못한다고 함께 적는다.
