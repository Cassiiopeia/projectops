# How to read the Figma MCP — shared rules

**Every skill that receives a Figma link reads it by these rules** (#630). Current users:

| Skill | What it gets |
|---|---|
| `pro-figma` | Counts every value as a worklist, then compares after implementation |
| `pro-design-brief` | Separates **states drawn in the design from states left out** and builds the list to request from the designer |

These rules used to live only inside `pro-figma`, so other skills had to copy them. Copies drift when only one side
is fixed. The rules live here, in one place. How to count states: `design-states.md`.

The numbers in this document **come from counting real responses**. A tool was once built only from invented
examples and could not be used at all on a real response, so since then only measured values are written down.

---

## 0. Reading order — summary

1. **Pull the arguments from the link** — `fileKey` and `nodeId` (hyphen → colon)
2. **Fetch in two passes** — ① the screen list with `depth: 2` → ② one chosen screen without `depth`
3. **Look at shared components before screens** — if one is off, every screen that uses it is off
4. **Keep the response in a file and count it with a script** — styles arrive only as references, and shadows
   arrive bundled in one string. Reading by hand always misses something (call examples in §4 below)
5. **Count every state** — one component is drawn in several states (`design-states.md`)

### Look at shared components before screens ⚠️

First look at things **several screens share**, such as buttons, checks, icons, and the back button. If one is off,
**every screen that uses it is off together.** Starting from screens means writing up the same cause once per screen.

> In one real case, a single wrong fill value on a back icon put **five screens off at once.**
> Reported per screen it would have been five defects, but the fix was one file.

The component source is not a screen but the **definition** (`COMPONENT` and `COMPONENT_SET` nodes, usually in a
components section). Looking only at instances inside screens hides the state variants.

If you do not know the node id, ask the user — a guess compares against the wrong design, everything comes out
different, and **the differences you actually need to see get buried.**

---

## 1. Two tools

### `mcp__figma__get_figma_data` — reads values

| Argument | Required | Notes |
|---|:-:|---|
| `fileKey` | ✅ | `figma.com/design/<fileKey>/...` in the link |
| `nodeId` | | `?node-id=238-1846` in the link → **`238:1846`** |
| `depth` | | **Do not use it.** Only when the user explicitly asks |

```
https://www.figma.com/design/VSmGuv1iuOpLZmp6QeBHWr/이룸?node-id=238-1846
                             └──── fileKey ────┘          └ nodeId → 238:1846
```

#### Fetch in two passes ⚠️

**There is no guarantee that the link's `node-id` is a screen.** Measured: the link pointed to a `SECTION`
(named '이게 진짜 디자인', "this is the real design"), and even with `nodeId` the response was **1,083,214
characters**, so the tool dropped it to a file. It was no different from fetching the whole file.

| Order | Call | Result (measured) |
|---|---|---|
| ① **Screen list** | Fetch with `depth: 2` | **12KB** — ids and names of 54 screens at a glance |
| ② **One screen** | Fetch again with the FRAME id chosen in ① | **15KB** — an amount you can classify |

```
238:1846  SECTION  이게 진짜 디자인
  238:3022  SECTION  온보딩_보호자
    238:1808  FRAME  로그인_iOS      ← this is a screen
    204:991   FRAME  이름
    ...
```

A screen is usually a **`FRAME` whose layout resolves to the device's logical size** (393×852 and so on).
`IMAGE-SVG`, `RECTANGLE`, `ELLIPSE`, and label `TEXT` nodes mixed in at the same level are not screens.

> **Do not use `depth` for classification.** It cuts the tree **without marking that it was cut**, so if you fetch
> shallow and conclude "this screen has only a few elements", you are simply wrong.
> Use it **only to find the screen list**, and never pass it in ②.

#### Large responses are dropped to a file

When a response exceeds the context limit, the tool saves it to a file and tells you the path.
**Pass that path straight to `--dump`** — no need to copy it anywhere.
Save it to a file yourself only when it is small and arrives inline.
- Nodes inside instances are chained with semicolons, like `I204:993;510:1641;1503:15324`.
  Of 2,617 measured nodes, **1,440** have this form. Use them as is; trimming them gives a different node.

### `mcp__figma__download_figma_images` — fetches images

| Argument | Required | Notes |
|---|:-:|---|
| `fileKey` | ✅ | |
| `localPath` | ✅ | **An absolute path inside the project.** Created if missing |
| `nodes[]` | ✅ | `{nodeId, fileName}` + `imageRef` and so on, depending on the case |
| `pngScale` | | Default 2. Applies to PNG only |

> **Paths outside the project are rejected.** Measured: passing `/private/tmp/...` returned
> `Invalid path specified. Directory traversal is not allowed.`
> Even for a temporary look, download **inside the project**.

`nodes[]` entries:

| Key | When |
|---|---|
| `nodeId` | Always |
| `fileName` | Always — **only `^[a-zA-Z0-9_.-]+\.(png\|svg)$` passes** |
| `imageRef` | **Required** when the node has an `imageRef` fill. Leave it empty for vectors |
| `needsCropping` · `cropTransform` · `filenameSuffix` | For cropped images |
| `requiresImageDimensions` | When size is needed as a CSS variable |

---

## 2. Gaps — and how to turn that information into precision

### ① The response is **YAML**, not JSON

`json.loads` simply fails on it. When this skill's tool first met a real response, it actually died with
`dump_unreadable`. → `figma_cli.py` accepts both JSON and YAML.

### ② Nodes hold styles **only by reference**

```yaml
- id: '1:200'
  fills: fill_5PQ06X          # a name tag, not a value
  effects: effect_ZI8QJT
globalVars:
  styles:
    fill_5PQ06X: ['#F7F2EF']
    effect_ZI8QJT: {boxShadow: '...'}
```

If you do not join them through `globalVars.styles`, you have classified **without knowing a single value.**
942 style definitions measured. → `styles_resolved` in `coverage` tells you how many were resolved.

### ③ One string holds **several** shadow layers

```yaml
effect_ZI8QJT:
  boxShadow: '0px 4px 20px 0px rgba(204,188,246,1),
              inset 0px 8px 24px -16px rgba(255,255,255,0.24),
              inset 0px -24px 32px 0px rgba(255,255,255,0.24),
              inset 0px 0px 10px 2px rgba(255,255,255,1)'
```

**This is the very value from a real incident.** Of the four layers, the three inner ones were missing when it shipped.
Counted as one item, losing three layers does not change the count, so it never shows.

Measured: 12 definitions → **16** actual shadow layers. Effect items 153 → **171**.
→ The tool splits by counting parenthesis depth (commas inside `rgba(...)` are left alone).

### ④ Even sizes are **behind a reference**

`dimensions` is not on the node but inside a `layout_XXXX` style. If not resolved, the size becomes `None`,
and without a size there is nothing to tell icons apart by.

### ⑤ **There is no shape information for icons** ← most important

This is all an icon node in the dump contains.

```yaml
- id: I204:993;510:1641;1503:15321
  name: Wifi-path
  type: IMAGE-SVG
  layout: layout_CIJ1TC
  fills: fill_5PQ06X
```

**No path, no points, no shape.** So the dump alone cannot tell whether two icons are the same picture.
Figma's default name for vectors is `Vector`, so —

> Measured: **71** nodes named `Vector`, of which **48** were actually different pictures.

Grouping by name uses one icon wrongly in 48 places. It fails silently and you only notice by looking at the screen.

**How to make it precise**: group only what has evidence.

| Evidence | Verdict |
|---|---|
| Same `componentId` | **Certainly** the same picture (`certain: true`) |
| The whole node content is the same | **Likely** the same — check by eye after downloading |
| Only the name is the same | **Do not group** |

### ⑥ Assets are **separate files to download**, not values

Of 2,617 measured nodes, **609** were `IMAGE-SVG`. However well you port the values, without downloading these
the screen has no icons. `get_figma_data` does not give you images.

### ⑦ The `fileName` pattern is narrow, so **layer names used as is get rejected**

`^[a-zA-Z0-9_.-]+\.(png|svg)$` — Korean (non-ASCII) characters, spaces, and `/` are all disallowed.

> Measured: of 609 assets, **281 (46%)** had names that do not pass, such as `뒤로가기` ("back"),
> `Icon / Mobile Signal`, and `채크_라운드` ("check_round").

### ⑧ Names **overwrite each other**

> Measured: of 609, **592** were concentrated in 45 names. `Wifi-path` 144, `Vector` 71.

Making files from names leaves only the last one.

### ⑨ Leave out `imageRef` and you get **the wrong picture**

For photo-type nodes (nodes with an `imageRef` fill), without this argument you get something other than the node's render.

### ⑩ The downloaded image is **larger than the size the dump states**

For nodes with effects, **the blur arrives baked into the image as an SVG filter**.

> Measured: a glow shape whose `layout` is **36×34** (`boxShadow: 0px 0px 30px`) came back as
> **96×94**. It grew by 30px on every side.

```svg
<svg width="96" height="94" viewBox="0 0 96 94">
  <g filter="url(#filter0_d_726_4744)">   <!-- the glow is in here -->
    <path d="M48 64C38.05 64 30 56.39 ..." fill="#9AFFE9"/>
  </g>
```

If you miss this, one of two things happens.

| Mistake | Result |
|---|---|
| Squeeze it into the layout size (36×34) | The glow shrinks too, and **the shape shrivels** |
| Add the effect again in code | **Applied twice**, so it blurs twice as much |

→ `assets` **flags it in advance** with `baked_effect`. For that entry, remove the effect from the code, keep the
downloaded image's size as is, and place it by the **center of the shape**.

### ⑪ `imageRef` is also **behind a reference**

The node only has `fills: fill_JJ816G`; the real value is inside globalVars.
Without resolving the reference, **you miss photo assets entirely.** That value also tells you the arguments you need.

```yaml
fill_JJ816G:
  - type: IMAGE
    imageRef: 2e210b97f13d12e21d5e8dab278dde3a5e05b251
    imageDownloadArguments:
      needsCropping: false
      requiresImageDimensions: false
```

**Do not guess; use these values as is.**

### ⑫ Style keys may be **names people gave them**

You do not only get automatic names like `fill_5PQ06X`. Measured: names with slashes and spaces such as
`Label Color/Light/Primary`, `Callout / Bold`, and `System Background/Dark Base/Primary` are mixed in.
Detecting references by prefix (`fill_`, `effect_`) **passes over these unresolved.** Put the keys in a table and
detect by **whether the value is in the table**.

### ⑬ Things that are not screen elements are mixed in

| What gets mixed in | What it is |
|---|---|
| Entries in `metadata.components` | The component **catalog**. Not nodes drawn on screen |
| `type: VARIANT` (`Dark Mode=False` and so on) | Component **property declarations** |
| `visible: false` nodes | Hidden layers. Their children are not visible either |

Counting them inflates the numbers. Measured: 41 elements → really 28.

### ⑭ **Every state** of a component is included

Measured: 479 variants like `Property 1=disable`. The screen shows only one state, and implementers usually
build only the default one.

### ⑮ Text is **only the one set written in the design**

Measured: 575 text items with a median length of 4 characters and a maximum of 35. Real data is longer.
Building to the design's lengths breaks with long text.

---

## 3. Always check after downloading

| Check | Why |
|---|---|
| Is the file **count** what you requested | The response has succeeded while some files never arrived |
| Are there no **0-byte** files | Empty files appear silently |
| Does the SVG contain a `<path>` | Sometimes only a shell arrives |
| Do the fill values match the tokens | The shape can match while the color differs |
| Does the size differ from the dump | If so, **an effect is baked in** (⑩). Remove that effect from the code |

---

## 4. Calling the counting tools from other skills

The counting tools are in `pro-figma`'s scripts. **Call the script, not the skill**
(use the script lookup block from `common-rules.md` §"Standard call pattern" with `SKILL=pro-figma`).

```bash
# List every element, effect, and style in the dump (the response file from ②) — resolves references and splits shadow layers
PYTHONIOENCODING=utf-8 {PYTHON} {FIGMA_SCRIPTS}/figma_cli.py coverage --dump {dump file} --node {node id}

# Group the assets to download and build the nodes[] to pass straight to download_figma_images
PYTHONIOENCODING=utf-8 {PYTHON} {FIGMA_SCRIPTS}/figma_cli.py assets --dump {dump file} --node {node id}
```

| Caller | What it uses it for |
|---|---|
| Design request (`pro-design-brief`) | Runs `coverage` **for each state node** to count drawn states and builds the gap table against the code's state list. Uses the tokens (color, font, radius) in alternative mockups |
| Comparison (`pro-figma`) | Classifies every item as implemented, approximated, or omitted, leaving none out |

> **Do not drop `--node` when passing a dump.** Passing the whole file yields thousands — measured: one board had
> 3,851 elements and 5,931 style entries.
