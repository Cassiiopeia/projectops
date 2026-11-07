# Fidelity: making a mockup look like the real product

> When to read: before writing a mockup for a project that already has code or a design system.

## Pick a level for each question

| Level | How | Use for | Cost |
|---|---|---|---|
| 1. HTML | HTML/CSS/JS with the repo's tokens and fonts. It can move and respond | Direction, motion, flows, structures that do not exist yet | Fast |
| 2. Real code render | Temporary code draws the real widgets to PNG (`pro-launch render`) | "Make it look exactly like the app", small details, empty and error states | Slower; still image |
| 3. Real capture | Device or browser screen, or a recording (`pro-launch app shot` · `app record` · `web shot`) | "What it looks like now", checking motion after building | Needs a running app |

Start from the configured default, then move up when the question needs it. A common page shows the current screen (level 3) above options (level 1 or 2). Say which level each image is: level 1 is a reproduction, not a pixel match.

## Level 1: follow the design system

1. Read the notes from `start`'s `project_profile`. If they are missing or `changed_files` is not empty, run `tokens`.
2. **Read the candidates.** Copy real values; do not guess from memory.
3. Write `screens_dir/tokens.css`. The frame links it automatically, after its own defaults:

   ```css
   :root { --ui-bg: #f6f2ef; --ui-ink: #242634; --ui-accent: #4f6bff; --ui-radius: 16px; --ui-font: "Project Sans", sans-serif;
           --app-sheet: #f6f2ef; }
   html[data-theme="dark"] { --ui-bg: #17181d; --ui-ink: #f1f1f4; }
   @font-face { font-family: "Project Sans"; src: url(/files/fonts/ProjectSans-Regular.ttf); font-weight: 400; }
   ```

   Keep the project's own names as extra variables when they say more than the `--ui-*` names do. If the project defines light and dark, define both.
4. **Copy font files** into `screens_dir/fonts/`. A font named but not loaded shows a different font on any machine without it.
5. Read shared components (button, sheet, card, row, navigation) and imitate their radius, padding, weight, shadow and states.
6. Run `check`. Everything it reports is either fixed or explained.

Mockups use `var(--...)`, not literal colors. No external URLs: mockups must work offline.

**No design files?** Use the neutral defaults and say so. Do not invent a brand.

## Frame classes

| Class | Use |
|---|---|
| `.ui-options` > `.ui-option` | Compare options. `h3` names the option, `[data-choice="a"]` records a pick |
| `.ui-device` > `.ui-device-screen` | Device frame. Follows the toolbar, or pin with `data-device="tablet"` |
| `.subtitle` · `h2` | Page question and hint. Always ask the question on the page |

Show 2 to 4 options. Name files for what they show (`sheet-motion.html`) and never reuse a name: the viewer keeps every earlier file, and a new one appears by itself. Put images and fonts in subfolders freely and reference them as `/files/<path>`. Files starting with `_` are hidden from the list.

## Level 2: real code render

Follow `pro-launch` `references/render.md` exactly: `render snapshot` → `render scaffold` (Flutter) → `render run`. It cleans up and checks for leftovers. Copy collected PNGs into `screens_dir` and show them in `.ui-option` cards. Delete only what you created.

## Level 3: real capture

Capture with `pro-launch` into its run folder, then copy what you show into `screens_dir`. Recordings work too: `<video src="/files/flow.webm" controls loop>`.
