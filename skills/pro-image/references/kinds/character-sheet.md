# Kind: character-sheet

One image that fixes a character's look before any scene uses them. Every later sprite attaches it as the reference.

## Brief must have
- Fixed look in words: age, build, hair (length, color, bangs), eyes (color, shape), skin, distinguishing marks.
- Default outfit, colors named.
- The style anchor (STYLE.md + the app's best existing image of this character, if any).

## Prompt pattern
```
Character design sheet for <name>, <role> in <app>.
Layout: left, full body in three turnarounds (front, three-quarter, side), same scale, standing on an invisible line.
Right, six head close-ups in a 3x2 grid: neutral, smile, sad, surprised, angry, embarrassed.
Fixed look (identical in every view): <copied from characters/<id>.md>.
Outfit: <default outfit>.
Style: <STYLE.md look>. Match ref/<file> for line weight, coloring and eye style.
Plain very light cream background. No labels, no text, no arrows, no color swatches.
```

## Traps
- Views drift (hair longer in the side view, eye color changes). Repeat the fixed look line once at the end.
- Text labels appear on sheets. Forbid them explicitly.
- Size 1536x1024 (3:2), opaque. Approve the sheet before making sprites; save the approved one to `refs/` and point
  `characters/<id>.md` at it.
