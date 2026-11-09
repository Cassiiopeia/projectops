# Kind: item

Single objects on transparency: game items and props, stickers, emoji-like reactions, product cut-outs.

## Brief must have
- The object, its material and condition, the angle (front, three-quarter, top-down).
- Whether it belongs to a set (same angle, light and outline for every member).
- Final size (often 512x512) and `--alpha`.

## Prompt pattern
```
Game item icon for <app>: <object>, <material>, <condition>.
View: <three-quarter from above>, light from the top left, same as ref/<existing item>.
Style: <STYLE.md look>, outline <thickness and color>.
Centered with 12% padding, whole object visible.
No background, no floor, no cast shadow, no glow, no text.
```

## Traps
- Sticker-style white outlines appear. Say whether you want one; the background removal keeps an outline only
  when it is not the same color as the background.
- Sets drift in angle and light. Approve one and attach it to the rest.
