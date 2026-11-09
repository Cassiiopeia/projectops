# Kind: sprite

A character (or creature) cut out on a transparent background, placed over backgrounds: standing poses,
expressions, a mascot in an empty state.

## Brief must have
- Character id and its approved sheet (attach it with `--ref`).
- Pose, expression, framing (full body / knees up / waist up), facing direction.
- Outfit for this scene if it differs from the default.
- Final size (portrait sprites are often 1024x1536) and `--alpha`.

## Prompt pattern
```
Character sprite of <name> for <app>, cut out to place over different backgrounds.
Match ref/<sheet> exactly for face, hair, eyes and body; this is the same person.
Pose: <pose>, facing <direction>. Expression: <expression>. Framing: <waist up>, centered, whole head and hands
inside the frame with a small margin.
Outfit: <outfit>.
Style: <STYLE.md look>.
No background scenery, no floor, no cast shadow, no glow, no border, no text.
```

## Traps
- A floor shadow or ground line sneaks in. Name it in "no".
- Tools without transparency (Antigravity) get a flat key color background from the CLI; tell it the character
  must not wear that color (pass `--key-color "#FF00FF"` for a green-clad character).
- Face drift across a set: attach only the approved sheet, not old scene images.
- Fit mode for alpha images is `contain` (never crops the character); ask for "centered with margin".
