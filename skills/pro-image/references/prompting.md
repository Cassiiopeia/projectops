# Prompting: from a loose request to a prompt Codex follows

> When to read: before writing every prompt. The quality gap between "user asks Codex directly" and "agent asks
> Codex for the user" comes from this page: the agent adds what the user did not say but the app needs.

## 1. Write the brief first (requirements, numbered)

Turn the request plus the app context into a numbered list before writing any prompt. Each line is one checkable fact.

| Slot | Where it comes from | Example |
|---|---|---|
| Purpose and placement | The screen or file that will use it (read the code) | Dialogue scene background, `public/img/bg_*.webp`, shown full screen behind a dialogue box |
| Final size and aspect | The slot it fills: CSS size, sprite frame, store spec. Ask only if nothing tells you | 1536x1024 (3:2) |
| Background | Placement: sprites, items, stickers, icons on colored UI → transparent | Transparent PNG |
| Style anchor | `STYLE.md` + the reference images it names. Never invent a new style for an app that has art | Watercolor anime, thin ink lines, ref `refs/cover.png` |
| Subject | The user's words, kept literally (names, objects, mood words) | Empty seaside cafe at dusk |
| Composition | Placement constraints: empty zones for UI, focal point, camera angle, crop | Bottom third empty for the dialogue box, eye-level |
| Light and color | STYLE palette + the scene's time and mood | Warm sunset light from the left window, teal sea outside |
| Consistency anchors | `characters/<id>.md` fixed look + its reference sheet | Black waist-length hair, blue-grey eyes, sky-blue sailor dress |
| Must not | STYLE "Never" + this request's traps | No text on the menu board, no people |

Mark each line as **said** (user said it), **app** (you read it from the code or harness) or **guess** (your call).
Show the user only the image later, but keep the brief: you check the result against it.

## 2. Write the prompt (English, in this order)

Write the prompt in English: image models follow English instructions more reliably. Keep proper nouns and any
in-image text exactly as given (quote them). One idea per line; concrete nouns beat adjectives.

1. **Context line**: what this is and where it is used. "Background for a visual novel dialogue scene, shown full screen."
2. **Reference roles**: one line per attached image, saying what to take from it and what to ignore.
   "ref/cover.png: match line weight, coloring and eye style. Do not copy its pose or background."
3. **Subject**: what is in the image, from most to least important.
4. **Composition**: framing, camera, focal point, empty zones as fractions ("keep the bottom third clear").
5. **Style**: the STYLE.md look in 2-4 lines. Say "same style as the references" and also describe it.
6. **Light and color**: direction, time of day, palette, saturation.
7. **Consistency**: the character's fixed look, copied from `characters/<id>.md`, word for word every time.
8. **Must not**: a short list. Name the trap you expect ("no text on signs", "no second character").

The CLI appends the output rules (file path, exact size, transparency, no code drawing, unavailable answer).
Do not repeat them; do not contradict them.

Read `kind <name>` for the kind's own rules and its last approved prompts, and reuse the parts that worked.

## 3. Check the result against the brief

Open the image with Read. Go through the brief line by line and mark pass or fail. Then:

| Result | Do |
|---|---|
| All lines pass | Show it to the user |
| A size or alpha line fails (`problems`) | Fix with code only if it is a resize or crop; a missing transparency means run again |
| A content line fails (wrong hair, text appeared, no empty zone) | Run again once with that line moved up and said more strongly. Do not show a failed image as if it were fine |
| It fails twice on the same line | Show the best one and say which line it misses. Ask whether to accept or change the request |

## 4. After the user decides

- Approved: place it (convert to the app's format, e.g. WebP, at the slot's path), then
  `record --status approved --placed-at <path>`.
- Rejected: `record --status rejected --note "<the user's reason>"`.
- If the reason applies to future images ("always softer shadows", "her hair is shorter"), add it to `STYLE.md` or
  `characters/<id>.md` now. The next prompt then includes it without anyone remembering.

## Hard requests (several constraints at once)

- Put the constraint most likely to be dropped first in its section and repeat it once under "Must not".
- Characters across many images: make the character sheet first (`kind character-sheet`), get it approved, then
  attach the sheet to every later prompt. Do not attach five old scene images; one clear sheet works better.
- Many images in one set: run them one at a time in the background, check each, and keep the approved first one
  as an extra reference for the rest of the set.
- Exact layouts (a UI mock, a chart, text-heavy art) are weak spots of image models. Draw those with code or
  `pro-ui-design` instead, and use generated art only for the illustration inside.
