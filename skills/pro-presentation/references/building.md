# Building and editing the deck

The deck is HTML. You edit the files; the practice page redraws within two seconds. That is why the HTML is the source,
and PPT and PDF are only exports.

## Where a deck starts

| The user has | Do |
|---|---|
| Nothing, or only an idea | Run the init questions, agree an outline (one line per slide: kind + message), then build each slide from the template kinds |
| An outline, plan, script, or notes | Turn it into the outline, then build |
| A reference they like (another deck, a site, a screenshot) | Read it for structure, rhythm, and look; do not copy its content or brand. Put the look into `theme.css`. If several looks are possible, show 2 or 3 with `pro-ui-design` and let the user pick |
| An existing PPT or PDF | `import`. Slides arrive as pictures with their text in `notes.md` `## Original text`, so rehearsal can start at once. Rebuild a slide as HTML only when it has to change |
| A deck folder from before | `start --deck` and continue; read `memory.md` first |

## Outline first

Before building, write the outline into `deck.json` (`slides` with `id` and `kind`) and agree it with the user in one message:
the slide count, the kind of each, and the one message each slide carries. Check the time limit with a rough 20 to 40 seconds per content slide.

## Slide HTML rules

- One `<section class="slide">` per `slide.html`, laid out at 1920 x 1080. The page and the export both render it at that size.
- Use only `theme.css` variables for colour, font and spacing. If a value is missing, add a variable to `theme.css` first.
- Mark every element that should be a real PPT object with `data-pp`:

| `data-pp` | Becomes in PPT | Use for |
|---|---|---|
| `title` | text box | the slide heading |
| `text` | text box (paragraphs and bullet lists keep their lines) | body text, captions, numbers |
| `image` | picture | screenshots, photos (put the file next to `slide.html`) |
| `shape` | rectangle, rounded rectangle or ellipse (from `border-radius`), with fill and border | cards, bands, lines |
| `table` | table | comparisons |

- Put pieces directly inside the section and position them absolutely (`theme.css` classes). An element without `data-pp` becomes a **picture** in the PPT; its child pieces stay real text. `check` lists every such picture part; aim for none.
- Text must be real text, never baked into an image, so the PPT stays editable and the words can be checked.
- Images: keep them next to the slide and refer to them by file name.

## Rebuilding an imported slide as HTML

1. Look at `slide.jpg` (Read it) and `## Original text` in `notes.md`.
2. Pick the closest template kind, write `slide.html` with the same message and order, using `theme.css`. Match the original look only as far as the theme allows; consistency across the deck wins.
3. Keep `slide.jpg` until the user accepts the new version, then delete it (the page shows `slide.html` first).

## Editing loop

- Small changes: edit and say in one line what changed. The page updates by itself.
- When the user points at the screen ("the left box", "the second line"), map it to the piece and change only that.
- After structural changes (slides added, removed, reordered), run `check` and report the new estimate against the limit.
- The user can reorder slides in the page's flow view; that writes `deck.json`. Reread `deck.json` before you edit it.

## Exports are versions

`export` never overwrites. Each run writes `exports/v<n>/` (PDF, PPT, verify report). A PPT that is open in PowerPoint stays untouched,
and the user can compare v2 with v3. Tell the user the version number you made.
