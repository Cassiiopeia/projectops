# Input · state list · capture

> When to read: Steps 1–3, when you receive a Figma link or images, when you list states, and when you decide what to capture by render, real device or ASCII.

## 1. Understand the input

| What the user gave | What to do |
|---|---|
| Nothing | Build it from the code, captures and conversation only |
| **Figma link** | Read it with the rules in `../../references/figma-mcp.md` (fetch in two passes · shared components first). If reading fails, continue without Figma and note it in the summary |
| Images (screenshots · reference apps) | Put them next to the board's "current implementation" slot and write one line on what was referenced |

Decide implementation status: **implemented / partial / not yet.** If not yet, the center of the brief is **mockups rendered with real components** instead of captures. Text drawings (ASCII) are not the center.

**What a Figma file gives you**: the **gap table** of drawn vs missing states (`../../references/design-states.md` §4;
the missing states are the request list), tokens and components (to express alternatives in the design's language), and design exports (`design | current | alternative` on the board).
To count the dump, run pro-figma's `coverage` for each state node. **Do not fix places where design frames disagree; raise them as questions.**

## 2. State list: the screens designers do not draw

Pick from the **5 axes** in `../../references/design-states.md` (data · input · environment · person · display).
**No script scans the branches. You read the code and list them.**

- For each state, record **implemented / temporary screen / not implemented** (board data `status`: `done` · `temp` · `none`).
- For each state, record **whether the current flow produces it** (`reachable`: `yes` · `old_data` · `unknown`). **Check in the code whether the
  input path that creates the state (the UI that selects it, the stored value) still exists.** "Temporary" or "replace later" in specs and comments
  describe the time they were written. Drop states that appear only with old data, or mark them separately as "old data only".
  > A state whose selection UI was already gone was requested based on a spec sentence alone, and the designer got a screen that never appears.
- **Text the server sends is also a state**: notice popups, terms, server error messages. Code search does not find them,
  so check the production API or admin screens. (Reading only the code gave "shown in 6 places"; with the notice popup it was 7.)
- Include **only the axes that really apply to that screen.** Do not force them (a version label has no "0 items" state).
- The display axis (200% text, small phones) applies to almost every screen. **Breakage shows up here often.**
  If it is a separate problem from the request, mark it "separate" and keep it apart.

## 3. Capture: with pro-launch

**Rendering is a way to stage states; evidence for "this is how the app is now" is the real device.** ⚠️

Claims written from widget renders alone differed from the real device in 7 places. The render harness does not draw the modal scrim, fake
failure objects look different from real failures, fake providers skip the offline-first path and automatic retries,
render width differs from device width, and fixture values are not production values. Some defects also appear only on real devices.

| What you want to show | With what |
|---|---|
| How the app looks, behaves and what numbers it shows now (facts) | **Real device · production API · production settings**; never substitute a render |
| States that are hard to create (empty list, failure, long text) | Render · response swapping; label the capture **"render · fake data"** |
| Options that do not exist yet | Render real components. Use ASCII only when rendering fails, and publish it **only if the user has seen and allowed it** |

- Read **numbers** such as grant amounts and limits **from the production API or settings, not fixtures**.
- Record the source of each capture (`source`: `render` · `device` · `server` · `design`). The board adds a label.
- Put "this is how the app is now" statements in `facts[]` **with evidence**. Statements backed only by a render
  must be checked on a real device before publishing, or dropped (`preflight` in `board` flags them).

**Fidelity ladder (fixed in one place)**: real component render > device / browser capture > text drawing (ASCII). Designers judge the brief as if it were the app,
so a text drawing is "the last resort for explaining a state that cannot be drawn". On the publish approval screen, state **what the weakest output is** (for example "2 ASCII drawings") so the user can decide.
An issue once went up with ASCII mixed in and was sent back with "draw it like the real app".

Order: **code render → real device / browser → ASCII.** For staged states that a real device can reproduce, also capture them once on the device.

| With what | Command | When |
|---|---|---|
| Code render | `render snapshot` → `render scaffold` (Flutter; other stacks: write it by hand) → edit it → `render run` | Edge states and alternative mockups. Recipe: `../../pro-launch/references/render.md` |
| Device | `app shot --clean-status` (navigate with `app tap --text` · `app swipe`) | The real screen as is |
| Browser | `web viewport` · `web route` · `web shot` | Web: stage empty lists and failures without a server |
| ASCII | `design_brief_cli.py ascii --spec '{...}'` | States that cannot be rendered, options with no code yet. Label it "render failed" |

```bash
source "{env_file value}"          # $SHOT_DIR · $RUN_DIR · $DEV
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app tap  --device "$DEV" --text "{text that leads to the screen}" --shot 02_list
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app shot --device "$DEV" --out 03_empty_list --clean-status
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py web route --match "**/api/items*" --status 200 --body "[]"
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/design_brief_cli.py ascii --spec '{"title":"Empty list","rows":["Nothing yet","---",{"text":"Add","align":"center"}],"width":24}'
```

- **Navigate by element** (`app tap --text|--id|--desc`). Do not guess coordinates; if you do not know the text, use `app tree`.
- **ascii spec**: `{"title": "title (optional)", "rows": ["text", {"text": "text", "align": "left|center|right"}, "---"],
  "width": 24, "caption": "caption below (optional)"}`. `width` is an integer of 1 or more (default 30); `"---"` in `rows` is a divider.
  Keys outside these four (`boxes` and so on) are ignored and reported in `warnings`. Wide characters (such as Korean) count as two columns so the right border lines up. Save to a file with `--out`.
- **Render alternative mockups with real components too.** Redrawing them in HTML changes fonts and spacing and confuses the designer.
  Moving elements on the real screen with the real text tokens is the most accurate.
- **Make zoomed crops of small elements** (4x, nearest-neighbor). 10px text is invisible in a full-screen capture.
- **Do not call AI generation APIs** to make captures. Fill them with fake data.
- If `render run` reports `residue`, **do not delete it** unless you created it. If you made it, clean it up; if it is a change you do not know, only report it.
