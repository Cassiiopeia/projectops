# What in the design does not translate as is

> When to read: during classification, when you need to decide "approximate" or "omit": spots where the framework cannot take a design value as is (React · Flutter · React Native).

This lists **the spots that "silently drop out while translating"**. When a framework cannot take some expression in the design
as is, the implementer decides to approximate or omit it. **That decision itself is normal.
The problem is that it is not recorded.**

This document tells you in advance "where that decision tends to happen".

## Why this becomes an incident

The values that cannot be translated are usually **small, subtle effects**: inner shadows, glows, 1px borders and the like.
On a full screen they look about the same with or without them. So:

1. The implementer decides "this cannot go in, let's approximate"
2. Leaves no word of it in the code or the report
3. Checks with a full-screen golden and reports "it matches"
4. **The designer finds it after release**

Why step 3 does not catch it is in the "Keep comparison renders separate from regression goldens" section of `rendering.md`.

---

## Flutter

| Expression in the design | Reality | What to do |
|---|---|---|
| **Inner shadow (inset)** | `BoxDecoration` **does not support it** | Approximate with overlapping widgets, `ShaderMask` or a custom painter, or omit it and **always record it** |
| **Gradient border** | `Border` **cannot take a gradient** | Work around it with two nested boxes |

> The inner shadow was **the direct cause** of the incident. The inner three of four effect lines were missing,
> and the last one was what made that button look "glowing".

---

## React (web · CSS)

CSS is the closest to Figma in expression. **That is exactly why things get dropped after assuming "this will work".**

| Expression in the design | Reality | What to do |
|---|---|---|
| **Inner shadow (inset)** | Works **as is** with `box-shadow: inset` | Do not drop it thinking it is not possible |
| **Multiple shadow lines** | Works **as is**, joined with commas | Pasting the Figma value as is is the most accurate |
| **Gradient border** | `border` **cannot take a gradient** | `border-image`, or two background layers + `background-clip` |
| **Background blur** | `backdrop-filter`; Safari needs the `-webkit-` prefix | Not available in old Android WebViews |
| **Layer blur** | `filter: blur()`: **children blur too** | Same behavior as Figma's layer blur |

> Mixing up background blur and layer blur gives a completely different result. `coverage` emits them
> **under different names**, so translate them as they are.

---

## React Native

**This is where the most gets dropped.** It uses names that look like CSS, but they behave differently.

| Expression in the design | Reality | What to do |
|---|---|---|
| **Inner shadow (inset)** | None | Approximate with overlapping views, or omit and **record it** |
| **Multiple shadow lines** | Older versions take **only one** | Use `boxShadow` on RN 0.76+, or keep only the most visible line and **record the rest** |
| **Shadow color and offset (Android)** | `shadow*` is **iOS only**. Android has only `elevation`, which sets neither color nor direction | RN 0.76+ `boxShadow`, otherwise something like `react-native-shadow-2` |
| **Gradient** | None | `react-native-linear-gradient` |
| **Background blur** | None | `BlurView` from `@react-native-community/blur` |
| **Gradient border** | None | Work around it with two layers |

> Putting `overflow: 'hidden'` and a shadow on the same view **clips the shadow away.**
> Split it: shadow on the outer view, `overflow` on the inner view.

---

## Other frameworks

Find out **what in the design does not translate as is** in the framework you use, and add a section here.

Finding it is simple: every item in the `coverage` list that you classified **as approximated or omitted**
is a candidate. If you keep approximating at the same spot for the same reason, that belongs in this table.

The more of this table is filled in, the less the next person silently drops things at the same spot.
