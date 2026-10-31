---
name: pro-figma
description: "Turn a Figma design into code and verify it matches: enumerate every element and effect as a worklist, download assets, then pixel-compare export vs render. Use for 'implement this Figma design', 'does it match the design'."
---

# Design → code → comparison

## When to use

- 'implement this Figma design', 'build it like the design', 'convert Figma to code', 'download the Figma assets', 'download the icons'
  (Korean: 'figma 디자인 구현해줘', '시안대로 만들어줘', 'figma 코드로 바꿔줘', 'figma 에셋 받아줘', '아이콘 다운로드')
- 'check it matches the design', 'see if it follows the design', 'compare against Figma'
  (Korean: '시안이랑 같은지 확인해줘', '디자인대로 됐는지 봐줘', 'figma 대조해줘')
- 'make the store screenshots', 'check the store images', 'are the screenshots the right size for every language'
- 'is a shadow missing?', 'the corners look square', 'the rounding did not apply'
  (Korean: '그림자 빠진 거 없나', '모서리가 각진 것 같은데', '라운드 안 먹었어')
- Driving the app to find behavior bugs is pro-agent-test. Works with React, Flutter and React Native alike.

Talk to the user in their language (or the configured `language` preference).

**You cannot catch it by eye.** A button shipped with the inner three of its four effect lines missing. It passed a full-screen golden,
and the designer told us **after** release. Value assertions also guard only what someone thought to assert. So do both **counting** and **rendering**.
Translating and counting are one skill (omissions happen while translating; comparison is only an after-the-fact check).

Use it when: building a screen from a design (start by counting) · right after building, before release · pinning down what "this looks different" means ·
reusing existing assets or components. **Do not use it for**: driving the app to find behavior bugs (`pro-agent-test`; the accessibility tree has no
shadows, colors or font weights), or screens with no design (nothing to compare against; to request the missing states, use `pro-design-brief`).

The **absolute rules** in `../references/common-rules.md` apply. Arguments: $ARGUMENTS

## What you want to do → command → detailed doc

| Goal | Command | Details |
|---|---|---|
| Output locations (evidence folder · asset candidates) | `figma_cli.py get-output-path --title` | `references/counting.md` |
| Read Figma (screen list → one screen) | `mcp__figma__get_figma_data` | `../references/figma-mcp.md` |
| Save the MCP result file as a dump (do not retype 30KB) | `figma_cli.py ingest --source --file-key --node --dump-dir` | Phase 0 |
| Did the design change since the dump was saved? | `figma_cli.py check-fresh --dump` | Phase 0 · Phase 4 |
| Save a Figma token (once) | `figma_cli.py token --prompt` · `token --from-env NAME` | Phase 0 |
| List elements · effects · styles **without gaps** | `figma_cli.py coverage --dump --node` | `references/counting.md` |
| Did you count every state (disabled · empty value · zero items)? | `coverage` per state node | `../references/design-states.md` |
| Group the assets to download → download | `figma_cli.py assets` → `mcp__figma__download_figma_images` | `references/assets.md` |
| Translate values to code · decide approximate or omit | — | `references/conversion.md` · `references/framework-gaps.md` |
| Capture the render under the same conditions as the design | `launch_cli.py render run` · `app shot --keep-format` · `web shot --keep-format` | `references/rendering.md` |
| Compare by property (corners · fills · shadows) | `figma_cli.py conform` | `references/comparing.md` |
| Compare by pixels (secondary) | `figma_cli.py diff` | `references/comparing.md` |
| Report · pitfall table | — | `references/comparing.md` |
| Store screenshots · feature graphic · icon: specs and per-locale check | `figma_cli.py store-specs` · `store-check --dir` | `references/store-assets.md` |

## Find the scripts once

**The Bash tool resets its state on every call.** Find them once, then **write the actual paths as values into later blocks.**

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
for SKILL in pro-figma pro-launch; do
  ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  [ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
    H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
    [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
  done
  # Home-copied installs from npx projectops: GitHub Copilot and Cursor (#200)
  [ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.copilot ~/.cursor; do [ -d "$B/skills/$SKILL/scripts" ] && { ROOT="$B"; break; }; done
  [ -d "$ROOT/skills/$SKILL/scripts" ] || { echo "$SKILL scripts not found. Check the plugin installation."; exit 1; }
  echo "$SKILL=$ROOT/skills/$SKILL/scripts"
done
echo "PYTHON=$PYTHON PROJECT_ROOT=$PROJECT_ROOT"
```

The `pro-figma=` value is `{SCRIPTS}` and the `pro-launch=` value is `{LAUNCH}`. **pro-launch does the capturing** (`../pro-launch/SKILL.md`).

## Common rules

- **Each command returns one JSON object.** Decide the next move from `ok` · `code` · `summary` · `next`. **You make the judgment.**
  The scripts only count, list and render.
- **One screen at a time.** Passing the whole file without `--node` returns thousands of items you cannot classify. **Shared components before screens.**
- **Look at effects first, and separately.** `effect_counts` → `effects`, one line at a time. The code must have as many as there are indexes `boxShadow[0]` · `[1]` ….
  Do not swap blur (the layer itself blurs) and background blur (what is behind it blurs).
- **Every item gets one of three classes**: implemented · approximated (reason required) · omitted (reason required). Leave the reason for approximations and omissions **in a code comment too**.
- **Do not download assets into the evidence folder (`run_dir`).** Use one of `asset_dir_candidates` (files that must be committed). If there are no candidates, ask.
- **Captures for comparison are original PNGs** (`--keep-format`). The pro-launch default (WebP, 1200 on the long side) blurs the pixels.
- **Do not demand a 100% pixel match, and do not add a CI gate by default.** Do not read percentages or blob counts as defect counts.
- The reference is always **the design export**. A golden made by the implementer is not a reference.
  Get the design export by downloading the screen node with `download_figma_images`, with `pngScale` matched to the device scale (3 for a 3x device). See `references/comparing.md`, "Getting the design export".

## Order: decision rules per phase

**Phase 0: get the locations and read Figma.**

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/figma_cli.py get-output-path --title "{screen name}"
```

Dumps, exports, renders and diff images go under `run_dir` (not tracked). Assets the app uses go in `asset_dir_candidates` (tracked).
Get Figma at `depth: 2` for the screen list → fetch the chosen screen **without `depth`** and keep it **as a file** (cutting with `depth` gives no sign that it was cut).
There is no guarantee that a link's node-id (`238-1846` → `238:1846`) is a screen. If you do not know the node id, ask.

**Save the dump with `ingest`, not by retyping it.** When the harness saved the `get_figma_data` result to a file, pass that file:

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/figma_cli.py ingest --source {saved result file} --file-key {fileKey} --node {node id} --dump-dir {dump path from get-output-path}
```

It writes the dump and `<dump>.meta.json` (file key, node id, `lastModified`, `version`). Use the returned `path` for `coverage` and `next` as is.
It knows JSON, text-block wrappers and YAML. Anything else comes back as `unknown_wrapper`; do not retype the dump, tell the user.

**Check that the design has not changed** before you start building and again before comparing (Phase 4):

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/figma_cli.py check-fresh --dump {dump file}
```

`verdict: design_changed` → fetch and `ingest` again, then recount. `unknown` → say so in the report; do not call the design current.
If it returns `figma_token_missing` (or `figma_token_rejected`), **ask the user** which of the returned `options` to take:
register a token (`token --prompt` in their own terminal, or put it in an environment variable and use `--from-env NAME`), skip the check, or have them confirm the design is unchanged.
Never paste, read or print a token yourself, and never ask for one in the chat. The token is stored once in the same place `pro-launch cred` uses (`provider: figma`).

**Phase 1: classify everything.**

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/figma_cli.py coverage --dump {dump file} --node {node id}
```

Classify elements (`elements`: is it on screen) · effects (`effects`: is not a single line missing) · styles (`items`) **without leaving any out**.
`styles_resolved` tells you how many references were resolved. Run it for every state node, and pass states the design **does not have** on as things to request.

**Phase 2: download the assets.** `get_figma_data` does not give images (`IMAGE-SVG` nodes have no shape data).

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/figma_cli.py assets --dump {dump file} --node {node id}
```

Pass the returned `nodes` **as is** to `download_figma_images`'s `nodes`, with `localPath` set to the absolute path of the chosen asset folder.
After downloading, check `rename_me` · `certain: false` · 0-byte files · the count. Items marked `baked_effect` **come in larger**:
remove the effect from the code, keep the downloaded size, and center it on the shape. After placing them, sweep every `fill`/`stroke` value to find colors not in the tokens.

**Phase 3: translate.** The classification table is the worklist. Use existing tokens and components first (`references/conversion.md`).
For spots the framework cannot take as is (inner shadow, glow etc.), see `references/framework-gaps.md`.

**Phase 4: compare by property (before pixels).** Run `check-fresh` first; a changed design makes every finding below meaningless.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/figma_cli.py conform --dump {dump} --render {app render.png} --node {screen node id}
#   --check corners,fills,shadows   narrow down     --fail-on high   exit code 1 at that level or above (default none)
```

Findings come out as definite statements, such as `[high] … top-left r=16 → the render is square`.
**When a corner comes out square, do not set the radius again; check whether a child covers it**
(Flutter `clipBehavior: Clip.antiAlias` · CSS/RN `overflow: hidden`). If an `INSTANCE` has only a `componentId` and no style,
fetch the component node separately.

**Phase 5: compare by pixels (secondary).** Render at the same logical size, the same safe area and with the same content as the design (`references/rendering.md`).

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py render snapshot --root {repo}
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py render run --root {repo} --cmd "{render command}" --collect "{render output glob}" --cleanup {temp folder}
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app shot --device "$DEV" --keep-format --out render   # or straight from the device (borrow it with device acquire and release it when done)
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py web shot --keep-format --out render
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/figma_cli.py diff --render {app render.png} --design {design export.png} --out {diff.png} \
  --mask-top {status bar height} --mask-bottom {home indicator height}
```

If there are several blobs, **start with `shift_probe`**. If `looks_shifted: true`, one container has shifted. Blobs where text sits are usually harmless;
blobs on shapes, spacing or backgrounds are real mistakes. If the design's corners are transparent, pass `--bg RRGGBB`.

**Phase 6: check components separately at 3x.** Shadows, glows and 1px borders vanish on a full screen at 1x. The pro-launch browser
is fixed at 1x, so for 3x run temporary render code with `render run` (`references/rendering.md`).

**Phase 7: report.** **Omissions and approximations go at the top**, then property comparison, and pixel comparison last. Write values so they can be recounted (coordinates · size · mean difference),
and record the node id you compared against. Format and pitfall table: `references/comparing.md`.

## Failure code → next action

| code | Next action |
|---|---|
| `dump_not_found` · `dump_unreadable` | Save the dump to a file again (JSON or YAML). Do not paste the MCP response in directly |
| `source_not_found` · `source_unreadable` | Check the path of the file the harness saved the `get_figma_data` result to |
| `unknown_wrapper` | `ingest` does not recognise the file shape and will not guess. Tell the user; do not retype the dump |
| `meta_not_found` | The dump was not saved with `ingest`. Run `ingest` on the result file first |
| `figma_token_missing` · `figma_token_rejected` | Ask the user which `options` to take (see Phase 0). Do not read or print the token |
| `figma_file_not_found` | The file key is wrong, or the token's account cannot open the file |
| `no_tty` · `env_empty` | `token --prompt` needs the user's own terminal; or the named environment variable is empty |
| `node_not_found` | `--node` is not in the dump. Pick the screen node again from the `depth: 2` list, or fetch that node |
| `no_style_found` | Zero style items. Check that the node id is right and that the dump includes styles (fetched without `depth`). Passing with zero items means no comparison was done |
| `render_not_found` · `image_not_found` · `image_unreadable` | Check the render and design PNG paths. If they were shrunk to WebP, capture again with `--keep-format` |
| `imaging_missing` | The image library (Pillow) is missing. Suggest installing it to the user |
| `unknown_check` | `--check` accepts only `corners` · `fills` · `shadows` |
| `bad_bg` · `bad_mask` | `--bg` must be `auto` or `RRGGBB` · `--mask-top`+`--mask-bottom` must be 0 or more and less than the design height |
| `conformance_failed` | There are items at or above `--fail-on`. Fix the listed items, or record a reason for approximating or omitting them |
| `dir_not_found` | `store-check --dir` does not exist. Export the images into `{store}/{locale}/{slot}/` first (`references/store-assets.md`) |
| `mkdir_failed` | Could not create the output location. Check permissions and `--root` |
| `bad_args` | Check the subcommand and required arguments (`--dump` · `--render` · `--design` · `--title`) |

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-figma`.
Keys for this skill: the common `language`, `tone`, `rules` only.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.
