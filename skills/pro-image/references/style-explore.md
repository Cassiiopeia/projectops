# Style explore: let the user see and pick the look

> When to read: the repo has no `STYLE.md`, the user asks "what style fits?", or a new project starts its art.
> People only know which look fits their project when they see it next to others.

## Flow

1. **Read the project's mood.** App name, audience, screens, colors in the design tokens, any existing art and
   copy tone. Write one line: "a calm seaside visual novel for adults", "a playful SQL quiz for students".
2. **Pick 3-4 distinct looks** that could fit that mood, and one subject that shows them well (the main character,
   the app mascot, or the most-used background). Make them really different, e.g.:
   - anime watercolor with thin ink lines
   - flat vector with bold shapes and 3 colors
   - soft 3D clay
   - pixel art 32 px
   - hand-drawn pencil and marker
   - paper cut-out collage
3. **Generate each look** with the same subject, same size, same provider, in the background, one by one
   (`run --name style_<n> ...`). Only the style lines differ between the prompts.
4. **Show one board.** `board style_1.final.png style_2.final.png ... --out style_board.png`, open it with Read to
   check it, show it to the user, and ask with AskUserQuestion: one option per number with a 3-6 word name of the
   look, plus "mix: describe it". Do not show the four runs separately and do not describe the process.
5. **Lock the pick.** Write `STYLE.md` from the chosen prompt's style lines (concrete: line, shading, palette with
   hex, light), copy the chosen image to `refs/`, `record --status approved`, and `record --status rejected` for the
   others with the user's reason if they gave one.
6. **Default when the user skips:** pick the look that matches the existing app best (or the first one), say which
   in one line, and continue. They can run this again any time.

Run it again when the user wants to change direction ("make it cuter", "try other styles"): same subject, new looks,
and include the current look as option 1 so they can keep it.
