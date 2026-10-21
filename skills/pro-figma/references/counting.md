# Counting: output locations · reading the dump · classifying without gaps

> When to read: Phases 0 · 1, right after getting the output locations and before classifying the `coverage` result. For a Figma file you have not used before, read `../../references/figma-mcp.md` first.

## Why count

**You cannot catch it by eye.** A button once shipped with the inner three of its four effect lines missing.
It got past even though a full-screen golden existed: a 10px inner shadow inside 361×68
is only a few pixels at that size, so it looks about the same with or without it. The designer
told us in chat **after** release.

Value assertions (`expect(shadow.blur, 10)`) block only half of it. They guard **only what someone thought
to assert.** Nobody wrote an assertion for the missing lines in the first place, so nobody counts them.

**Translating and counting are one skill.** If they are split, the translating side builds from the picture without knowing
what it has to translate. That really was the state for a long time, and that is how three of the four effect lines
shipped missing. **Omissions happen while translating; comparison is only an after-the-fact check.**

## Phase 0: output locations

**Do not decide where to put things yourself.** Without a fixed location they pile up somewhere different every time; in another skill,
8MB of screenshots once piled up in the wrong folder while being tracked (#611).

The locations returned are **split into two kinds, and mixing them always makes one side wrong.**

| What | Where | Tracked |
|---|---|:-:|
| Dumps · design exports · app renders · diff images | `dump` · `design` · `render` · `diff` under `run_dir` | ❌ the folder carries its own `.gitignore` |
| **Real assets** (icons and images the app uses) | One of `asset_dir_candidates` (`assets/images` etc.) | ✅ **the app uses these files, so they must be committed** |

> **Do not download assets into the evidence folder.** It is excluded from tracking, so they are not committed, and when someone else
> checks out the repo the app has no icons at all. If there are no candidates, ask the user.

## Phase 0: read Figma (summary)

**How to read it is in `../../references/figma-mcp.md`.** Another skill (`pro-design-brief`) reads with the same rules,
so it is not copied here.

| Order | What | Why |
|---|---|---|
| ① | Compare **shared components before screens** | If one is off, every screen that uses it is off. One icon really did make five screens wrong |
| ② | Extract `fileKey` · `nodeId` from the link (`238-1846` → `238:1846`) | |
| ③ | **Fetch in two passes**: the screen list at `depth: 2` → the chosen screen without `depth` | There is no guarantee the link's node-id is a screen (measured: a SECTION, 1.08 million characters) |
| ④ | **Save the response as a file** and pass it to `coverage` (it accepts JSON and YAML) | Styles arrive only as references, and several shadows arrive packed into one string |

> **Never pass `depth` when fetching the chosen screen.** It cuts the tree with no sign that it was cut.

Pair each design node id with the screen that corresponds to it (or will be built). If you do not know the node id, ask the user.

> **One screen at a time.** Passing the whole file returns thousands of items. Measured: one board had
> 3,851 elements and 5,931 style items. Picking one screen with `--node` brings that down to dozens,
> which a person can actually classify.

> **Nodes hold styles only as references.** The real values are separately in `globalVars.styles`, and
> the script resolves them. Without resolving, `fills: "fill_B16QZY"` becomes the value and
> cannot be classified. Worse, **a multi-line effect collapses into one reference line**, so a missing line
> does not show. The output's `styles_resolved` tells you how many were resolved.

## Phase 1: classify the dump without gaps ⚠️

**Look at three layers.** `coverage` returns all three.

| Layer | Question | If you miss it |
|---|---|---|
| **Elements** (`elements`) | Is this **on the screen**? | *"It is in the design but not on screen"*. Counting styles alone does not show this |
| **Effects** (`effects`) | Is **not a single line** of shadow or blur missing? | The incident above: three of four lines were missing |
| **Style items** (`items`) | Did **all** the other values arrive? | Colors, spacing and weights quietly drift |

### Look at effects first, and separately ⚠️

**Buried among dozens of layout lines, effects get looked at by nobody.** Measured: one screen had
`layout 3,294 · fills 1,849 · effects 171`, so effects are 3%. Yet **what gets missed is
almost always here**, because they are small and subtle and nobody notices when they are gone.

So `coverage` **pulls effects out separately and names each kind.** The kind names below are the literal values the CLI emits.

| Kind (CLI value) | What | If missing |
|---|---|---|
| `shadow` | Offset outer shadow | The floating feel disappears |
| `inner shadow` | `inset ...` | **Missed most often**; frameworks often do not support it |
| `glow` | Zero offset, spread only (`0px 0px 30px`) | The "glowing" feel disappears entirely |
| `blur` | `filter: blur()`: the layer itself and its children blur | |
| `background blur` | `backdropFilter: blur()`: what is **behind** blurs | The glass feel disappears |

> **Mixing up blur and background blur gives a completely different result.** The names are similar, so they get swapped often.

Check the count per kind in `effect_counts` first, then compare `effects` **line by line**.

> **One string holds several shadow lines.** Measured: 12 definitions → 16 actual lines.
> The script splits them, so they come out as `boxShadow[0]` · `[1]` …. **If there are indexes, the code
> must have that many too.**

### Did you count every state? ⚠️

**A design draws one component in several states** (disabled · empty value · in progress · zero items). Implementers usually
build from the default state alone. If you pass only one node to `coverage`, the other states are never counted.
**Run it for every state node.** Also note whether the design is drawn with only one kind of content (short text).

How to count, commonly missed states, and the 5-axis state list for code are in **`../../references/design-states.md`**.
If you find a state the design **does not have**, it is not something to compare; it is something to request from the designer (`pro-design-brief`).

### Classify into one of three

Classify the items `coverage` gave you **without leaving any out**.

| Class | Meaning | Reason |
|---|---|---|
| **Implemented** | The design value went in as is | Not needed |
| **Approximated** | The value is slightly different | **Required**: why could it not go in as is? |
| **Omitted** | Not put in | **Required**: why was it left out? |

**Telling "could not translate" apart from "chose not to translate" is the whole point of this step.**
Without a written reason, you cannot tell them apart later, and if you cannot tell them apart, you cannot review them.

> In the real incident there was a moment of deciding *"this framework does not support inner shadows, so let's approximate"*,
> but **that sentence was in neither the code comments nor the report.** When an omission is not recorded,
> nobody can trace it back.

Arrays come out **one line per element** (`effects[0]` `effects[1]` …). If one line of a four-line effect
is missing, it shows up here as unclassified. As a single combined line, it would not show.

Spots where the framework cannot take a design value as is are in `framework-gaps.md`. How to translate is in `conversion.md`.
