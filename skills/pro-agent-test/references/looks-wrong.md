# Look for what works but looks wrong — viewing axes 4·5·6·7

> When to read: Phase 4.4 — after walking, when you lay the captured screens side by side and scan for "works but looks wrong".

**Axes 1·2·3 choose "what to walk"; this document is about "what to look at while walking".**
They are different in kind. If you only check that features run, everything below ends as a pass.

| Ends as a pass | What is really true |
|---|---|
| The button responds and the next screen appears | Only that button sits 20px lower than on other screens |
| Dangerous actions have a warning color | The same color is also used for **disabled**, so users think it cannot be tapped |
| Tapping the arrow goes back | The **device back button** is blocked |
| The screen appears and the values are right | There is only one thing to tap, so the screen has no reason to exist |
| Built to the design, with the design's own assets | **The renderer dropped the effects**, so it looks completely different |

**Nobody finds these unless told to look.** What was caught by luck will not be caught next time.

## When to do it

Once, right after walking, **while you still remember the screens.** Lay the captured screenshots (`$SHOT_DIR`)
side by side. Do it **before** the wide-view step (cross-cutting, symmetry, ripple effects) — that step asks "are other
places like this too", while this one asks "does this place make sense".

## How to write evidence ⚠️

**Only what can be counted again is evidence.** "Awkward" or "a bit off" is not evidence.

| Counts as evidence | Does not |
|---|---|
| Counts — "title font size has 3 variants across 4 screens" | "Fonts feel inconsistent" |
| Coordinates and dimensions — "button heights 48 / 44 / 52" | "Buttons are uneven" |
| Screen and logs — "tapped, 0 screen change, 0 log lines" | "It seems unresponsive" |
| Setting values — "moves for 280ms with reduce motion at 0" | "Animation is excessive" |

When written as numbers, **anyone who judges gets the same answer.** On these axes in particular, "good enough"
differs from person to person, so without pinning evidence to values, it ends in argument.

---

## Axis 4 — Do the same things look the same

Move between screens and check **whether things with the same role look the same.** You never see this looking at one screen.

| What | How to count | Defect candidate |
|---|---|---|
| Text | **How many variants** of size and weight are used for the same role (title, body, button text) | 2 or more variants |
| Buttons | Are height, corner radius and horizontal padding the same on every screen | If values differ |
| Color | Is **a different color used for the same meaning**? Conversely, **the same color for different meanings**? | Both are defects |
| Spacing | Is the title-to-body gap the same on every screen | If values differ |

> **A mismatch between meaning and color is the most dangerous.** If a disabled color is used to signal danger,
> users read it as "a button I cannot tap". The feature works perfectly, so "does the feature run" will
> never catch it.

**Pull candidates from the code first.** Places that override styles ad hoc despite shared styles are candidates.

```
fontSize · font-size · fontWeight · font-weight · copyWith( · textStyle
#RRGGBB · Color(0x · rgb( · rgba(
padding: · margin: · EdgeInsets. · gap:
```

The more overrides, the more likely things have diverged. **Start with the screens that have the most hits.**

---

## Axis 5 — Does tapping make sense

| What | How to check | What to write as evidence |
|---|---|---|
| **Tappable but no response** | Tap it and check both screen and logs | "0 change · 0 log lines" |
| **Disabled without a reason** | Is there text next to the dimmed button saying why it cannot be tapped | Whether the text exists |
| **No way back** | Walk the arrow and **the device back button separately** | The result of each |
| **One step too many** | Is there only one thing to tap on that screen | The number of tappable things |
| **Tap area too small** | Is a finger target smaller than 48dp | The measured dimension |

> **Always walk the arrow and the device back button separately.** It is common for one to be fixed while the other
> stays blocked. If the router opened the screen by **replacing**, there is no place to go back to at all.

> **For a screen with only one thing to tap, ask why the screen exists.** It can usually be merged into the screen before or after.
> Write this as a proposal, not a defect.

```
onPressed: null · onTap: null · disabled · pointer-events: none
GestureDetector · InkWell · onClick · addEventListener('click'
WillPopScope · PopScope · onWillPop · history.back · router.back
```

---

## Axis 6 — Is the motion right (only if there is any)

If the product has no motion, skip this axis.

| What | How to check |
|---|---|
| Missing where it should be | Is motion missing from screen transitions or failure alerts? **Is it present elsewhere and missing only here** |
| Leftover after it ends | After motion ends, did position and opacity **return to the original** |
| Ignores reduce motion | Does it keep moving with animations turned off in accessibility settings |

> **Leftovers after motion are invisible to the eye.** Damped motion only approaches 0 mathematically,
> so it stops slightly off even after it ends. It passes by eye and is caught only by numbers —
> record it and compare the position in the last frame with the first ("Checking motion with numbers" in
> `target-app.md`).

```
Animation · AnimationController · Tween · Curves. · transition: · @keyframes · animate(
```

---

## Axis 7 — Is this screen from a design (only if there is a design)

The earlier axes ask **"does it make sense within this product"**. Only this axis has the correct answer outside.

**`pro-figma` does the counting itself.** It classifies every `fills` · `strokes` · `effects` entry in the dump without missing one,
and compares the design export with the app render pixel by pixel. Here, the job is to **notice while walking that "this screen
came from a design but there is no comparison record"** — that fact itself is a defect.
The accessibility tree has no shadows, colors or weights, so this skill cannot see whether all design values made it.
In one real case, three of four effect lines shipped missing, and the designer found it after release.

Below are **signals to suspect at once when they catch your eye** while walking. They show even before running a comparison.

### The asset is the design's own file but looks different ⚠️

**"I put in the file from the design as is, so it must be the same" is the trap.** The renderer can fail to draw part of the file
and **silently drop it**.

| What the design used | The renderer | What it looks like |
|---|---|---|
| SVG `<filter>` (blur, shadow, inner glow) | flutter_svg **ignores it entirely** | The translucent shape for the halo is not blurred and lies flat, leaving a **muddy band** |
| Layer blur | Apps have no such concept | The halo disappears entirely |

> In a real case, a star screen **differed by 21%** for this reason. Opening the asset showed it was
> **byte-identical** to what came from the design. This is **a different kind** from the case where the framework does not support something
> and the implementer approximated it (`framework-gaps.md` in `pro-figma`) — here the implementer
> never even had a chance to judge. They put it in and expected it to work.

**The console usually tells you first.** In that incident, `unhandled element <filter/>` was there
from the start. **Read console warnings while walking screens.**

```
unhandled element · unsupported · not supported · ignoring · failed to decode
```

### The size the design reports is not the actual drawing size

For an element with effects, **the box grows as far as the effect spreads.** If you use that value as is, the drawing
stretches and looks blunt — a large star came out as `299×299`, but the actual drawing was `264×255`.

Compare the **actual size** of the received asset with the size measured from the design drawing. If they differ, use the **measured value**.

### The design is drawn for one device only ⚠️

Designs are usually drawn for **one iPhone model** (e.g. 393×852). Matching only on that device is not enough —
**it must look the same at other aspect ratios.**

| What to check | What goes wrong |
|---|---|
| Narrower / wider devices | Text wraps at a different point than in the design |
| Shorter / taller devices | Lower elements get cut off or empty space appears |
| Square elements | Using different scales for width and height turns circles into ellipses |
| **Safe area height** | Hard-coding one value shifts the whole screen by that much |

> **Hard-coded safe area numbers are especially prone to drift.** The status bar was assumed to be 52 and subtracted from the design
> coordinates, but the real device was 59, so the whole screen floated up by 7. Looking at one device only, it is at the level of
> "is it a bit high?" and passes.

**Look on at least two devices.** The reference device and the device with the most different aspect ratio
(`references/devices.md`).

```
MediaQuery.of · padding.top · viewPadding · SafeArea · statusBarHeight
```

---

## The person who built it is the one judging ⚠️

Right now, **the implementer judges their own work.** They read it in the direction they want it to pass.
This is especially true for axes 4·5·7 — "good enough" differs from person to person.

Use both of the following. They are not exclusive.

**B. Write evidence only as values — you can do this right now**

That is the "How to write evidence" section above. Written as numbers, someone else can recount and verify later,
and once it is verifiable, it is hard to go easy on it.

**A. Judge from a position that does not know the implementation context — needs structure**

Give only the screenshots in `$SHOT_DIR` and this document, **without the code or what this work changed**, and
ask it to "find what looks wrong". Hand it to a new session.

```
The screenshots below are several screens of one product.
Look only through axes 4·5·6·7 of references/looks-wrong.md and find what looks wrong.
Write evidence only as counts, dimensions and screen changes.
```

Since it does not know what was built, "this is how it is supposed to be" never comes up. **If you cannot do A,
at least always keep B.**

## Report what comes out of here separately

The requested feature passed, but it **looks wrong**. If you mix them, it reads as "this work
failed". Separate defects from proposals too — "one step too many" is a proposal, not a defect.
