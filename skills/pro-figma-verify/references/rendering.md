# 렌더를 시안과 같게 맞춘다

픽셀로 맞대려면 **두 그림이 같은 조건에서 나와야** 한다. 조건이 어긋나면 구현이
맞아도 전부 다르게 나오고, 그러면 결과를 아무도 안 믿는다.

**찍는 것 자체는 pro-launch 가 한다** (#633). 기기·시뮬레이터 캡처는 `app shot`, 브라우저는
`web shot`, 코드로 그려 찍는 것은 `render run` 이다. 스택별 렌더 레시피는
`../../pro-launch/references/render.md`. 이 문서에는 **시안과 맞대기 위해 그 기본값에서
바꿔야 하는 것**만 남긴다.

```bash
# pro-launch 스크립트는 common-rules.md 표준 블록을 SKILL=pro-launch 로 돌려 찾는다 → {LAUNCH}
{PYTHON} {LAUNCH}/launch_cli.py get-output-path --skill figma-verify --title "{화면 이름}"
```

## pro-launch 기본값과 다르게 찍는 것 — 한눈에

| 무엇 | pro-launch 기본 | 시안 대조 | 왜 다른가 |
|---|---|---|---|
| **형식·크기** | 긴 변 1200 WebP 로 줄인다 | **원본 PNG** — `--keep-format` 또는 `--out` 에 경로를 준다 | 줄이면 픽셀이 뭉개져 대조가 무의미해진다. 기본값은 세션 토큰을 아끼려는 것이다 |
| **배율** | 기기·브라우저 배율 그대로 (웹 `viewport` 는 폭만 바꾼다) | 컴포넌트는 **3배** — 아래 스택별 방법 | 그림자·1px 테두리는 1배 전체 화면에서 사라진다 (Phase 6) |
| **안전영역** | 레포 기본값 · 테스트 기본값(보통 0) | **기기 실측값** | 시안 프레임은 상태바·홈 인디케이터를 포함해 그려진다. 안 맞추면 본문이 통째로 뜬다 |
| **상태바** | `--clean-status` 로 시각 고정 가능 | 고정해도 **가린다** (`diff --mask-top`) | 앱이 그리는 영역이 아니라 시안과 늘 다르다 |
| **내용** | 아무 데이터 | **시안에 그려진 내용 그대로** | 목록 개수·문구가 다르면 diff 가 통째로 붉어져 정작 봐야 할 어긋남이 묻힌다 |
| **렌더 폴더** | 임시 폴더(`_launch_render`), 끝나면 지운다 | 같다 — **레포의 `goldens/` 에 쓰지 않는다** | 회귀용 골든과 대조용 렌더는 목적이 다르다 (아래) |

## 맞춰야 하는 네 가지

| 무엇 | 안 맞추면 |
|---|---|
| **논리 크기** | 전부 어긋난다 |
| **안전영역** (상태바·홈 인디케이터) | 본문이 상태바 높이만큼 떠서 모든 줄이 어긋난 것으로 나온다 |
| **배율** | 컴포넌트를 크게 볼 때 글자만 안 커지거나 캡처가 작게 나온다 |
| **내용** | 목록 개수·문구가 시안과 다르면 diff 가 통째로 붉어진다 |

> **논리 크기**는 기기 해상도가 아니라 앱이 좌표를 재는 단위다 (예: 논리 393 폭이
> 3배 기기에서 실제 1179 픽셀). 시안 프레임도 논리 크기로 그려지므로 둘을 맞춘다.

## 안전영역 — 가장 많이 틀리는 자리

시안 프레임은 보통 상태바와 홈 인디케이터를 **포함한** 높이로 그려진다. 앱은 그
띠를 직접 그리지 않으므로,

- 렌더에 **같은 여백을 넣어** 본문 시작 y 를 맞추고
- 비교할 때 그 띠를 `--mask-top` · `--mask-bottom` 으로 **가린다**

둘 다 해야 한다. 여백만 넣고 안 가리면 시계·배터리 자리가 늘 다르게 나오고,
가리기만 하고 여백을 안 넣으면 본문이 떠서 전부 어긋난다.

기기별 실측값은 프로젝트에서 확인해 기록해 둔다 (`pro-agent-test` 의 `note`).

## 대조용 렌더는 회귀용 골든과 분리한다

| | 회귀용 골든 | 대조용 렌더 |
|---|---|---|
| 목적 | 전에 만든 그림과 같은가 | **시안과** 같은가 |
| 기준 | 구현자가 만든 이전 캡처 | 시안 export |
| 안전영역 | 보통 0 | 기기 실측값 |

**섞으면 안 된다.** 회귀용 기준은 **구현자가 만든다.** 첫 이미지가 시안과 다르면
**틀린 것을 그대로 고정**하고, 이후에는 그 틀린 그림에서 벗어나는 것만 잡아낸다.
회귀는 막지만 정합은 못 본다 — 이미 여러 장이 그 상태일 수 있다.

## 무엇과 맞댔는지 남긴다

화면마다 **시안 노드 id** 를 테스트 이름이나 코드 주석에 남긴다.

```
testWidgets('{화면 이름} (Figma {노드 id})', ...)
```

없으면 다음 사람이 어느 시안과 비교해야 하는지 몰라 처음부터 찾는다.

---

## Flutter

**찍는 법**: 위젯 테스트 렌더 → `render run` (레시피는 pro-launch `render.md` 의 Flutter 절).

```bash
{PYTHON} {LAUNCH}/launch_cli.py render snapshot --root {레포}
#   임시 위젯 테스트를 client/test/_launch_render/ 에 만든다 — 아래 조정을 넣어서
{PYTHON} {LAUNCH}/launch_cli.py render run --root {레포} --cwd client \
  --cmd "flutter test test/_launch_render --update-goldens" \
  --collect "client/test/_launch_render/shots/*.png" --cleanup client/test/_launch_render
```

### 논리 크기 · 안전영역

```dart
// 시안 프레임과 같은 논리 크기로 뷰포트를 잡는다
// 안전영역은 기기 실측값을 MediaQuery 로 넣는다 — 안 넣으면 본문이 위로 뜬다
MediaQuery(
  data: MediaQuery.of(context).copyWith(
    padding: const EdgeInsets.only(top: {상단}, bottom: {하단}),
  ),
  child: child!,
)
```

### 컴포넌트를 3배로 찍기 (RepaintBoundary)

- 화면을 3배로 넓히고 **dpr 은 1 로 둔다** (dpr = device pixel ratio). dpr 을 올리는 방법은
  통하지 않는다 — **골든은 논리 픽셀로 캡처하기 때문이다**
- 크기 스케일링 패키지(`flutter_screenutil` 등)를 쓰면 대개 **너비만 키우고 글자
  크기는 안 건드린다.** `MediaQuery(textScaler:)` 를 함께 줘야 글자까지 3배가 된다
- `RepaintBoundary` 가 없으면 **화면 전체가 찍힌다** — 컴포넌트만 찍으려면 감싼다

### 골든 파일은 대조 대상이 아니다

`matchesGoldenFile` 로 만든 PNG 를 **시안 export 와** 맞댄다. 골든끼리 비교하는 것은
회귀 확인이지 시안 대조가 아니다.

---

## React (웹)

**찍는 법**: 논리 크기가 시안과 같으면 pro-launch 브라우저로 충분하다.

```bash
{PYTHON} {LAUNCH}/launch_cli.py web viewport --preset 393x852          # 시안 프레임 논리 크기
{PYTHON} {LAUNCH}/launch_cli.py web goto --url {화면}
{PYTHON} {LAUNCH}/launch_cli.py web shot --keep-format --out {화면}      # 원본 PNG
{PYTHON} {LAUNCH}/launch_cli.py web shot --keep-format --selector '[data-testid="cta"]' --out {컴포넌트}
```

**3배는 pro-launch 브라우저로 못 한다** — `deviceScaleFactor` 는 컨텍스트를 만들 때만 정해지고,
pro-launch 는 이어 붙는 브라우저라 1배로 고정이다. 3배 컴포넌트는 Playwright 스크립트를
임시로 짜 `render run` 으로 돌린다.

```js
// _launch_render/shot.mjs — render run 이 끝나면 지운다
const ctx = await browser.newContext({ viewport: { width: 393, height: 852 }, deviceScaleFactor: 3 });
const page = await ctx.newPage();
await page.goto(URL);
await page.evaluate(() => document.fonts.ready);          // 글꼴이 다 실리기 전에 찍지 않는다
await page.addStyleTag({ content: `*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}` });
await page.locator('[data-testid="cta"]').screenshot({ path: '_launch_render/cta@3x.png' });
```

### 글꼴이 다 실리기 전에 찍으면 전부 다르게 나온다 ⚠️

가장 자주 틀리는 자리다. 대체 글꼴로 찍히면 **모든 글자 줄이 어긋난 것으로** 잡혀
정작 봐야 할 어긋남이 묻힌다. 위 `document.fonts.ready` 를 빼지 않는다.

### 안전영역

웹에는 상태바가 없다. 시안 프레임이 상태바를 포함해 그려졌다면 렌더에 억지로
만들지 말고 **`--mask-top` 으로 가린다.** `env(safe-area-inset-*)` 를 쓰는 화면이면
그 값을 CSS 변수로 고정해 시안과 맞춘다.

Storybook 을 쓰면 스토리 하나를 열어 그 루트를 찍는 것이 가장 깔끔하다.

---

## React Native

**찍는 법**: 시안 프레임과 **논리 크기가 같은 기기**를 골라 pro-launch 로 받는다
(iPhone 15 = 393×852 논리). 크기가 다른 기기로 찍으면 맞출 방법이 없다.

```bash
{PYTHON} {LAUNCH}/launch_cli.py app shot --device {UDID 또는 시리얼} --keep-format --out render
```

받은 그림은 **물리 해상도**다 (3배 기기면 1179×2556). 시안을 같은 배율로 내보내거나
받은 그림을 논리 크기로 줄여 맞춘다 — 둘 중 하나를 반드시 한다.

### 안전영역

`react-native-safe-area-context` 의 `initialMetrics` 로 값을 **고정**한다.

```jsx
<SafeAreaProvider initialMetrics={{
  frame: { x: 0, y: 0, width: 393, height: 852 },
  insets: { top: 59, left: 0, right: 0, bottom: 34 },
}}>
```

### 컴포넌트만 찍기

```jsx
import { captureRef } from 'react-native-view-shot';
await captureRef(ref, { format: 'png', quality: 1, result: 'tmpfile' });
```

`captureRef` 는 **논리 픽셀로 찍는다.** 3배로 보려면 `pixelRatio: 3` 을 준다. 이 코드를 앱에 넣었다면
대조가 끝나고 되돌린다 — `render snapshot` 으로 기준을 떠 두면 되돌렸는지 `render run` 이 검사한다.

---

## 그 밖의 프레임워크

위 네 가지(논리 크기 · 안전영역 · 배율 · 내용)는 프레임워크를 가리지 않는다.
쓰는 것에서 각각을 어떻게 맞추는지 알아내 **여기에 절을 추가한다.** 찍는 법이 새로 생기면
pro-launch `render.md` 에 레시피로 넣는다 — 찍는 법이 두 곳에 갈라지지 않게.
