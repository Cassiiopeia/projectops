# Comparison: properties (conform) · pixels (diff) · components at 3x · report · pitfalls

> When to read: Phases 4–7, when reading `conform` · `diff` results after translating, when a corner comes out "square" (`the render is square`) or there are several blobs, and when writing the report.

> **Do not demand a 100% pixel match.** Figma and the app use different text rasterizers (the part that draws
> glyphs into actual pixels), so it never reaches 0. The goal is to let a person decide **whether a blob sits on text or on a shape**.
>
> **Do not use it as a CI gate (by default).** With a badly chosen threshold it goes red every time and nobody looks.
> Use it as an aid right after implementing, and discuss a gate once it is stable.

## Phase 4: compare by property ⚠️ (before pixels)

**A pixel percentage says only where it differs, not what differs or how.**

> Real incident: the top corners of a bottom sheet were square. The pixel tool was already running, and it even **reported**
> that spot as `476~519 / 0~785 / mean diff 77`. But there was no way to read from that line that it meant "the corners
> are square". 5.5% different overall with 22 blobs: **the real defect was buried in noise.** People do not read a 22-line coordinate table.

Properties are definite: "top-left r=20, but the render is square". Sample output:

```
31 rectangles · corners·fills·shadows checks (scale 3) — high 2 · medium 1
   [high  ] Card 40x68 @16,390 top-left r=16 → the render is square
   [high  ] Badge 24x24 @300,120 transparency is missing — design alpha=0.4 but the render is the solid rgb(...)
   [medium] Sheet 393x420 @0,432 shadow is not visible — design has 0,8 blur 12 but …
```

The `corner` field uses `top-left` · `top-right` · `bottom-right` · `bottom-left`; the corner finding's `verdict` value stays `각짐` (a contract value).

On a correct screen it ends with one line, `no issues`. **That is what the 22 percentage lines could not do.**

| Check | What it catches | Severity |
|---|---|---|
| `corners` | The design says rounded, but it is **square** (judged geometrically) | high |
| `fills` | Different color · **opacity missing** · **a gradient laid down as a solid color** | high |
| `shadows` | An outer shadow is **missing entirely** | medium |

All three "look similar" on screen. Neither the eye nor a pixel percentage catches them; they are caught only **when you know the value and probe that spot**.

You can narrow with `--check corners,fills`. **Photo (`imageRef`) fills are not checked**: the design's image reference and the rendered pixels
are not comparable in the first place, and checking them floods you with false positives. Adjust scale and tolerance with `--scale` (default auto) · `--tolerance` (default 12).

### CI gate

`conform … --fail-on high`: if there is even one item at that severity or above, **exit code 1** (`conformance_failed`).
The default is `none` (does not fail): with a badly chosen threshold it goes red every time and nobody looks.

### When it says "square", suspect this first ⚠️

**Usually the radius was not left out; a child covered the radius you set.**

If the parent paints only its background with rounded corners and **does not clip its children** (clipping is off), the background color a child lays down
fills the rounded spot. The parent's radius value is right there in the code, so you cannot see the problem by reading code;
you have to render it.

| Framework | The clipping switch |
|---|---|
| Flutter | `Container` paints only the background with `decoration.borderRadius`. `clipBehavior` defaults to `none`; turn it on with `Clip.antiAlias` |
| React (CSS) | `overflow: hidden` on the parent |
| React Native | `overflow: 'hidden'` on the parent, but combined with a shadow it clips the shadow (`framework-gaps.md`) |

### Look at other properties the same way

`conform` automates **what can be measured and judged from the render**. For the rest, compare the values `coverage`
listed against the code and by eye. The following often drift.

| Item | What often gets missed |
|---|---|
| Color | The hex is right but the **opacity** is missing (`conform` catches it) |
| Stroke | `strokeWeight` is right but `strokeAlign` (inside / center / outside) differs |
| Typography | `lineHeight` · `letterSpacing` left at defaults |
| Gradient | Angle and **stop positions** differ. A gradient laid down as a solid color is caught by `conform` |
| Effects | The table in `framework-gaps.md`: inner shadow, glow |
| States | Only one variant is built (Phase 1) |

> **A component's source is in the component definition, not the screen frame.** An `INSTANCE` in a screen sometimes
> only references it. Measured: **81 of 474 (17%)** had only a `componentId` and no style keys at all.
> For such nodes you cannot tell the radius, color or state by reading the screen alone.
> Follow the `componentId` and **fetch the component's node separately** to check the values.

## Phase 5: compare by pixels (secondary)

**Look only for what properties cannot catch**: the image itself differs, or an element is missing entirely.
**Do not read** percentages and blob counts **as defect counts.**

Export the design node as an image, render the app at **the same logical size and the same safe area**, and compare.
How to make the render match the design is in `rendering.md`. **If you do not match them, the whole body floats and everything comes out as off.**
This is for comparison, so get **original PNGs** (`--keep-format`). The pro-launch default (WebP, 1200 on the long side) blurs the pixels.

### Getting the design export (the reference image)

Download the screen's **frame node** as a PNG with `mcp__figma__download_figma_images`. Save it in `design/` under `run_dir` (not tracked).
Match `pngScale` to **the scale of the device you captured the app on** (`3` for a 3x device, `2` for 2x). If the scale differs, the sizes are off from the start and everything comes out as blobs.
When looking at one component only (Phase 6), fetch just that node at the same scale.

### With several blobs, first check "did it shift as a whole?" ⚠️

`diff` moves the render a little (`--probe-shift`, default 40px) and tells you **whether there is a position where it lines up at once**
(`shift_probe`). If there is, it is not many separate misalignments but **one container that shifted**.

```json
{"shift_probe": {"dy": -35, "dx": 0, "before": 31.88, "after": 0.0,
                 "looks_shifted": true}}
```

Then the place to fix is not the elements inside but **what contains them**: container height, spacing, safe area.

> In one real case the sheet's top edge sat 35px too low, and the steps, rewards and button inside **all looked doubled**.
> Ten blobs came out, but only one thing was wrong. Counting blobs alone reads as "ten places are off"
> and leads you to fix the wrong places.

**Look at where the blobs are, not the percentage.**

| Where the blob is | Usually |
|---|---|
| On text | Rasterizer difference: harmless |
| On shapes, spacing or backgrounds | **Actually wrong** |

> The background color defaults to `auto`, read from the design's corners. The app render keeps outer glows semi-transparent,
> while the design arrives with the background composited in, so unless both sit on the same background, **the entire glow
> is flagged as "different"** and the result loses its meaning. If the design's corners are transparent, pass `--bg RRGGBB`.

> The status bar and home indicator are areas the app does not draw, so they always come out different. Mask them with `--mask-top` · `--mask-bottom`.
> If there is a lot of noise, adjust `--threshold` (default 24) · `--min-area` (default 200).

## Phase 6: check components separately ⚠️

**Shadows, glows and 1px borders vanish on a full screen.** Looking only at the full screen at 1x lets it slip through
exactly as in the incident.

Capture only the component in question at **the same scale** as the design export (usually 3x) and compare again.
How to match the scale is in `rendering.md`: for Flutter, a widget test wrapped in `RepaintBoundary`;
for the web, a temporary Playwright script with `deviceScaleFactor: 3`, run with `render run`
(the pro-launch browser is fixed at 1x and cannot capture 3x directly).

## Phase 7: report

**Collect omissions and approximations at the top.** They come before pixel results, because those are the decisions that need review.
Write the report in the user's language (or the configured `language` preference). Example structure:

```
## Not classified / omitted · approximated
  931:4010/effects[1]  inner highlight   omitted — the framework does not support inset
  ...

## Property comparison
  [high] sheet 393x420 top-left r=20 → render is square

## Pixel comparison
  full screen  2.9% pixels differ  3 blobs
    y120~168 x24~369   on text — judged a rasterization difference
    y430~498 x16~377   on a shape — needs checking
  button at 3x   mean channel difference 3.0
```

Write values **so they can be recounted** (coordinates, size, mean difference). "Looks similar" is not evidence.
Record what you compared against (node id) in tests and comments.

## Common pitfalls

| Pitfall | What to do |
|---|---|
| **Pass on the full screen alone** | Shadows, glows and 1px borders are a few pixels at that size. Check components separately at 3x |
| **The implementer makes the golden** | Captured with effects missing, that still becomes the reference. The reference must be **the design export** |
| **Pick tokens from the PNG alone** | Weights and color codes cannot be read from an image. Read **the values in the dump** |
| **Reuse an existing asset because the shape matches** | The shape can match while the color differs. Reuse is also something to classify |
| **Render with content different from the design** | If list counts or text differ, the whole diff turns red and the misalignment you need to see gets buried |
| **Safe area not matched** | The body floats by the status bar height and everything comes out as off |
| **Report per pixel without blobs** | Buried in anti-aliasing noise, unreadable (the script groups them) |
| **Read blob count as defect count** | If one container shifts, every line inside is flagged. Check `shift_probe` first |
| **Start with screens** | If a shared component is off, you write the same cause once per screen |
| **"I put the asset in, so it must be right"** | The shape can match while the **fill value** differs. Sweep for colors not in the tokens |
| **Use the golden as the reference** | Goldens are **made by the implementer.** It locks in what is wrong and catches only departures from that. The reference is the design export |
| **Not recording what you compared against** | The next person does not know which node to compare with and starts over. Record the node id in tests and comments |
| **Look at effects mixed into the style list** | At 3% of thousands of lines they get buried. Look at `effects` **separately**, first |
| **Count `boxShadow` as one line** | One string holds four lines. The code needs as many as the indexes (`[0]` · `[1]` …) |
| **Swap blur and background blur** | The layer blurring itself and what is behind it blurring are completely different |
| **Translate values without downloading assets** | The dump has no images. The screen has no icons at all |
| **"Same name, so same icon"** | 71 `Vector` nodes were 48 different images. If `certain` is false, check by eye |
| **Fetch the whole file without `nodeId`** | 5,949 style items arrive and classification becomes impossible |
| **Classify from a shallow `depth` fetch** | There is no sign that it was cut, so you wrongly conclude "there are only a few elements". Use `depth` only to find the screen list |
| **Trust that the link's node-id is a screen** | If it is a SECTION, 1MB arrives. Look at the screen list with `depth 2` first |
| **Place a downloaded asset at layout size** | Effects are baked in and it arrives larger. The shape shrinks |
| **Add an effect baked into the asset again in code** | Applied twice, it spreads twice as far |
| **Decide pass/fail from the percentage alone** | You learn only where it differs, not what is wrong. Run `conform` first |
| **Set the radius again because it is square** | The value is already there. **A child is covering it**; turn on clipping |
| **Judge component values from screen nodes alone** | 17% of INSTANCEs have no style at all. Follow the `componentId` |
| **Match the color but drop the opacity** | Same hex, different screen |
