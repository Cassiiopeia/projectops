# Kind: icon

App icons, feature icons, badge and achievement icons, small illustrated symbols.

## Brief must have
- Use: app icon (opaque, the store rounds the corners), UI icon on colored surfaces (transparent), set member.
- Final size: app icon master 1024x1024 opaque; UI icons 512x512 transparent (scaled down later).
- For a set: the shared grid (same stroke, same corner radius, same light direction) and the list of members.

## Prompt pattern
```
<App icon / UI icon> for <app>: <one concrete object or symbol>, <what it should make the user feel>.
One central shape, recognizable at 48 px. Simple silhouette, at most <3> main colors: <palette>.
Style: <flat / soft 3D / line icon with 2 px stroke>, consistent with ref/<existing icon>.
Centered with <10%> padding on every side.
App icon: full-bleed background color <color>, square, no rounded corners (the platform rounds them).
UI icon: transparent background.
No text, no letters, no tiny details, no drop shadow outside the shape.
```

## Traps
- Letters and numbers come out wrong. Never ask for text in an icon; add text in code if needed.
- Tiny details vanish when scaled. Ask for "readable at 48 px".
- Sets drift. Make one, approve it, then attach it as the reference for every other member.
- An exact geometric or brand-logo shape is better drawn as SVG (claude-vector) than generated.
