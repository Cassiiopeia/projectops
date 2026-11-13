# Translating design values to code

> When to read: Phase 3, when translating values to code following the classification table (unit conversion · token reuse · comments for approximations and omissions).

**The classification table is the worklist.** Handle the items `coverage` listed one by one, applying the rules
in this document. If you skip the list and work from the picture alone, the small and subtle things simply get dropped.

## Contents

- [Before you start: see what this project uses](#before-you-start-see-what-this-project-uses)
- [Core principles](#core-principles)
- [What, in which unit](#what-in-which-unit)
- [By framework](#by-framework)
- [Position: copy the design's coordinates ⚠️](#position-copy-the-designs-coordinates-)
- [Shapes and illustrations are assets, not code ⚠️](#shapes-and-illustrations-are-assets-not-code-)
- [Split tokens by use, not by value](#split-tokens-by-use-not-by-value)
- [Leave the reason for approximations and omissions in the code ⚠️](#leave-the-reason-for-approximations-and-omissions-in-the-code-)
- [After translating](#after-translating)

## Before you start: see what this project uses

Before translating values, check **the container that will receive them**. If you ignore what the project already uses
and bring in a new approach, styles split from screen to screen.

| What | Where to look |
|---|---|
| Styling approach | Config files · one or two existing screens |
| Design tokens | Where spacing · type · color · corner radius · breakpoints are defined |
| Screen size baseline | Is the design canvas width the same as the code's baseline width? |

## Core principles

- **Do not hard-code px.** It drifts by that much on a different device
- Calculate **as a ratio of the design canvas**
- **Use existing tokens.** A new value makes only that screen different
- **Follow the project's existing patterns**

## What, in which unit

| Value in the design | When translating |
|---|---|
| Width close to full width (90%+) | 100% + parent padding |
| Fixed size such as icons and buttons | Relative unit or fixed value |
| Medium size | Ratio or `clamp(min, preferred, max)` |
| Spacing that exists in the design system | **Token** (do not create a new value) |
| Spacing proportional to the screen | Screen-width unit or `clamp()` |
| Font size | Relative unit. `clamp()` if responsive |
| Corner radius | Relative unit or framework token |

## By framework

Set a baseline width and convert **by that ratio**. The names differ, but the job is the same.

| Framework | Conversion | Spacing |
|---|---|---|
| CSS utilities (Tailwind etc.) | Round to the token scale | Parent padding |
| CSS-in-JS | px → screen-width unit helper · `clamp()` | Theme spacing |
| React Native | `screen width ÷ design width × value`, bounded by min and max | `StyleSheet` |
| Flutter | `MediaQuery`-based extensions (`.w` · `.h` · `.sp`) | `EdgeInsets` |

> ⚠️ **Size extensions (`.w` etc.) usually do not touch font size.** To scale text too,
> use the text unit (`.sp`) separately. Mixing them makes it right on only one device.

## Position: copy the design's coordinates ⚠️

Figma positions are absolute. **Do not imitate them with flexible space** (`Spacer`, `flex`, `justify-content: space-between`)
or by stacking spacing tokens. Both look right on one screen height and drift everywhere else.

> Measured: splitting a screen with `Spacer` pushed a checklist to the very bottom. The design had it at y=569 (about 67% down).
> Stacking spacing tokens pushed another block 140px down.

| Situation | How |
|---|---|
| An element is fixed in the design | Absolute placement (`Stack` + `Positioned`, `position: absolute`), the design y minus the top bar |
| A list grows with data | Normal flow, with **the design's gap** between items |
| A bottom button (CTA) | At the design's y, not glued to the screen bottom, unless the design glues it |

**Fix title and paragraph widths to the design's text box width,** so lines break where the design breaks them.
If the longest line almost touches the box edge, leave a little slack and **count the lines in the render**.
A fixed width that is 1px short adds a whole extra line (measured: a title wrapped to a fourth line).

## Shapes and illustrations are assets, not code ⚠️

Draw in code only what is simple: a solid background, a rectangular card, a border, a plain linear gradient.
**Anything with a shape** (illustrations, blobs, stars, radial gradients that form a picture) is downloaded as an asset.

> Measured: an illustration rebuilt with a container and a radial gradient came out as a square.
> A blurred-circle background (aurora) imitated with three circles looked different from the design's two: the difference went 26.95% → 3.56% once the
> design's `Gradient` group was copied circle by circle (count, position, size, color, blur).

When a gradient is drawn in code, match **every stop, including the transparent end's color**. A transparent stop still carries a color,
and it blends: unifying the stops to one color made a pink circle's center turn lavender (3.10% → 12.01%).

**Do not substitute a stock icon** (Material, SF Symbols) for the design's icon, even when it looks alike.
Stroke count and weight differ (measured: 2 vs 3 strokes, ink area 607 vs 212 px). Download the design's vector.

## Split tokens by use, not by value

Two places with the same hex still get **two tokens when they change for different reasons**.
Ask: "if the designer changes one, must the other change too?" If not, they are different tokens.

> Measured: one shared "selected" token served goal chips and character cards. The goal chips showed the fox's peach color
> because the token could hold only one pair. Splitting by use fixed it without breaking the character screen.

## Leave the reason for approximations and omissions in the code ⚠️

Some design values cannot be taken as is by the framework (`framework-gaps.md`).
**Deciding to approximate or drop them is normal. Not recording it is the problem.**

```
// Design: inset 0px 0px 10px 2px #FFFFFF (inner white border)
// This framework has no inner shadow, so approximated with an overlapping border
```

Without the comment, the next person cannot tell **whether it could not be translated or was deliberately left out**.

## After translating

Matching the values is not the end. **Compare by pixels** (the comparison phases in SKILL.md).
Shadows, glows and 1px borders can silently drop out at render time even when the values are right.
