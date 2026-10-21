# Translating design values to code

> When to read: Phase 3, when translating values to code following the classification table (unit conversion · token reuse · comments for approximations and omissions).

**The classification table is the worklist.** Handle the items `coverage` listed one by one, applying the rules
in this document. If you skip the list and work from the picture alone, the small and subtle things simply get dropped.

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
