# Kind: illustration

Spot art inside a page: empty states, onboarding steps, error pages, feature explainers, banners.

## Brief must have
- The message it supports (the screen's title and body text, read from the code).
- Where it sits (above a title on a white card, beside text) and the surface color under it.
- Final size and whether it sits on a colored surface (then transparent) or fills a box (then opaque).

## Prompt pattern
```
Illustration for the <screen> of <app>: it supports the message "<screen title>".
Show <one simple scene or metaphor>, <one character or object at most two>.
Style: <STYLE.md look>; consistent with ref/<existing illustration>.
Palette limited to <colors from the app's tokens>, leave plenty of empty space.
Composition: subject centered, <shape: wide banner / square>, nothing touching the edges.
<Transparent background / soft flat <color> background>.
No text, no UI elements, no device frames, no logos.
```

## Traps
- Generic stock-art look. Give the app's actual palette (read the design tokens) and its existing art as a reference.
- UI mockups inside illustrations come out broken. Keep illustrations free of screens and buttons.
- A set of onboarding illustrations: same character, same camera distance, same palette; make step 1, approve,
  attach it to the rest.
