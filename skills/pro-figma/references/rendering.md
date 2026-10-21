# Make the render match the design

> When to read: Phases 5 · 6, before comparing by pixels, when matching the render to the design's conditions (logical size · safe area · scale).

To compare by pixels, **both images must come from the same conditions**. If the conditions differ, everything comes out as different
even when the implementation is right, and then nobody trusts the result.

**pro-launch does the capturing itself** (#633). Device and simulator captures are `app shot`, the browser is
`web shot`, and drawing through code and capturing is `render run`. Per-stack render recipes are in
`../../pro-launch/references/render.md`. This document keeps only **what to change from those defaults
to compare against the design**.

```bash
# Find the pro-launch scripts by running the standard block from common-rules.md with SKILL=pro-launch → {LAUNCH}
{PYTHON} {LAUNCH}/launch_cli.py get-output-path --skill figma --title "{screen name}"
```

## Where captures differ from the pro-launch defaults, at a glance

| What | pro-launch default | Design comparison | Why it differs |
|---|---|---|---|
| **Format · size** | Shrinks to WebP, 1200 on the long side | **Original PNG**: `--keep-format`, or give a path to `--out` | Shrinking blurs the pixels and makes comparison meaningless. The default exists to save session tokens |
| **Scale** | The device or browser scale as is (web `viewport` changes only the width) | **3x** for components; per-stack methods below | Shadows and 1px borders vanish on a full screen at 1x (Phase 6) |
| **Safe area** | Repo default · test default (usually 0) | **Measured device values** | Design frames are drawn including the status bar and home indicator. Without matching, the whole body floats |
| **Status bar** | The time can be fixed with `--clean-status` | Even when fixed, **mask it** (`diff --mask-top`) | The app does not draw it, so it always differs from the design |
| **Content** | Any data | **Exactly the content drawn in the design** | If list counts or text differ, the whole diff turns red and the misalignment you need to see gets buried |
| **Render folder** | A temp folder (`_launch_render`), deleted when done | Same. **Do not write into the repo's `goldens/`** | Regression goldens and comparison renders serve different purposes (below) |

## The four things to match

| What | If not matched |
|---|---|
| **Logical size** | Everything is off |
| **Safe area** (status bar · home indicator) | The body floats by the status bar height and every line comes out as off |
| **Scale** | When enlarging a component, only the text fails to grow, or the capture comes out small |
| **Content** | If list counts or text differ from the design, the whole diff turns red |

> **Logical size** is not the device resolution but the unit the app measures coordinates in (for example, a logical width of 393
> is 1179 actual pixels on a 3x device). Design frames are also drawn in logical size, so match the two.

## Safe area: the spot most often wrong

Design frames are usually drawn at a height that **includes** the status bar and home indicator. The app does not draw
those bands itself, so:

- **Add the same padding** to the render so the body starts at the same y
- **Mask** those bands with `--mask-top` · `--mask-bottom` when comparing

Do both. With padding but no mask, the clock and battery area always differ.
With a mask but no padding, the body floats and everything is off.

Measure the values for each device in the project and record them (`note` in `pro-agent-test`).

## Keep comparison renders separate from regression goldens

| | Regression golden | Comparison render |
|---|---|---|
| Purpose | Is it the same as the image made before? | Is it the same as **the design**? |
| Reference | A previous capture made by the implementer | The design export |
| Safe area | Usually 0 | Measured device values |

**Do not mix them.** The regression reference **is made by the implementer.** If the first image differs from the design,
it **locks in what is wrong**, and from then on it only catches departures from that wrong image.
It prevents regressions but cannot check conformance. Several images may already be in that state.

## Record what you compared against

For each screen, put **the design node id** in the test name or a code comment.

```
testWidgets('{screen name} (Figma {node id})', ...)
```

Without it, the next person does not know which design to compare with and has to search from scratch.

---

## Flutter

**How to capture**: widget test render → `render run` (recipe in the Flutter section of pro-launch `render.md`).

```bash
{PYTHON} {LAUNCH}/launch_cli.py render snapshot --root {repo}
#   Create a temporary widget test in client/test/_launch_render/, with the adjustments below
{PYTHON} {LAUNCH}/launch_cli.py render run --root {repo} --cwd client \
  --cmd "flutter test test/_launch_render --update-goldens" \
  --collect "client/test/_launch_render/shots/*.png" --cleanup client/test/_launch_render
```

### Logical size · safe area

```dart
// Set the viewport to the same logical size as the design frame
// Pass the measured device safe area through MediaQuery; without it the body floats up
MediaQuery(
  data: MediaQuery.of(context).copyWith(
    padding: const EdgeInsets.only(top: {top}, bottom: {bottom}),
  ),
  child: child!,
)
```

### Capturing a component at 3x (RepaintBoundary)

- Make the screen 3x wider and **keep dpr at 1** (dpr = device pixel ratio). Raising dpr
  does not work, **because goldens are captured in logical pixels**
- Size-scaling packages (`flutter_screenutil` etc.) usually **enlarge only the width and leave
  font size alone.** Pass `MediaQuery(textScaler:)` as well to make the text 3x too
- Without `RepaintBoundary`, **the whole screen is captured**. Wrap the component to capture only it

### Golden files are not the comparison target

Compare the PNG made by `matchesGoldenFile` **against the design export**. Comparing goldens with each other is
a regression check, not a design comparison.

---

## React (web)

**How to capture**: if the logical size matches the design, the pro-launch browser is enough.

```bash
{PYTHON} {LAUNCH}/launch_cli.py web viewport --preset 393x852          # logical size of the design frame
{PYTHON} {LAUNCH}/launch_cli.py web goto --url {screen}
{PYTHON} {LAUNCH}/launch_cli.py web shot --keep-format --out {screen}      # original PNG
{PYTHON} {LAUNCH}/launch_cli.py web shot --keep-format --selector '[data-testid="cta"]' --out {component}
```

**3x is not possible with the pro-launch browser**: `deviceScaleFactor` is set only when the context is created,
and pro-launch attaches to a running browser, so it is fixed at 1x. For a 3x component, write a temporary Playwright script
and run it with `render run`.

```js
// _launch_render/shot.mjs — deleted when render run finishes
const ctx = await browser.newContext({ viewport: { width: 393, height: 852 }, deviceScaleFactor: 3 });
const page = await ctx.newPage();
await page.goto(URL);
await page.evaluate(() => document.fonts.ready);          // do not capture before all fonts have loaded
await page.addStyleTag({ content: `*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}` });
await page.locator('[data-testid="cta"]').screenshot({ path: '_launch_render/cta@3x.png' });
```

### Capturing before fonts finish loading makes everything differ ⚠️

This is the spot most often wrong. If it is captured with a fallback font, **every line of text is flagged as off**,
and the misalignment you need to see gets buried. Do not remove the `document.fonts.ready` above.

### Safe area

The web has no status bar. If the design frame was drawn with a status bar, do not fake one in the render;
**mask it with `--mask-top`.** If the screen uses `env(safe-area-inset-*)`, fix those values as CSS variables to match the design.

If you use Storybook, opening one story and capturing its root is the cleanest.

---

## React Native

**How to capture**: pick a device with **the same logical size as the design frame** and capture with pro-launch
(iPhone 15 = 393×852 logical). If you capture on a device of a different size, there is no way to match.

```bash
{PYTHON} {LAUNCH}/launch_cli.py app shot --device {UDID or serial} --keep-format --out render
```

The image you get is at **physical resolution** (1179×2556 on a 3x device). Either export the design at the same scale
or shrink the captured image to logical size. You must do one of the two.

### Safe area

**Fix** the values with `initialMetrics` from `react-native-safe-area-context`.

```jsx
<SafeAreaProvider initialMetrics={{
  frame: { x: 0, y: 0, width: 393, height: 852 },
  insets: { top: 59, left: 0, right: 0, bottom: 34 },
}}>
```

### Capturing only a component

```jsx
import { captureRef } from 'react-native-view-shot';
await captureRef(ref, { format: 'png', quality: 1, result: 'tmpfile' });
```

`captureRef` **captures in logical pixels.** Pass `pixelRatio: 3` to see it at 3x. If you added this code to the app,
revert it when the comparison is done. If you take a baseline with `render snapshot`, `render run` checks that it was reverted.

---

## Other frameworks

The four things above (logical size · safe area · scale · content) apply to every framework.
Find out how to match each one in what you use, and **add a section here.** If a new way to capture appears,
put it in pro-launch `render.md` as a recipe, so capturing instructions do not split across two places.
